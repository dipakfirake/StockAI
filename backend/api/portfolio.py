"""Portfolio API router."""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import get_current_user
from backend.core.market_hours import is_indian_market_open
from backend.models.paper_trade import PaperTrade
from backend.services.market_data import market_data_service
from backend.services.paper_trading import paper_trading_service

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

    # Opportunistically sweep actionable pending orders during live market hours
    if trades and is_indian_market_open() and any(t.status == "PENDING" for t in trades):
        try:
            filled = await paper_trading_service.evaluate_pending_orders(db, user_id=str(current_user.id))
            if filled > 0:
                await db.flush()
                result = await db.execute(
                    select(PaperTrade).where(PaperTrade.user_id == current_user.id)
                )
                trades = result.scalars().all()
        except Exception:
            pass

    if not trades:
        return {
            "initial_capital": 100000.0,
            "current_value": 100000.0,
            "total_invested": 0.0,
            "total_current_value": 0.0,
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
            "closed_trades_list": [],
            "sold_today_count": 0,
            "auto_sold_count": 0,
            "user_sold_count": 0,
            "win_rate": 0.0,
            "allocation": [],
            "pending_orders_list": [],
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

        gross_pnl = multiplier * (current_price - entry_p) * t.quantity
        unrealized = gross_pnl - comm - stt
        total_unrealized += unrealized

        invested = entry_p * t.quantity
        value = current_price * t.quantity
        total_invested += invested

        # Net Return on Buying percentage (matches rupee unrealized P&L after commission & STT)
        pnl_pct = round((unrealized / invested) * 100.0, 2) if invested > 0 else 0.0
        # Gross price movement percentage (raw market movement from entry)
        price_change_pct = round(((current_price - entry_p) / entry_p) * 100.0 * multiplier, 2) if entry_p > 0 else 0.0

        # Days held calculation & Indian IST timezone resolution
        opened_at = t.opened_at if isinstance(getattr(t, "opened_at", None), datetime) else now_utc
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
            "gross_pnl": round(gross_pnl, 2),
            "total_charges": round(comm + stt, 2),
            "commission": round(comm, 2),
            "stt_tax": round(stt, 2),
            "pnl_pct": pnl_pct,
            "price_change_pct": price_change_pct,
            "day_change": day_change,
            "day_change_pct": day_change_pct,
            "day_pnl": day_pnl,
            "opened_at": opened_at_utc.isoformat(),
            "buy_date_formatted": buy_date_formatted,
            "days_held": days_held,
            "stop_loss": float(t.stop_loss) if t.stop_loss is not None else None,
            "target_price": float(t.target_price) if t.target_price is not None else None,
            "target_1": float(t.target_1) if getattr(t, "target_1", None) is not None else None,
            "target_2": float(t.target_2) if getattr(t, "target_2", None) is not None else None,
            "target_3": float(t.target_3) if getattr(t, "target_3", None) is not None else None,
            "initial_stop_loss": float(t.initial_stop_loss) if getattr(t, "initial_stop_loss", None) is not None else None,
            "highest_price_recorded": float(t.highest_price_recorded) if getattr(t, "highest_price_recorded", None) is not None else None,
            "ratchet_stage": getattr(t, "ratchet_stage", "INITIAL") or "INITIAL",
            "trailing_enabled": bool(getattr(t, "trailing_enabled", True)),
        })

    total_pnl = total_realized + total_unrealized
    current_value = initial_capital + total_pnl

    def _sort_closed_key(tr: PaperTrade) -> float:
        dt = getattr(tr, "closed_at", None) or getattr(tr, "opened_at", None)
        if not isinstance(dt, datetime):
            return 0.0
        dt_utc = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        return dt_utc.timestamp()

    closed_sorted = sorted(closed, key=_sort_closed_key, reverse=True)
    closed_trades_list = []
    sold_today_count = 0
    auto_sold_count = 0
    user_sold_count = 0
    for c in closed_sorted:
        c_open = c.opened_at if isinstance(getattr(c, "opened_at", None), datetime) else now_utc
        c_open_utc = c_open if c_open.tzinfo else c_open.replace(tzinfo=timezone.utc)
        c_close = getattr(c, "closed_at", None)
        c_close_utc = (c_close if c_close.tzinfo else c_close.replace(tzinfo=timezone.utc)) if isinstance(c_close, datetime) else None
        c_entry_p = float(c.entry_price) if getattr(c, "entry_price", None) is not None else None
        exit_meta = paper_trading_service.resolve_trade_exit_details(c, now_utc=now_utc)
        if exit_meta["is_sold_today"]:
            sold_today_count += 1
        if exit_meta["closed_by"] == "AUTO_SYSTEM":
            auto_sold_count += 1
        elif exit_meta["closed_by"] == "USER_MANUAL":
            user_sold_count += 1
        closed_trades_list.append({
            "trade_id": str(c.id),
            "symbol": c.symbol,
            "direction": c.direction,
            "order_type": c.order_type,
            "product_type": c.product_type,
            "quantity": c.quantity,
            "entry_price": round(c_entry_p, 2) if c_entry_p is not None else None,
            "exit_price": exit_meta["exit_price"],
            "gross_pnl": exit_meta["gross_pnl"],
            "realized_pnl": round(float(c.realized_pnl), 2) if c.realized_pnl is not None else None,
            "pnl_pct": exit_meta["pnl_pct"],
            "commission": round(float(c.commission or 0.0), 2),
            "stt_tax": round(float(c.stt_tax or 0.0), 2),
            "total_charges": exit_meta["total_charges"],
            "target_price": float(c.target_price) if getattr(c, "target_price", None) is not None else None,
            "target_1": float(c.target_1) if getattr(c, "target_1", None) is not None else None,
            "target_2": float(c.target_2) if getattr(c, "target_2", None) is not None else None,
            "target_3": float(c.target_3) if getattr(c, "target_3", None) is not None else None,
            "stop_loss": float(c.stop_loss) if getattr(c, "stop_loss", None) is not None else None,
            "initial_stop_loss": float(c.initial_stop_loss) if getattr(c, "initial_stop_loss", None) is not None else None,
            "highest_price_recorded": float(c.highest_price_recorded) if getattr(c, "highest_price_recorded", None) is not None else None,
            "ratchet_stage": getattr(c, "ratchet_stage", "INITIAL") or "INITIAL",
            "opened_at": c_open_utc.isoformat(),
            "closed_at": c_close_utc.isoformat() if c_close_utc else None,
            "buy_date_formatted": exit_meta["buy_date_formatted"],
            "sell_date_formatted": exit_meta["sell_date_formatted"],
            "days_held": exit_meta["days_held"],
            "holding_duration_label": exit_meta["holding_duration_label"],
            "is_sold_today": exit_meta["is_sold_today"],
            "closed_by": exit_meta["closed_by"],
            "exit_reason": exit_meta["exit_reason"],
            "exit_reason_label": exit_meta["exit_reason_label"],
        })

    # Day's PnL percentage across all open holdings
    total_day_pnl_pct = round((total_day_pnl / total_prev_value) * 100.0, 2) if total_prev_value > 0 else 0.0

    # Holdings Current Market Value & Weight allocation
    total_current_value = sum(a["value"] for a in allocation)
    weight_denominator = total_current_value if total_current_value > 0 else 1.0
    for a in allocation:
        a["weight_pct"] = round(a["value"] / weight_denominator * 100, 2)

    pending_orders_list = []
    for t in sorted(pending, key=lambda x: x.opened_at or now_utc, reverse=True):
        opened_at = t.opened_at if isinstance(getattr(t, "opened_at", None), datetime) else now_utc
        opened_at_utc = opened_at if opened_at.tzinfo else opened_at.replace(tzinfo=timezone.utc)
        pending_orders_list.append({
            "trade_id": str(t.id),
            "symbol": t.symbol,
            "direction": t.direction,
            "order_type": t.order_type,
            "product_type": t.product_type,
            "quantity": t.quantity,
            "limit_price": float(t.limit_price) if t.limit_price is not None else None,
            "stop_price": float(t.stop_price) if t.stop_price is not None else None,
            "target_price": float(t.target_price) if t.target_price is not None else None,
            "stop_loss": float(t.stop_loss) if t.stop_loss is not None else None,
            "status": t.status,
            "opened_at": opened_at_utc.isoformat(),
            "buy_date_formatted": opened_at_utc.strftime("%d %b %Y, %I:%M %p"),
        })

    return {
        "initial_capital": initial_capital,
        "current_value": round(current_value, 2),
        "total_invested": round(total_invested, 2),
        "total_current_value": round(total_current_value, 2),
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
        "closed_trades_list": closed_trades_list,
        "sold_today_count": sold_today_count,
        "auto_sold_count": auto_sold_count,
        "user_sold_count": user_sold_count,
        "win_rate": round(win_rate, 4),
        "allocation": allocation,
        "pending_orders_list": pending_orders_list,
    }

