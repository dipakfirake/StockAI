"""Portfolio API router."""

from datetime import datetime, timezone, timedelta
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
    """Get comprehensive portfolio summary for all paper trades with Day P&L and holding analytics."""
    result = await db.execute(
        select(PaperTrade).where(PaperTrade.user_id == current_user.id)
    )
    trades = result.scalars().all()

    if not trades:
        return {
            "initial_capital": 100000.0,
            "current_value": 100000.0,
            "total_invested": 0.0,
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "total_day_pnl": 0.0,
            "total_day_pnl_pct": 0.0,
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

    # Calculate unrealized PnL, Day's PnL, and Holding Days for open trades
    total_unrealized = 0.0
    total_invested = 0.0
    total_day_pnl = 0.0
    total_prev_value = 0.0
    allocation = []
    open_symbols = list({t.symbol for t in open_trades})
    quotes_map = await market_data_service.fetch_quotes_bulk(open_symbols) if open_symbols else {}
    now_utc = datetime.now(timezone.utc)

    for t in open_trades:
        quote = quotes_map.get(t.symbol)
        if not quote or quote.get("price", 0) <= 0:
            clean = t.symbol.replace(".BO", "").replace(".NS", "")
            quote = quotes_map.get(f"{clean}.NS") or quotes_map.get(f"{clean}.BO") or quotes_map.get(clean)

        current_price = float(quote.get("price", 0.0) or 0.0) if quote else 0.0
        entry_p = float(t.entry_price) if t.entry_price is not None else current_price
        if current_price <= 0.0:
            current_price = entry_p

        multiplier = 1 if t.direction == "BUY" else -1
        comm = float(t.commission) if t.commission is not None else 0.0

        stt = 0.0
        if t.product_type == "DELIVERY":
            stt = current_price * t.quantity * 0.001

        unrealized = multiplier * (current_price - entry_p) * t.quantity - comm - stt
        total_unrealized += unrealized

        invested = entry_p * t.quantity
        value = current_price * t.quantity
        total_invested += invested

        # Profit percentage gain or loss percentage of buying
        pnl_pct = round(((current_price - entry_p) / entry_p) * 100.0 * multiplier, 2) if entry_p > 0 else 0.0

        # Days held calculation & Indian IST timezone resolution
        opened_at = t.opened_at if t.opened_at else now_utc
        opened_at_utc = opened_at if opened_at.tzinfo else opened_at.replace(tzinfo=timezone.utc)
        delta_seconds = max(0.0, (now_utc - opened_at_utc).total_seconds())
        days_held = int(delta_seconds // 86400)
        buy_date_formatted = opened_at_utc.strftime("%d %b %Y, %I:%M %p")

        ist_tz = timezone(timedelta(hours=5, minutes=30))
        now_ist = now_utc.astimezone(ist_tz)
        opened_at_ist = opened_at_utc.astimezone(ist_tz)
        is_bought_today = (opened_at_ist.date() == now_ist.date()) or (days_held == 0)

        # Day's P&L calculation:
        # If the stock was bought TODAY: Day's P&L starts from the exact time and buy price it was bought, NOT today's starting price.
        # If the stock was bought PREVIOUSLY: Day's P&L is today's session movement from previous close.
        if is_bought_today:
            day_baseline = entry_p
            day_baseline_type = "BUY_PRICE"
        else:
            prev_close = float(quote.get("previous_close", 0.0) or 0.0) if quote else 0.0
            if prev_close <= 0.0 and quote:
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
        total_day_pnl += day_pnl
        total_prev_value += day_baseline * t.quantity

        allocation.append({
            "trade_id": str(t.id),
            "symbol": t.symbol,
            "direction": t.direction,
            "order_type": t.order_type,
            "product_type": t.product_type,
            "quantity": t.quantity,
            "entry_price": round(entry_p, 2),
            "current_price": round(current_price, 2),
            "previous_close": round(day_baseline, 2),
            "day_baseline": round(day_baseline, 2),
            "day_baseline_type": day_baseline_type,
            "is_bought_today": is_bought_today,
            "invested": round(invested, 2),
            "value": round(value, 2),
            "unrealized_pnl": round(unrealized, 2),
            "pnl_pct": pnl_pct,
            "day_change": day_change,
            "day_change_pct": day_change_pct,
            "day_pnl": day_pnl,
            "opened_at": opened_at_utc.isoformat(),
            "buy_date_formatted": buy_date_formatted,
            "days_held": days_held,
        })

    total_pnl = total_realized + total_unrealized
    current_value = initial_capital + total_pnl

    # Day's PnL percentage across all open holdings
    total_day_pnl_pct = round((total_day_pnl / total_prev_value) * 100.0, 2) if total_prev_value > 0 else 0.0

    # Weight allocation
    total_value = sum(a["value"] for a in allocation) or 1.0
    for a in allocation:
        a["weight_pct"] = round(a["value"] / total_value * 100, 2)

    return {
        "initial_capital": initial_capital,
        "current_value": round(current_value, 2),
        "total_invested": round(total_invested, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / initial_capital * 100, 2) if initial_capital > 0 else 0.0,
        "total_day_pnl": round(total_day_pnl, 2),
        "total_day_pnl_pct": total_day_pnl_pct,
        "realized_pnl": round(total_realized, 2),
        "unrealized_pnl": round(total_unrealized, 2),
        "total_stt_paid": round(total_stt, 2),
        "open_trades": len(open_trades),
        "pending_orders": len(pending),
        "closed_trades": len(closed),
        "win_rate": round(win_rate, 4),
        "allocation": allocation,
    }

