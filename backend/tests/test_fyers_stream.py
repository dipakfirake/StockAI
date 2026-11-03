"""Unit tests for FyersStreamService."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.fyers_stream import FyersStreamService


@pytest.fixture
def stream_service():
    service = FyersStreamService()
    return service


def test_fyers_stream_singleton():
    """Verify singleton returns the same instance."""
    s1 = FyersStreamService.get_instance()
    s2 = FyersStreamService.get_instance()
    assert s1 is s2


@pytest.mark.asyncio
async def test_fyers_stream_start_without_creds(stream_service):
    """If no Fyers credentials exist, start() gracefully returns False without crashing."""
    with patch("backend.services.fyers_stream.settings") as mock_settings:
        mock_settings.FYERS_CLIENT_ID = None
        mock_settings.FYERS_ACCESS_TOKEN = None
        
        with patch("backend.services.market_data.MarketDataService._env_cache", {}), \
             patch("backend.core.cache.cache_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.core.database.AsyncSessionLocal", side_effect=Exception("No DB")):
            result = await stream_service.start()
            assert result is False
            assert stream_service.is_connected is False


@pytest.mark.asyncio
async def test_subscribe_symbols_normalizes_and_maps(stream_service):
    """Subscribing adds normalized symbols to internal tracking."""
    symbols = ["RELIANCE", "TCS.NS", "^NSEI"]
    await stream_service.subscribe_symbols(symbols)

    assert "NSE:RELIANCE-EQ" in stream_service._subscribed_symbols
    assert "NSE:TCS-EQ" in stream_service._subscribed_symbols
    assert "NSE:NIFTY50-INDEX" in stream_service._subscribed_symbols
    assert stream_service._symbol_map.get("NSE:RELIANCE-EQ") == "RELIANCE.NS"
    assert stream_service._symbol_map.get("NSE:NIFTY50-INDEX") == "^NSEI"


@pytest.mark.asyncio
async def test_on_tick_dispatches_broadcast_and_cache(stream_service):
    """When a tick arrives, it resolves the mapped symbol and dispatches broadcast."""
    mock_loop = MagicMock()
    mock_loop.is_running.return_value = True
    stream_service._loop = mock_loop
    stream_service._symbol_map["NSE:RELIANCE-EQ"] = "RELIANCE.NS"

    tick = {
        "symbol": "NSE:RELIANCE-EQ",
        "ltp": 2850.50,
        "ch": 15.50,
        "chp": 0.55,
        "vol_traded_today": 3500000,
        "open_price": 2840.0,
        "high_price": 2860.0,
        "low_price": 2835.0,
        "timestamp": "1710000000"
    }

    with patch("asyncio.run_coroutine_threadsafe") as mock_run_coro:
        def _fake_run_coro(coro, loop):
            coro.close()
            return MagicMock()
        mock_run_coro.side_effect = _fake_run_coro
        stream_service._on_tick(tick)
        # Should call run_coroutine_threadsafe for broadcast and multi-key cache update
        assert mock_run_coro.call_count >= 2


@pytest.mark.asyncio
async def test_stop_cleans_up_socket(stream_service):
    """Calling stop() resets running state and closes socket."""
    mock_socket = MagicMock()
    stream_service._socket = mock_socket
    stream_service._is_connected = True
    stream_service._is_running = True

    await stream_service.stop()

    assert stream_service._is_connected is False
    assert stream_service._is_running is False
    assert stream_service._socket is None
    mock_socket.close_connection.assert_called_once()


import asyncio
import time
from backend.services.market_data import MarketDataService
from backend.services.fyers_stream import _HSM_TOKEN_MEMORY_CACHE


@pytest.mark.asyncio
async def test_fyers_stream_lifecycle_lock_serialization(stream_service):
    """Verify that start(), stop(), and restart() serialize cleanly via _lifecycle_lock."""
    execution_order = []

    async def fake_start_internal():
        execution_order.append("start_begin")
        await asyncio.sleep(0.05)
        execution_order.append("start_end")
        return True

    async def fake_stop_internal():
        execution_order.append("stop_begin")
        await asyncio.sleep(0.05)
        execution_order.append("stop_end")

    with patch.object(stream_service, "_start_internal", side_effect=fake_start_internal), \
         patch.object(stream_service, "_stop_internal", side_effect=fake_stop_internal):

        # Launch concurrent stop and restart
        t1 = asyncio.create_task(stream_service.start())
        t2 = asyncio.create_task(stream_service.restart())

        await asyncio.gather(t1, t2)

        # Confirm non-overlapping serialization
        assert execution_order == [
            "start_begin", "start_end",
            "stop_begin", "stop_end",
            "start_begin", "start_end"
        ]


@pytest.mark.asyncio
async def test_fyers_stream_connect_timeout_handling(stream_service):
    """If socket.connect blocks beyond the 3.0s timeout guard, start() cleanly returns False."""
    mock_socket_class = MagicMock()
    mock_socket = MagicMock()

    def hanging_connect():
        import time
        time.sleep(5.0)

    mock_socket.connect.side_effect = hanging_connect
    mock_socket_class.return_value = mock_socket

    with patch("backend.services.fyers_stream.FyersDataSocket", mock_socket_class), \
         patch("backend.services.fyers_stream.settings") as mock_settings:
        mock_settings.FYERS_CLIENT_ID = "DEMO_CLIENT"
        mock_settings.FYERS_ACCESS_TOKEN = "DEMO_TOKEN_12345"

        orig_wait_for = asyncio.wait_for

        async def fast_wait_for(coro, timeout):
            return await orig_wait_for(coro, timeout=0.05)

        with patch("asyncio.wait_for", side_effect=fast_wait_for):
            res = await stream_service.start()
            assert res is False
            assert stream_service.is_connected is False
            assert stream_service.is_running is False


@pytest.mark.asyncio
async def test_fyers_stream_close_timeout_handling(stream_service):
    """If socket.close_connection blocks beyond 3.0s (e.g. thread join), stop() catches timeout."""
    mock_socket = MagicMock()

    def hanging_close():
        import time
        time.sleep(5.0)

    mock_socket.close_connection.side_effect = hanging_close
    stream_service._socket = mock_socket
    stream_service._is_connected = True
    stream_service._is_running = True

    orig_wait_for = asyncio.wait_for

    async def fast_wait_for(coro, timeout):
        return await orig_wait_for(coro, timeout=0.05)

    with patch("asyncio.wait_for", side_effect=fast_wait_for):
        await stream_service.stop()

        assert stream_service.is_connected is False
        assert stream_service.is_running is False
        assert stream_service._socket is None


@pytest.mark.asyncio
async def test_hsm_token_resolution_and_caching(stream_service):
    """Verify HSM token resolution reads Redis cache (24h TTL) and falls back to HTTP."""
    _HSM_TOKEN_MEMORY_CACHE.clear()

    redis_cache = {}

    async def fake_cache_get(key):
        return redis_cache.get(key)

    async def fake_cache_set(key, val, ttl=60):
        redis_cache[key] = val

    # Seed Redis cache for RELIANCE
    redis_cache["fyers:hsm_token:NSE:RELIANCE-EQ"] = {
        "fyToken": "10100000002885",
        "symbol": "NSE:RELIANCE-EQ"
    }

    with patch("backend.core.cache.cache_get", side_effect=fake_cache_get), \
         patch("backend.core.cache.cache_set", side_effect=fake_cache_set), \
         patch.object(stream_service, "_fetch_hsm_tokens_http") as mock_http:

        mock_http.return_value = {
            "NSE:INFY-EQ": {
                "fyToken": "10100000001594",
                "symbol": "NSE:INFY-EQ"
            }
        }
        stream_service._client_id = "TEST_ID"
        stream_service._access_token = "TEST_TOK"

        await stream_service._resolve_and_cache_hsm_tokens(["NSE:RELIANCE-EQ", "NSE:INFY-EQ"])

        assert "NSE:RELIANCE-EQ" in _HSM_TOKEN_MEMORY_CACHE
        assert "NSE:INFY-EQ" in _HSM_TOKEN_MEMORY_CACHE
        assert redis_cache.get("fyers:hsm_token:NSE:INFY-EQ") is not None
        mock_http.assert_called_once()
        queried_symbols = mock_http.call_args[0][0]
        assert "NSE:INFY-EQ" in queried_symbols
        assert "NSE:RELIANCE-EQ" not in queried_symbols


@pytest.mark.asyncio
async def test_non_blocking_chunked_symbol_subscriptions(stream_service):
    """Verify that subscriptions are chunked into batches of 20 and pace across chunks."""
    stream_service._socket = MagicMock()
    stream_service._is_connected = True

    symbols = [f"NSE:SYM{i}-EQ" for i in range(45)]
    subscribed_chunks = []

    def fake_subscribe(symbols, data_type):
        subscribed_chunks.append(list(symbols))

    stream_service._socket.subscribe.side_effect = fake_subscribe

    with patch.object(stream_service, "_resolve_and_cache_hsm_tokens", new_callable=AsyncMock), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:

        await stream_service._subscribe_chunks(symbols)

        assert len(subscribed_chunks) == 3
        assert len(subscribed_chunks[0]) == 20
        assert len(subscribed_chunks[1]) == 20
        assert len(subscribed_chunks[2]) == 5
        assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_restart_deduplication_in_market_data():
    """Verify that concurrent stream restart calls in check_credentials_changed are debounced."""
    MarketDataService._last_loaded_token = "OLD_TOKEN"
    MarketDataService._last_restart_dispatch_time = 0.0

    restart_calls = []

    async def fake_restart():
        restart_calls.append(time.time())
        return True

    with patch("backend.services.fyers_stream.fyers_stream_service.restart", side_effect=fake_restart), \
         patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock), \
         patch("backend.core.database.AsyncSessionLocal", side_effect=Exception("No DB")):

        with patch("backend.core.cache.cache_get", new_callable=AsyncMock, return_value={"access_token": "NEW_TOKEN"}):
            changed1 = await MarketDataService.check_credentials_changed()
            assert changed1 is True

            changed2 = await MarketDataService.check_credentials_changed()
            assert changed2 is False

            # Reset token check throttle interval to simulate next check pass
            MarketDataService._last_token_check_time = 0.0
            MarketDataService._last_loaded_token = "YET_ANOTHER"
            with patch("backend.core.cache.cache_get", new_callable=AsyncMock, return_value={"access_token": "TOKEN_RAPID"}):
                changed3 = await MarketDataService.check_credentials_changed()
                assert changed3 is True

            await asyncio.sleep(0.05)
            # Despite credential change, restart was debounced within 3.0s window
            assert len(restart_calls) == 1


@pytest.mark.asyncio
async def test_rate_budget_warmup_governor_pacing():
    """Verify that 60s warmup governor restricts burst requests and routes excess to fallback."""
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0

    MarketDataService.engage_warmup_governor(duration_seconds=60.0)
    assert MarketDataService.is_in_warmup() is True

    now = time.time()
    admitted1 = MarketDataService._check_and_record_fyers_rate_budget()
    assert admitted1 is True

    # Immediate 2nd request at t=0.1s (< 1.5s warmup spacing): denied
    admitted2 = MarketDataService._check_and_record_fyers_rate_budget()
    assert admitted2 is False

    with patch("time.time", return_value=now + 1.6):
        admitted3 = MarketDataService._check_and_record_fyers_rate_budget()
        assert admitted3 is True

    with patch("time.time", return_value=now + 65.0):
        assert MarketDataService.is_in_warmup() is False
        admitted4 = MarketDataService._check_and_record_fyers_rate_budget()
        assert admitted4 is True


@pytest.mark.asyncio
async def test_candle_pagination_rate_limit_tracking():
    """Verify that fetch_candles records against rate budget and halts when quota exhausted."""
    MarketDataService.reset_fyers_health()
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0

    mock_fyers = MagicMock()
    mock_fyers.history.return_value = {
        "s": "ok",
        "candles": [
            [1680000000, 100.0, 105.0, 95.0, 102.0, 50000]
        ]
    }

    call_count = 0

    async def mock_rate_budget():
        nonlocal call_count
        call_count += 1
        return call_count <= 1  # Chunk 1 admitted, chunk 2 denied

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock, return_value=mock_fyers), \
         patch.object(MarketDataService, "check_and_record_fyers_rate_budget", side_effect=mock_rate_budget), \
         patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("backend.services.market_data.cache_set", new_callable=AsyncMock), \
         patch("asyncio.sleep", new_callable=AsyncMock):

        # Explicit date range spanning 250 days with 100-day max chunk size -> requires multiple chunks
        candles = await MarketDataService.fetch_candles(
            "RELIANCE.NS",
            "15m",
            start_date="2023-01-01",
            end_date="2023-09-01"
        )

        assert len(candles) >= 1
        assert call_count >= 2


