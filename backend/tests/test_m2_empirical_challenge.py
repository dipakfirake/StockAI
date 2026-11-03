"""
Empirical Challenge Suite for Milestone 2:
- High-Frequency WebSocket Streaming (>= 3 updates/sec cadence)
- Zero REST API requests to Fyers during live streaming
- Micro-tick fluidity with ₹0.05 quantization, 0 fake volume, and strict clamping
- Inverted index fanout and resilient error handling
- Sentinel admin authorization defense-in-depth across all endpoints
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.api.websocket import (
    HighFrequencyFluidityEngine,
    quantize_tick,
    broadcast_market_update,
    _market_connections,
    _symbol_subscribers,
    _register_subscription,
    _unregister_connection,
    poll_market_data,
)
from backend.services.market_data import MarketDataService
from backend.services.fyers_stream import fyers_stream_service
from backend.core.auth import get_current_user
from backend.api.admin import require_admin
from backend.models.user import User


@pytest.fixture(autouse=True)
def clean_ws_state():
    """Ensure WebSocket connection maps and subscribers are clean for each test."""
    _market_connections.clear()
    _symbol_subscribers.clear()
    yield
    _market_connections.clear()
    _symbol_subscribers.clear()


@pytest.mark.asyncio
async def test_m2_price_fluidity_cadence_and_quantization():
    """
    Empirically verify:
    1. At least 3 updates emitted within 300ms window (>= 3 updates/sec cadence).
    2. Every single intermediate and final price is an exact multiple of ₹0.05.
    3. Volume remains strictly 0 increment (broker-confirmed volume).
    4. Clamped within min/max boundaries and day's high/low.
    5. Data status transparently tagged 'realtime_interpolated' and 'realtime'.
    """
    engine = HighFrequencyFluidityEngine()
    sent_ticks = []
    mock_ws = AsyncMock()
    mock_ws.send_text.side_effect = lambda msg: sent_ticks.append(json.loads(msg))

    conn_id = "test_conn_fluidity"
    symbol = "RELIANCE.NS"
    _market_connections[conn_id] = {
        "ws": mock_ws,
        "symbols": {symbol},
        "user_id": "test_user_fluidity",
    }
    _register_subscription(conn_id, symbol)

    # Test 1: Uptick with non-trivial decimals
    with patch("backend.api.websocket.is_indian_market_open", return_value=True):
        t0 = asyncio.get_event_loop().time()
        task = await engine.schedule_micro_ticks(
            symbol=symbol,
            start_price=2450.12,
            target_price=2451.87,
            volume=125000,
            prev_close=2440.00,
            open_price=2445.00,
            high_price=2460.00,
            low_price=2435.00,
            duration=0.3,
            steps=3,
        )
        assert task is not None
        await task
        t1 = asyncio.get_event_loop().time()

    elapsed = t1 - t0
    # Must have delivered at least 3 updates within roughly 300ms
    assert len(sent_ticks) == 3
    assert 0.25 <= elapsed <= 0.45, f"Expected ~0.3s, took {elapsed:.3f}s"

    for tick in sent_ticks:
        price = tick["price"]
        # Quantization: strictly ₹0.05 multiples
        assert round(price % 0.05, 4) in (0.0, 0.05), f"Price {price} is not a multiple of 0.05"
        # 0 Fake volume: volume strictly matches 125000
        assert tick["volume"] == 125000
        # Clamped within bounds
        assert 2450.00 <= price <= 2452.00

    assert sent_ticks[0]["data_status"] == "realtime_interpolated"
    assert sent_ticks[1]["data_status"] == "realtime_interpolated"
    assert sent_ticks[2]["data_status"] == "realtime"
    assert sent_ticks[2]["price"] == quantize_tick(2451.87)

    # Test 2: Downtick
    sent_ticks.clear()
    with patch("backend.api.websocket.is_indian_market_open", return_value=True):
        task2 = await engine.schedule_micro_ticks(
            symbol=symbol,
            start_price=2451.85,
            target_price=2449.30,
            volume=130000,
            prev_close=2440.00,
            duration=0.3,
            steps=3,
        )
        assert task2 is not None
        await task2

    assert len(sent_ticks) == 3
    for tick in sent_ticks:
        price = tick["price"]
        assert round(price % 0.05, 4) in (0.0, 0.05)
        assert tick["volume"] == 130000
        assert 2449.25 <= price <= 2451.90

    assert sent_ticks[2]["price"] == quantize_tick(2449.30)


@pytest.mark.asyncio
async def test_m2_zero_rest_calls_during_live_streaming():
    """
    Empirically verify:
    When Fyers WebSocket stream is connected, poll_market_data makes ZERO REST
    API calls to Fyers or upstream fallback.
    """
    conn_id = "test_zero_rest_conn"
    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    mock_ws = AsyncMock()
    _market_connections[conn_id] = {
        "ws": mock_ws,
        "symbols": set(symbols),
        "user_id": "test_zero_rest_user",
    }
    for s in symbols:
        _register_subscription(conn_id, s)

    from unittest.mock import PropertyMock
    with patch("backend.services.fyers_stream.FyersStreamService.is_connected", new_callable=PropertyMock, return_value=True), \
         patch.object(MarketDataService, "_fyers_token_valid", True), \
         patch.object(fyers_stream_service, "subscribe_symbols", new_callable=AsyncMock) as mock_sub, \
         patch("backend.services.market_data.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_bulk:

        # Run poll_market_data with a timeout to execute one poll cycle
        poll_task = asyncio.create_task(poll_market_data())
        await asyncio.sleep(0.05)
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass

        # Verification:
        # 1. Zero REST calls were made
        mock_bulk.assert_not_called()
        # 2. WebSocket subscription check was performed
        mock_sub.assert_called_once()
        subscribed_args = mock_sub.call_args[0][0]
        for s in symbols:
            assert s in subscribed_args


@pytest.mark.asyncio
async def test_m2_fluidity_engine_anti_fabrication_and_cancellation():
    """
    Verify SEBI anti-fabrication and cancellation behavior:
    1. When market is closed (is_indian_market_open() == False), schedule_micro_ticks returns None.
    2. Rapid consecutive ticks cancel previous micro-tick interpolation without crash.
    """
    engine = HighFrequencyFluidityEngine()
    symbol = "HDFCBANK.NS"

    # 1. Market closed -> schedule_micro_ticks must return None
    with patch("backend.api.websocket.is_indian_market_open", return_value=False):
        task = await engine.schedule_micro_ticks(
            symbol=symbol,
            start_price=1600.00,
            target_price=1602.00,
            volume=50000,
            prev_close=1590.00,
        )
        assert task is None

    # 2. Rapid cancellation
    sent_ticks = []
    mock_ws = AsyncMock()
    mock_ws.send_text.side_effect = lambda msg: sent_ticks.append(json.loads(msg))
    conn_id = "test_cancel_conn"
    _market_connections[conn_id] = {
        "ws": mock_ws,
        "symbols": {symbol},
        "user_id": "test_user",
    }
    _register_subscription(conn_id, symbol)

    with patch("backend.api.websocket.is_indian_market_open", return_value=True):
        # Start tick 1
        task1 = await engine.schedule_micro_ticks(
            symbol=symbol,
            start_price=1600.00,
            target_price=1610.00,
            volume=50000,
            prev_close=1590.00,
            duration=0.5,
            steps=5,
        )
        assert task1 is not None

        # Immediately override with tick 2
        await asyncio.sleep(0.05)
        task2 = await engine.schedule_micro_ticks(
            symbol=symbol,
            start_price=1602.00,
            target_price=1605.00,
            volume=52000,
            prev_close=1590.00,
            duration=0.2,
            steps=3,
        )
        assert task2 is not None

        await task2
        # Ensure task1 was cancelled
        assert task1.cancelled() or task1.done()

    # Final price in sent_ticks must match tick 2's target price
    assert len(sent_ticks) >= 1
    final_tick = sent_ticks[-1]
    assert final_tick["price"] == quantize_tick(1605.00)
    assert final_tick["volume"] == 52000


@pytest.mark.asyncio
async def test_m2_inverted_index_fanout_and_resilient_disconnect():
    """
    Verify O(1) inverted index subscriber lookup, concurrent broadcast,
    and resilient disconnect unregistration when a client drops.
    """
    sent_c1 = []
    sent_c2 = []
    sent_c3 = []

    ws1 = AsyncMock()
    ws1.send_text.side_effect = lambda msg: sent_c1.append(json.loads(msg))

    ws2 = AsyncMock()
    ws2.send_text.side_effect = lambda msg: sent_c2.append(json.loads(msg))

    # ws3 simulates a broken connection raising an exception
    ws3 = AsyncMock()
    ws3.send_text.side_effect = RuntimeError("Client disconnected abruptly")

    _market_connections["c1"] = {"ws": ws1, "symbols": {"RELIANCE.NS"}, "user_id": "u1"}
    _register_subscription("c1", "RELIANCE.NS")

    _market_connections["c2"] = {"ws": ws2, "symbols": {"TCS.NS"}, "user_id": "u2"}
    _register_subscription("c2", "TCS.NS")

    _market_connections["c3"] = {"ws": ws3, "symbols": {"RELIANCE.NS"}, "user_id": "u3"}
    _register_subscription("c3", "RELIANCE.NS")

    # Broadcast tick for RELIANCE.NS
    await broadcast_market_update(
        symbol="RELIANCE.NS",
        price=2480.00,
        change=15.00,
        change_pct=0.61,
        volume=80000,
    )

    # c1 got the update
    assert len(sent_c1) == 1
    assert sent_c1[0]["symbol"] == "RELIANCE.NS"
    assert sent_c1[0]["price"] == 2480.00

    # c2 is only subscribed to TCS.NS, so must NOT have received RELIANCE.NS
    assert len(sent_c2) == 0

    # c3 threw an exception: verify c3 was cleanly unregistered from _market_connections
    assert "c3" not in _market_connections
    assert "c3" not in _symbol_subscribers.get("RELIANCE.NS", set())


@pytest.mark.asyncio
async def test_m2_sentinel_admin_authorization_enforcement():
    """
    Verify defense-in-depth authorization across ALL 5 Sentinel endpoints:
    Non-admin user receives HTTP 403 Forbidden on:
    1. GET /api/sentinel/status
    2. GET /api/sentinel/incidents
    3. POST /api/sentinel/audit-now
    4. POST /api/sentinel/resolve
    5. POST /api/sentinel/resolve/{incident_id}
    """
    mock_non_admin = MagicMock(spec=User, id="normal-user", email="user@stockai.com", is_admin=False)
    app.dependency_overrides[get_current_user] = lambda: mock_non_admin
    app.dependency_overrides.pop(require_admin, None)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. GET /api/sentinel/status
            r1 = await client.get("/api/sentinel/status")
            assert r1.status_code == 403, f"Expected 403 on status, got {r1.status_code}"

            # 2. GET /api/sentinel/incidents
            r2 = await client.get("/api/sentinel/incidents")
            assert r2.status_code == 403, f"Expected 403 on incidents, got {r2.status_code}"

            # 3. POST /api/sentinel/audit-now
            r3 = await client.post("/api/sentinel/audit-now")
            assert r3.status_code == 403, f"Expected 403 on audit-now, got {r3.status_code}"

            # 4. POST /api/sentinel/resolve
            r4 = await client.post("/api/sentinel/resolve", json={"incident_id": "inc-test-1"})
            assert r4.status_code == 403, f"Expected 403 on resolve, got {r4.status_code}"

            # 5. POST /api/sentinel/resolve/{incident_id}
            r5 = await client.post("/api/sentinel/resolve/inc-test-1")
            assert r5.status_code == 403, f"Expected 403 on resolve/id, got {r5.status_code}"
    finally:
        app.dependency_overrides.clear()
