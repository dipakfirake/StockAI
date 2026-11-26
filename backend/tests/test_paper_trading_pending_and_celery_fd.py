"""
Regression tests for:
1. Celery persistent worker event loop & Redis/Fyers FD leak prevention.
2. Pending MARKET (AMO) and marketable LIMIT paper order execution.
3. Portfolio consolidated pending_orders_list & opportunistic sweep.
"""

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.portfolio import get_portfolio
from backend.core import cache as cache_mod
from backend.core.celery_async import run_in_worker_loop
from backend.models.paper_trade import PaperTrade
from backend.services.market_data import MarketDataService
from backend.services.paper_trading import PaperTradingService


def test_celery_worker_loop_reused_across_calls():
    """Repeated task executions in the same PID must reuse one persistent event loop."""
    loops = []

    async def _capture_loop():
        return asyncio.get_running_loop()

    for _ in range(15):
        loops.append(run_in_worker_loop(_capture_loop()))

    first = loops[0]
    assert all(lp is first for lp in loops), "Celery worker created multiple event loops!"
    assert not first.is_closed()


@pytest.mark.asyncio
async def test_cache_evicts_closed_loops_and_uses_non_deprecated_set():
    """Ensure get_redis() evicts closed loops and cache_set calls r.set(..., ex=ttl)."""
    closed_loop = asyncio.new_event_loop()
    closed_loop.close()
    cache_mod._redis_clients[id(closed_loop)] = (closed_loop, MagicMock())

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value='{"ok": true}')
    mock_redis.set = AsyncMock(return_value=True)

    with patch("backend.core.cache.redis.from_url", return_value=mock_redis):
        r = await cache_mod.get_redis()
        assert r is mock_redis
        assert id(closed_loop) not in cache_mod._redis_clients
        await cache_mod.cache_set("test:key", {"a": 1}, ttl=45)
        mock_redis.set.assert_awaited_once()
        _, kwargs = mock_redis.set.call_args
        assert kwargs.get("ex") == 45


def test_fyers_client_cached_and_celery_skips_websocket_restart():
    """Verify FyersModel instance reuse (no FileHandler leak) and no WS restart in Celery."""
    MarketDataService._cached_fyers_model = None
    with patch("backend.services.market_data.fyersModel.FyersModel", side_effect=lambda *a, **kw: MagicMock()) as mock_ctor:
        m1 = MarketDataService._build_cached_fyers_model("CID123", "TOK_ABC")
        m2 = MarketDataService._build_cached_fyers_model("CID123", "TOK_ABC")
        assert m1 is m2
        assert mock_ctor.call_count == 1
        # Different credentials invalidate cache cleanly
        m3 = MarketDataService._build_cached_fyers_model("CID123", "TOK_XYZ")
        assert m3 is not m1
        assert mock_ctor.call_count == 2

    MarketDataService._cached_fyers_model = None


@pytest.mark.asyncio
async def test_celery_worker_check_credentials_does_not_spawn_websocket_stream():
    """Celery worker processes must never start FyersStreamService background WS threads."""
    MarketDataService._last_token_check_time = 0.0
    MarketDataService._last_loaded_token = "OLD_TOKEN"

    with patch.object(MarketDataService, "_is_celery_worker_process", return_value=True), \
         patch("backend.core.cache.cache_get", new=AsyncMock(return_value={"client_id": "CID1", "access_token": "NEW_TOKEN"})), \
         patch("backend.services.fyers_stream.fyers_stream_service.restart", new_callable=AsyncMock) as mock_restart:
        changed = await MarketDataService.check_credentials_changed()
        assert changed is True
        mock_restart.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_pending_market_order_executes_when_liquidity_unlocks():
    """AMO/queued MARKET order (limit_price=None) must fill to OPEN when depth has asks."""
    user_id = uuid.uuid4()
    trade = PaperTrade(
        id=uuid.uuid4(),
        user_id=user_id,
        symbol="TITAN.NS",
        direction="BUY",
        order_type="MARKET",
        product_type="DELIVERY",
        quantity=10,
        limit_price=None,
        stop_price=None,
        status="PENDING",
        commission=Decimal("20.00"),
        opened_at=datetime(2026, 11, 25, 20, 52, tzinfo=timezone.utc),
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [trade]
    mock_db.execute.return_value = mock_res

    mock_depth = {
        "ltp": 4686.60,
        "total_buy_qty": 5000,
        "total_sell_qty": 5000,
        "bids": [{"price": 4686.55, "quantity": 500, "orders": 5}],
        "asks": [{"price": 4686.60, "quantity": 500, "orders": 5}],
    }

    with patch("backend.services.paper_trading.market_data_service.fetch_quotes_bulk", new=AsyncMock(return_value={"TITAN.NS": {"price": 4686.60}})), \
         patch("backend.services.market_depth_service.market_depth_service.get_market_depth", new=AsyncMock(return_value=mock_depth)), \
         patch("backend.services.paper_trading.event_bus.publish", new_callable=AsyncMock) as mock_pub:
        filled = await PaperTradingService.evaluate_pending_orders(mock_db)

    assert filled == 1
    assert trade.status == "OPEN"
    assert float(trade.entry_price) == 4686.60
    mock_pub.assert_awaited_once()


@pytest.mark.asyncio
async def test_evaluate_pending_orders_skips_null_prices_and_triggers_sl_limit():
    """Verify null-price rows never raise TypeError and valid SL_LIMIT fills cleanly."""
    uid = uuid.uuid4()
    bad_limit = PaperTrade(
        id=uuid.uuid4(), user_id=uid, symbol="TCS.NS", direction="BUY",
        order_type="LIMIT", product_type="DELIVERY", quantity=5,
        limit_price=None, status="PENDING", commission=Decimal("20"),
    )
    bad_sl = PaperTrade(
        id=uuid.uuid4(), user_id=uid, symbol="INFY.NS", direction="BUY",
        order_type="SL", product_type="DELIVERY", quantity=5,
        stop_price=None, status="PENDING", commission=Decimal("20"),
    )
    sl_lim = PaperTrade(
        id=uuid.uuid4(), user_id=uid, symbol="M&M.NS", direction="BUY",
        order_type="SL_LIMIT", product_type="DELIVERY", quantity=5,
        stop_price=Decimal("3450.00"), limit_price=Decimal("3480.00"),
        status="PENDING", commission=Decimal("20"),
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [bad_limit, bad_sl, sl_lim]
    mock_db.execute.return_value = mock_res

    mock_depth = {
        "ltp": 3473.0,
        "total_buy_qty": 2000,
        "total_sell_qty": 2000,
        "bids": [{"price": 3472.95, "quantity": 200, "orders": 4}],
        "asks": [{"price": 3473.00, "quantity": 200, "orders": 4}],
    }

    quotes = {
        "TCS.NS": {"price": 2550.0},
        "INFY.NS": {"price": 1800.0},
        "M&M.NS": {"price": 3473.0},
    }

    with patch("backend.services.paper_trading.market_data_service.fetch_quotes_bulk", new=AsyncMock(return_value=quotes)), \
         patch("backend.services.market_depth_service.market_depth_service.get_market_depth", new=AsyncMock(return_value=mock_depth)), \
         patch("backend.services.paper_trading.event_bus.publish", new_callable=AsyncMock):
        filled = await PaperTradingService.evaluate_pending_orders(mock_db)

    assert filled == 1
    assert bad_limit.status == "PENDING"
    assert bad_sl.status == "PENDING"
    assert sl_lim.status == "OPEN"
    assert float(sl_lim.entry_price) == 3473.0


@pytest.mark.asyncio
async def test_marketable_vs_nonmarketable_limit_order_during_open_market():
    """Marketable LIMIT BUY fills immediately to OPEN; lower LIMIT stays PENDING."""
    uid = str(uuid.uuid4())
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    open_depth = {
        "ltp": 4686.60,
        "total_buy_qty": 5000,
        "total_sell_qty": 5000,
        "bids": [{"price": 4686.55, "quantity": 500, "orders": 5}],
        "asks": [{"price": 4686.60, "quantity": 500, "orders": 5}],
    }

    with patch("backend.services.paper_trading.market_data_service.fetch_quote", new=AsyncMock(return_value={"price": 4686.60})), \
         patch("backend.services.market_depth_service.market_depth_service.get_market_depth", new=AsyncMock(return_value=open_depth)), \
         patch("backend.services.paper_trading.is_indian_market_open", return_value=True), \
         patch("backend.services.paper_trading.event_bus.publish", new_callable=AsyncMock):

        t_marketable = await PaperTradingService.place_order(
            db=mock_db, user_id=uid, symbol="TITAN.NS", direction="BUY",
            quantity=10, order_type="LIMIT", product_type="DELIVERY", limit_price=4686.60,
        )
        assert t_marketable.status == "OPEN"
        assert float(t_marketable.entry_price) == 4686.60

        t_waiting = await PaperTradingService.place_order(
            db=mock_db, user_id=uid, symbol="TITAN.NS", direction="BUY",
            quantity=10, order_type="LIMIT", product_type="DELIVERY", limit_price=4500.00,
        )
        assert t_waiting.status == "PENDING"
        assert t_waiting.entry_price is None


@pytest.mark.asyncio
async def test_portfolio_includes_pending_orders_list_and_sweeps_when_market_open():
    """Verify GET /api/portfolio exposes pending_orders_list and triggers sweep during open hours."""
    uid = uuid.uuid4()
    user = MagicMock()
    user.id = uid

    pending_trade = PaperTrade(
        id=uuid.uuid4(), user_id=uid, symbol="TITAN.NS", direction="BUY",
        order_type="LIMIT", product_type="DELIVERY", quantity=10,
        limit_price=Decimal("4500.00"), target_price=Decimal("5135.66"),
        stop_loss=Decimal("4462.07"), status="PENDING",
        opened_at=datetime.now(timezone.utc),
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [pending_trade]
    mock_db.execute.return_value = mock_res

    with patch("backend.api.portfolio.is_indian_market_open", return_value=False):
        res = await get_portfolio(current_user=user, db=mock_db)

    assert res["pending_orders"] == 1
    assert len(res["pending_orders_list"]) == 1
    assert res["pending_orders_list"][0]["symbol"] == "TITAN.NS"
    assert res["pending_orders_list"][0]["limit_price"] == 4500.0

    with patch("backend.api.portfolio.is_indian_market_open", return_value=True), \
         patch("backend.api.portfolio.paper_trading_service.evaluate_pending_orders", new=AsyncMock(return_value=1)) as mock_sweep:
        await get_portfolio(current_user=user, db=mock_db)
        mock_sweep.assert_awaited_once_with(mock_db, user_id=str(uid))
