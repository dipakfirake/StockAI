"""
Unit tests for Ticker Update Architecture and Consolidated Indices Request.

Verifies:
1. Single consolidated request for /api/market/indices returns both Nifty 50 and Nifty Bank.
2. Cache reuse prevents duplicate upstream calls to broker APIs.
3. Market update broadcasts deliver real-time price change events for subscribed index symbols.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.market_data import MarketDataService
from backend.api.websocket import broadcast_market_update, _market_connections


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_consolidated_indices_endpoint_returns_nifty_and_banknifty():
    """Verify GET /api/market/indices delivers consolidated indices with valid fields."""
    mock_quotes = {
        "^NSEI": {"price": 24500.5, "change": 120.5, "change_pct": 0.49, "previous_close": 24380.0},
        "^BSESN": {"price": 80100.0, "change": 350.0, "change_pct": 0.44, "previous_close": 79750.0},
        "^NSEBANK": {"price": 51200.0, "change": -80.0, "change_pct": -0.16, "previous_close": 51280.0},
        "^CNXIT": {"price": 42000.0, "change": 210.0, "change_pct": 0.50, "previous_close": 41790.0},
        "^NSEMDCP50": {"price": 16500.0, "change": 75.0, "change_pct": 0.46, "previous_close": 16425.0},
        "^INDIAVIX": {"price": 13.5, "change": -0.2, "change_pct": -1.46, "previous_close": 13.7},
    }

    with patch("backend.api.market.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("backend.api.market.cache_set", new_callable=AsyncMock) as mock_cache_set, \
         patch("backend.api.market.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock, return_value=mock_quotes) as mock_bulk:

        with TestClient(app) as test_client:
            resp = test_client.get("/api/market/indices")
            assert resp.status_code == 200
            data = resp.json()
            assert "indices" in data
            indices = data["indices"]

            # Verify single consolidated request fetched all index symbols in one call
            assert mock_bulk.call_count == 1
            requested_symbols = mock_bulk.call_args[0][0]
            assert "^NSEI" in requested_symbols
            assert "^NSEBANK" in requested_symbols

            # Verify Nifty 50 and Nifty Bank are present with accurate price fields
            n50 = next((i for i in indices if i["name"] == "Nifty 50"), None)
            assert n50 is not None
            assert n50["symbol"] == "^NSEI"
            assert n50["price"] == 24500.5
            assert n50["change"] == 120.5

            bnf = next((i for i in indices if i["name"] == "Nifty Bank"), None)
            assert bnf is not None
            assert bnf["symbol"] == "^NSEBANK"
            assert bnf["price"] == 51200.0
            assert bnf["change"] == -80.0

            # Verify caching was performed to prevent redundant network calls
            assert mock_cache_set.call_count >= 1


@pytest.mark.asyncio
async def test_cached_consolidated_indices_bypasses_upstream_fetch():
    """Verify that cached indices are served directly without triggering bulk broker fetches."""
    cached_payload = {
        "indices": [
            {"name": "Nifty 50", "symbol": "^NSEI", "price": 24550.0, "change": 170.0, "change_pct": 0.70},
            {"name": "Nifty Bank", "symbol": "^NSEBANK", "price": 51300.0, "change": 20.0, "change_pct": 0.04},
        ]
    }

    with patch("backend.api.market.cache_get", new_callable=AsyncMock, return_value=cached_payload), \
         patch("backend.api.market.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_bulk:

        with TestClient(app) as test_client:
            resp = test_client.get("/api/market/indices")
            assert resp.status_code == 200
            data = resp.json()
            assert data["indices"][0]["price"] == 24550.0
            # Upstream bulk fetch must not be called when cache is fresh
            mock_bulk.assert_not_called()


@pytest.mark.asyncio
async def test_price_change_broadcast_delivers_to_subscribed_ticker():
    """Verify WebSocket broadcast sends market_update when a price change occurs."""
    mock_ws = AsyncMock()
    conn_id = "test_ticker_conn_1"
    _market_connections[conn_id] = {
        "ws": mock_ws,
        "symbols": {"^NSEI", "^NSEBANK"},
        "user_id": "test_user_1",
    }

    try:
        await broadcast_market_update(
            symbol="^NSEI",
            price=24600.75,
            change=220.75,
            change_pct=0.91,
        )

        mock_ws.send_text.assert_called_once()
        sent_payload = mock_ws.send_text.call_args[0][0]
        assert '"type": "market_update"' in sent_payload
        assert '"symbol": "^NSEI"' in sent_payload
        assert '24600.75' in sent_payload
    finally:
        _market_connections.pop(conn_id, None)
