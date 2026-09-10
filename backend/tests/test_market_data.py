"""Unit tests for market data service."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from types import SimpleNamespace
import pandas as pd
from datetime import datetime

from backend.services.market_data import MarketDataService


@pytest.fixture
def sample_candles():
    return [
        {"timestamp": "2024-01-02T00:00:00", "open": 100.0, "high": 105.0, "low": 99.0, "close": 103.0, "volume": 1000000},
        {"timestamp": "2024-01-03T00:00:00", "open": 103.0, "high": 108.0, "low": 101.0, "close": 106.0, "volume": 1200000},
        {"timestamp": "2024-01-04T00:00:00", "open": 106.0, "high": 110.0, "low": 104.0, "close": 109.0, "volume": 900000},
    ]


def test_normalise_symbol_adds_ns_suffix():
    """Symbol without suffix should get NSE-EQ appended."""
    result = MarketDataService._normalise_symbol("RELIANCE")
    assert result == "NSE:RELIANCE-EQ"


def test_normalise_symbol_preserves_existing_suffix():
    """Symbol with .BO suffix should map to BSE-EQ."""
    result = MarketDataService._normalise_symbol("RELIANCE.BO")
    assert result == "BSE:RELIANCE-EQ"


def test_normalise_symbol_uppercases():
    """Symbol should always be uppercased and map to NSE-EQ."""
    result = MarketDataService._normalise_symbol("reliance")
    assert result == "NSE:RELIANCE-EQ"


@pytest.mark.asyncio
@patch("backend.services.market_data.cache_get", return_value=None)
@patch("backend.services.market_data.cache_set", new_callable=AsyncMock)
async def test_fetch_candles_returns_list(mock_cache_set, mock_cache_get):
    """fetch_candles should return a list of candle dicts."""
    mock_df = pd.DataFrame({
        "Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1000000]
    }, index=pd.DatetimeIndex([datetime(2024, 1, 2)]))

    with patch("backend.services.market_data.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.return_value = mock_df
        mock_ticker.return_value = mock_instance

        result = await MarketDataService.fetch_candles("RELIANCE.NS", "1d", 10)

    assert isinstance(result, list)
    if result:
        assert "open" in result[0]
        assert "close" in result[0]
        assert "volume" in result[0]


@pytest.mark.asyncio
@patch("backend.services.market_data.cache_get", return_value=None)
@patch("backend.services.market_data.cache_set", new_callable=AsyncMock)
async def test_fetch_candles_bse_dual_fetch_fallback(mock_cache_set, mock_cache_get):
    """BSE (.BO) stocks should attempt yfinance fallback if Fyers fails."""
    mock_df_valid = pd.DataFrame({
        "Open": [100.0], "High": [105.0], "Low": [99.0], "Close": [103.0], "Volume": [1000000]
    }, index=pd.DatetimeIndex([datetime(2024, 1, 2)]))

    with patch("backend.services.market_data.MarketDataService._get_fyers_client") as mock_fyers:
        # Mock Fyers to raise an exception, forcing fallback
        mock_fyers.side_effect = Exception("Fyers failed")
        
        with patch("backend.services.market_data.yf.Ticker") as mock_ticker:
            mock_instance = MagicMock()
            mock_instance.history.return_value = mock_df_valid
            mock_ticker.return_value = mock_instance

            result = await MarketDataService.fetch_candles("SMESTOCK.BO", "1d", 10)

            # Verify the fallback succeeded and returned data
            assert len(result) == 1
            assert result[0]["close"] == 103.0


@pytest.mark.asyncio
@patch("backend.services.market_data.cache_get", return_value=None)
@patch("backend.services.market_data.cache_set", new_callable=AsyncMock)
async def test_fetch_candles_invalid_timeframe(mock_cache_set, mock_cache_get):
    """Invalid timeframe should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid timeframe"):
        await MarketDataService.fetch_candles("RELIANCE.NS", "invalid", 10)


@pytest.mark.asyncio
@patch("backend.services.market_data.cache_get")
async def test_fetch_quote_returns_cache_hit(mock_cache_get):
    """If quote is cached, should return it without calling yfinance."""
    cached_quote = {"symbol": "RELIANCE.NS", "price": 2850.0}
    mock_cache_get.return_value = cached_quote

    result = await MarketDataService.fetch_quote("RELIANCE.NS")
    assert result == cached_quote
    mock_cache_get.assert_called_once()


@pytest.mark.asyncio
@patch("backend.services.market_data.cache_get", return_value=None)
@patch("backend.services.market_data.cache_set", new_callable=AsyncMock)
async def test_fetch_quote_uses_history_when_previous_close_missing(mock_cache_set, mock_cache_get):
    """Missing index reference closes must not result in invalid 0% change data."""
    history = pd.DataFrame(
        {"Close": [100.0, 103.0], "Volume": [100, 200]}, index=pd.DatetimeIndex([datetime(2024, 1, 1), datetime(2024, 1, 2)])
    )
    
    with patch("backend.services.market_data.MarketDataService._get_fyers_client") as mock_fyers:
        # Mock Fyers to raise an exception, forcing fallback
        mock_fyers.side_effect = Exception("Fyers failed")
        
        with patch("backend.services.market_data.yf.Ticker") as mock_ticker:
            instance = MagicMock()
            instance.history.return_value = history
            mock_ticker.return_value = instance
            
            quote = await MarketDataService.fetch_quote("^NSEI")

    assert quote["previous_close"] == 100.0
    assert quote["change"] == 3.0
    assert quote["change_pct"] == 3.0
