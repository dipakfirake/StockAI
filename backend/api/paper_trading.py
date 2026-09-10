"""Paper Trading API router."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import get_current_user
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


@router.post("")
async def place_paper_trade(
    request: PlaceOrderRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Place a simulated paper trade. No real money involved."""
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
        return {
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
            "entry_price": float(t.entry_price) if t.entry_price else None,
            "limit_price": float(t.limit_price) if t.limit_price else None,
            "stop_price": float(t.stop_price) if t.stop_price else None,
            "target_price": float(t.target_price) if t.target_price else None,
            "stop_loss": float(t.stop_loss) if t.stop_loss else None,
            "commission": float(t.commission),
            "stt_tax": float(t.stt_tax),
            "status": t.status,
            "realized_pnl": float(t.realized_pnl) if t.realized_pnl else None,
            "opened_at": t.opened_at.isoformat(),
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        }
        if t.status == "OPEN":
            quote = quotes_map.get(t.symbol)
            if quote and quote.get("price", 0) > 0:
                current_price = quote["price"]
                multiplier = 1 if t.direction == "BUY" else -1
                unrealized = multiplier * (current_price - float(t.entry_price)) * t.quantity - float(t.commission)
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
    try:
        trade = await paper_trading_service.close_trade(db, trade_id, str(current_user.id))
        return {
            "trade_id": str(trade.id),
            "exit_price": float(trade.exit_price),
            "realized_pnl": float(trade.realized_pnl) if trade.realized_pnl else None,
            "commission": float(trade.commission),
            "stt_tax": float(trade.stt_tax),
            "status": trade.status,
            "closed_at": trade.closed_at.isoformat() if trade.closed_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
