"""
Regression tests for:
1. Alerts Best Buy Proximity Radar (PRE_BUY vs AT_BEST_BUY strict filtering,
   ±proximity bounds on ALL, summary KPI reconciliation, live quote overlay,
   10-sector cache hydration, and orphan alert cleanup / Holdings Guard sync).
2. Portfolio & Paper Trading Sold Stocks Ledger (derived exit_price on legacy
   rows, closed_by AUTO_SYSTEM vs USER_MANUAL attribution, closed days_held,
   DELIVERY exit STT parity across /portfolio and /paper-trades, and orphan alert
   deactivation on exit).
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from backend.api.alerts import get_screener_proximity_radar, sync_holdings_alerts
from backend.api.paper_trading import close_paper_trade, list_paper_trades
from backend.api.portfolio import get_portfolio
from backend.models.alert import Alert
from backend.models.paper_trade import PaperTrade
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.services.paper_trading import PaperTradingService


@compiles(PG_UUID, "sqlite")
def _compile_pg_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


class _LocalAsyncSQLiteProxy:
    def __init__(self, sync_session: Session):
        self._s = sync_session

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


def _make_setup(
    symbol: str,
    sector: str,
    score: float,
    best_buy: float,
    target: float,
    sl: float,
    t1: float | None = None,
    t2: float | None = None,
    t3: float | None = None,
) -> dict:
    return {
        "symbol": symbol,
        "name": f"{symbol} Ltd",
        "sector": sector,
        "action": "BUY",
        "total_score": score,
        "indicators": {"rsi_14": 48.0, "atr_14": 25.0},
        "ai_analysis": {"confidence": 0.78, "probabilities": {"buy": 0.66}},
        "trade_plan": {
            "best_buy_price": best_buy,
            "current_price": best_buy,
            "target_price": target,
            "target_1": t1,
            "target_2": t2,
            "target_3": t3,
            "stop_loss": sl,
            "expected_gain_pct": round(((target - best_buy) / best_buy) * 100.0, 2),
            "risk_reward_ratio": 2.4,
            "entry_type": "PULLBACK_DIP",
        },
    }


@pytest.mark.asyncio
async def test_radar_pre_buy_excludes_at_best_buy_and_all_enforces_lower_bound():
    """
    PRE_BUY must strictly show setups descending above Best Buy (> +0.5% to <= proximity_pct)
    and NEVER leak 0.00% AT_BEST_BUY stocks like TITAN.NS.
    ALL must strictly enforce abs(distance_pct) <= proximity_pct (or is_near_target),
    excluding deeply crashed setups like -10.0%.
    Summary KPI counts must reconcile 1:1 with the displayed candidates.
    """
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    setups = [
        _make_setup("TITAN.NS", "NIFTY_50", 76.1, 4675.3, 5100.58, 4462.66, 4880.0, 5100.58, 5350.0),
        _make_setup("ULTRACEMCO.NS", "NIFTY_50", 74.0, 11000.0, 11850.0, 10550.0),
        _make_setup("DEEPDIP.NS", "NIFTY_50", 72.0, 1000.0, 1120.0, 950.0),
        _make_setup("NEARTGT.NS", "NIFTY_50", 80.0, 1000.0, 1100.0, 960.0),
    ]

    quotes = {
        "TITAN.NS": {"price": 4675.3, "timestamp": "2026-11-27T10:00:00+00:00"},       # 0.00% -> AT_BEST_BUY
        "ULTRACEMCO.NS": {"price": 11110.0, "timestamp": "2026-11-27T10:00:00+00:00"}, # +1.00% -> PRE_BUY
        "DEEPDIP.NS": {"price": 900.0, "timestamp": "2026-11-27T10:00:00+00:00"},      # -10.00% -> OUTSIDE ±2%
        "NEARTGT.NS": {"price": 1080.0, "timestamp": "2026-11-27T10:00:00+00:00"},     # +1.85% from T -> SELL_PRE_ALERT
    }

    with patch("backend.core.cache.cache_get", new_callable=AsyncMock) as mock_cache_get, \
         patch("backend.services.market_data.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_bulk:

        async def _cache_side_effect(key: str):
            if key == "screener_results_NIFTY_50":
                return {"timestamp": "2026-11-27T09:30:00+00:00", "buy_stocks": setups}
            return None

        mock_cache_get.side_effect = _cache_side_effect
        mock_bulk.return_value = quotes

        # 1. Stage = PRE_BUY, Proximity = 2.0%
        res_pre = await get_screener_proximity_radar(
            sector="NIFTY_50", proximity_pct=2.0, min_score=60.0, stage="PRE_BUY", current_user=mock_user
        )
        syms_pre = [c["symbol"] for c in res_pre["candidates"]]
        assert syms_pre == ["ULTRACEMCO.NS"]
        assert "TITAN.NS" not in syms_pre
        assert res_pre["total_candidates"] == 1
        assert res_pre["summary"]["at_best_buy"] == 0
        assert res_pre["summary"]["near_best_buy"] == 1
        assert res_pre["summary"]["pre_buy_prime"] == 1

        # 2. Stage = AT_BEST_BUY
        res_at = await get_screener_proximity_radar(
            sector="NIFTY_50", proximity_pct=2.0, min_score=60.0, stage="AT_BEST_BUY", current_user=mock_user
        )
        assert [c["symbol"] for c in res_at["candidates"]] == ["TITAN.NS"]
        assert res_at["summary"]["at_best_buy"] == 1
        assert res_at["summary"]["near_best_buy"] == 0
        assert res_at["candidates"][0]["target_1"] == 4880.0
        assert res_at["candidates"][0]["target_3"] == 5350.0

        # 3. Stage = ALL, Proximity = 2.0% -> DEEPDIP (-10%) MUST be excluded
        res_all = await get_screener_proximity_radar(
            sector="NIFTY_50", proximity_pct=2.0, min_score=60.0, stage="ALL", current_user=mock_user
        )
        syms_all = [c["symbol"] for c in res_all["candidates"]]
        assert set(syms_all) == {"TITAN.NS", "ULTRACEMCO.NS", "NEARTGT.NS"}
        assert "DEEPDIP.NS" not in syms_all
        assert res_all["total_candidates"] == 3
        assert res_all["summary"]["at_best_buy"] == 1
        assert res_all["summary"]["near_best_buy"] == 1
        assert res_all["summary"]["sell_pre_alerts"] == 1


@pytest.mark.asyncio
async def test_radar_live_quote_overlay_and_10_sector_cache_hydration():
    """
    Even if stale alerts_screener_radar keys exist in Redis and screener_all_sectors_aggregated
    has expired, sector='ALL' must merge per-sector results & LKG snapshots across sectors and
    ALWAYS recalculate CMP & distances dynamically from the latest live bulk quote call.
    """
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    nifty_setups = [_make_setup("TITAN.NS", "NIFTY_50", 76.1, 4675.3, 5100.58, 4462.66)]
    it_setups = [_make_setup("WIPRO.NS", "IT", 74.5, 560.0, 610.0, 535.0)]
    bank_setups = [_make_setup("BANKBARODA.NS", "BANKING", 75.2, 245.0, 268.0, 234.0)]

    with patch("backend.core.cache.cache_get", new_callable=AsyncMock) as mock_cache_get, \
         patch("backend.services.market_data.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_bulk:

        async def _cache_side_effect(key: str):
            if key == "alerts_screener_radar:ALL:2.0:60.0:ALL":
                return {"candidates": [{"symbol": "STALE.NS", "cmp": 1.0}], "total_candidates": 1}
            if key == "screener_results_NIFTY_50":
                return {"timestamp": "2026-11-27T09:30:00+00:00", "buy_stocks": nifty_setups}
            if key == "screener_lkg_IT":
                return {"timestamp": "2026-11-27T09:15:00+00:00", "buy_stocks": it_setups}
            if key == "screener_results_BANKING":
                return {"timestamp": "2026-11-27T09:40:00+00:00", "buy_stocks": bank_setups}
            return None

        mock_cache_get.side_effect = _cache_side_effect

        # Call 1: CMP at exact Best Buy
        mock_bulk.return_value = {
            "TITAN.NS": {"price": 4675.3, "timestamp": "2026-11-27T10:00:00+00:00"},
            "WIPRO.NS": {"price": 564.0, "timestamp": "2026-11-27T10:00:00+00:00"},
            "BANKBARODA.NS": {"price": 247.0, "timestamp": "2026-11-27T10:00:00+00:00"},
        }
        res_1 = await get_screener_proximity_radar(
            sector="ALL", proximity_pct=2.0, min_score=60.0, stage="ALL", current_user=mock_user
        )
        syms_1 = {c["symbol"]: c for c in res_1["candidates"]}
        assert set(syms_1.keys()) == {"TITAN.NS", "WIPRO.NS", "BANKBARODA.NS"}
        assert "STALE.NS" not in syms_1
        assert syms_1["TITAN.NS"]["cmp"] == 4675.3
        assert syms_1["TITAN.NS"]["distance_pct"] == 0.0
        assert res_1["quotes_live_count"] == 3
        assert "generated_at" in res_1

        # Call 2: Price moves live (+1.2% on TITAN) -> MUST reflect immediately without force_refresh
        mock_bulk.return_value = {
            "TITAN.NS": {"price": 4731.4, "timestamp": "2026-11-27T10:05:00+00:00"},
            "WIPRO.NS": {"price": 564.0, "timestamp": "2026-11-27T10:05:00+00:00"},
            "BANKBARODA.NS": {"price": 247.0, "timestamp": "2026-11-27T10:05:00+00:00"},
        }
        res_2 = await get_screener_proximity_radar(
            sector="ALL", proximity_pct=2.0, min_score=60.0, stage="PRE_BUY", force_refresh=True, current_user=mock_user
        )
        syms_2 = {c["symbol"]: c for c in res_2["candidates"]}
        assert "TITAN.NS" in syms_2
        assert syms_2["TITAN.NS"]["cmp"] == 4731.4
        assert syms_2["TITAN.NS"]["distance_pct"] == 1.2
        assert syms_2["TITAN.NS"]["is_pre_buy"] is True
        assert mock_bulk.call_args.kwargs == {"use_fallback": True, "bypass_cache": True}


@pytest.mark.asyncio
async def test_portfolio_and_paper_trades_sold_ledger_exit_attribution_and_stt_parity():
    """
    Verify:
    1. Legacy CLOSED rows without exit_price / closed_by accurately derive exit_price,
       days_held (closed_at - opened_at), and AUTO_SYSTEM target/SL vs USER_MANUAL trigger.
    2. OPEN DELIVERY trades with default Decimal('0.00') stt_tax apply identical 0.1% exit STT
       deduction in BOTH /api/portfolio and /api/paper-trades (zero P&L mismatch).
    3. evaluate_open_trades auto-exits persist AUTO_SYSTEM + specific SYSTEM_AUTO_* reason and
       deactivate orphan exit alerts only when the user has 0 remaining OPEN lots of that symbol.
    """
    engine = create_engine("sqlite:///:memory:", future=True)
    for tbl in (User.__table__, SystemSettings.__table__, PaperTrade.__table__, Alert.__table__):
        tbl.create(engine, checkfirst=True)

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    sync_s = SessionLocal()
    db = _LocalAsyncSQLiteProxy(sync_s)
    try:
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            email="trader@example.com",
            hashed_password="hashed",
            name="Trader",
            is_admin=False,
            is_active=True,
        )
        db.add(user)

        now_utc = datetime.now(timezone.utc)
        # 1. Legacy Auto Target exit (PERSISTENT.NS case from live DB)
        t_persistent = PaperTrade(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol="PERSISTENT.NS",
            direction="BUY",
            order_type="LIMIT",
            product_type="DELIVERY",
            quantity=10,
            entry_price=Decimal("5746.2405"),
            exit_price=None,
            target_price=Decimal("6255.17"),
            stop_loss=Decimal("5517.54"),
            commission=Decimal("20.00"),
            stt_tax=Decimal("62.68"),
            status="CLOSED",
            realized_pnl=Decimal("5139.41"),
            opened_at=now_utc - timedelta(days=36, hours=2),
            closed_at=now_utc - timedelta(days=1, hours=2),
        )
        # 2. Legacy Auto Stop-Loss exit (COFORGE.NS case)
        t_coforge = PaperTrade(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol="COFORGE.NS",
            direction="BUY",
            order_type="MARKET",
            product_type="DELIVERY",
            quantity=10,
            entry_price=Decimal("1750.00"),
            exit_price=None,
            target_price=Decimal("1900.00"),
            stop_loss=Decimal("1680.00"),
            commission=Decimal("20.00"),
            stt_tax=Decimal("16.70"),
            status="CLOSED",
            realized_pnl=Decimal("-836.70"),  # implied exit = 1670.00 <= SL 1680.00
            opened_at=now_utc - timedelta(days=14),
            closed_at=now_utc - timedelta(days=10),
        )
        # 3. OPEN DELIVERY lot with DB default stt_tax=0.00 (checks STT parity!)
        t_titan_open = PaperTrade(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol="TITAN.NS",
            direction="BUY",
            order_type="MARKET",
            product_type="DELIVERY",
            quantity=10,
            entry_price=Decimal("4637.24"),
            target_price=Decimal("5100.00"),
            stop_loss=Decimal("4460.00"),
            target_1=Decimal("4880.00"),
            target_2=Decimal("5100.00"),
            target_3=Decimal("5350.00"),
            initial_stop_loss=Decimal("4460.00"),
            ratchet_stage="INITIAL",
            commission=Decimal("0.00"),
            stt_tax=Decimal("0.00"),
            status="OPEN",
            opened_at=now_utc - timedelta(days=1),
        )
        # 4. OPEN single-lot stock ready for progressive T2 ratchet exit + orphan alert cleanup
        t_infy_open = PaperTrade(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol="INFY.NS",
            direction="BUY",
            order_type="MARKET",
            product_type="DELIVERY",
            quantity=5,
            entry_price=Decimal("1500.00"),
            target_price=Decimal("1650.00"),
            stop_loss=Decimal("1440.00"),
            target_1=Decimal("1560.00"),
            target_2=Decimal("1650.00"),
            initial_stop_loss=Decimal("1440.00"),
            ratchet_stage="INITIAL",
            commission=Decimal("20.00"),
            stt_tax=Decimal("0.00"),
            status="OPEN",
            opened_at=now_utc - timedelta(hours=3),
        )
        infy_alert = Alert(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol="INFY.NS",
            condition_type="TARGET_PROXIMITY",
            condition_value="1633.5",
            is_active=True,
        )
        titan_alert = Alert(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol="TITAN.NS",
            condition_type="STOP_LOSS_HIT",
            condition_value="4460.0",
            is_active=True,
        )
        db.add_all([t_persistent, t_coforge, t_titan_open, t_infy_open, infy_alert, titan_alert])
        await db.flush()

        # Part A: Check /api/portfolio & /api/paper-trades STT parity and sold history BEFORE auto-exit
        quotes = {
            "TITAN.NS": {"price": 4675.30, "previous_close": 4631.10},
            "INFY.NS": {"price": 1520.00, "previous_close": 1500.00},
        }
        with patch("backend.api.portfolio.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mp_port, \
             patch("backend.api.paper_trading.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mp_pt:
            mp_port.return_value = quotes
            mp_pt.return_value = quotes

            port_res = await get_portfolio(current_user=user, db=db)
            pt_res = await list_paper_trades(current_user=user, db=db)

        titan_port = next(a for a in port_res["allocation"] if a["symbol"] == "TITAN.NS")
        titan_pt = next(t for t in pt_res["trades"] if t["symbol"] == "TITAN.NS" and t["status"] == "OPEN")
        assert titan_port["unrealized_pnl"] == titan_pt["unrealized_pnl"] == 333.85  # (4675.30 - 4637.24)*10 - 46.75 STT
        assert titan_port["stt_tax"] == titan_pt["stt_tax"] == 46.75

        sold_map = {item["symbol"]: item for item in port_res["closed_trades_list"]}
        assert sold_map["PERSISTENT.NS"]["exit_price"] == 6268.45
        assert sold_map["PERSISTENT.NS"]["days_held"] == 35
        assert sold_map["PERSISTENT.NS"]["closed_by"] == "AUTO_SYSTEM"
        assert sold_map["PERSISTENT.NS"]["exit_reason"] == "SYSTEM_AUTO_TARGET"
        assert sold_map["COFORGE.NS"]["exit_price"] == 1670.0
        assert sold_map["COFORGE.NS"]["closed_by"] == "AUTO_SYSTEM"
        assert sold_map["COFORGE.NS"]["exit_reason"] == "SYSTEM_AUTO_STOPLOSS"

        # Part B: System auto-exits INFY.NS when T2 (1650) is reached -> closes INFY, preserves TITAN
        with patch("backend.services.market_data.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_eval_q:
            mock_eval_q.return_value = {
                "TITAN.NS": {"price": 4675.30},
                "INFY.NS": {"price": 1660.00},
            }
            await PaperTradingService.evaluate_open_trades(db)
            await db.flush()

        assert t_infy_open.status == "CLOSED"
        assert t_infy_open.closed_by == "AUTO_SYSTEM"
        assert t_infy_open.exit_reason == "SYSTEM_AUTO_TARGET_2"
        assert t_infy_open.closed_at is not None
        assert infy_alert.is_active is False   # Final INFY lot exited -> orphan alert deactivated
        assert titan_alert.is_active is True   # TITAN still OPEN -> alert kept active!

        # Part C: User manually closes TITAN.NS via close_paper_trade -> tagged USER_MANUAL & cleans alert
        with patch("backend.services.market_data.market_data_service.fetch_quote", new_callable=AsyncMock) as mock_q:
            mock_q.return_value = {"price": 4700.0}
            close_resp = await close_paper_trade(str(t_titan_open.id), current_user=user, db=db)

        assert close_resp["status"] == "CLOSED"
        assert close_resp["closed_by"] == "USER_MANUAL"
        assert close_resp["exit_reason"] == "USER_MANUAL_EXIT"
        assert titan_alert.is_active is False

        # Re-check /api/portfolio closed_trades_list count (4 total exits: 3 AUTO_SYSTEM, 1 USER_MANUAL)
        with patch("backend.api.portfolio.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mp_port2:
            mp_port2.return_value = {}
            port_after = await get_portfolio(current_user=user, db=db)

        assert port_after["closed_trades"] == 4
        assert port_after["auto_sold_count"] == 3
        assert port_after["user_sold_count"] == 1
        assert len(port_after["closed_trades_list"]) == 4
    finally:
        sync_s.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_sync_holdings_alerts_dedup_and_orphan_cleanup():
    """
    Holdings Guard sync must:
    1. Group duplicate lots of an open stock (4x TITAN.NS -> 1 guard set, not 4x duplicates)
       and still add TARGET/SL guard even when BUY_PROXIMITY already exists.
    2. Deactivate orphan TARGET/STOP_LOSS alerts belonging to exited holdings (PERSISTENT.NS)
       that have no active BUY_PROXIMITY watchlist alert.
    """
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    open_1 = MagicMock(spec=PaperTrade, id=uuid.uuid4(), symbol="TITAN.NS", direction="BUY", status="OPEN", entry_price=4637.24, target_price=None, stop_loss=None)
    open_2 = MagicMock(spec=PaperTrade, id=uuid.uuid4(), symbol="TITAN.NS", direction="BUY", status="OPEN", entry_price=4637.24, target_price=None, stop_loss=None)
    closed_1 = MagicMock(spec=PaperTrade, id=uuid.uuid4(), symbol="PERSISTENT.NS", direction="BUY", status="CLOSED", entry_price=5746.24, target_price=6255.17, stop_loss=5517.54)

    buy_prox_titan = Alert(id=uuid.uuid4(), user_id=mock_user.id, symbol="TITAN.NS", condition_type="BUY_PROXIMITY", condition_value="4675", is_active=True)
    orphan_persistent = Alert(id=uuid.uuid4(), user_id=mock_user.id, symbol="PERSISTENT.NS", condition_type="TARGET_PROXIMITY", condition_value="6192.62", is_active=True)

    alerts_res = MagicMock()
    alerts_res.scalars.return_value.all.return_value = [buy_prox_titan, orphan_persistent]

    mock_db = AsyncMock()
    mock_db.execute.return_value = alerts_res
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    with patch("backend.services.paper_trading.paper_trading_service.get_all_trades", new_callable=AsyncMock) as mock_trades, \
         patch("backend.api.alerts.broadcast_alert", new_callable=AsyncMock):
        mock_trades.return_value = [open_1, open_2, closed_1]
        res = await sync_holdings_alerts(current_user=mock_user, db=mock_db)

    assert res["synced_count"] == 1
    assert res["deactivated_orphans"] == 1
    assert orphan_persistent.is_active is False
    added_types = [call.args[0].condition_type for call in mock_db.add.call_args_list]
    assert added_types == ["TARGET_PROXIMITY", "STOP_LOSS_PROXIMITY", "STOP_LOSS_HIT"]
