from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import get_current_user
from backend.core.idempotency import idempotency_manager
from backend.core.audit_logger import log_security_event
from backend.services.paper_trading import paper_trading_service
from backend.services.market_data import market_data_service

router = APIRouter()


class PlaceOrderRequest(BaseModel):
    symbol: str
    direction: str       # BUY or SELL
    quantity: int
    order_type: str = "MARKET"
    product_type: str = "INTRADAY"
    limit_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    stop_loss: float | None = None
    idempotency_key: str | None = None


@router.post("")
async def place_paper_trade(
    request: PlaceOrderRequest,
    idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Place a simulated paper trade with replay and double-order protection."""
    # Resolve idempotency key from header or body
    effective_key = idempotency_key_header or request.idempotency_key
    if effective_key:
        idempotency_status, cached_rec = await idempotency_manager.get_or_create(effective_key)
        if idempotency_status == "IN_PROGRESS":
            log_security_event(
                event_type="IDEMPOTENCY_RACE_DETECTED",
                severity="WARNING",
                user_id=str(current_user.id),
                details={"key": effective_key, "symbol": request.symbol},
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An identical order request is currently being processed. Please wait.",
            )
        elif idempotency_status == "COMPLETED" and cached_rec:
            return JSONResponse(
                status_code=cached_rec.response_status_code,
                content=cached_rec.response_body,
                headers={"X-Idempotent-Replay": "true"},
            )

    try:
        trade = await paper_trading_service.place_order(
            db=db,
            user_id=str(current_user.id),
            symbol=request.symbol.upper(),
            direction=request.direction.upper(),
            quantity=request.quantity,
            order_type=request.order_type.upper(),
            product_type=request.product_type.upper(),
            limit_price=request.limit_price,
            stop_price=request.stop_price,
            target_price=request.target_price,
            stop_loss=request.stop_loss,
        )
        response_data = {
            "trade_id": str(trade.id),
            "symbol": trade.symbol,
            "direction": trade.direction,
            "order_type": trade.order_type,
            "product_type": trade.product_type,
            "quantity": trade.quantity,
            "entry_price": float(trade.entry_price) if trade.entry_price else None,
            "limit_price": float(trade.limit_price) if trade.limit_price else None,
            "stop_price": float(trade.stop_price) if trade.stop_price else None,
            "target_price": float(trade.target_price) if trade.target_price else None,
            "stop_loss": float(trade.stop_loss) if trade.stop_loss else None,
            "commission": float(trade.commission),
            "status": trade.status,
            "opened_at": trade.opened_at.isoformat(),
        }

        if effective_key:
            await idempotency_manager.mark_completed(effective_key, 200, response_data)

        return response_data
    except ValueError as e:
        if effective_key:
            await idempotency_manager.mark_failed(effective_key)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if effective_key:
            await idempotency_manager.mark_failed(effective_key)
        raise


@router.get("")
async def list_paper_trades(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all paper trades with current unrealized PnL for open trades."""
    trades = await paper_trading_service.get_all_trades(db, str(current_user.id))

    open_symbols = list({t.symbol for t in trades if t.status == "OPEN"})
    quotes_map = await market_data_service.fetch_quotes_bulk(open_symbols) if open_symbols else {}

    now_utc = datetime.now(timezone.utc)
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = now_utc.astimezone(ist_tz)
    result = []
    for t in trades:
        opened_at_utc = t.opened_at if t.opened_at.tzinfo else t.opened_at.replace(tzinfo=timezone.utc)
        delta_sec = max(0.0, (now_utc - opened_at_utc).total_seconds())
        days_held = int(delta_sec // 86400)
        buy_date_formatted = opened_at_utc.strftime("%d %b %Y, %I:%M %p")
        opened_at_ist = opened_at_utc.astimezone(ist_tz)
        is_bought_today = (opened_at_ist.date() == now_ist.date()) or (days_held == 0)

        entry = {
            "trade_id": str(t.id),
            "symbol": t.symbol,
            "direction": t.direction,
            "order_type": t.order_type,
            "product_type": t.product_type,
            "quantity": t.quantity,
            "entry_price": float(t.entry_price) if t.entry_price is not None else None,
            "limit_price": float(t.limit_price) if t.limit_price is not None else None,
            "stop_price": float(t.stop_price) if t.stop_price is not None else None,
            "target_price": float(t.target_price) if t.target_price is not None else None,
            "stop_loss": float(t.stop_loss) if t.stop_loss is not None else None,
            "commission": float(t.commission) if t.commission is not None else 0.0,
            "stt_tax": float(t.stt_tax) if t.stt_tax is not None else 0.0,
            "status": t.status,
            "realized_pnl": float(t.realized_pnl) if t.realized_pnl is not None else None,
            "opened_at": opened_at_utc.isoformat(),
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            "days_held": days_held,
            "buy_date_formatted": buy_date_formatted,
            "is_bought_today": is_bought_today,
        }
        if t.status == "OPEN":
            quote = quotes_map.get(t.symbol)
            if not quote or quote.get("price", 0) <= 0:
                clean = t.symbol.replace(".BO", "").replace(".NS", "")
                quote = quotes_map.get(f"{clean}.NS") or quotes_map.get(f"{clean}.BO") or quotes_map.get(clean)
            if quote and quote.get("price", 0) > 0:
                current_price = float(quote["price"])
                multiplier = 1 if t.direction == "BUY" else -1
                entry_p = float(t.entry_price) if t.entry_price is not None else current_price
                comm = float(t.commission) if t.commission is not None else 0.0
                unrealized = multiplier * (current_price - entry_p) * t.quantity - comm
                
                # If bought today: Day's P&L is calculated from purchase price, NOT today's starting price
                if is_bought_today:
                    day_baseline = entry_p
                    day_baseline_type = "BUY_PRICE"
                else:
                    prev_close = float(quote.get("previous_close", 0.0) or 0.0)
                    if prev_close <= 0.0:
                        change_val = float(quote.get("change", 0.0) or 0.0)
                        if change_val != 0.0:
                            prev_close = current_price - change_val
                    if prev_close <= 0.0:
                        prev_close = entry_p
                    day_baseline = prev_close
                    day_baseline_type = "PREV_CLOSE"

                day_change = round(current_price - day_baseline, 2)
                day_change_pct = round((day_change / day_baseline) * 100.0, 2) if day_baseline > 0 else 0.0
                day_pnl = round(day_change * t.quantity * multiplier, 2)
                pnl_pct = round(((current_price - entry_p) / entry_p) * 100.0 * multiplier, 2) if entry_p > 0 else 0.0

                entry["current_price"] = round(current_price, 2)
                entry["unrealized_pnl"] = round(unrealized, 2)
                entry["pnl_pct"] = pnl_pct
                entry["invested"] = round(entry_p * t.quantity, 2)
                entry["value"] = round(current_price * t.quantity, 2)
                entry["previous_close"] = round(day_baseline, 2)
                entry["day_baseline"] = round(day_baseline, 2)
                entry["day_baseline_type"] = day_baseline_type
                entry["day_change"] = day_change
                entry["day_change_pct"] = day_change_pct
                entry["day_pnl"] = day_pnl
        result.append(entry)

    return {"trades": result}


@router.put("/{trade_id}/close")
async def close_paper_trade(
    trade_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Close an open paper trade at current market price."""
    import uuid
    try:
        uuid.UUID(str(trade_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid trade_id format: '{trade_id}'. Must be a valid UUID.")

    try:
        trade = await paper_trading_service.close_trade(db, trade_id, str(current_user.id))
        return {
            "trade_id": str(trade.id),
            "exit_price": float(trade.exit_price) if trade.exit_price is not None else None,
            "realized_pnl": float(trade.realized_pnl) if trade.realized_pnl is not None else None,
            "commission": float(trade.commission) if trade.commission is not None else 0.0,
            "stt_tax": float(trade.stt_tax) if trade.stt_tax is not None else 0.0,
            "status": trade.status,
            "closed_at": trade.closed_at.isoformat() if trade.closed_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
