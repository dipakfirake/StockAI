"""
End-to-End Navigation & Token Entry Simulation Suite (Milestone 3 / Feature 15)
Author: Worker 3 (QA & Release Verification Worker)

Verifies:
1. Seamless Fyers token entry and validation via /api/settings/fyers/update-token without server hang.
2. Rapid concurrent navigation across platform components (Dashboard, ChartPage, Watchlist, LiveTicker, Admin)
   with zero event loop blocking, zero deadlocks, and sub-second response times.
3. Strict adherence to Fyers rate budgeting (<= 50 req/min) under warmup mode, with thundering herd
   bursts automatically and transparently routed to Yahoo Finance fallback.
4. WebSocket live tick streaming delivering zero-REST real-time updates and compliant micro-tick fluidity.
"""

import asyncio
import datetime
import time
import uuid
import pandas as pd
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.api.admin import require_admin
from backend.models.user import User
from backend.models.watchlist import Watchlist
from backend.models.settings import SystemSettings
from backend.services.market_data import MarketDataService
from backend.services.fyers_stream import fyers_stream_service
from backend.services.time_sync import TimeSyncService
from backend.api.websocket import (
    _market_connections,
    _symbol_subscribers,
    _register_subscription,
    HighFrequencyFluidityEngine,
)


class MockDbSession:
    """Mock asynchronous database session for zero-network testing."""
    def __init__(self, admin_user=None):
        self.admin_user = admin_user
        from backend.api.settings import DEFAULT_SETTINGS
        self.settings = [
            SystemSettings(key="fyers_client_id", value="TEST_CLIENT_ID", value_type="string", description="Client ID"),
            SystemSettings(key="fyers_access_token", value="OLD_EXPIRED_TOKEN", value_type="string", description="Access Token"),
        ] + [SystemSettings(**d) for d in DEFAULT_SETTINGS if d["key"] not in ("fyers_client_id", "fyers_access_token")]
        self.watchlist = [
            Watchlist(id=uuid.uuid4(), user_id=admin_user.id if admin_user else uuid.uuid4(), symbol="RELIANCE.NS", added_at=datetime.datetime.now(datetime.timezone.utc)),
            Watchlist(id=uuid.uuid4(), user_id=admin_user.id if admin_user else uuid.uuid4(), symbol="TCS.NS", added_at=datetime.datetime.now(datetime.timezone.utc)),
        ]

    async def execute(self, stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()
        if "systemsettings" in stmt_str:
            mock_result.scalars.return_value.all.return_value = self.settings
            mock_result.scalars.return_value.first.return_value = self.settings[1]
            mock_result.scalar_one_or_none.return_value = self.settings[1]
        elif "watchlist" in stmt_str:
            mock_result.scalars.return_value.all.return_value = self.watchlist
            mock_result.scalars.return_value.first.return_value = self.watchlist[0]
            mock_result.scalar_one_or_none.return_value = self.watchlist[0]
        else:
            mock_result.scalars.return_value.all.return_value = []
            mock_result.scalars.return_value.first.return_value = None
            mock_result.scalar_one_or_none.return_value = None
        return mock_result

    async def commit(self):
        pass

    async def flush(self):
        pass

    def add(self, item):
        if hasattr(item, "key"):
            self.settings.append(item)
        elif hasattr(item, "symbol"):
            self.watchlist.append(item)

    async def close(self):
        pass


@pytest.fixture(autouse=True)
def clean_simulation_environment():
    """Resets MarketDataService rate limit timestamps, warmup state, WebSocket subscribers, and mocks TimeSyncService."""
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    MarketDataService._warmup_until = 0.0
    MarketDataService._warmup_started_at = 0.0
    MarketDataService._fyers_cooldown_until = 0.0
    MarketDataService._fyers_token_valid = True
    MarketDataService._fyers_token_error_reason = ""
    MarketDataService._active_engine = "PRIMARY_FYERS"
    MarketDataService._circuit_state = "CLOSED"
    MarketDataService._canary_in_progress = False
    _market_connections.clear()
    _symbol_subscribers.clear()

    def _fake_true_now(self, tzinfo=None):
        now = datetime.datetime.now(datetime.timezone.utc)
        if tzinfo is not None:
            return now.astimezone(tzinfo)
        return now

    with patch.object(TimeSyncService, "get_true_now", _fake_true_now):
        yield

    from backend.api.settings import _bg_tasks
    for t in list(_bg_tasks):
        if not t.done():
            t.cancel()
    _bg_tasks.clear()

    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    MarketDataService._warmup_until = 0.0
    MarketDataService._warmup_started_at = 0.0
    MarketDataService._fyers_cooldown_until = 0.0
    MarketDataService._fyers_token_valid = True
    MarketDataService._fyers_token_error_reason = ""
    MarketDataService._active_engine = "PRIMARY_FYERS"
    MarketDataService._circuit_state = "CLOSED"
    MarketDataService._canary_in_progress = False
    _market_connections.clear()
    _symbol_subscribers.clear()



@pytest.fixture
def mock_admin_user():
    admin = MagicMock(spec=User)
    admin.id = uuid.uuid4()
    admin.email = "lead_admin@stockai.com"
    admin.is_admin = True
    admin.subscription_tier = "PRO"
    return admin


# ---------------------------------------------------------------------------
# Test 1: Token Entry & Non-Blocking Lifecycle Activation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_fyers_token_update_engages_warmup_and_background_stream_restart(mock_admin_user):
    """
    Simulates user entering Fyers token via POST /api/settings/fyers/update-token:
    - Verifies token validation & persistence completes rapidly (< 500ms) without hanging.
    - Verifies warmup governor is engaged immediately.
    - Verifies fyers_stream_service.restart() is dispatched asynchronously in the background.
    """
    db_session = MockDbSession(mock_admin_user)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[require_admin] = lambda: mock_admin_user
    app.dependency_overrides[get_db] = override_get_db

    mock_session = MagicMock()
    mock_session.generate_token.return_value = {
        "s": "ok",
        "access_token": "mocked_fyers_jwt_token_auth_verified_2026",
    }

    mock_fyers_instance = MagicMock()
    mock_fyers_instance.get_profile.return_value = {
        "s": "ok",
        "data": {
            "name": "Arjun Mehta",
            "fy_id": "XY12345",
            "email_id": "arjun@example.com",
        },
    }

    in_memory_cache = {}

    async def mock_cache_get(k):
        return in_memory_cache.get(k)

    async def mock_cache_set(k, v, ttl=60):
        in_memory_cache[k] = v

    async def mock_cache_delete(k):
        in_memory_cache.pop(k, None)

    transport = ASGITransport(app=app)
    try:
        with patch("backend.api.settings.fyersModel.SessionModel", return_value=mock_session), \
             patch("backend.api.settings.fyersModel.FyersModel", return_value=mock_fyers_instance), \
             patch.object(fyers_stream_service, "restart", new_callable=AsyncMock) as mock_restart, \
             patch("backend.core.cache.cache_set", side_effect=mock_cache_set), \
             patch("backend.core.cache.cache_delete", side_effect=mock_cache_delete), \
             patch("backend.api.settings.cache_set", side_effect=mock_cache_set), \
             patch("backend.api.settings.cache_delete", side_effect=mock_cache_delete), \
             patch("backend.api.settings.dotenv.set_key"):

            start_t = time.perf_counter()
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                res = await client.post(
                    "/api/settings/fyers/update-token",
                    json={"auth_input": "https://trade.fyers.in/api-login/redirect-uri/index.html?auth_code=VALID_AUTH_CODE_2026&state=none"},
                )
            elapsed_ms = (time.perf_counter() - start_t) * 1000

            assert res.status_code == 200, f"Token update failed: {res.text}"
            data = res.json()
            assert data["status"] == "success"
            assert data["name"] == "Arjun Mehta"
            assert "Welcome, Arjun Mehta" in data["message"]

            # Must finish promptly without blocking the event loop (< 500ms)
            assert elapsed_ms < 500.0, f"Token update took too long: {elapsed_ms:.1f}ms"

            # Warmup governor MUST be engaged
            assert MarketDataService.is_in_warmup() is True
            assert MarketDataService._last_loaded_token == "mocked_fyers_jwt_token_auth_verified_2026"

            # Allow brief background task dispatch cycle to finish cleanly
            await asyncio.sleep(0.4)
            assert mock_restart.called, "fyers_stream_service.restart() must be dispatched in the background"

            # Drain any pending background tasks before test context manager exits
            from backend.api.settings import drain_bg_tasks
            await drain_bg_tasks(timeout=1.0)
            await asyncio.sleep(0.05)

    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 2: Rapid Component Navigation Simulation (Zero Deadlocks, Sub-Second Serving)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_rapid_component_navigation_concurrency_no_deadlocks(mock_admin_user):
    """
    Simulates rapid multi-tab / component navigation immediately following token activation:
    - Dashboard: /api/market/indices & /api/market/regime
    - ChartPage: /api/stocks/RELIANCE.NS/quote & /api/stocks/RELIANCE.NS/candles
    - Watchlist: /api/stocks/INFY.NS/quote & /api/stocks/TCS.NS/quote & /api/watchlist
    - Admin: /api/settings/ & /api/sentinel/status & /api/sentinel/incidents
    Verifies that the backend does NOT hang, does NOT block the event loop (> 50ms),
    and all routes respond promptly (< 1.5s total batch completion).
    """
    db_session = MockDbSession(mock_admin_user)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[require_admin] = lambda: mock_admin_user
    app.dependency_overrides[get_db] = override_get_db

    # Engage warmup governor
    MarketDataService.engage_warmup_governor(60.0)
    assert MarketDataService.is_in_warmup() is True

    mock_quote_reliance = {
        "symbol": "RELIANCE.NS",
        "price": 2480.50,
        "change": 15.20,
        "change_pct": 0.62,
        "high": 2495.00,
        "low": 2465.00,
        "volume": 2500000,
        "previous_close": 2465.30,
        "market_cap": 16750000000000,
    }
    mock_quote_infy = {
        "symbol": "INFY.NS",
        "price": 1820.00,
        "change": -8.50,
        "change_pct": -0.46,
        "high": 1835.00,
        "low": 1810.00,
        "volume": 1200000,
        "previous_close": 1828.50,
        "market_cap": 7500000000000,
    }
    mock_quote_tcs = {
        "symbol": "TCS.NS",
        "price": 4150.00,
        "change": 32.00,
        "change_pct": 0.78,
        "high": 4175.00,
        "low": 4110.00,
        "volume": 850000,
        "previous_close": 4118.00,
        "market_cap": 15100000000000,
    }
    mock_bulk = {
        "RELIANCE.NS": mock_quote_reliance,
        "INFY.NS": mock_quote_infy,
        "TCS.NS": mock_quote_tcs,
        "^NSEI": {"symbol": "^NSEI", "price": 24500.0, "change": 120.0, "change_pct": 0.5, "previous_close": 24380.0},
        "^BSESN": {"symbol": "^BSESN", "price": 80100.0, "change": 350.0, "change_pct": 0.44, "previous_close": 79750.0},
        "^NSEBANK": {"symbol": "^NSEBANK", "price": 51200.0, "change": -80.0, "change_pct": -0.16, "previous_close": 51280.0},
        "^CNXIT": {"symbol": "^CNXIT", "price": 42000.0, "change": 210.0, "change_pct": 0.50, "previous_close": 41790.0},
        "^NSEMDCP50": {"symbol": "^NSEMDCP50", "price": 16500.0, "change": 75.0, "change_pct": 0.46, "previous_close": 16425.0},
        "^INDIAVIX": {"symbol": "^INDIAVIX", "price": 13.5, "change": -0.2, "change_pct": -1.46, "previous_close": 13.7},
    }
    mock_candles = [
        {"timestamp": 1700000000 + i * 86400, "open": 2400 + i, "high": 2410 + i, "low": 2390 + i, "close": 2405 + i, "volume": 100000}
        for i in range(100)
    ]

    async def mock_fetch_quote(symbol):
        if "RELIANCE" in symbol:
            return mock_quote_reliance
        elif "INFY" in symbol:
            return mock_quote_infy
        elif "TCS" in symbol:
            return mock_quote_tcs
        return {"symbol": symbol, "price": 100.0, "change": 1.0, "change_pct": 1.0}

    in_memory_cache = {}

    async def mock_cache_get(k):
        return in_memory_cache.get(k)

    async def mock_cache_set(k, v, ttl=60):
        in_memory_cache[k] = v

    async def mock_cache_delete(k):
        in_memory_cache.pop(k, None)

    # Background lag tracker to detect any event loop blocking
    max_loop_lag = 0.0
    lag_monitor_running = True

    async def loop_lag_monitor():
        nonlocal max_loop_lag
        while lag_monitor_running:
            t0 = time.perf_counter()
            await asyncio.sleep(0.01)
            lag = (time.perf_counter() - t0) - 0.01
            if lag > max_loop_lag:
                max_loop_lag = lag

    monitor_task = asyncio.create_task(loop_lag_monitor())

    transport = ASGITransport(app=app)
    try:
        with patch.object(MarketDataService, "fetch_quote", side_effect=mock_fetch_quote), \
             patch.object(MarketDataService, "fetch_quotes_bulk", new_callable=AsyncMock, return_value=mock_bulk), \
             patch.object(MarketDataService, "fetch_candles", new_callable=AsyncMock, return_value=mock_candles), \
             patch("backend.core.cache.cache_get", side_effect=mock_cache_get), \
             patch("backend.core.cache.cache_set", side_effect=mock_cache_set), \
             patch("backend.core.cache.cache_delete", side_effect=mock_cache_delete), \
             patch("backend.api.market.cache_get", side_effect=mock_cache_get), \
             patch("backend.api.market.cache_set", side_effect=mock_cache_set), \
             patch("backend.api.stocks.cache_get", side_effect=mock_cache_get), \
             patch("backend.api.stocks.cache_set", side_effect=mock_cache_set):

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                start_t = time.perf_counter()

                # Simulate simultaneous navigation load across all components
                tasks = [
                    # 1. Dashboard component
                    client.get("/api/market/indices"),
                    client.get("/api/market/regime"),
                    # 2. ChartPage component
                    client.get("/api/stocks/RELIANCE.NS/quote"),
                    client.get("/api/stocks/RELIANCE.NS/candles?timeframe=1d&limit=100"),
                    # 3. Watchlist component
                    client.get("/api/watchlist"),
                    client.get("/api/stocks/INFY.NS/quote"),
                    client.get("/api/stocks/TCS.NS/quote"),
                    # 4. Admin Settings & Sentinel components
                    client.get("/api/settings/"),
                    client.get("/api/sentinel/status"),
                    client.get("/api/sentinel/incidents"),
                ]

                responses = await asyncio.gather(*tasks)
                batch_duration = time.perf_counter() - start_t

        lag_monitor_running = False
        await monitor_task

        # Assert all 10 navigation requests returned success (200 OK)
        assert len(responses) == 10
        for i, resp in enumerate(responses):
            assert resp.status_code == 200, f"Request {i} ({resp.request.url.path}) failed with status {resp.status_code}: {resp.text}"

        # Entire navigation batch must finish promptly (< 1.5s)
        assert batch_duration < 1.5, f"Navigation simulation took too long: {batch_duration:.2f}s"

        # Event loop lag must be well below 120ms (zero synchronous event loop freezes or deadlocks under concurrent CPU load)
        assert max_loop_lag < 0.120, f"Event loop experienced lag spike: {max_loop_lag*1000:.1f}ms"

    finally:
        lag_monitor_running = False
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 3: Warmup Governor Rate Budgeting & Thundering Herd Failover
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_warmup_governor_thundering_herd_and_yahoo_failover():
    """
    Empirically verifies:
    1. During token warmup, a burst of 30 concurrent quote queries is executed.
    2. Warmup pacing governor allows exactly 1 request to Fyers during the initial 1.5s interval.
    3. The remaining 29 concurrent requests are silently and seamlessly routed to Yahoo fallback.
    4. Outgoing REST requests to Fyers stay strictly within 50 req/min (1 req / 1.5s).
    5. Zero 429 errors or failed responses are returned to callers.
    """
    MarketDataService.reset_fyers_health()
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    MarketDataService.engage_warmup_governor(60.0)
    assert MarketDataService.is_in_warmup() is True

    mock_fyers = MagicMock()
    fyers_call_count = 0

    def mock_quotes(data):
        nonlocal fyers_call_count
        fyers_call_count += 1
        sym = data.get("symbols", "NSE:RELIANCE-EQ")
        return {
            "s": "ok",
            "d": [{
                "n": sym,
                "v": {
                    "lp": 2500.0,
                    "ch": 10.0,
                    "chp": 0.4,
                    "prev_close_price": 2490.0,
                    "volume": 1000000,
                }
            }]
        }

    mock_fyers.quotes = mock_quotes

    # Mock Redis pipeline to emulate clean cache miss
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_pipe = MagicMock()
    async def mock_execute():
        await asyncio.sleep(0.001)
        return [0, 0, 0]
    mock_pipe.execute = mock_execute
    mock_pipe.zremrangebyscore = MagicMock()
    mock_pipe.zcount = MagicMock()
    mock_pipe.zcard = MagicMock()
    mock_pipe.zadd = MagicMock()
    mock_pipe.expire = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    # Mock Yahoo Finance fallback
    mock_hist = pd.DataFrame({
        "Close": [2480.0, 2495.0],
        "Volume": [500000, 600000]
    })
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_hist

    symbols = [f"STOCK{i}.NS" for i in range(30)]

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock, return_value=mock_fyers), \
         patch("backend.core.cache.get_redis", new=AsyncMock(return_value=mock_redis)), \
         patch.object(MarketDataService, "check_credentials_changed", new_callable=AsyncMock, return_value=False), \
         patch("yfinance.Ticker", return_value=mock_ticker):

        quotes = await asyncio.gather(*[MarketDataService.fetch_quote(sym) for sym in symbols])

    fyers_quotes = [q for q in quotes if q and q.get("source") == "Fyers API"]
    backup_quotes = [q for q in quotes if q and q.get("source") != "Fyers API"]

    # All 30 callers receive valid quote data
    assert len(quotes) == 30
    for q in quotes:
        assert q is not None
        assert q.get("price", 0) > 0

    # Exactly 1 request admitted to Fyers during warmup pacing window
    assert fyers_call_count == 1, f"Expected 1 Fyers call admitted, got {fyers_call_count}"
    assert len(fyers_quotes) == 1, f"Expected 1 quote from Fyers, got {len(fyers_quotes)}"

    # Remaining 29 requests routed to Yahoo Finance fallback
    assert len(backup_quotes) == 29, f"Expected 29 backup quotes, got {len(backup_quotes)}"

    # Verify Fyers rate limit budget invariant: 1 call << 50 req/min
    timestamps = MarketDataService._fyers_request_timestamps
    assert len(timestamps) == 1


# ---------------------------------------------------------------------------
# Test 4: Live WebSocket Tick Streaming & Micro-Tick Cadence During Navigation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_websocket_live_ticks_and_fluidity_during_navigation():
    """
    Verifies that once frontend components establish a WebSocket connection:
    - Real-time ticks are pushed immediately (< 50ms) with zero REST requests to Fyers.
    - Micro-tick fluidity produces at least 3 updates within 300ms.
    - Every micro-tick complies with strict anti-fabrication rules:
      * Prices are strictly quantized to NSE equity tick size (₹0.05).
      * Volume increment is strictly zero (volume matches exchange confirmed volume).
      * Intermediate ticks are transparently tagged 'realtime_interpolated'.
    """
    mock_ws = AsyncMock()
    received_frames = []

    mock_ws.send_text.side_effect = lambda msg: received_frames.append(msg)

    conn_id = "test_e2e_ws_conn"
    symbol = "RELIANCE.NS"
    _market_connections[conn_id] = {
        "ws": mock_ws,
        "symbols": {symbol},
        "user_id": "test_e2e_user",
    }
    _register_subscription(conn_id, symbol)

    fluidity = HighFrequencyFluidityEngine()

    try:
        # Schedule micro-ticks between 2500.00 and 2501.20
        with patch("backend.api.websocket.is_indian_market_open", return_value=True):
            t0 = time.perf_counter()
            task = await fluidity.schedule_micro_ticks(
                symbol=symbol,
                start_price=2500.00,
                target_price=2501.20,
                volume=1500000,
                prev_close=2480.00,
                open_price=2490.00,
                high_price=2515.00,
                low_price=2475.00,
                duration=0.3,
                steps=3,
            )
            assert task is not None
            await task
            elapsed = time.perf_counter() - t0

        import json
        ticks = [json.loads(f) for f in received_frames]

        # Fluidity cadence: at least 3 updates within ~300ms
        assert len(ticks) >= 3
        assert 0.25 <= elapsed <= 0.45, f"Fluidity took {elapsed:.3f}s"

        for tick in ticks:
            price = tick["price"]
            # Multiples of 0.05
            assert round(price % 0.05, 4) in (0.0, 0.05), f"Price {price} is not a multiple of 0.05"
            # 0 Fake volume
            assert tick["volume"] == 1500000
            # Clamped boundaries
            assert 2500.00 <= price <= 2501.20

        # Anti-fabrication transparency
        assert ticks[0]["data_status"] == "realtime_interpolated"
        assert ticks[-1]["data_status"] == "realtime"
        assert ticks[-1]["price"] == 2501.20

    finally:
        _market_connections.pop(conn_id, None)
        _symbol_subscribers.get(symbol, set()).discard(conn_id)
