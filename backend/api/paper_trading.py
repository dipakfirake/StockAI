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

    result = []
    for t in trades:
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
            "opened_at": t.opened_at.isoformat(),
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
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
                entry["current_price"] = current_price
                entry["unrealized_pnl"] = round(unrealized, 2)
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
