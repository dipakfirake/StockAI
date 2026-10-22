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


@pytest.mark.asyncio
@patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None)
@patch("backend.services.market_data.cache_set", new_callable=AsyncMock)
async def test_fetch_quotes_bulk_fyers_and_fallback(mock_cache_set, mock_cache_get):
    """Test fetch_quotes_bulk parses Fyers response and hydrates missing via fallback."""
    mock_fyers_resp = {
        "s": "ok",
        "d": [
            {
                "n": "NSE:SBIN-EQ",
                "v": {
                    "lp": 965.5,
                    "prev_close_price": 960.0,
                    "ch": 5.5,
                    "chp": 0.57,
                    "volume": 5000000
                }
            }
        ]
    }
    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock) as mock_fyers:
        instance = MagicMock()
        instance.quotes.return_value = mock_fyers_resp
        mock_fyers.return_value = instance

        MarketDataService.reset_fyers_health()
        res = await MarketDataService.fetch_quotes_bulk(["SBIN.NS"], use_fallback=False)
        assert "SBIN.NS" in res
        assert res["SBIN.NS"]["price"] == 965.5
        assert res["SBIN.NS"]["change"] == 5.5
        assert res["SBIN.NS"]["source"] == "Fyers API"


def test_parse_yahoo_chart_meta_pcjeweller():
    """Verify Yahoo Chart meta parsing avoids chartPreviousClose 5-day boundary trap."""
    mock_meta = {
        "regularMarketPrice": 18.13,
        "chartPreviousClose": 14.10,  # 5-day boundary close, NOT yesterday's close!
        "regularMarketChangePercent": 11.364,
        "fulldayChange": 1.85,
        "fulldayChangePercent": 11.364,
        "fiftyTwoWeekHigh": 18.65,
        "fiftyTwoWeekLow": 7.47,
        "regularMarketVolume": 1697147831,
    }
    res = MarketDataService._parse_yahoo_chart_meta(mock_meta, "PCJEWELLER.NS")
    assert res is not None
    assert res["price"] == 18.13
    assert res["change"] == 1.85
    assert res["change_pct"] == 11.36
    assert res["previous_close"] == 16.28
    assert res["52w_high"] == 18.65
    assert res["52w_low"] == 7.47


@pytest.mark.asyncio
@patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None)
@patch("backend.services.market_data.cache_set", new_callable=AsyncMock)
async def test_fyers_after_hours_prev_close_rollover(mock_cache_set, mock_cache_get):
    """Verify Fyers quote parsing correctly derives prev_close when post-market rolls prev_close_price to lp."""
    mock_fyers_resp = {
        "s": "ok",
        "d": [
            {
                "n": "NSE:PCJEWELLER-EQ",
                "v": {
                    "lp": 18.13,
                    "prev_close_price": 18.13,  # Rolled over to lp after market close
                    "ch": 1.85,
                    "chp": 11.36,
                    "volume": 16971478,
                }
            }
        ]
    }
    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock) as mock_fyers:
        instance = MagicMock()
        instance.quotes.return_value = mock_fyers_resp
        mock_fyers.return_value = instance

        MarketDataService.reset_fyers_health()
        res = await MarketDataService.fetch_quote("PCJEWELLER.NS")
        assert res is not None
        assert res["price"] == 18.13
        assert res["change"] == 1.85
        assert res["change_pct"] == 11.36
        assert res["previous_close"] == 16.28


@pytest.mark.asyncio
@patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None)
@patch("backend.services.market_data.cache_set", new_callable=AsyncMock)
async def test_get_stock_info_with_screener_fundamentals(mock_cache_set, mock_cache_get):
    """Verify get_stock_info hydrates full balance sheet and valuation ratios via Screener fallback."""
    fake_screener_data = {
        "name": "PC Jeweller Ltd",
        "market_cap": 177320000000.0,
        "pe_ratio": 23.6,
        "forward_pe": 23.6,
        "book_value": 9.28,
        "price_to_book": 1.95,
        "roe": 0.0996,
        "roa": 0.0957,
        "dividend_yield": 0.0,
        "debt_to_equity": 0.04,
        "total_revenue": 35170000000.0,
        "revenue_growth": 0.0492,
        "ebitda": 7670000000.0,
        "current_ratio": 5.0,
        "sector": "Consumer Discretionary",
        "industry": "Gems, Jewellery And Watches",
        "description": "PC Jeweller is engaged in the manufacturing and retail of jewellery.",
    }

    with patch.object(MarketDataService, "_fetch_screener_fundamentals", new_callable=AsyncMock) as mock_screener, \
         patch("yfinance.Ticker") as mock_ticker:

        mock_screener.return_value = fake_screener_data
        # Simulate Yahoo Finance failing with 429
        mock_ticker.side_effect = Exception("429 Client Error: Too Many Requests")

        info = await MarketDataService.get_stock_info("PCJEWELLER.NS")

        assert info is not None
        assert info["pe_ratio"] == 23.6
        assert info["book_value"] == 9.28
        assert info["price_to_book"] == 1.95
        assert info["roe"] == 0.0996
        assert info["debt_to_equity"] == 0.04
        assert info["total_revenue"] == 35170000000.0
        assert info["sector"] == "Consumer Discretionary"
        assert info["industry"] == "Gems, Jewellery And Watches"
        mock_screener.assert_called_once_with("PCJEWELLER")


@pytest.mark.asyncio
@patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None)
@patch("backend.services.market_data.cache_set", new_callable=AsyncMock)
async def test_get_stock_info_handles_index(mock_cache_set, mock_cache_get):
    """Verify get_stock_info returns clean benchmark index metadata without failing."""
    info = await MarketDataService.get_stock_info("^NSEI")
    assert info is not None
    assert info["is_index"] is True
    assert info["sector"] == "Broad Market Index"
    assert "benchmark" in info["description"].lower()


