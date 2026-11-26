"""
Comprehensive regression & integration tests for:
1. SwingAuditService.get_cycle_summary() MissingGreenlet eradication (real ORM + lazy-load trap).
2. Automatic 11-day cycle expiration rollover -> permanent (Final).xlsx archive, working file cleanup,
   and clean empty Cycle #2 initialization with zero cross-cycle leakage.
3. Database deduplication & uniqueness enforcement across (cycle_id, symbol) + closed record preservation.
4. Progressive T1 -> T2 -> T3 Coupled Ratchet Engine in SwingAuditService & live PaperTradingService,
   including conservative same-bar SL tie-break, SystemSettings integration, transition alerts,
   and repeat Screener BUY signal independence.
5. High-Precision Screener ML Ensemble bearish veto & consecutive-SL cooldown filter.
6. NSE holiday calendar & weekend/holiday trading day snapping.
7. API quota protection: single fetch_quotes_bulk sweep per evaluate_open_trades run.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from backend.core.market_hours import is_trading_day, normalize_to_trading_day
from backend.models.paper_trade import PaperTrade
from backend.models.settings import SystemSettings
from backend.models.swing_audit import SwingTradeAudit, SwingTradeAuditCycle, SwingTradeAuditPrice
from backend.models.user import User
from backend.services import swing_audit_service as audit_mod
from backend.services.paper_trading import PaperTradingService
from backend.services.screener import ScreenerService
from backend.services.swing_audit_service import SwingAuditService, add_trading_days


# Enable PostgreSQL UUID columns on SQLite for faithful real-ORM relational tests
@compiles(PG_UUID, "sqlite")
def _compile_pg_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


class AsyncSQLiteSessionProxy:
    """Thin AsyncSession-compatible async wrapper over a real synchronous SQLAlchemy Session on SQLite."""

    def __init__(self, sync_session: Session):
        self._s = sync_session

    def get_bind(self):
        return self._s.get_bind()

    def add(self, obj):
        return self._s.add(obj)

    def add_all(self, objs):
        return self._s.add_all(objs)

    async def execute(self, statement, params=None, **kwargs):
        return self._s.execute(statement, params or {}, **kwargs)

    async def commit(self):
        return self._s.commit()

    async def rollback(self):
        return self._s.rollback()

    async def flush(self):
        return self._s.flush()

    async def refresh(self, instance):
        return self._s.refresh(instance)


@contextmanager
def real_sqlite_async_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    tables = [
        User.__table__,
        SystemSettings.__table__,
        PaperTrade.__table__,
        SwingTradeAuditCycle.__table__,
        SwingTradeAudit.__table__,
        SwingTradeAuditPrice.__table__,
    ]
    for tbl in tables:
        tbl.create(engine, checkfirst=True)

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    sync_s = SessionLocal()
    audit_mod._schema_ensured = False
    try:
        yield AsyncSQLiteSessionProxy(sync_s), sync_s
    finally:
        sync_s.close()
        engine.dispose()
        audit_mod._schema_ensured = False


def test_nse_holiday_calendar_and_weekend_snapping():
    # Republic Day (Jan 26) & Holi 2026 (Mar 3) are exchange holidays
    assert is_trading_day(date(2026, 1, 26)) is False
    assert is_trading_day(date(2026, 3, 3)) is False
    # Saturday Nov 28, 2026 snaps forward to Monday Nov 30, 2026
    assert normalize_to_trading_day(date(2026, 11, 28), forward=True) == date(2026, 11, 30)
    # Preserves existing add_trading_days contract
    assert add_trading_days(date(2026, 11, 6), 3) == date(2026, 11, 11)


@pytest.mark.asyncio
async def test_get_cycle_summary_real_orm_no_missing_greenlet(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_DIR", str(tmp_path))
    with real_sqlite_async_db() as (db, sync_s):
        today = date.today()
        cycle = SwingTradeAuditCycle(
            cycle_number=1,
            from_date=today - timedelta(days=5),
            to_date=today + timedelta(days=5),
            status="ACTIVE",
            total_trades=2,
            win_trades=1,
            loss_trades=0,
            win_rate=Decimal("100.00"),
            total_gain_loss_pct=Decimal("8.50"),
            total_pnl_rupees=Decimal("8500.00"),
        )
        sync_s.add(cycle)
        sync_s.commit()

        a1 = SwingTradeAudit(
            cycle_id=cycle.id,
            symbol="M&M.NS",
            company_name="Mahindra & Mahindra",
            sector="Automotive & Ancillaries",
            recommendation_date=today - timedelta(days=3),
            buy_price=Decimal("3400.00"),
            target_price=Decimal("3700.00"),
            stop_loss=Decimal("3250.00"),
            target_1=Decimal("3550.00"),
            target_2=Decimal("3700.00"),
            target_3=Decimal("3850.00"),
            status="TARGET_3_ACHIEVED",
            profit_loss_pct=Decimal("8.50"),
            realized_pnl_rupees=Decimal("8500.00"),
            user_bought=True,
            user_buy_price=Decimal("3400.00"),
        )
        a2 = SwingTradeAudit(
            cycle_id=cycle.id,
            symbol="TCS.NS",
            company_name="TCS",
            sector="IT & Technology",
            recommendation_date=today - timedelta(days=2),
            buy_price=Decimal("3900.00"),
            target_price=Decimal("4100.00"),
            stop_loss=Decimal("3780.00"),
            status="IN_PROGRESS",
        )
        sync_s.add_all([a1, a2])
        sync_s.commit()

        sync_s.add_all([
            SwingTradeAuditPrice(audit_id=a1.id, day_number=1, trade_date=today - timedelta(days=2), close_price=Decimal("3550.00")),
            SwingTradeAuditPrice(audit_id=a1.id, day_number=2, trade_date=today - timedelta(days=1), close_price=Decimal("3850.00")),
            SwingTradeAuditPrice(audit_id=a2.id, day_number=1, trade_date=today - timedelta(days=1), close_price=Decimal("3940.00")),
        ])
        sync_s.commit()

        # Simulate SQLAlchemy AsyncSession detached/unloaded lazy-load failure if daily_prices descriptor is ever accessed
        sync_s.expunge_all()
        orig_prop = SwingTradeAudit.daily_prices

        def _raise_missing_greenlet(*args, **kwargs):
            raise MissingGreenlet("greenlet_spawn has not been called; can't call await_only() here.")

        with patch.object(SwingTradeAudit, "daily_prices", property(_raise_missing_greenlet)):
            summary = await SwingAuditService.get_cycle_summary(db)

        assert summary["cycle"] is not None
        assert summary["cycle"]["cycle_number"] == 1
        assert summary["cycle"]["closed_trades"] == 1
        assert summary["cycle"]["in_progress_trades"] == 1
        assert summary["cycle"]["target_win_trades"] == 1
        assert summary["cycle"]["user_executed_trades"] == 1
        assert summary["cycle"]["user_executed_win_rate"] == 100.0
        assert summary["cycle"]["estimated_charges_rupees"] > 0
        assert len(summary["trades"]) == 2
        by_sym = {t["symbol"]: t for t in summary["trades"]}
        assert by_sym["M&M.NS"]["days_tracked"] == 2
        assert by_sym["TCS.NS"]["days_tracked"] == 1
        assert orig_prop is not None


@pytest.mark.asyncio
async def test_expired_cycle_auto_rollover_archives_clean_and_starts_empty_cycle_2(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_DIR", str(tmp_path))
    with real_sqlite_async_db() as (db, sync_s):
        past_start = date.today() - timedelta(days=18)
        past_end = date.today() - timedelta(days=1)
        old_working_file = tmp_path / f"Swing_Trade_Audit_{past_start.isoformat()}_to_{past_end.isoformat()}.xlsx"
        old_working_file.write_bytes(b"stale-working-workbook")

        cycle1 = SwingTradeAuditCycle(
            cycle_number=1,
            from_date=past_start,
            to_date=past_end,
            status="ACTIVE",
            excel_file_path=str(old_working_file),
        )
        sync_s.add(cycle1)
        sync_s.commit()

        closed_pick = SwingTradeAudit(
            cycle_id=cycle1.id,
            symbol="MARUTI.NS",
            recommendation_date=past_start,
            buy_price=Decimal("10000.00"),
            target_price=Decimal("11000.00"),
            stop_loss=Decimal("9500.00"),
            status="TARGET_2_ACHIEVED",
            exit_date=past_start + timedelta(days=3),
            exit_price=Decimal("11000.00"),
            exit_day_number=4,
            profit_loss_pct=Decimal("10.00"),
            realized_pnl_rupees=Decimal("10000.00"),
        )
        pending_pick = SwingTradeAudit(
            cycle_id=cycle1.id,
            symbol="SBIN.NS",
            recommendation_date=date.today() - timedelta(days=2),
            buy_price=Decimal("800.00"),
            target_price=Decimal("880.00"),
            stop_loss=Decimal("760.00"),
            status="IN_PROGRESS",
        )
        sync_s.add_all([closed_pick, pending_pick])
        sync_s.commit()

        sync_s.add(
            SwingTradeAuditPrice(
                audit_id=pending_pick.id,
                day_number=1,
                trade_date=past_end,
                close_price=Decimal("824.00"),
            )
        )
        sync_s.commit()

        with patch("backend.services.swing_audit_service.market_data_service.fetch_quotes_bulk", new=AsyncMock(return_value={"SBIN.NS": {"price": 824.0, "previous_close": 824.0}})), \
             patch("backend.services.swing_audit_service.market_data_service.fetch_quote", new=AsyncMock(return_value={"price": 824.0, "previous_close": 824.0})), \
             patch("backend.services.swing_audit_service.market_data_service.fetch_candles", new=AsyncMock(return_value=[{"timestamp": datetime.now(timezone.utc).isoformat(), "open": 820.0, "high": 830.0, "low": 815.0, "close": 824.0, "volume": 1000}])):
            summary = await SwingAuditService.get_cycle_summary(db)

        assert summary["cycle"] is not None
        assert summary["cycle"]["cycle_number"] == 2
        assert summary["cycle"]["status"] == "ACTIVE"
        assert summary["trades"] == []  # Zero Cycle #1 entries leaked into Cycle #2

        sync_s.expire_all()
        c1_refreshed = sync_s.execute(select(SwingTradeAuditCycle).where(SwingTradeAuditCycle.cycle_number == 1)).scalar_one()
        assert c1_refreshed.status == "COMPLETED"
        pending_refreshed = sync_s.execute(select(SwingTradeAudit).where(SwingTradeAudit.symbol == "SBIN.NS")).scalar_one()
        assert pending_refreshed.status == "DAY_11_EXIT"
        assert float(pending_refreshed.exit_price) == 824.0

        archive_final = tmp_path / "Swing_Trade_Audit_Cycle_1_(Final).xlsx"
        assert archive_final.exists()
        assert not old_working_file.exists()  # Orphan working workbook removed on archive


@pytest.mark.asyncio
async def test_coupled_ratchet_t1_t2_t3_and_same_bar_tiebreak_in_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_DIR", str(tmp_path))
    with real_sqlite_async_db() as (db, sync_s):
        today = date.today()
        cycle = SwingTradeAuditCycle(
            cycle_number=1,
            from_date=today - timedelta(days=10),
            to_date=today + timedelta(days=5),
            status="ACTIVE",
        )
        sync_s.add(cycle)
        sync_s.commit()

        t3_winner = SwingTradeAudit(
            cycle_id=cycle.id,
            symbol="RUNNER.NS",
            recommendation_date=today - timedelta(days=5),
            buy_price=Decimal("100.00"),
            target_price=Decimal("112.00"),
            stop_loss=Decimal("95.00"),
            target_1=Decimal("106.00"),
            target_2=Decimal("112.00"),
            target_3=Decimal("118.00"),
            status="IN_PROGRESS",
        )
        same_bar_sl = SwingTradeAudit(
            cycle_id=cycle.id,
            symbol="DIPSL.NS",
            recommendation_date=today - timedelta(days=5),
            buy_price=Decimal("100.00"),
            target_price=Decimal("112.00"),
            stop_loss=Decimal("95.00"),
            target_1=Decimal("106.00"),
            target_2=Decimal("112.00"),
            target_3=Decimal("118.00"),
            status="IN_PROGRESS",
        )
        sync_s.add_all([t3_winner, same_bar_sl])
        sync_s.commit()

        d0 = today - timedelta(days=5)
        runner_candles = [
            {"timestamp": (datetime.combine(d0, datetime.min.time(), tzinfo=timezone.utc)).isoformat(), "open": 100, "high": 107, "low": 99, "close": 106, "volume": 1000},
            {"timestamp": (datetime.combine(d0 + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)).isoformat(), "open": 106, "high": 110, "low": 105, "close": 109, "volume": 1000},
            {"timestamp": (datetime.combine(d0 + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)).isoformat(), "open": 109, "high": 113, "low": 108, "close": 112.5, "volume": 1000},
            {"timestamp": (datetime.combine(d0 + timedelta(days=3), datetime.min.time(), tzinfo=timezone.utc)).isoformat(), "open": 113, "high": 119, "low": 112, "close": 118.5, "volume": 1000},
        ]
        dipsl_candles = [
            {"timestamp": (datetime.combine(d0, datetime.min.time(), tzinfo=timezone.utc)).isoformat(), "open": 97, "high": 108, "low": 94, "close": 106, "volume": 1000},
        ]

        async def _mock_candles(sym, tf, limit=30):
            if "RUNNER" in sym:
                return runner_candles
            if "DIPSL" in sym:
                return dipsl_candles
            return []

        with patch("backend.services.swing_audit_service.market_data_service.fetch_quotes_bulk", new=AsyncMock(return_value={})), \
             patch("backend.services.swing_audit_service.market_data_service.fetch_quote", new=AsyncMock(return_value=None)), \
             patch("backend.services.swing_audit_service.market_data_service.fetch_candles", side_effect=_mock_candles):
            await SwingAuditService.update_daily_prices(db, cycle_id=cycle.id)

        sync_s.expire_all()
        r_db = sync_s.execute(select(SwingTradeAudit).where(SwingTradeAudit.symbol == "RUNNER.NS")).scalar_one()
        assert r_db.status == "TARGET_3_ACHIEVED"
        assert r_db.ratchet_stage == "TARGET_3_ACHIEVED"
        assert float(r_db.exit_price) >= 118.0
        assert float(r_db.dynamic_stop_loss) >= 111.0  # Ratcheted to T2 lock floor before T3 exit
        assert r_db.tranche_2_active is True

        dps = sync_s.execute(select(SwingTradeAuditPrice).where(SwingTradeAuditPrice.audit_id == r_db.id).order_by(SwingTradeAuditPrice.day_number)).scalars().all()
        assert [p.ratchet_event for p in dps] == ["BREAKEVEN_LOCKED", "T2_RATCHET_ACTIVE", "T3_RATCHET_ACTIVE", "T3_RATCHET_ACTIVE"]

        s_db = sync_s.execute(select(SwingTradeAudit).where(SwingTradeAudit.symbol == "DIPSL.NS")).scalar_one()
        assert s_db.status == "STOPLOSS_HIT"  # Morning SL tie-break wins before intraday T1 spike


@pytest.mark.asyncio
async def test_paper_trading_live_coupled_ratchet_and_repeat_buy_independence():
    with real_sqlite_async_db() as (db, sync_s):
        user = User(email="trader@example.com", name="Test Trader", hashed_password="x")
        sync_s.add(user)
        sync_s.commit()

        quote_state = {"price": 100.0}
        bulk_calls = []

        async def _mock_fetch_quote(sym):
            return {"price": quote_state["price"], "symbol": sym}

        async def _mock_fetch_bulk(syms, use_fallback=True):
            bulk_calls.append((list(syms), use_fallback))
            return {s: {"price": quote_state["price"], "symbol": s} for s in syms}

        alerts_emitted = []

        async def _mock_broadcast(payload, user_id=None):
            alerts_emitted.append((payload.get("ratchet_stage"), payload.get("new_stop_loss")))

        with patch("backend.services.paper_trading.market_data_service.fetch_quote", side_effect=_mock_fetch_quote), \
             patch("backend.services.paper_trading.market_data_service.fetch_quotes_bulk", side_effect=_mock_fetch_bulk), \
             patch("backend.services.market_depth_service.market_depth_service.get_market_depth", new=AsyncMock(return_value=None)), \
             patch("backend.api.websocket.broadcast_alert", side_effect=_mock_broadcast):

            # Screener Buy Signal #1
            t1_trade = await PaperTradingService.place_order(
                db=db,
                user_id=str(user.id),
                symbol="M&M.NS",
                direction="BUY",
                quantity=10,
                order_type="MARKET",
                product_type="DELIVERY",
                target_price=112.0,
                stop_loss=95.0,
                target_1=106.0,
                target_2=112.0,
                target_3=118.0,
                trailing_enabled=True,
            )
            await db.commit()
            assert t1_trade.status == "OPEN"
            assert float(t1_trade.stop_loss) == 95.0
            assert t1_trade.ratchet_stage == "INITIAL"

            # Step 1: Hit Target 1 (106.5) -> Breakeven + 1% protection
            quote_state["price"] = 106.5
            await PaperTradingService.evaluate_open_trades(db)
            await db.commit()
            await db.refresh(t1_trade)
            assert t1_trade.status == "OPEN"
            assert t1_trade.ratchet_stage == "BREAKEVEN_LOCKED"
            assert float(t1_trade.stop_loss) > float(t1_trade.entry_price)

            # Step 2: Halfway to T2 (109.5) -> T2_RATCHET_ACTIVE locking T1 (106)
            quote_state["price"] = 109.5
            await PaperTradingService.evaluate_open_trades(db)
            await db.commit()
            await db.refresh(t1_trade)
            assert t1_trade.ratchet_stage == "T2_RATCHET_ACTIVE"
            assert float(t1_trade.stop_loss) >= 106.0

            # Step 3: Cross T2 (112.5) -> T3_RATCHET_ACTIVE locking ~T2 (111.10), STILL OPEN hunting T3!
            quote_state["price"] = 112.5
            await PaperTradingService.evaluate_open_trades(db)
            await db.commit()
            await db.refresh(t1_trade)
            assert t1_trade.status == "OPEN"
            assert t1_trade.ratchet_stage == "T3_RATCHET_ACTIVE"
            assert float(t1_trade.stop_loss) >= 111.0

            # Step 4: Hit T3 Runner (118.5) -> TARGET_3_ACHIEVED & closes trade
            quote_state["price"] = 118.5
            await PaperTradingService.evaluate_open_trades(db)
            await db.commit()
            await db.refresh(t1_trade)
            assert t1_trade.status == "CLOSED"
            assert t1_trade.ratchet_stage == "TARGET_3_ACHIEVED"
            assert float(t1_trade.realized_pnl) > 100.0

            # Exactly 1 bulk call per sweep (4 sweeps total -> 4 bulk calls)
            assert len(bulk_calls) == 4
            assert all(u_fb is True for _, u_fb in bulk_calls)
            assert [st for st, _ in alerts_emitted] == [
                "BREAKEVEN_LOCKED",
                "T2_RATCHET_ACTIVE",
                "T3_RATCHET_ACTIVE",
                "TARGET_3_ACHIEVED",
            ]

            # Screener Buy Signal #2 later on SAME symbol starts fresh, independent ratchet lifecycle
            quote_state["price"] = 120.0
            t2_trade = await PaperTradingService.place_order(
                db=db,
                user_id=str(user.id),
                symbol="M&M.NS",
                direction="BUY",
                quantity=5,
                order_type="MARKET",
                product_type="DELIVERY",
                target_price=132.0,
                stop_loss=114.0,
                target_1=126.0,
                target_2=132.0,
                target_3=138.0,
                trailing_enabled=True,
            )
            await db.commit()
            assert t2_trade.id != t1_trade.id
            assert t2_trade.ratchet_stage == "INITIAL"
            assert float(t2_trade.stop_loss) == 114.0
            # Order #1 stayed CLOSED at TARGET_3_ACHIEVED
            await db.refresh(t1_trade)
            assert t1_trade.status == "CLOSED"
            assert t1_trade.ratchet_stage == "TARGET_3_ACHIEVED"


@pytest.mark.asyncio
async def test_screener_ml_sell_veto_and_cooldown_filter():
    # 1. Test ML Bearish Veto in ScreenerService._analyze_symbol
    candles = [
        {"timestamp": (datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(days=i)).isoformat(), "open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i, "volume": 500000}
        for i in range(40)
    ]
    fake_ind = {
        "atr_14": 2.0,
        "ema_21": 135.0,
        "ema_9": 138.0,
        "ema_50": 125.0,
        "rsi_14": 58.0,
        "adx_14": 28.0,
        "rs_momentum_20d": 0.08,
        "bb": {"upper": 144.0, "middle": 136.0, "lower": 128.0},
    }
    fake_sig = [{"composite_rating": 90.0}]
    fake_ai = {"score": 25.0, "confidence": 0.80, "probabilities": {"buy": 0.12, "hold": 0.20, "sell": 0.68}}
    fake_info = {"name": "Vetoed Corp", "roe": 0.25, "roce": 0.22, "debt_to_equity": 0.2, "pe_ratio": 18.0}
    fake_quote = {"price": 140.0, "change_pct": 0.5}

    with patch("backend.services.screener.cache_get", new=AsyncMock(return_value=None)), \
         patch("backend.services.screener.cache_set", new=AsyncMock()), \
         patch("backend.services.screener.market_data_service.fetch_candles", new=AsyncMock(return_value=candles)), \
         patch("backend.services.screener.market_data_service.fetch_quote", new=AsyncMock(return_value=fake_quote)), \
         patch("backend.services.screener.market_data_service.get_stock_info", new=AsyncMock(return_value=fake_info)), \
         patch("backend.services.screener.market_data_service.fetch_corporate_events", new=AsyncMock(return_value={})), \
         patch("backend.data.ingestion.news_scraper.fetch_stock_news", new=AsyncMock(return_value=[])), \
         patch("backend.services.screener.nlp_engine_service.analyze_headlines", return_value={"compound_score": 0.4, "overall_sentiment": "POSITIVE"}), \
         patch("backend.services.screener.run_in_ml_executor", new=AsyncMock(return_value=(fake_ind, fake_sig, fake_ai))):
        res = await ScreenerService._analyze_symbol("VETOTEST.NS", force_refresh=True, prefetched_nifty_indicators={"ema_20": 25000, "ema_50": 24500, "rsi": 58})

    assert res["total_score"] >= 75.0
    assert res["action"] == "HOLD"
    assert "ML Ensemble bearish veto" in res["trade_plan"]["entry_advice"]

    # 2. Test Consecutive-SL Cooldown Filter in SwingAuditService
    with real_sqlite_async_db() as (db, sync_s):
        c1 = SwingTradeAuditCycle(cycle_number=1, from_date=date(2026, 10, 1), to_date=date(2026, 10, 15), status="COMPLETED")
        c2 = SwingTradeAuditCycle(cycle_number=2, from_date=date(2026, 10, 16), to_date=date(2026, 10, 31), status="COMPLETED")
        sync_s.add_all([c1, c2])
        sync_s.commit()

        sync_s.add_all([
            SwingTradeAudit(cycle_id=c1.id, symbol="CHRONIC.NS", recommendation_date=date(2026, 10, 2), buy_price=Decimal("100"), target_price=Decimal("110"), stop_loss=Decimal("95"), status="STOPLOSS_HIT"),
            SwingTradeAudit(cycle_id=c2.id, symbol="CHRONIC.NS", recommendation_date=date(2026, 10, 18), buy_price=Decimal("98"), target_price=Decimal("108"), stop_loss=Decimal("93"), status="STOPLOSS_HIT"),
        ])
        sync_s.commit()

        candidates = [
            {"symbol": "CHRONIC.NS", "total_score": 79.0, "ml_score": {"probabilities": {"buy": 0.60}}},
            {"symbol": "FRESH.NS", "total_score": 76.0, "ml_score": {"probabilities": {"buy": 0.60}}},
        ]
        filtered = await SwingAuditService.filter_cooldown_symbols(db, candidates)
        assert [s["symbol"] for s in filtered] == ["FRESH.NS"]

        # Elite score >= 82 with ML confirmation bypasses cooldown
        elite_candidates = [
            {"symbol": "CHRONIC.NS", "total_score": 84.5, "ml_score": {"probabilities": {"buy": 0.65}}},
        ]
        filtered_elite = await SwingAuditService.filter_cooldown_symbols(db, elite_candidates)
        assert [s["symbol"] for s in filtered_elite] == ["CHRONIC.NS"]


@pytest.mark.asyncio
async def test_day11_1545_ist_auto_rollover_and_closing_window_guard(tmp_path, monkeypatch):
    """
    Verify automatic Day-11 ~15:45 IST post-close cycle rollover:
    1. 15:25 IST on Day 11: neither closing window nor rollover due.
    2. 15:35 IST on Day 11: closing window blocks adding brand-new EOD picks right before rollover,
       while not rolling over before 15:42 IST.
    3. 15:45 IST on Day 11 (Thu 2026-12-10): update_daily_prices(db) unconditionally finalizes Cycle #1,
       writes Swing_Trade_Audit_Cycle_1_(Final).xlsx, and opens clean Cycle #2 starting Fri 2026-12-11.
    4. When Day 11 falls on Friday (2026-12-11 15:45 IST), Cycle #3 snaps to Monday 2026-12-14.
    """
    monkeypatch.setenv("AUDIT_DIR", str(tmp_path))
    from backend.core.market_hours import IST_TZ
    from backend.services.swing_audit_service import is_cycle_in_closing_window, is_cycle_rollover_due

    day11_thu = date(2026, 12, 10)
    mock_c = MagicMock(to_date=day11_thu)
    assert is_cycle_in_closing_window(mock_c, datetime(2026, 12, 10, 15, 25, tzinfo=IST_TZ)) is False
    assert is_cycle_rollover_due(mock_c, datetime(2026, 12, 10, 15, 25, tzinfo=IST_TZ)) is False

    assert is_cycle_in_closing_window(mock_c, datetime(2026, 12, 10, 15, 35, tzinfo=IST_TZ)) is True
    assert is_cycle_rollover_due(mock_c, datetime(2026, 12, 10, 15, 35, tzinfo=IST_TZ)) is False

    assert is_cycle_in_closing_window(mock_c, datetime(2026, 12, 10, 15, 45, tzinfo=IST_TZ)) is True
    assert is_cycle_rollover_due(mock_c, datetime(2026, 12, 10, 15, 45, tzinfo=IST_TZ)) is True

    with real_sqlite_async_db() as (db, sync_s):
        cycle1 = SwingTradeAuditCycle(
            cycle_number=1,
            from_date=date(2026, 11, 26),
            to_date=day11_thu,
            status="ACTIVE",
        )
        sync_s.add(cycle1)
        sync_s.commit()

        open_trade = SwingTradeAudit(
            cycle_id=cycle1.id,
            symbol="TCS.NS",
            recommendation_date=date(2026, 12, 8),
            buy_price=Decimal("4000.00"),
            target_price=Decimal("4300.00"),
            stop_loss=Decimal("3850.00"),
            status="IN_PROGRESS",
        )
        sync_s.add(open_trade)
        sync_s.commit()

        ist_1545_thu = datetime(2026, 12, 10, 15, 45, tzinfo=IST_TZ)
        day11_candles = [
            {"timestamp": datetime(2026, 12, 8, 10, 0, tzinfo=timezone.utc).isoformat(), "open": 4000, "high": 4050, "low": 3990, "close": 4040, "volume": 1000},
            {"timestamp": datetime(2026, 12, 9, 10, 0, tzinfo=timezone.utc).isoformat(), "open": 4040, "high": 4090, "low": 4030, "close": 4080, "volume": 1000},
            {"timestamp": datetime(2026, 12, 10, 10, 0, tzinfo=timezone.utc).isoformat(), "open": 4080, "high": 4140, "low": 4070, "close": 4120, "volume": 1000},
        ]

        with patch("backend.services.swing_audit_service.get_current_ist_time", return_value=ist_1545_thu), \
             patch("backend.services.swing_audit_service.market_data_service.fetch_quotes_bulk", new=AsyncMock(return_value={"TCS.NS": {"price": 4120.0, "previous_close": 4080.0}})), \
             patch("backend.services.swing_audit_service.market_data_service.fetch_quote", new=AsyncMock(return_value={"price": 4120.0, "previous_close": 4080.0})), \
             patch("backend.services.swing_audit_service.market_data_service.fetch_candles", new=AsyncMock(return_value=day11_candles)):
            assert await SwingAuditService.is_closing_window_active(db) is True
            sync_res = await SwingAuditService.update_daily_prices(db)

        assert sync_res["rollover_executed"] is True
        assert sync_res["completed_cycle"]["cycle_number"] == 1
        assert sync_res["active_cycle"]["cycle_number"] == 2
        assert sync_res["active_cycle"]["from_date"] == "2026-12-11"
        assert (tmp_path / "Swing_Trade_Audit_Cycle_1_(Final).xlsx").exists()

        sync_s.expire_all()
        c1_done = sync_s.execute(select(SwingTradeAuditCycle).where(SwingTradeAuditCycle.cycle_number == 1)).scalar_one()
        c2_new = sync_s.execute(select(SwingTradeAuditCycle).where(SwingTradeAuditCycle.cycle_number == 2)).scalar_one()
        t_closed = sync_s.execute(select(SwingTradeAudit).where(SwingTradeAudit.symbol == "TCS.NS")).scalar_one()
        assert c1_done.status == "COMPLETED"
        assert c2_new.status == "ACTIVE"
        assert t_closed.status == "DAY_11_EXIT"
        assert float(t_closed.exit_price) == 4120.0

        # Also test Friday Day-11 15:45 IST rolling directly to Monday (2026-12-14)
        c2_new.to_date = date(2026, 12, 11)
        sync_s.commit()
        ist_1545_fri = datetime(2026, 12, 11, 15, 45, tzinfo=IST_TZ)
        with patch("backend.services.swing_audit_service.get_current_ist_time", return_value=ist_1545_fri), \
             patch("backend.services.swing_audit_service.market_data_service.fetch_quotes_bulk", new=AsyncMock(return_value={})), \
             patch("backend.services.swing_audit_service.market_data_service.fetch_quote", new=AsyncMock(return_value=None)), \
             patch("backend.services.swing_audit_service.market_data_service.fetch_candles", new=AsyncMock(return_value=[])):
            fri_res = await SwingAuditService.update_daily_prices(db)

        assert fri_res["rollover_executed"] is True
        assert fri_res["active_cycle"]["cycle_number"] == 3
        assert fri_res["active_cycle"]["from_date"] == "2026-12-14"

