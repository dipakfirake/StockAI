import pytest
import time
from unittest.mock import patch, MagicMock
from backend.services.market_data import MarketDataService

@pytest.mark.asyncio
async def test_direct_yahoo_chart_candles_fast_fallback():
    """Verify direct Yahoo Chart API is invoked as primary fallback and returns standard OHLCV candles."""
    MarketDataService._fyers_token_valid = False
    MarketDataService._fyers_cooldown_until = time.time() + 300.0

    t0 = time.time()
    candles = await MarketDataService.fetch_candles("RELIANCE.NS", "1d", limit=50)
    duration = time.time() - t0

    assert isinstance(candles, list)
    assert len(candles) > 0, "Should return candles via direct Yahoo chart fallback"
    assert "timestamp" in candles[-1]
    assert "close" in candles[-1]
    assert candles[-1]["close"] > 0
    # Should complete rapidly via direct chart API (< 12.0s even with cold connection)
    assert duration < 12.0, f"Expected < 12.0s, took {duration:.2f}s"

@pytest.mark.asyncio
async def test_direct_yahoo_chart_404_quarantine():
    """Verify 404 responses from Yahoo (delisted symbols) return empty list immediately without hanging."""
    MarketDataService._fyers_token_valid = False
    MarketDataService._fyers_cooldown_until = time.time() + 300.0

    t0 = time.time()
    candles = await MarketDataService.fetch_candles("NONEXISTENT_STOCK_XYZ.NS", "1d", limit=50)
    duration = time.time() - t0

    assert candles == []
    assert duration < 4.0, f"404 handling took too long: {duration:.2f}s"

@pytest.mark.asyncio
async def test_fyers_code_minus_15_triggers_immediate_token_expiry():
    """Verify that code -15 in history pagination immediately marks token expired and halts further chunks."""
    MarketDataService._fyers_token_valid = True
    MarketDataService._fyers_cooldown_until = 0.0

    mock_fyers = MagicMock()
    mock_fyers.history.return_value = {
        "s": "error",
        "code": -15,
        "message": "Please provide a valid token",
    }

    with patch.object(MarketDataService, "_get_fyers_client", return_value=mock_fyers):
        with patch.object(MarketDataService, "acquire_fyers_rate_budget_slot", return_value=True):
            candles = await MarketDataService.fetch_candles("INFY.NS", "1d", limit=100)
            assert MarketDataService._fyers_token_valid is False
            assert "code -15" in MarketDataService._fyers_token_error_reason.lower()
