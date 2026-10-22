"""
Automated unit tests for the Autonomous Dual-Connection Market Data Engine.
Verifies seamless failover to Yahoo Finance on Fyers token expiry,
cooldown suppression, and instant hot-swap upon token renewal.
"""

import pytest
import time
from unittest.mock import patch, MagicMock, AsyncMock

from backend.services.market_data import MarketDataService


@pytest.fixture(autouse=True)
def reset_dual_engine():
    """Ensure clean engine state before each test."""
    MarketDataService.reset_fyers_health()
    yield
    MarketDataService.reset_fyers_health()


def test_dual_engine_default_state():
    status = MarketDataService.get_feed_status()
    assert status["active_engine"] == "PRIMARY_FYERS"
    assert status["fyers_valid"] is True
    assert status["fyers_expiry_schedule"] == "06:00 AM IST Daily"
    assert "Fyers API" in status["source_label"]


def test_mark_fyers_token_expired():
    MarketDataService.mark_fyers_token_expired(reason="Token expired at 06:00 AM IST", cooldown_seconds=300.0)
    status = MarketDataService.get_feed_status()
    assert status["active_engine"] == "BACKUP_YAHOO"
    assert status["fyers_valid"] is False
    assert status["fyers_cooldown_remaining"] > 0
    assert "Token expired at 06:00 AM IST" in status["fyers_token_error"]
    assert "Yahoo Finance" in status["source_label"]


def test_reset_fyers_health_restores_primary():
    MarketDataService.mark_fyers_token_expired(reason="Daily reset")
    assert MarketDataService._fyers_token_valid is False

    MarketDataService.reset_fyers_health()
    status = MarketDataService.get_feed_status()
    assert status["active_engine"] == "PRIMARY_FYERS"
    assert status["fyers_valid"] is True
    assert status["fyers_cooldown_remaining"] == 0
    assert status["fyers_token_error"] == ""


@pytest.mark.asyncio
async def test_fetch_quotes_bulk_detects_token_expiry_and_fails_over():
    """When Fyers returns -300 Token Expired, system automatically switches to BACKUP_YAHOO."""
    mock_fyers = MagicMock()
    # Fyers returns official -300 token expired response
    mock_fyers.quotes.return_value = {
        "s": "error",
        "code": -300,
        "message": "Token has expired"
    }

    sample_meta = {
        "regularMarketPrice": 2500.0,
        "regularMarketChange": 25.0,
        "regularMarketChangePercent": 1.01,
        "chartPreviousClose": 2475.0,
        "regularMarketVolume": 5000000,
        "fiftyTwoWeekHigh": 2800.0,
        "fiftyTwoWeekLow": 2100.0
    }

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock) as mock_get_client, \
         patch.object(MarketDataService, "_parse_yahoo_chart_meta") as mock_parse_meta, \
         patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("httpx.AsyncClient.get") as mock_http_get:
        
        mock_get_client.return_value = mock_fyers
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"chart": {"result": [{"meta": sample_meta}]}}
        mock_http_get.return_value = mock_resp
        
        mock_parse_meta.return_value = {
            "symbol": "RELIANCE.NS",
            "price": 2500.0,
            "previous_close": 2475.0,
            "change": 25.0,
            "change_pct": 1.01,
            "volume": 5000000,
            "timestamp": "2026-10-20T09:15:00Z",
            "data_status": "live_backup",
            "source": "Backup (Yahoo Chart API)",
        }

        quotes = await MarketDataService.fetch_quotes_bulk(["RELIANCE.NS"], use_fallback=True)

        # 1. Assert Fyers was detected as expired
        assert MarketDataService._fyers_token_valid is False
        assert MarketDataService._active_engine == "BACKUP_YAHOO"
        
        # 2. Assert quote was served via autonomous Yahoo backup without failing
        assert "RELIANCE.NS" in quotes
        assert quotes["RELIANCE.NS"]["price"] == 2500.0
        assert quotes["RELIANCE.NS"]["source"] == "Backup (Yahoo Chart API)"


@pytest.mark.asyncio
async def test_fetch_quotes_bulk_bypasses_fyers_when_in_backup_mode():
    """When already in backup mode, bulk quotes query Yahoo directly without calling Fyers."""
    MarketDataService.mark_fyers_token_expired(reason="Expired at 06:00 AM")

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock) as mock_get_client, \
         patch.object(MarketDataService, "_parse_yahoo_chart_meta") as mock_parse_meta, \
         patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("httpx.AsyncClient.get") as mock_http_get:

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"chart": {"result": [{"meta": {}}]}}
        mock_http_get.return_value = mock_resp

        mock_parse_meta.return_value = {
            "symbol": "TCS.NS",
            "price": 3800.0,
            "previous_close": 3780.0,
            "change": 20.0,
            "change_pct": 0.53,
            "volume": 2000000,
            "timestamp": "2026-10-20T09:15:00Z",
            "data_status": "live_backup",
            "source": "Backup (Yahoo Chart API)",
        }

        quotes = await MarketDataService.fetch_quotes_bulk(["TCS.NS"], use_fallback=True)

        # Assert Fyers client was NOT called (zero latency wasted)
        mock_get_client.assert_not_called()
        assert "TCS.NS" in quotes
        assert quotes["TCS.NS"]["price"] == 3800.0


def test_record_fyers_rate_limit_maintains_token_validity():
    """Rate limits (-360, 429) must NOT mark the Fyers token expired."""
    assert MarketDataService._fyers_token_valid is True
    MarketDataService.record_fyers_rate_limit(reason="Plan limit reached: 50 req/min", cooldown_seconds=30.0)

    # Token must remain valid!
    assert MarketDataService._fyers_token_valid is True
    status = MarketDataService.get_feed_status()
    assert status["fyers_status"] == "RATE_LIMITED"
    assert status["active_engine"] == "BACKUP_YAHOO"
    assert status["fyers_cooldown_remaining"] > 0
    assert "Throttled" in status["source_label"]


@pytest.mark.asyncio
async def test_fetch_quotes_bulk_handles_rate_limit_code_360_without_expiring_token():
    """When Fyers returns -360 (Rate Limit), system temporarily diverts to Yahoo but preserves token validity."""
    mock_fyers = MagicMock()
    mock_fyers.quotes.return_value = {
        "code": -360,
        "message": "You've reached the Standard plan limit of 50 requests/minute. Upgrade to Prime for higher API limits."
    }

    sample_meta = {
        "regularMarketPrice": 1450.0,
        "chartPreviousClose": 1440.0,
        "regularMarketChange": 10.0,
        "regularMarketChangePercent": 0.69,
        "regularMarketVolume": 1000000,
    }

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock) as mock_get_client, \
         patch.object(MarketDataService, "_parse_yahoo_chart_meta") as mock_parse_meta, \
         patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("httpx.AsyncClient.get") as mock_http_get:

        mock_get_client.return_value = mock_fyers
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"chart": {"result": [{"meta": sample_meta}]}}
        mock_http_get.return_value = mock_resp

        mock_parse_meta.return_value = {
            "symbol": "INFY.NS",
            "price": 1450.0,
            "previous_close": 1440.0,
            "change": 10.0,
            "change_pct": 0.69,
            "volume": 1000000,
            "timestamp": "2026-10-22T09:15:00Z",
            "data_status": "live_backup",
            "source": "Backup (Yahoo Chart API)",
        }

        quotes = await MarketDataService.fetch_quotes_bulk(["INFY.NS"], use_fallback=True)

        # Fyers token MUST remain valid!
        assert MarketDataService._fyers_token_valid is True
        # Engine is temporarily routed to Yahoo backup
        assert quotes["INFY.NS"]["price"] == 1450.0
        assert quotes["INFY.NS"]["source"] == "Backup (Yahoo Chart API)"


def test_extract_auth_code_variants():
    """Test URL and auth code parsing from mobile redirect formats."""
    from backend.api.settings import _extract_auth_code

    # 1. Full standard redirect URL
    url1 = "https://trade.fyers.in/api-login/redirect-uri/index.html?s=ok&code=200&auth_code=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.testcode"
    assert _extract_auth_code(url1) == "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.testcode"

    # 2. URL fragment format (#auth_code=...)
    url2 = "https://trade.fyers.in/api-login/redirect-uri/index.html#auth_code=eyJhbGciOiJIUzI1NiJ9.fragment_code"
    assert _extract_auth_code(url2) == "eyJhbGciOiJIUzI1NiJ9.fragment_code"

    # 3. Percent-encoded URL
    url3 = "https://trade.fyers.in/api-login/redirect-uri/index.html?auth_code=eyJ0eX%3D%3D"
    assert _extract_auth_code(url3) == "eyJ0eX=="

    # 4. Direct code with quotes or whitespace
    code_raw = '  "eyJhbGciOiJIUzI1NiJ9.raw_code"  '
    assert _extract_auth_code(code_raw) == "eyJhbGciOiJIUzI1NiJ9.raw_code"

