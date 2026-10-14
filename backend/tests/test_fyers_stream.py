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
        
        with patch("backend.services.market_data.MarketDataService._env_cache", {}):
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
        # Should call run_coroutine_threadsafe for broadcast and cache update
        assert mock_run_coro.call_count == 2


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
