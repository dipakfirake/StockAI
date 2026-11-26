"""Regression tests for continuous live price streaming, Fyers HSM subscriptions, and cache TTL bounds."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from backend.core.config import Settings
from backend.services.fyers_stream import (
    FyersStreamService,
    _HSM_TOKEN_MEMORY_CACHE,
    _MEMORY_QUOTES,
    _MEMORY_QUOTE_TIMES,
    get_fresh_memory_quote,
)
from backend.services.market_data import MarketDataService


def test_effective_live_ttl_caps_legacy_env_values():
    """Legacy .env overrides (60s quotes / 15s index) must be capped <= 3s for live tickers."""
    legacy = Settings(CACHE_TTL_QUOTE=60, CACHE_TTL_INDEX_QUOTE=15)
    assert legacy.effective_live_quote_ttl == 3
    assert legacy.effective_live_index_ttl == 3

    tight = Settings(CACHE_TTL_QUOTE=1, CACHE_TTL_INDEX_QUOTE=2)
    assert tight.effective_live_quote_ttl == 1
    assert tight.effective_live_index_ttl == 2


def test_patched_symbol_to_hsmtoken_returns_four_tuple_for_sdk():
    """
    fyers_apiv3 FyersDataSocket.__symbol_conversion unpacks symbol_value[3].
    Verify patched symbol_to_hsmtoken always returns a 4-tuple so subscriptions never raise IndexError.
    """
    from fyers_apiv3.FyersWebsocket import data_ws

    conv = data_ws.SymbolConversion("CLIENT:TOKEN", "SymbolUpdate", "")
    _HSM_TOKEN_MEMORY_CACHE["NSE:NIFTY50-INDEX"] = {
        "fyToken": "101000000026000",
        "symbol": "NSE:NIFTY50-INDEX",
    }
    try:
        res = conv.symbol_to_hsmtoken(["NSE:NIFTY50-INDEX"])
        assert isinstance(res, tuple)
        assert len(res) == 4
        datadict, wrong_syms, dp_index_flag, err_msg = res
        assert "if|nse_cm|Nifty 50" in datadict
        assert wrong_syms == []
        assert dp_index_flag is False
        assert err_msg == ""

        empty_res = conv.symbol_to_hsmtoken([])
        assert len(empty_res) == 4
    finally:
        _HSM_TOKEN_MEMORY_CACHE.pop("NSE:NIFTY50-INDEX", None)


def test_memory_quote_staleness_guard():
    """Stale _MEMORY_QUOTES entries older than max_age_seconds must expire cleanly."""
    sym = "RELIANCE.NS"
    _MEMORY_QUOTES[sym] = {"symbol": sym, "price": 1380.2}
    _MEMORY_QUOTE_TIMES[sym] = time.monotonic() - 10.0
    try:
        assert get_fresh_memory_quote(sym, max_age_seconds=5.0) is None
        _MEMORY_QUOTE_TIMES[sym] = time.monotonic()
        fresh = get_fresh_memory_quote(sym, max_age_seconds=5.0)
        assert fresh is not None and fresh["price"] == 1380.2
    finally:
        _MEMORY_QUOTES.pop(sym, None)
        _MEMORY_QUOTE_TIMES.pop(sym, None)


@pytest.mark.asyncio
async def test_fetch_quotes_bulk_bypass_cache_fetches_fresh_quote():
    """poll_market_data passes bypass_cache=True so Redis quote cache never freezes ticks for 60s."""
    stale_cached = {"symbol": "^NSEI", "price": 25000.0, "timestamp": "2026-11-26T06:00:00+00:00"}
    fresh_fyers_resp = {
        "s": "ok",
        "d": [{
            "n": "NSE:NIFTY50-INDEX",
            "v": {"lp": 25950.5, "ch": 131.25, "chp": 0.51, "prev_close_price": 25819.25, "volume": 0},
        }],
    }
    mock_fyers = MagicMock()
    mock_fyers.quotes.return_value = fresh_fyers_resp

    MarketDataService.reset_fyers_health()
    with patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=stale_cached), \
         patch("backend.services.market_data.cache_set", new_callable=AsyncMock) as mock_set, \
         patch.object(MarketDataService, "check_credentials_changed", new_callable=AsyncMock, return_value=False), \
         patch.object(MarketDataService, "acquire_fyers_rate_budget_slot", new_callable=AsyncMock, return_value=True), \
         patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock, return_value=mock_fyers):
        res = await MarketDataService.fetch_quotes_bulk(["^NSEI"], use_fallback=False, bypass_cache=True)

    assert res["^NSEI"]["price"] == 25950.5
    assert res["^NSEI"]["source"] == "Fyers API"
    mock_set.assert_awaited()


def test_stream_stall_detector_only_trips_for_real_stalled_socket():
    """Connected socket with zero ticks for >15s during market hours flags stalled cleanly."""
    svc = FyersStreamService()
    svc._subscribed_symbols = {"NSE:NIFTY50-INDEX"}
    assert svc.is_stream_stalled(15.0) is False

    mock_sock = MagicMock()
    mock_sock.is_connected.return_value = True
    svc._socket = mock_sock
    svc._is_connected = True
    svc._connected_at = time.monotonic() - 20.0
    svc._last_tick_at = 0.0

    with patch("backend.core.market_hours.is_indian_market_open", return_value=True):
        assert svc.is_stream_stalled(15.0) is True
        svc._last_tick_at = time.monotonic() - 2.0
        assert svc.is_stream_stalled(15.0) is False


@pytest.mark.asyncio
async def test_settings_fyers_status_does_not_rearm_warmup_when_already_healthy():
    """Viewing /admin must not repeatedly engage 60s warmup when Fyers was already valid."""
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.api.auth import get_current_user

    mock_user = MagicMock()
    mock_user.id = "00000000-0000-0000-0000-000000000001"
    mock_user.email = "admin@example.com"
    mock_user.is_admin = True

    MarketDataService.reset_fyers_health(engage_warmup=False)
    mock_fyers = MagicMock()
    mock_fyers.get_profile.return_value = {"s": "ok", "data": {"name": "Test Trader", "fy_id": "TEST01"}}

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch("backend.api.settings.cache_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.api.settings.cache_set", new_callable=AsyncMock), \
             patch("fyers_apiv3.fyersModel.FyersModel", return_value=mock_fyers), \
             patch("backend.services.fyers_stream.FyersStreamService.is_connected", new_callable=PropertyMock, return_value=True):
            client = TestClient(app)
            resp = client.get("/api/settings/fyers/status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["connected"] is True
            assert body["dual_engine"]["warmup_active"] is False
            assert "websocket_stream" in body["dual_engine"]
    finally:
        app.dependency_overrides.clear()
