"""Swing Trade 11-Day Audit Service — Automated tracking, milestone price recording,
target/stoploss execution rules, and multi-sheet Excel generation.
"""

import os
import math
import uuid
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.logging_config import get_logger
from backend.core.database import AsyncSessionLocal
from backend.models.swing_audit import SwingTradeAuditCycle, SwingTradeAudit, SwingTradeAuditPrice
from backend.services.market_data import market_data_service

logger = get_logger(__name__)

# Base folder for persisted audit spreadsheets
AUDIT_REPORTS_DIR = Path("/app/audits/swing_trades") if (os.name == "posix" and Path("/app").is_dir()) else Path("audits/swing_trades")


def get_audit_dir() -> Path:
    """Ensures audit reports directory exists and returns Path object."""
    env_dir = os.environ.get("AUDIT_DIR")
    target_dir = Path(env_dir) if env_dir else AUDIT_REPORTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


CLOSED_AUDIT_STATUSES = {
    "TARGET_ACHIEVED",
    "TARGET_1_ACHIEVED",
    "TARGET_2_ACHIEVED",
    "TARGET_3_ACHIEVED",
    "STOPPED_IN_PROFIT",
    "STOPLOSS_HIT",
    "DAY_11_EXIT",
    "CLOSED",
    "EXITED",
    "COMPLETED",
    "MANUAL_EXIT",
    "SQUARED_OFF",
}


def safe_date_sort_key(d: Any) -> Tuple[int, str]:
    """
    Returns a sortable tuple (priority, iso_string) so that NoneType, date, datetime,
    and strings never raise TypeError: '<' not supported between instances of 'NoneType' and 'str' / 'datetime'.
    """
    if d is None:
        return (0, "")
    if isinstance(d, (datetime, date)):
        return (1, d.isoformat())
    return (1, str(d))


def is_closed_audit(a: Any) -> bool:
    """Checks whether an audit setup has concluded or exited."""
    status = getattr(a, "status", None)
    if not status:
        return bool(getattr(a, "exit_date", None) is not None or getattr(a, "exit_price", None) is not None)
    st = str(status).strip().upper()
    if st in CLOSED_AUDIT_STATUSES:
        return True
    if st != "IN_PROGRESS" and (getattr(a, "exit_date", None) is not None or getattr(a, "exit_price", None) is not None):
        return True
    return False


_schema_ensured = False


async def ensure_swing_audit_schema(db: AsyncSession):
    """Ensures that newly added columns for Coupled Ratchet exist in the PostgreSQL table."""
    global _schema_ensured
    if _schema_ensured:
        return
    try:
        from unittest.mock import MagicMock, AsyncMock
        if isinstance(db, (MagicMock, AsyncMock)):
            return
        if not hasattr(db, "get_bind"):
            return
        bind = db.get_bind()
        if isinstance(bind, (MagicMock, AsyncMock)):
            return
        dialect = getattr(bind, "dialect", None)
        dialect_name = str(getattr(dialect, "name", getattr(bind, "name", "")))
        if any(p in dialect_name.lower() for p in ("postgres", "asyncpg", "psycopg")):
            await db.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'swing_trade_audits') THEN
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS target_1 NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS target_2 NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS target_3 NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS reward_to_risk NUMERIC(8, 2);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS total_score NUMERIC(6, 2);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS allocated_capital NUMERIC(14, 2) DEFAULT 100000.00;
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS dynamic_stop_loss NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS tranche_2_active BOOLEAN DEFAULT FALSE;
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS tranche_2_buy_price NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS tranche_2_stop_loss NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS ratchet_stage VARCHAR(40) DEFAULT 'INITIAL';
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS highest_price_recorded NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS user_bought BOOLEAN DEFAULT FALSE;
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS user_buy_price NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS user_buy_time TIMESTAMPTZ;
                    END IF;
                    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'swing_trade_audit_prices') THEN
                        ALTER TABLE swing_trade_audit_prices ADD COLUMN IF NOT EXISTS dynamic_sl_day NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audit_prices ADD COLUMN IF NOT EXISTS atr_value NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audit_prices ADD COLUMN IF NOT EXISTS ratchet_event VARCHAR(40);
                    END IF;
                    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'swing_trade_audit_cycles') THEN
                        ALTER TABLE swing_trade_audit_cycles ADD COLUMN IF NOT EXISTS excel_file_path VARCHAR(500);
                        ALTER TABLE swing_trade_audit_cycles ADD COLUMN IF NOT EXISTS total_gain_loss_pct NUMERIC(8, 2) DEFAULT 0.00;
                        ALTER TABLE swing_trade_audit_cycles ADD COLUMN IF NOT EXISTS total_pnl_rupees NUMERIC(14, 2) DEFAULT 0.00;
                    END IF;
                END $$;
            """))
            await db.commit()
        _schema_ensured = True
    except Exception as e:
        logger.warning(f"Schema check for swing audit skipped/deferred: {e}")


def add_trading_days(start_date: date, num_days: int) -> date:
    """Adds approximately N trading days (skipping Saturdays and Sundays)."""
    current = start_date
    added = 0
    while added < num_days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Monday to Friday
            added += 1
    return current


class SwingAuditService:
    """Institutional audit service tracking swing trade accuracy and PnL."""

    @staticmethod
    def get_audit_dir() -> Path:
        """Expose get_audit_dir on the service class and instance."""
        return get_audit_dir()

    @staticmethod
    async def get_or_create_active_cycle(db: AsyncSession, target_date: Optional[date] = None) -> SwingTradeAuditCycle:
        """
        Retrieves the current ACTIVE 11-day audit cycle, or creates a new one
        if none exists or if the current one has expired past its 11th trading day.
        """
        await ensure_swing_audit_schema(db)
        ref_date = target_date or date.today()
        
        stmt = (
            select(SwingTradeAuditCycle)
            .where(SwingTradeAuditCycle.status == "ACTIVE")
            .order_by(SwingTradeAuditCycle.cycle_number.desc())
            .options(selectinload(SwingTradeAuditCycle.audits))
        )
        cycle = (await db.execute(stmt)).scalars().first()

        if cycle:
            # If current active cycle is past its end date, close it and start a new one
            if ref_date > cycle.to_date:
                cycle.status = "COMPLETED"
                await db.commit()
                await db.refresh(cycle)
                logger.info(f"Closed audit cycle #{cycle.cycle_number} ({cycle.from_date} to {cycle.to_date})")
                cycle = None

        if not cycle:
            # Determine cycle number
            count_stmt = select(func.count(SwingTradeAuditCycle.id))
            cycle_count = (await db.execute(count_stmt)).scalar() or 0
            new_num = cycle_count + 1
            
            end_date = add_trading_days(ref_date, 11)
            filename = f"Swing_Trade_Audit_{ref_date.isoformat()}_to_{end_date.isoformat()}.xlsx"
            file_path = str(get_audit_dir() / filename)
            
            cycle = SwingTradeAuditCycle(
                cycle_number=new_num,
                from_date=ref_date,
                to_date=end_date,
                status="ACTIVE",
                excel_file_path=file_path,
                total_trades=0,
                win_trades=0,
                loss_trades=0,
                win_rate=Decimal("0.00"),
                total_gain_loss_pct=Decimal("0.00"),
                total_pnl_rupees=Decimal("0.00")
            )
            db.add(cycle)
            await db.commit()
            await db.refresh(cycle)
            logger.info(f"Initialized new 11-day Swing Audit Cycle #{new_num} ({ref_date} to {end_date})")

        return cycle

    @staticmethod
    async def track_swing_trade(
        db: AsyncSession,
        symbol: str,
        trade_plan: dict,
        company_name: Optional[str] = None,
        recommendation_date: Optional[date] = None,
        total_score: Optional[float] = None,
        allocated_capital: float = 100000.0,
        user_bought: bool = False,
        user_buy_price: Optional[float] = None,
        notes: Optional[str] = None
    ) -> SwingTradeAudit:
        """
        Catalogs a stock recommendation into the active 11-day audit ledger.
        Idempotent: prevents duplicate entries for the same symbol on the same day,
        while seamlessly updating user_bought status if the user decides to enter.
        """
        rec_date = recommendation_date or date.today()
        cycle = await SwingAuditService.get_or_create_active_cycle(db, rec_date)

        norm_symbol = symbol.strip().upper()
        if not norm_symbol.endswith(".NS") and not norm_symbol.endswith(".BO") and not norm_symbol.startswith("^"):
            norm_symbol = f"{norm_symbol}.NS"

        # Check for duplicate recommendation on same date
        existing_stmt = select(SwingTradeAudit).where(
            and_(
                SwingTradeAudit.cycle_id == cycle.id,
                SwingTradeAudit.symbol == norm_symbol,
                SwingTradeAudit.recommendation_date == rec_date
            )
        )
        existing = (await db.execute(existing_stmt)).scalars().first()
        if existing:
            # If user explicitly bought this stock after initial auto-cataloging, update user buy state
            if user_bought and not existing.user_bought:
                existing.user_bought = True
                u_price = user_buy_price if (user_buy_price and user_buy_price > 0) else float(existing.buy_price)
                existing.user_buy_price = Decimal(str(round(u_price, 2)))
                existing.user_buy_time = datetime.now(timezone.utc)
                await db.commit()
                await db.refresh(existing)
                await SwingAuditService.update_daily_prices(db, cycle_id=cycle.id)
                logger.info(f"Updated user execution for existing audit {norm_symbol} @ ₹{existing.user_buy_price}")
            else:
                logger.info(f"Audit entry already exists for {norm_symbol} on {rec_date}. Preserving record {existing.id}.")
            return existing

        buy_price = Decimal(str(round(float(trade_plan.get("entry_price") or trade_plan.get("current_price") or 0.0), 2)))
        target_price = Decimal(str(round(float(trade_plan.get("target_price") or trade_plan.get("target_2") or (float(buy_price) * 1.06)), 2)))
        stop_loss = Decimal(str(round(float(trade_plan.get("stop_loss") or (float(buy_price) * 0.96)), 2)))

        t1 = Decimal(str(round(float(trade_plan.get("target_1")), 2))) if trade_plan.get("target_1") else None
        t2 = Decimal(str(round(float(trade_plan.get("target_2")), 2))) if trade_plan.get("target_2") else target_price
        t3 = Decimal(str(round(float(trade_plan.get("target_3")), 2))) if trade_plan.get("target_3") else None
        rr = Decimal(str(round(float(trade_plan.get("reward_to_risk") or 2.0), 2)))
        score_dec = Decimal(str(round(float(total_score), 1))) if total_score is not None else None

        user_buy_dec = None
        if user_bought:
            u_price = user_buy_price if (user_buy_price and user_buy_price > 0) else float(buy_price)
            user_buy_dec = Decimal(str(round(u_price, 2)))

        audit = SwingTradeAudit(
            cycle_id=cycle.id,
            symbol=norm_symbol,
            company_name=company_name or norm_symbol.replace(".NS", ""),
            recommendation_date=rec_date,
            buy_price=buy_price,
            target_price=target_price,
            stop_loss=stop_loss,
            target_1=t1,
            target_2=t2,
            target_3=t3,
            reward_to_risk=rr,
            total_score=score_dec,
            status="IN_PROGRESS",
            allocated_capital=Decimal(str(allocated_capital)),
            user_bought=user_bought,
            user_buy_price=user_buy_dec,
            user_buy_time=datetime.now(timezone.utc) if user_bought else None,
            notes=notes or f"Generated via Swing Trade Analysis (Score: {total_score or 'N/A'})"
        )
        db.add(audit)
        await db.commit()
        await db.refresh(audit)

        logger.info(f"Audited new swing recommendation: {norm_symbol} @ ₹{buy_price} (User Bought: {user_bought}, Target: ₹{target_price}, SL: ₹{stop_loss})")

        # Immediately update daily prices for the active cycle and generate Excel
        await SwingAuditService.update_daily_prices(db, cycle_id=cycle.id)
        return audit

    @staticmethod
    async def track_batch_swing_trades(
        db: AsyncSession,
        stocks: list[dict],
        recommendation_date: Optional[date] = None,
    ) -> int:
        """
        Catalogs a batch of recommended swing trade setups into the active 11-day audit cycle.
        Idempotent: skips existing recommendations for the same symbol on the same date.
        Updates daily prices and generates Excel report once after the batch is added.
        """
        if not stocks:
            return 0

        rec_date = recommendation_date or date.today()
        cycle = await SwingAuditService.get_or_create_active_cycle(db, rec_date)

        added_count = 0
        for stock_data in stocks:
            symbol = stock_data.get("symbol", "")
            trade_plan = stock_data.get("trade_plan")
            if not symbol or not trade_plan or not isinstance(trade_plan, dict):
                continue

            norm_symbol = symbol.strip().upper()
            if not norm_symbol.endswith(".NS") and not norm_symbol.endswith(".BO") and not norm_symbol.startswith("^"):
                norm_symbol = f"{norm_symbol}.NS"

            # Check for duplicate
            existing_stmt = select(SwingTradeAudit).where(
                and_(
                    SwingTradeAudit.cycle_id == cycle.id,
                    SwingTradeAudit.symbol == norm_symbol,
                    SwingTradeAudit.recommendation_date == rec_date
                )
            )
            existing = (await db.execute(existing_stmt)).scalars().first()
            if existing:
                continue

            buy_price = Decimal(str(round(float(trade_plan.get("entry_price") or trade_plan.get("current_price") or 0.0), 2)))
            target_price = Decimal(str(round(float(trade_plan.get("target_price") or trade_plan.get("target_2") or (float(buy_price) * 1.06)), 2)))
            stop_loss = Decimal(str(round(float(trade_plan.get("stop_loss") or (float(buy_price) * 0.96)), 2)))

            t1 = Decimal(str(round(float(trade_plan.get("target_1")), 2))) if trade_plan.get("target_1") else None
            t2 = Decimal(str(round(float(trade_plan.get("target_2")), 2))) if trade_plan.get("target_2") else target_price
            t3 = Decimal(str(round(float(trade_plan.get("target_3")), 2))) if trade_plan.get("target_3") else None
            rr = Decimal(str(round(float(trade_plan.get("reward_to_risk") or 2.0), 2)))
            total_sc = stock_data.get("total_score")
            score_dec = Decimal(str(round(float(total_sc), 1))) if total_sc is not None else None

            audit = SwingTradeAudit(
                cycle_id=cycle.id,
                symbol=norm_symbol,
                company_name=stock_data.get("name") or norm_symbol.replace(".NS", ""),
                recommendation_date=rec_date,
                buy_price=buy_price,
                target_price=target_price,
                stop_loss=stop_loss,
                target_1=t1,
                target_2=t2,
                target_3=t3,
                reward_to_risk=rr,
                total_score=score_dec,
                status="IN_PROGRESS",
                allocated_capital=Decimal("100000.00"),
                user_bought=False,
                notes=f"Auto-cataloged from Swing Trade Screener (Score: {total_sc or 'N/A'})"
            )
            db.add(audit)
            added_count += 1

        if added_count > 0:
            await db.commit()
            logger.info(f"Batch cataloged {added_count} swing recommendations into Cycle #{cycle.cycle_number}")
            await SwingAuditService.update_daily_prices(db, cycle_id=cycle.id)

        return added_count

    @staticmethod
    async def update_daily_prices(db: AsyncSession, cycle_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        """
        Evaluates daily price progression (Day 1..11) for all audited stocks in the cycle.
        Applies strict Stop Loss and Target Achievement exit rules:
        - If Low <= Stop Loss -> SELL IMMEDIATELY (Book Loss, stop tracking).
        - If High >= Target -> PROFIT BOOKED (Book Gain, stop tracking).
        - If Day 11 reached -> Square off at Day 11 Close price.
        """
        try:
            await ensure_swing_audit_schema(db)
            if cycle_id:
                stmt = select(SwingTradeAuditCycle).where(SwingTradeAuditCycle.id == cycle_id)
            else:
                stmt = select(SwingTradeAuditCycle).where(SwingTradeAuditCycle.status == "ACTIVE").order_by(SwingTradeAuditCycle.cycle_number.desc())
            
            cycle = (await db.execute(stmt)).scalars().first()
            if not cycle:
                cycle = await SwingAuditService.get_or_create_active_cycle(db)

            if not cycle:
                return {
                    "status": "no_active_cycle",
                    "updated_count": 0,
                    "total_trades": 0,
                    "win_trades": 0,
                    "loss_trades": 0,
                    "win_rate": 0.0,
                    "total_gain_loss_pct": 0.0,
                    "total_pnl_rupees": 0.0
                }

            # Fetch audits in cycle with their daily prices
            audits_stmt = (
                select(SwingTradeAudit)
                .where(SwingTradeAudit.cycle_id == cycle.id)
                .options(selectinload(SwingTradeAudit.daily_prices))
            )
            audits = (await db.execute(audits_stmt)).scalars().all()

            updated_count = 0

            for audit in audits:
                # If trade was already exited in an earlier run, skip candle re-evaluation
                if audit.status in ("TARGET_ACHIEVED", "STOPLOSS_HIT", "DAY_11_EXIT") and audit.exit_price is not None:
                    continue

                # Fetch daily candles from recommendation date to present
                try:
                    # Coerce recommendation_date safely to a date object
                    rec_date = audit.recommendation_date
                    if isinstance(rec_date, datetime):
                        rec_date = rec_date.date()
                    elif isinstance(rec_date, str):
                        try:
                            rec_date = date.fromisoformat(rec_date[:10])
                        except Exception:
                            rec_date = date.today()
                    elif not isinstance(rec_date, date):
                        rec_date = date.today()

                    candles = await market_data_service.fetch_candles(audit.symbol, "1d", limit=30)
                    if not candles or not isinstance(candles, list):
                        # Multi-tier fallback 1: Alternate exchange (.BO <-> .NS)
                        clean_sym = audit.symbol.replace(".NS", "").replace(".BO", "").strip().upper()
                        alt_sym = f"{clean_sym}.BO" if audit.symbol.endswith(".NS") else f"{clean_sym}.NS"
                        candles = await market_data_service.fetch_candles(alt_sym, "1d", limit=30)

                    # Multi-tier fallback 2: Check local database candles hypertable
                    if not candles or not isinstance(candles, list):
                        try:
                            from backend.models.candle import Candle
                            clean_sym = audit.symbol.replace(".NS", "").replace(".BO", "").strip().upper()
                            db_c_stmt = (
                                select(Candle)
                                .where(Candle.symbol.ilike(f"%{clean_sym}%"))
                                .where(Candle.timeframe == "1d")
                                .order_by(Candle.timestamp.asc())
                            )
                            db_c_rows = (await db.execute(db_c_stmt)).scalars().all()
                            if db_c_rows:
                                candles = [
                                    {
                                        "timestamp": c.timestamp.isoformat(),
                                        "open": float(c.open),
                                        "high": float(c.high),
                                        "low": float(c.low),
                                        "close": float(c.close),
                                        "volume": int(c.volume or 0)
                                    }
                                    for c in db_c_rows
                                ]
                        except Exception as db_c_err:
                            logger.debug(f"DB candles hypertable fallback error: {db_c_err}")

                    # Parse candle timestamps to dates and filter on/after recommendation_date
                    valid_candles = []
                    if candles and isinstance(candles, list):
                        for c in candles:
                            ts_str = c.get("timestamp", "")
                            try:
                                c_date = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).date()
                            except Exception:
                                continue
                            if c_date >= rec_date:
                                valid_candles.append((c_date, c))

                    # Multi-tier fallback 3: Append trading day prices up through today
                    today_dt = date.today()
                    quote = None
                    try:
                        quote = await market_data_service.fetch_quote(audit.symbol)
                    except Exception as q_err:
                        logger.debug(f"Quote fetch fallback failed for {audit.symbol}: {q_err}")

                    curr_price = 0.0
                    prev_close = 0.0
                    if quote and isinstance(quote, dict):
                        curr_price = float(quote.get("price") or quote.get("ltp") or quote.get("close") or 0.0)
                        prev_close = float(quote.get("previous_close") or curr_price)

                    # Defensive fallback: If live quote is missing, use latest candle close or recommendation buy price
                    if curr_price <= 0:
                        if valid_candles:
                            curr_price = float(valid_candles[-1][1].get("close") or audit.buy_price or 0.0)
                        else:
                            curr_price = float(audit.buy_price or 0.0)
                    if prev_close <= 0:
                        prev_close = curr_price

                    if valid_candles:
                        last_c_date = valid_candles[-1][0]
                        if last_c_date < today_dt and len(valid_candles) < 11 and curr_price > 0:
                            # Advance day by day (skipping weekends) from last_c_date to today_dt
                            cur_step = last_c_date + timedelta(days=1)
                            while cur_step <= today_dt and len(valid_candles) < 11:
                                if cur_step.weekday() < 5:  # Monday to Friday
                                    is_today = (cur_step == today_dt)
                                    step_close = curr_price if is_today else prev_close
                                    step_open = float(quote.get("open") or prev_close) if (is_today and quote) else prev_close
                                    step_high = max(step_open, step_close)
                                    step_low = min(step_open, step_close)
                                    step_candle = {
                                        "timestamp": datetime(cur_step.year, cur_step.month, cur_step.day, 10, 0, tzinfo=timezone.utc).isoformat(),
                                        "open": step_open,
                                        "high": step_high,
                                        "low": step_low,
                                        "close": step_close,
                                        "volume": int(quote.get("volume") or 0) if (is_today and quote) else 0
                                    }
                                    valid_candles.append((cur_step, step_candle))
                                cur_step += timedelta(days=1)
                    elif not valid_candles and curr_price > 0:
                        # If zero historical candles could be fetched, populate trading days from rec_date to today_dt
                        cur_step = rec_date
                        while cur_step <= today_dt and len(valid_candles) < 11:
                            if cur_step.weekday() < 5:
                                is_today = (cur_step == today_dt)
                                step_close = curr_price if is_today else prev_close
                                step_open = float(quote.get("open") or prev_close) if (is_today and quote) else prev_close
                                step_candle = {
                                    "timestamp": datetime(cur_step.year, cur_step.month, cur_step.day, 10, 0, tzinfo=timezone.utc).isoformat(),
                                    "open": step_open,
                                    "high": max(step_open, step_close),
                                    "low": min(step_open, step_close),
                                    "close": step_close,
                                    "volume": int(quote.get("volume") or 0) if (is_today and quote) else 0
                                }
                                valid_candles.append((cur_step, step_candle))
                            cur_step += timedelta(days=1)

                    if not valid_candles:
                        continue

                    # Deduplicate by calendar date and sort chronologically
                    date_candle_dict = {}
                    for c_date, c_data in valid_candles:
                        date_candle_dict[c_date] = c_data
                    valid_candles = sorted(date_candle_dict.items(), key=lambda x: x[0])

                    existing_price_map = {p.day_number: p for p in audit.daily_prices}
                    # Effective buy price: User's execution price if bought, else system recommendation price
                    raw_buy = audit.user_buy_price if (audit.user_bought and audit.user_buy_price is not None) else audit.buy_price
                    buy_val = float(raw_buy or 0.0)
                    t1_val = float(audit.target_1 or audit.target_price or (buy_val * 1.06))
                    t2_val = float(audit.target_2 or 0.0)
                    has_t2 = bool(t2_val > t1_val)
                    initial_sl = float(audit.stop_loss or (buy_val * 0.96))
                    capital_val = float(audit.allocated_capital or 100000.0)

                    # Dynamic Coupled Ratchet & Trailing Stop state
                    current_sl = float(audit.dynamic_stop_loss or initial_sl)
                    highest_p = float(audit.highest_price_recorded or buy_val)
                    tranche_2_active = bool(audit.tranche_2_active)
                    tranche_2_buy = float(audit.tranche_2_buy_price or 0.0)
                    tranche_2_sl = float(audit.tranche_2_stop_loss or 0.0)
                    ratchet_stage = audit.ratchet_stage or "INITIAL"

                    # Process Day 1 through Day 11
                    for idx, (candle_date, c_data) in enumerate(valid_candles[:11]):
                        day_num = idx + 1
                        open_p = float(c_data.get("open", 0.0) or 0.0)
                        high_p = float(c_data.get("high", 0.0) or 0.0)
                        low_p = float(c_data.get("low", 0.0) or 0.0)
                        close_p = float(c_data.get("close", 0.0) or 0.0)

                        highest_p = max(highest_p, high_p)
                        atr_val = round(max(high_p - low_p, 0.02 * close_p), 2)

                        change_pct = round(((close_p - buy_val) / buy_val) * 100, 2) if buy_val > 0 else 0.0
                        day_ratchet_event = None
                        just_ratcheted = False

                        # ─── COUPLED RATCHET ENGINE: TARGET 1 CROSS & TRANCHE 2 ACTIVATION ─
                        if high_p >= t1_val and audit.status == "IN_PROGRESS":
                            if has_t2:
                                # Multi-target active: Do NOT close! Activate Tranche 2 & ratchet Tranche 1
                                if not tranche_2_active:
                                    tranche_2_active = True
                                    tranche_2_buy = round(max(t1_val, open_p), 2)
                                    tranche_2_sl = round(max(buy_val * 1.01, tranche_2_buy - (1.5 * atr_val)), 2)
                                    just_ratcheted = True
                                
                                # Ratchet Tranche 1 SL to Break-Even + 1% or ATR trailing floor
                                atr_trail_floor = round(highest_p - (1.5 * atr_val), 2)
                                t1_new_sl = round(max(current_sl, buy_val * 1.01, atr_trail_floor), 2)
                                if t1_new_sl > current_sl:
                                    current_sl = t1_new_sl
                                    just_ratcheted = True

                                ratchet_stage = "BREAKEVEN_LOCKED"
                                day_ratchet_event = "BREAKEVEN_LOCKED"

                                # Step 2: If price reaches halfway to T2 (or >= 108 in our example)
                                half_way_t2 = t1_val + 0.5 * (t2_val - t1_val)
                                if high_p >= half_way_t2:
                                    # Lock Tranche 1 at Target 1!
                                    current_sl = max(current_sl, t1_val)
                                    # Ratchet Tranche 2 SL to Target 1 (near breakeven!)
                                    tranche_2_sl = max(tranche_2_sl, t1_val)
                                    ratchet_stage = "T2_RATCHET_ACTIVE"
                                    day_ratchet_event = "T2_RATCHET_ACTIVE"

                        tgt_hit = (high_p >= t2_val) if (has_t2 and tranche_2_active) else (high_p >= t1_val)
                        # On the day a target is crossed and stop elevated, pre-existing stop governs that day's morning lows
                        if just_ratcheted:
                            sl_hit = (low_p <= initial_sl)
                        else:
                            sl_hit = (low_p <= current_sl)

                        # Update or insert daily price record
                        if day_num in existing_price_map:
                            dp = existing_price_map[day_num]
                            dp.trade_date = candle_date
                            dp.open_price = Decimal(str(open_p))
                            dp.high_price = Decimal(str(high_p))
                            dp.low_price = Decimal(str(low_p))
                            dp.close_price = Decimal(str(close_p))
                            dp.change_pct_from_buy = Decimal(str(change_pct))
                            dp.target_hit = tgt_hit
                            dp.stoploss_hit = sl_hit
                            dp.dynamic_sl_day = Decimal(str(current_sl))
                            dp.atr_value = Decimal(str(atr_val))
                            dp.ratchet_event = day_ratchet_event
                        else:
                            dp = SwingTradeAuditPrice(
                                audit_id=audit.id,
                                day_number=day_num,
                                trade_date=candle_date,
                                open_price=Decimal(str(open_p)),
                                high_price=Decimal(str(high_p)),
                                low_price=Decimal(str(low_p)),
                                close_price=Decimal(str(close_p)),
                                change_pct_from_buy=Decimal(str(change_pct)),
                                target_hit=tgt_hit,
                                stoploss_hit=sl_hit,
                                dynamic_sl_day=Decimal(str(current_sl)),
                                atr_value=Decimal(str(atr_val)),
                                ratchet_event=day_ratchet_event,
                            )
                            db.add(dp)

                        # Persist active audit ratchet state on each day
                        audit.dynamic_stop_loss = Decimal(str(current_sl))
                        audit.highest_price_recorded = Decimal(str(highest_p))
                        audit.tranche_2_active = tranche_2_active
                        audit.tranche_2_buy_price = Decimal(str(tranche_2_buy)) if tranche_2_active else None
                        audit.tranche_2_stop_loss = Decimal(str(tranche_2_sl)) if tranche_2_active else None
                        audit.ratchet_stage = ratchet_stage

                        # ─── EXECUTION RULE 1: TARGET 2 ACHIEVED ────────────────────────
                        if has_t2 and tranche_2_active and high_p >= t2_val and audit.status == "IN_PROGRESS":
                            # Exit both tranches at Target 2
                            exit_price_val = max(open_p, t2_val) if open_p > 0 else t2_val
                            t1_gain = ((exit_price_val - buy_val) / buy_val) * 100 if buy_val > 0 else 0.0
                            t2_gain = ((exit_price_val - tranche_2_buy) / tranche_2_buy) * 100 if tranche_2_buy > 0 else 0.0
                            
                            # 50/50 capital allocation between tranches
                            combined_pnl_rs = round(((t1_gain / 100.0) * (capital_val * 0.5)) + ((t2_gain / 100.0) * (capital_val * 0.5)), 2)
                            combined_gain_pct = round((combined_pnl_rs / capital_val) * 100.0, 2)

                            audit.status = "TARGET_2_ACHIEVED"
                            audit.ratchet_stage = "TARGET_2_ACHIEVED"
                            audit.exit_date = candle_date
                            audit.exit_price = Decimal(str(round(exit_price_val, 2)))
                            audit.exit_day_number = day_num
                            audit.profit_loss_pct = Decimal(str(combined_gain_pct))
                            audit.realized_pnl_rupees = Decimal(str(combined_pnl_rs))
                            audit.notes = f"Target 2 reached on Day {day_num} ({candle_date}). Tranche 1 (+{t1_gain:.1f}%) and Tranche 2 (+{t2_gain:.1f}%) profit booked @ ₹{exit_price_val:.2f}."
                            logger.info(f"[Audit T2 Hit] {audit.symbol} reached Target 2 on Day {day_num} @ ₹{exit_price_val:.2f} (+{combined_gain_pct}%, ₹{combined_pnl_rs})")
                            break

                        # ─── EXECUTION RULE 2: STOP LOSS / PROFIT RATCHET BREACH ───────
                        elif sl_hit and audit.status == "IN_PROGRESS":
                            exit_price_val = min(open_p, current_sl) if open_p > 0 else current_sl

                            if tranche_2_active:
                                # Both tranches exit at ratcheted protective floors
                                t1_gain = ((exit_price_val - buy_val) / buy_val) * 100 if buy_val > 0 else 0.0
                                t2_exit_p = min(open_p, tranche_2_sl) if open_p > 0 else tranche_2_sl
                                t2_gain = ((t2_exit_p - tranche_2_buy) / tranche_2_buy) * 100 if tranche_2_buy > 0 else 0.0

                                combined_pnl_rs = round(((t1_gain / 100.0) * (capital_val * 0.5)) + ((t2_gain / 100.0) * (capital_val * 0.5)), 2)
                                combined_gain_pct = round((combined_pnl_rs / capital_val) * 100.0, 2)

                                audit.status = "STOPPED_IN_PROFIT" if combined_pnl_rs >= 0 else "STOPLOSS_HIT"
                                audit.ratchet_stage = "STOPPED_IN_PROFIT" if combined_pnl_rs >= 0 else "STOPLOSS_HIT"
                                audit.exit_date = candle_date
                                audit.exit_price = Decimal(str(round(exit_price_val, 2)))
                                audit.exit_day_number = day_num
                                audit.profit_loss_pct = Decimal(str(combined_gain_pct))
                                audit.realized_pnl_rupees = Decimal(str(combined_pnl_rs))
                                audit.notes = f"Coupled Ratchet stop triggered on Day {day_num} ({candle_date}). Tranche 1 @ ₹{exit_price_val:.2f} (+{t1_gain:.1f}%), Tranche 2 @ ₹{t2_exit_p:.2f} ({t2_gain:+.1f}%). Net: ₹{combined_pnl_rs:+,.2f}."
                                logger.info(f"[Audit Ratchet Exit] {audit.symbol} exited in profit on Day {day_num} @ ₹{exit_price_val:.2f} (Net: +{combined_gain_pct}%, ₹{combined_pnl_rs})")
                            else:
                                # Normal initial stoploss breach before Target 1
                                loss_pct = round(((exit_price_val - buy_val) / buy_val) * 100, 2) if buy_val > 0 else 0.0
                                pnl_val = round((loss_pct / 100.0) * capital_val, 2)

                                audit.status = "STOPLOSS_HIT"
                                audit.ratchet_stage = "STOPLOSS_HIT"
                                audit.exit_date = candle_date
                                audit.exit_price = Decimal(str(round(exit_price_val, 2)))
                                audit.exit_day_number = day_num
                                audit.profit_loss_pct = Decimal(str(loss_pct))
                                audit.realized_pnl_rupees = Decimal(str(pnl_val))
                                audit.notes = f"Stop Loss breached on Day {day_num} ({candle_date}). Sold at ₹{exit_price_val:.2f}."
                                logger.info(f"[Audit SL Executed] {audit.symbol} stopped out on Day {day_num} @ ₹{exit_price_val:.2f} ({loss_pct}%)")
                            break

                        # ─── EXECUTION RULE 3: SINGLE-TARGET WIN (NO T2 CONFIGURED) ─────
                        elif (not has_t2) and high_p >= t1_val and audit.status == "IN_PROGRESS":
                            exit_price_val = max(open_p, t1_val) if open_p > 0 else t1_val
                            gain_pct = round(((exit_price_val - buy_val) / buy_val) * 100, 2) if buy_val > 0 else 0.0
                            pnl_val = round((gain_pct / 100.0) * capital_val, 2)

                            audit.status = "TARGET_ACHIEVED"
                            audit.ratchet_stage = "TARGET_1_LOCKED"
                            audit.exit_date = candle_date
                            audit.exit_price = Decimal(str(round(exit_price_val, 2)))
                            audit.exit_day_number = day_num
                            audit.profit_loss_pct = Decimal(str(gain_pct))
                            audit.realized_pnl_rupees = Decimal(str(pnl_val))
                            audit.notes = f"Target achieved on Day {day_num} ({candle_date}). Profit booked at ₹{exit_price_val:.2f}."
                            logger.info(f"[Audit Target Hit] {audit.symbol} reached target on Day {day_num} @ ₹{exit_price_val:.2f} (+{gain_pct}%)")
                            break

                        # ─── EXECUTION RULE 4: 11-DAY TIME HORIZON EXIT ─────────────────
                        elif day_num == 11 and audit.status == "IN_PROGRESS":
                            exit_price_val = close_p
                            if tranche_2_active:
                                t1_gain = ((exit_price_val - buy_val) / buy_val) * 100 if buy_val > 0 else 0.0
                                t2_gain = ((exit_price_val - tranche_2_buy) / tranche_2_buy) * 100 if tranche_2_buy > 0 else 0.0
                                combined_pnl_rs = round(((t1_gain / 100.0) * (capital_val * 0.5)) + ((t2_gain / 100.0) * (capital_val * 0.5)), 2)
                                combined_gain_pct = round((combined_pnl_rs / capital_val) * 100.0, 2)

                                audit.status = "DAY_11_EXIT"
                                audit.ratchet_stage = "DAY_11_EXIT"
                                audit.exit_date = candle_date
                                audit.exit_price = Decimal(str(round(exit_price_val, 2)))
                                audit.exit_day_number = 11
                                audit.profit_loss_pct = Decimal(str(combined_gain_pct))
                                audit.realized_pnl_rupees = Decimal(str(combined_pnl_rs))
                                audit.notes = f"11-Day horizon completed on {candle_date}. Position closed at CMP ₹{exit_price_val:.2f}. Net: ₹{combined_pnl_rs:+,.2f}."
                            else:
                                pnl_pct = round(((exit_price_val - buy_val) / buy_val) * 100, 2) if buy_val > 0 else 0.0
                                pnl_val = round((pnl_pct / 100.0) * capital_val, 2)

                                audit.status = "DAY_11_EXIT"
                                audit.ratchet_stage = "DAY_11_EXIT"
                                audit.exit_date = candle_date
                                audit.exit_price = Decimal(str(round(exit_price_val, 2)))
                                audit.exit_day_number = 11
                                audit.profit_loss_pct = Decimal(str(pnl_pct))
                                audit.realized_pnl_rupees = Decimal(str(pnl_val))
                                audit.notes = f"11-Day horizon completed on {candle_date}. Position closed at CMP ₹{exit_price_val:.2f}."
                            break

                    updated_count += 1

                except Exception as e:
                    logger.warning(f"Error updating audit prices for {audit.symbol}: {e}")

            # Recalculate cycle summary statistics defensively
            total_trades = len(audits)
            win_trades = 0
            loss_trades = 0
            total_gain_loss = 0.0
            total_pnl = 0.0

            for a in audits:
                pnl_pct = float(a.profit_loss_pct or 0.0)
                pnl_rs = float(a.realized_pnl_rupees or 0.0)
                if a.status in ("TARGET_ACHIEVED", "TARGET_2_ACHIEVED", "STOPPED_IN_PROFIT") or (a.status == "DAY_11_EXIT" and pnl_pct > 0):
                    win_trades += 1
                elif a.status == "STOPLOSS_HIT" or (a.status == "DAY_11_EXIT" and pnl_pct < 0):
                    loss_trades += 1
                total_gain_loss += pnl_pct
                total_pnl += pnl_rs

            closed_trades = win_trades + loss_trades
            win_rate = round((win_trades / closed_trades) * 100, 2) if closed_trades > 0 else 0.0

            cycle.total_trades = total_trades
            cycle.win_trades = win_trades
            cycle.loss_trades = loss_trades
            cycle.win_rate = Decimal(str(win_rate))
            cycle.total_gain_loss_pct = Decimal(str(round(total_gain_loss, 2)))
            cycle.total_pnl_rupees = Decimal(str(round(total_pnl, 2)))

            try:
                await db.commit()
                await db.refresh(cycle)
            except Exception as commit_err:
                logger.warning(f"Database commit warning during audit cycle update: {commit_err}")
                await db.rollback()

            # Generate & save the updated Excel spreadsheet file safely
            excel_path = None
            try:
                excel_path = await SwingAuditService.generate_excel_workbook(db, cycle.id)
                if excel_path:
                    cycle.excel_file_path = str(excel_path)
                    await db.commit()
            except Exception as xl_err:
                logger.error(f"Excel generation warning during audit sync: {xl_err}", exc_info=True)

            return {
                "status": "success",
                "cycle_id": str(cycle.id),
                "cycle_number": cycle.cycle_number,
                "total_trades": total_trades,
                "win_trades": win_trades,
                "loss_trades": loss_trades,
                "win_rate": float(win_rate),
                "total_gain_loss_pct": round(total_gain_loss, 2),
                "total_pnl_rupees": round(total_pnl, 2),
                "updated_count": updated_count,
                "excel_file_path": str(excel_path) if excel_path else cycle.excel_file_path
            }
        except Exception as exc:
            logger.error(f"Top-level failure in update_daily_prices: {exc}", exc_info=True)
            return {
                "status": "partial_success",
                "message": f"Price update completed with warning: {str(exc)}",
                "updated_count": 0,
                "win_rate": 0.0,
                "total_pnl_rupees": 0.0
            }

    @staticmethod
    async def generate_excel_workbook(db: AsyncSession, cycle_id: uuid.UUID) -> Optional[Path]:
        """
        Creates or updates an institutional-grade multi-sheet Excel file (.xlsx)
        with conditional formatting, custom colors, formulas, and auto-adjusted widths.
        """
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter

            await ensure_swing_audit_schema(db)

            # Fetch cycle and audits with daily prices
            stmt = (
                select(SwingTradeAuditCycle)
                .where(SwingTradeAuditCycle.id == cycle_id)
                .options(
                    selectinload(SwingTradeAuditCycle.audits).selectinload(SwingTradeAudit.daily_prices)
                )
            )
            cycle = (await db.execute(stmt)).scalars().first()
            if not cycle:
                return None

            audits = sorted(
                cycle.audits or [],
                key=lambda a: (
                    safe_date_sort_key(getattr(a, "recommendation_date", None)),
                    str(getattr(a, "symbol", "") or "")
                )
            )

            wb = openpyxl.Workbook()
        
            # ─── SHEET 1: AUDIT SCORECARD & EXECUTIVE SUMMARY ─────────────────────
            ws_summary = wb.active
            ws_summary.title = "Audit Scorecard"
            ws_summary.views.sheetView[0].showGridLines = True

            # Styles
            navy_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
            card_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
            emerald_fill = PatternFill(start_color="065F46", end_color="065F46", fill_type="solid")
            rose_fill = PatternFill(start_color="881337", end_color="881337", fill_type="solid")
            amber_fill = PatternFill(start_color="78350F", end_color="78350F", fill_type="solid")

            header_font = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
            sub_font = Font(name="Calibri", size=10, italic=True, color="94A3B8")
            card_title_font = Font(name="Calibri", size=10, color="94A3B8")
            card_val_font = Font(name="Calibri", size=18, bold=True, color="FFFFFF")

            thin_border = Border(
                left=Side(style='thin', color='334155'),
                right=Side(style='thin', color='334155'),
                top=Side(style='thin', color='334155'),
                bottom=Side(style='thin', color='334155')
            )

            # Title Block
            ws_summary.merge_cells("A1:H2")
            title_cell = ws_summary["A1"]
            title_cell.value = "STOCKAI — 11-DAY SWING TRADE AUDIT & PERFORMANCE SCORECARD"
            title_cell.font = header_font
            title_cell.fill = navy_fill
            title_cell.alignment = Alignment(horizontal="center", vertical="center")

            ws_summary.merge_cells("A3:H3")
            sub_cell = ws_summary["A3"]
            from_dt_str = cycle.from_date.strftime('%d %b %Y') if hasattr(cycle.from_date, 'strftime') else str(cycle.from_date)
            to_dt_str = cycle.to_date.strftime('%d %b %Y') if hasattr(cycle.to_date, 'strftime') else str(cycle.to_date)
            sub_cell.value = f"Audit Cycle #{cycle.cycle_number} | Period: {from_dt_str} to {to_dt_str} | Status: {cycle.status} | Generated: {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}"
            sub_cell.font = sub_font
            sub_cell.fill = navy_fill
            sub_cell.alignment = Alignment(horizontal="center", vertical="center")

            # KPI Metrics Grid
            c_win_rate = float(cycle.win_rate or 0.0)
            c_ret = float(cycle.total_gain_loss_pct or 0.0)
            c_pnl = float(cycle.total_pnl_rupees or 0.0)

            t2_expansions = sum(1 for a in audits if a.tranche_2_active)
            stopped_in_profit_count = sum(1 for a in audits if a.status in ("STOPPED_IN_PROFIT", "TARGET_2_ACHIEVED"))

            kpi_metrics = [
                ("Total Recommendations", str(cycle.total_trades or 0), card_fill),
                ("Target Hits (Wins)", str(cycle.win_trades or 0), emerald_fill),
                ("Stop Loss Hits (Losses)", str(cycle.loss_trades or 0), rose_fill),
                ("Win Rate", f"{c_win_rate:.1f}%", emerald_fill if c_win_rate >= 50 else amber_fill),
                ("Total Cycle Return", f"{c_ret:+.2f}%", emerald_fill if c_ret >= 0 else rose_fill),
                ("Realized Net P&L", f"₹{c_pnl:+,.2f}", emerald_fill if c_pnl >= 0 else rose_fill),
                ("T2 Pyramiding Expansions", str(t2_expansions), emerald_fill if t2_expansions > 0 else card_fill),
                ("Coupled Ratchet Wins", str(stopped_in_profit_count), emerald_fill if stopped_in_profit_count > 0 else card_fill),
                ("Zero-Loss Protection Rate", f"{(stopped_in_profit_count / max(1, t2_expansions) * 100):.1f}%" if t2_expansions > 0 else "100.0%", emerald_fill),
            ]

            row = 5
            for idx, (label, val, fill) in enumerate(kpi_metrics):
                c_start = (idx % 3) * 3 + 1
                c_end = c_start + 2
                r_start = row + (idx // 3) * 4

                # Label Row
                ws_summary.merge_cells(start_row=r_start, start_column=c_start, end_row=r_start, end_column=c_end)
                l_cell = ws_summary.cell(row=r_start, column=c_start, value=label)
                l_cell.font = card_title_font
                l_cell.fill = fill
                l_cell.alignment = Alignment(horizontal="center", vertical="center")

                # Value Row
                ws_summary.merge_cells(start_row=r_start + 1, start_column=c_start, end_row=r_start + 2, end_column=c_end)
                v_cell = ws_summary.cell(row=r_start + 1, column=c_start, value=val)
                v_cell.font = card_val_font
                v_cell.fill = fill
                v_cell.alignment = Alignment(horizontal="center", vertical="center")

            # ─── SHEET 2: 11-DAY PRICE TRACKING LEDGER ────────────────────────────
            ws_ledger = wb.create_sheet(title="11-Day Price Tracking")
            ws_ledger.views.sheetView[0].showGridLines = True

            headers = [
                "Rec #",
                "Symbol",
                "Company Name",
                "Date Recommended",
                "Buy Price (₹)",
                "User Bought",
                "User Buy Price (₹)",
                "Target Price (₹)",
                "Stop Loss (₹)",
                "R:R",
                "Day 1 Price",
                "Day 2 Price",
                "Day 3 Price",
                "Day 4 Price",
                "Day 5 Price",
                "Day 6 Price (Check)",
                "Day 7 Price",
                "Day 8 Price",
                "Day 9 Price",
                "Day 10 Price",
                "Day 11 Price (Check)",
                "Dynamic Trailing SL (₹)",
                "Tranche 2 Buy (₹)",
                "Tranche 2 SL (₹)",
                "Ratchet Milestone",
                "Audit Status",
                "Exit Date",
                "Exit Price (₹)",
                "Gain / Loss %",
                "Realized P&L (₹)",
                "Holding Days"
            ]

            ws_ledger.row_dimensions[1].height = 28
            th_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
            th_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

            for col_idx, h_text in enumerate(headers, 1):
                cell = ws_ledger.cell(row=1, column=col_idx, value=h_text)
                cell.font = th_font
                cell.fill = th_fill
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = thin_border

            # Row color fills
            green_row_fill = PatternFill(start_color="F0FDF4", end_color="F0FDF4", fill_type="solid")  # Emerald 50
            red_row_fill = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid")    # Rose 50
            blue_row_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")   # Slate 50

            status_colors = {
                "TARGET_ACHIEVED": Font(name="Calibri", size=10, bold=True, color="166534"),
                "TARGET_1_ACHIEVED": Font(name="Calibri", size=10, bold=True, color="166534"),
                "TARGET_2_ACHIEVED": Font(name="Calibri", size=10, bold=True, color="047857"),
                "TARGET_3_ACHIEVED": Font(name="Calibri", size=10, bold=True, color="047857"),
                "STOPPED_IN_PROFIT": Font(name="Calibri", size=10, bold=True, color="0D9488"),
                "STOPLOSS_HIT": Font(name="Calibri", size=10, bold=True, color="991B1B"),
                "DAY_11_EXIT": Font(name="Calibri", size=10, bold=True, color="1E40AF"),
                "IN_PROGRESS": Font(name="Calibri", size=10, bold=True, color="854D0E"),
                "CLOSED": Font(name="Calibri", size=10, bold=True, color="1E40AF"),
                "EXITED": Font(name="Calibri", size=10, bold=True, color="1E40AF"),
                "COMPLETED": Font(name="Calibri", size=10, bold=True, color="1E40AF"),
                "MANUAL_EXIT": Font(name="Calibri", size=10, bold=True, color="1E40AF"),
                "SQUARED_OFF": Font(name="Calibri", size=10, bold=True, color="1E40AF"),
            }

            for r_idx, audit in enumerate(audits, 2):
                ws_ledger.row_dimensions[r_idx].height = 20

                # Map daily prices by day_number
                dp_map = {dp.day_number: dp for dp in audit.daily_prices}

                # Choose row fill based on status
                if audit.status in ("TARGET_ACHIEVED", "TARGET_1_ACHIEVED", "TARGET_2_ACHIEVED", "TARGET_3_ACHIEVED", "STOPPED_IN_PROFIT") or (float(audit.profit_loss_pct or 0.0) > 0 and audit.status != "IN_PROGRESS"):
                    r_fill = green_row_fill
                elif audit.status == "STOPLOSS_HIT" or (float(audit.profit_loss_pct or 0.0) < 0 and audit.status != "IN_PROGRESS"):
                    r_fill = red_row_fill
                else:
                    r_fill = blue_row_fill

                holding_days = f"{audit.exit_day_number} Days" if audit.exit_day_number else f"{len(audit.daily_prices)} Days (Active)"

                rec_dt_str = audit.recommendation_date.strftime("%d-%m-%Y") if hasattr(audit.recommendation_date, 'strftime') else str(audit.recommendation_date)

                a_pnl_pct = float(audit.profit_loss_pct or 0.0)
                a_pnl_rs = float(audit.realized_pnl_rupees or 0.0)

                dyn_sl = float(audit.dynamic_stop_loss or audit.stop_loss or 0.0)
                t2_buy_str = f"₹{float(audit.tranche_2_buy_price):.2f}" if (audit.tranche_2_active and audit.tranche_2_buy_price) else "—"
                t2_sl_str = f"₹{float(audit.tranche_2_stop_loss):.2f}" if (audit.tranche_2_active and audit.tranche_2_stop_loss) else "—"
                ratchet_milestone = (audit.ratchet_stage or "INITIAL").replace("_", " ")

                row_data = [
                    f"SW-{cycle.cycle_number:02d}-{r_idx - 1:03d}",
                    audit.symbol.replace(".NS", ""),
                    audit.company_name or audit.symbol,
                    rec_dt_str,
                    float(audit.buy_price or 0.0),
                    "YES" if audit.user_bought else "NO",
                    float(audit.user_buy_price) if audit.user_buy_price is not None else "—",
                    float(audit.target_price or 0.0),
                    float(audit.stop_loss or 0.0),
                    float(audit.reward_to_risk or 0.0),
                ]

                # Day 1..11 columns
                for d in range(1, 12):
                    if d in dp_map:
                        p = dp_map[d]
                        c_price = float(p.close_price or 0.0)
                        pct = float(p.change_pct_from_buy or 0.0)
                        row_data.append(f"₹{c_price:.2f} ({pct:+.1f}%)")
                    else:
                        if audit.exit_day_number and d > audit.exit_day_number:
                            row_data.append("— (Exited)")
                        else:
                            row_data.append("Pending")

                exit_dt_str = audit.exit_date.strftime("%d-%m-%Y") if (audit.exit_date and hasattr(audit.exit_date, 'strftime')) else (str(audit.exit_date) if audit.exit_date else "—")
                exit_p_val = float(audit.exit_price) if audit.exit_price is not None else "—"

                # Dynamic Ratchet and Outcome columns (22 to 31)
                row_data.extend([
                    dyn_sl,
                    t2_buy_str,
                    t2_sl_str,
                    ratchet_milestone,
                    (audit.status or "").replace("_", " "),
                    exit_dt_str,
                    exit_p_val,
                    f"{a_pnl_pct:+.2f}%" if audit.status != "IN_PROGRESS" else "—",
                    a_pnl_rs if audit.status != "IN_PROGRESS" else 0.0,
                    holding_days
                ])

                for c_idx, val in enumerate(row_data, 1):
                    cell = ws_ledger.cell(row=r_idx, column=c_idx, value=val)
                    cell.fill = r_fill
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical="center", horizontal="center" if c_idx in (1, 4, 6, 10, 25, 26, 27, 31) else "right" if c_idx in (5, 7, 8, 9, 22, 28, 29, 30) else "left")

                    # Highlight user bought status
                    if c_idx == 6:
                        cell.font = Font(name="Calibri", size=10, bold=True, color="166534" if audit.user_bought else "64748B")
                    elif c_idx == 7 and audit.user_buy_price is not None:
                        cell.number_format = '₹#,##0.00'
                    elif c_idx == 22:
                        cell.number_format = '₹#,##0.00'
                    elif c_idx == 26: # Audit Status
                        cell.font = status_colors.get(audit.status, Font(name="Calibri", size=10, bold=True))
                    elif c_idx == 29: # Gain/Loss %
                        cell.font = Font(name="Calibri", size=10, bold=True, color="166534" if a_pnl_pct >= 0 else "991B1B")
                    elif c_idx == 30: # Realized PnL ₹
                        cell.number_format = '₹#,##0.00;[Red]-₹#,##0.00'

            # Total summary row in Ledger
            if audits:
                sum_row = len(audits) + 2
                ws_ledger.row_dimensions[sum_row].height = 24
                ws_ledger.merge_cells(start_row=sum_row, start_column=1, end_row=sum_row, end_column=28)
                lbl = ws_ledger.cell(row=sum_row, column=1, value="TOTAL 11-DAY CYCLE GAIN / REALIZED PROFIT:")
                lbl.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
                lbl.fill = navy_fill
                lbl.alignment = Alignment(horizontal="right", vertical="center")

                # Apply fill across merged range
                for col_c in range(1, 29):
                    ws_ledger.cell(row=sum_row, column=col_c).fill = navy_fill
                    ws_ledger.cell(row=sum_row, column=col_c).border = thin_border

                # Total Gain/Loss % formula or direct value
                sum_pct_cell = ws_ledger.cell(row=sum_row, column=29, value=f"{c_ret:+.2f}%")
                sum_pct_cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
                sum_pct_cell.fill = emerald_fill if c_ret >= 0 else rose_fill
                sum_pct_cell.alignment = Alignment(horizontal="right", vertical="center")
                sum_pct_cell.border = thin_border

                # Total Realized PnL ₹ formula or value
                sum_pnl_cell = ws_ledger.cell(row=sum_row, column=30, value=c_pnl)
                sum_pnl_cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
                sum_pnl_cell.fill = emerald_fill if c_pnl >= 0 else rose_fill
                sum_pnl_cell.alignment = Alignment(horizontal="right", vertical="center")
                sum_pnl_cell.number_format = '₹#,##0.00;[Red]-₹#,##0.00'
                sum_pnl_cell.border = thin_border

                ws_ledger.cell(row=sum_row, column=31).fill = navy_fill
                ws_ledger.cell(row=sum_row, column=31).border = thin_border

            # Auto-adjust column widths
            for col in ws_ledger.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val_str = str(cell.value or '')
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                ws_ledger.column_dimensions[col_letter].width = max(max_len + 3, 12)

            # ─── SHEET 3: CLOSED & BOOKED TRADES JOURNAL ──────────────────────────
            ws_closed = wb.create_sheet(title="Booked Trades")
            ws_closed.views.sheetView[0].showGridLines = True

            closed_headers = ["Trade #", "Symbol", "Company", "Entry Date", "Rec Price (₹)", "User Bought", "Buy Price (₹)", "Exit Date", "Exit (₹)", "Holding Days", "Outcome", "Gain / Loss %", "Realized P&L (₹)"]
            for c_idx, h in enumerate(closed_headers, 1):
                cell = ws_closed.cell(row=1, column=c_idx, value=h)
                cell.font = th_font
                cell.fill = th_fill
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = thin_border

            closed_audits = [a for a in audits if is_closed_audit(a)]
            closed_audits = sorted(
                closed_audits,
                key=lambda a: (
                    safe_date_sort_key(getattr(a, "exit_date", None)),
                    safe_date_sort_key(getattr(a, "recommendation_date", None)),
                    str(getattr(a, "symbol", "") or "")
                )
            )
            for r_i, c_trade in enumerate(closed_audits, 2):
                c_pnl_pct = float(c_trade.profit_loss_pct or 0.0)
                c_pnl_rs = float(c_trade.realized_pnl_rupees or 0.0)
                is_win = c_pnl_pct >= 0
                row_f = green_row_fill if is_win else red_row_fill

                c_rec_dt_str = c_trade.recommendation_date.strftime("%d-%m-%Y") if hasattr(c_trade.recommendation_date, 'strftime') else str(c_trade.recommendation_date)
                c_exit_dt_str = c_trade.exit_date.strftime("%d-%m-%Y") if (c_trade.exit_date and hasattr(c_trade.exit_date, 'strftime')) else (str(c_trade.exit_date) if c_trade.exit_date else "—")
                c_exit_p = float(c_trade.exit_price) if c_trade.exit_price is not None else "—"

                c_vals = [
                    f"SW-{cycle.cycle_number:02d}-{r_i - 1:03d}",
                    c_trade.symbol.replace(".NS", ""),
                    c_trade.company_name or c_trade.symbol,
                    c_rec_dt_str,
                    float(c_trade.buy_price or 0.0),
                    "YES" if c_trade.user_bought else "NO",
                    float(c_trade.user_buy_price) if c_trade.user_bought and c_trade.user_buy_price is not None else float(c_trade.buy_price or 0.0),
                    c_exit_dt_str,
                    c_exit_p,
                    f"{c_trade.exit_day_number} Days" if c_trade.exit_day_number else "—",
                    (c_trade.status or "").replace("_", " "),
                    f"{c_pnl_pct:+.2f}%",
                    c_pnl_rs
                ]
                for c_i, v in enumerate(c_vals, 1):
                    cell = ws_closed.cell(row=r_i, column=c_i, value=v)
                    cell.fill = row_f
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical="center", horizontal="center" if c_i in (1, 4, 6, 8, 10, 11) else "right" if c_i in (5, 7, 9, 12, 13) else "left")
                    if c_i == 6:
                        cell.font = Font(name="Calibri", size=10, bold=True, color="166534" if c_trade.user_bought else "64748B")
                    elif c_i in (5, 7, 9):
                        if isinstance(v, (int, float)):
                            cell.number_format = '₹#,##0.00'
                    elif c_i == 13:
                        cell.number_format = '₹#,##0.00;[Red]-₹#,##0.00'

            for col in ws_closed.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = get_column_letter(col[0].column)
                ws_closed.column_dimensions[col_letter].width = max(max_len + 3, 12)

            # Save workbook to destination path
            audit_dir = get_audit_dir()
            filename = (
                Path(cycle.excel_file_path).name 
                if cycle.excel_file_path 
                else f"Swing_Trade_Audit_{cycle.from_date}_to_{cycle.to_date}.xlsx"
            )
            target_path = audit_dir / filename
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                wb.save(target_path)
            except Exception as save_err:
                logger.warning(f"Could not save directly to {target_path} ({save_err}). Attempting temporary directory fallback.")
                import tempfile
                fallback_tmp = Path(tempfile.gettempdir()) / filename
                wb.save(fallback_tmp)
                target_path = fallback_tmp

            if cycle.excel_file_path != str(target_path):
                cycle.excel_file_path = str(target_path)
                await db.commit()

            logger.info(f"Generated institutional Swing Audit Excel workbook: {target_path}")
            return target_path
        except ImportError:
            logger.error("openpyxl is not installed. Skipping Excel generation.")
            return None
        except Exception as exc:
            logger.error(f"Failed to generate Excel workbook for cycle {cycle_id}: {exc}", exc_info=True)
            return None

    @staticmethod
    async def get_cycle_summary(db: AsyncSession, cycle_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        """Returns JSON representation of active or specified audit cycle for dashboard API."""
        try:
            await ensure_swing_audit_schema(db)
            if cycle_id:
                stmt = (
                    select(SwingTradeAuditCycle)
                    .where(SwingTradeAuditCycle.id == cycle_id)
                    .options(
                        selectinload(SwingTradeAuditCycle.audits).selectinload(SwingTradeAudit.daily_prices)
                    )
                )
            else:
                stmt = (
                    select(SwingTradeAuditCycle)
                    .where(SwingTradeAuditCycle.status == "ACTIVE")
                    .order_by(SwingTradeAuditCycle.cycle_number.desc())
                    .options(
                        selectinload(SwingTradeAuditCycle.audits).selectinload(SwingTradeAudit.daily_prices)
                    )
                )

            cycle = (await db.execute(stmt)).scalars().first()
            if not cycle:
                cycle = await SwingAuditService.get_or_create_active_cycle(db)

            if not cycle:
                return {"cycle": None, "trades": []}

            trades_list = []
            for a in (cycle.audits or []):
                rec_dt = a.recommendation_date
                rec_dt_str = rec_dt.isoformat() if hasattr(rec_dt, "isoformat") else str(rec_dt)

                trades_list.append({
                    "id": str(a.id),
                    "symbol": a.symbol,
                    "company_name": a.company_name or a.symbol,
                    "recommendation_date": rec_dt_str,
                    "buy_price": float(a.buy_price or 0.0),
                    "user_bought": bool(a.user_bought),
                    "user_buy_price": float(a.user_buy_price) if a.user_buy_price is not None else None,
                    "user_buy_time": a.user_buy_time.isoformat() if a.user_buy_time and hasattr(a.user_buy_time, "isoformat") else (str(a.user_buy_time) if a.user_buy_time else None),
                    "target_price": float(a.target_price or 0.0),
                    "stop_loss": float(a.stop_loss or 0.0),
                    "target_1": float(a.target_1) if a.target_1 is not None else float(a.target_price or 0.0),
                    "target_2": float(a.target_2) if a.target_2 is not None else None,
                    "dynamic_stop_loss": float(a.dynamic_stop_loss) if a.dynamic_stop_loss is not None else float(a.stop_loss or 0.0),
                    "tranche_2_active": bool(a.tranche_2_active),
                    "tranche_2_buy_price": float(a.tranche_2_buy_price) if a.tranche_2_buy_price is not None else None,
                    "tranche_2_stop_loss": float(a.tranche_2_stop_loss) if a.tranche_2_stop_loss is not None else None,
                    "ratchet_stage": a.ratchet_stage or "INITIAL",
                    "reward_to_risk": float(a.reward_to_risk or 0.0),
                    "total_score": float(a.total_score) if a.total_score is not None else None,
                    "status": a.status or "IN_PROGRESS",
                    "exit_date": a.exit_date.isoformat() if a.exit_date and hasattr(a.exit_date, "isoformat") else (str(a.exit_date) if a.exit_date else None),
                    "exit_price": float(a.exit_price) if a.exit_price is not None else None,
                    "exit_day_number": a.exit_day_number,
                    "profit_loss_pct": float(a.profit_loss_pct or 0.0),
                    "realized_pnl_rupees": float(a.realized_pnl_rupees or 0.0),
                    "days_tracked": len(a.daily_prices) if hasattr(a, "daily_prices") and a.daily_prices else 0
                })

            from_dt_str = cycle.from_date.isoformat() if hasattr(cycle.from_date, "isoformat") else str(cycle.from_date)
            to_dt_str = cycle.to_date.isoformat() if hasattr(cycle.to_date, "isoformat") else str(cycle.to_date)

            return {
                "cycle": {
                    "id": str(cycle.id),
                    "cycle_number": cycle.cycle_number,
                    "from_date": from_dt_str,
                    "to_date": to_dt_str,
                    "status": cycle.status or "ACTIVE",
                    "total_trades": cycle.total_trades or 0,
                    "win_trades": cycle.win_trades or 0,
                    "loss_trades": cycle.loss_trades or 0,
                    "win_rate": float(cycle.win_rate or 0.0),
                    "total_gain_loss_pct": float(cycle.total_gain_loss_pct or 0.0),
                    "total_pnl_rupees": float(cycle.total_pnl_rupees or 0.0),
                    "excel_file_path": cycle.excel_file_path
                },
                "trades": trades_list
            }
        except Exception as exc:
            logger.error(f"Error getting cycle summary: {exc}", exc_info=True)
            return {"cycle": None, "trades": []}


swing_audit_service = SwingAuditService()
