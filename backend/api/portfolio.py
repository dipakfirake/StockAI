"""Portfolio API router."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import get_current_user
from backend.models.paper_trade import PaperTrade
from backend.services.market_data import market_data_service

router = APIRouter()


@router.get("")
async def get_portfolio(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get portfolio summary for all paper trades."""
    result = await db.execute(
        select(PaperTrade).where(PaperTrade.user_id == current_user.id)
    )
    trades = result.scalars().all()

    if not trades:
        return {
            "initial_capital": 100000.0,
            "current_value": 100000.0,
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "total_stt_paid": 0.0,
            "open_trades": 0,
            "pending_orders": 0,
            "closed_trades": 0,
            "win_rate": 0.0,
            "allocation": [],
        }

    initial_capital = 100000.0
    closed = [t for t in trades if t.status == "CLOSED"]
    open_trades = [t for t in trades if t.status == "OPEN"]
    pending = [t for t in trades if t.status == "PENDING"]

    total_realized = sum(float(t.realized_pnl or 0) for t in closed)
    total_stt = sum(float(t.stt_tax or 0) for t in closed)
    wins = [t for t in closed if (t.realized_pnl or 0) > 0]
    win_rate = len(wins) / len(closed) if closed else 0.0

    # Calculate unrealized PnL for open trades in one fast bulk query
    total_unrealized = 0.0
    allocation = []
    open_symbols = list({t.symbol for t in open_trades})
    quotes_map = await market_data_service.fetch_quotes_bulk(open_symbols) if open_symbols else {}

    for t in open_trades:
        quote = quotes_map.get(t.symbol)
        if quote and quote.get("price", 0) > 0:
            current_price = quote["price"]
            multiplier = 1 if t.direction == "BUY" else -1
            
            stt = 0.0
            if t.product_type == "DELIVERY":
                stt = current_price * t.quantity * 0.001
                
            unrealized = multiplier * (current_price - float(t.entry_price)) * t.quantity - float(t.commission) - stt
            total_unrealized += unrealized
            value = current_price * t.quantity
            allocation.append({
                "symbol": t.symbol,
                "direction": t.direction,
                "product_type": t.product_type,
                "quantity": t.quantity,
                "entry_price": float(t.entry_price),
                "current_price": current_price,
                "unrealized_pnl": round(unrealized, 2),
                "value": round(value, 2),
            })

    total_pnl = total_realized + total_unrealized
    current_value = initial_capital + total_pnl

    # Weight allocation
    total_value = sum(a["value"] for a in allocation) or 1
    for a in allocation:
        a["weight_pct"] = round(a["value"] / total_value * 100, 2)

    return {
        "initial_capital": initial_capital,
        "current_value": round(current_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / initial_capital * 100, 2),
        "realized_pnl": round(total_realized, 2),
        "unrealized_pnl": round(total_unrealized, 2),
        "total_stt_paid": round(total_stt, 2),
        "open_trades": len(open_trades),
        "pending_orders": len(pending),
        "closed_trades": len(closed),
        "win_rate": round(win_rate, 4),
        "allocation": allocation,
    }
