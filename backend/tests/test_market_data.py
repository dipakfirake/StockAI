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
    """Symbol without suffix should get .NS appended."""
    result = MarketDataService._normalise_symbol("RELIANCE")
    assert result == "RELIANCE.NS"


def test_normalise_symbol_preserves_existing_suffix():
    """Symbol with existing suffix should be unchanged."""
    result = MarketDataService._normalise_symbol("RELIANCE.BO")
    assert result == "RELIANCE.BO"


def test_normalise_symbol_uppercases():
    """Symbol should always be uppercased."""
    result = MarketDataService._normalise_symbol("reliance")
    assert result == "RELIANCE.NS"


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
        {"Close": [100.0, 103.0]}, index=pd.DatetimeIndex([datetime(2024, 1, 1), datetime(2024, 1, 2)])
    )
    fast_info = SimpleNamespace(
        last_price=103.0,
        previous_close=0.0,
        three_month_average_volume=0,
        market_cap=0,
        year_high=110.0,
        year_low=90.0,
    )
    with patch("backend.services.market_data.yf.Ticker") as mock_ticker:
        instance = MagicMock()
        instance.fast_info = fast_info
        instance.history.return_value = history
        mock_ticker.return_value = instance
        quote = await MarketDataService.fetch_quote("^NSEI")

    assert quote["previous_close"] == 100.0
    assert quote["change"] == 3.0
    assert quote["change_pct"] == 3.0
