"""
Unit tests for Milestone 1: Feed Failover & Autonomous Handover.
Tests:
- Authoritative Yahoo Symbol Normalization (indices & equities)
- State-Machine Circuit Breaker (CLOSED, OPEN, HALF_OPEN)
- Canary Recovery Probe (Success restoration & Failure cooldown trip)
- Dynamic Credential Inspection & Hot-Swap (DB, Redis, .env mtime)
- WebSocket Reconnection Handshake Primary Restoration (_on_open)
- Settings -300 Bad Request Decoupling (Preserves Active Broker Session)
"""

import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from backend.services.market_data import MarketDataService
from backend.services.fyers_stream import FyersStreamService


@pytest.fixture(autouse=True)
def reset_engine_state():
    """Ensure clean engine state before and after each test."""
    MarketDataService.reset_fyers_health()
    yield
    MarketDataService.reset_fyers_health()


# ---------------------------------------------------------------------------
# 1. Authoritative Yahoo Symbol Normalization Tests
# ---------------------------------------------------------------------------

def test_normalise_yf_symbol_naked_indices():
    """Naked index strings without broker or caret syntax resolve directly to Yahoo tickers."""
    assert MarketDataService._normalise_yf_symbol("NIFTY") == "^NSEI"
    assert MarketDataService._normalise_yf_symbol("NIFTY50") == "^NSEI"
    assert MarketDataService._normalise_yf_symbol("NIFTY 50") == "^NSEI"
    assert MarketDataService._normalise_yf_symbol("BANKNIFTY") == "^NSEBANK"
    assert MarketDataService._normalise_yf_symbol("NIFTYBANK") == "^NSEBANK"
    assert MarketDataService._normalise_yf_symbol("SENSEX") == "^BSESN"
    assert MarketDataService._normalise_yf_symbol("INDIAVIX") == "^INDIAVIX"
    assert MarketDataService._normalise_yf_symbol("NIFTYIT") == "^CNXIT"
    assert MarketDataService._normalise_yf_symbol("NIFTYAUTO") == "^CNXAUTO"
    assert MarketDataService._normalise_yf_symbol("NIFTYENERGY") == "^CNXENERGY"
    assert MarketDataService._normalise_yf_symbol("NIFTYREALTY") == "^CNXREALTY"
    assert MarketDataService._normalise_yf_symbol("NIFTYMETAL") == "^CNXMETAL"
    assert MarketDataService._normalise_yf_symbol("NIFTYFMCG") == "^CNXFMCG"
    assert MarketDataService._normalise_yf_symbol("NIFTYPHARMA") == "^CNXPHARMA"
    assert MarketDataService._normalise_yf_symbol("NIFTYMIDCAP50") == "^NSEMDCP50"


def test_normalise_yf_symbol_broker_prefixes_and_equities():
    """Broker formats (NSE:..., BSE:..., -EQ, -INDEX) map cleanly to .NS, .BO, or caret indices."""
    assert MarketDataService._normalise_yf_symbol("NSE:RELIANCE-EQ") == "RELIANCE.NS"
    assert MarketDataService._normalise_yf_symbol("BSE:TCS-EQ") == "TCS.BO"
    assert MarketDataService._normalise_yf_symbol("NSE:NIFTY50-INDEX") == "^NSEI"
    assert MarketDataService._normalise_yf_symbol("NSE:BANKNIFTY-INDEX") == "^NSEBANK"
    assert MarketDataService._normalise_yf_symbol("BSE:SENSEX-INDEX") == "^BSESN"
    assert MarketDataService._normalise_yf_symbol("NSE:INDIAVIX-INDEX") == "^INDIAVIX"
    # Bare equities without exchange default to NSE (.NS)
    assert MarketDataService._normalise_yf_symbol("RELIANCE") == "RELIANCE.NS"
    assert MarketDataService._normalise_yf_symbol("INFY") == "INFY.NS"
    # Existing suffixes preserved
    assert MarketDataService._normalise_yf_symbol("RELIANCE.NS") == "RELIANCE.NS"
    assert MarketDataService._normalise_yf_symbol("TCS.BO") == "TCS.BO"
    assert MarketDataService._normalise_yf_symbol("^NSEI") == "^NSEI"
    # Suffix on index name stripped and resolved to caret
    assert MarketDataService._normalise_yf_symbol("BANKNIFTY.NS") == "^NSEBANK"
    assert MarketDataService._normalise_yf_symbol("NIFTY.NS") == "^NSEI"


# ---------------------------------------------------------------------------
# 2. State-Machine Circuit Breaker Transitions
# ---------------------------------------------------------------------------

def test_circuit_breaker_transitions():
    """State machine transitions cleanly between CLOSED, OPEN, and HALF_OPEN."""
    # Default: CLOSED
    status = MarketDataService.get_feed_status()
    assert status["circuit_state"] == "CLOSED"
    assert status["active_engine"] == "PRIMARY_FYERS"
    assert status["fyers_valid"] is True

    # Mark expired: OPEN
    MarketDataService.mark_fyers_token_expired(reason="Daily 06:00 AM reset", cooldown_seconds=100.0)
    status = MarketDataService.get_feed_status()
    assert status["circuit_state"] == "OPEN"
    assert status["active_engine"] == "BACKUP_YAHOO"
    assert status["fyers_valid"] is False
    assert status["fyers_cooldown_remaining"] > 0

    # Advance time past cooldown: HALF_OPEN
    MarketDataService._fyers_cooldown_until = time.time() - 1.0
    status = MarketDataService.get_feed_status()
    assert status["circuit_state"] == "HALF_OPEN"
    assert status["active_engine"] == "BACKUP_YAHOO"
    assert status["fyers_cooldown_remaining"] == 0


# ---------------------------------------------------------------------------
# 3. Canary Recovery Probe Tests (Success & Failure)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_canary_probe_success_restores_primary_feed():
    """When cooldown expires and canary probe succeeds, primary feed is restored automatically."""
    # Place system in expired state with cooldown in the past (HALF_OPEN)
    MarketDataService.mark_fyers_token_expired("Auth glitch")
    MarketDataService._fyers_cooldown_until = time.time() - 10.0
    assert MarketDataService._fyers_token_valid is False

    mock_fyers = MagicMock()
    mock_fyers.quotes.return_value = {
        "s": "ok",
        "d": [
            {
                "n": "NSE:NIFTY50-INDEX",
                "v": {
                    "lp": 24500.5,
                    "prev_close_price": 24400.0,
                    "ch": 100.5,
                    "chp": 0.41,
                    "volume": 0
                }
            }
        ]
    }

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock) as mock_get_client:
        mock_get_client.return_value = mock_fyers

        # Trigger canary probe
        success = await MarketDataService.probe_fyers_canary("NSE:NIFTY50-INDEX")

        assert success is True
        # Assert full handover restoration
        assert MarketDataService._fyers_token_valid is True
        assert MarketDataService._active_engine == "PRIMARY_FYERS"
        assert MarketDataService._fyers_cooldown_until == 0.0
        status = MarketDataService.get_feed_status()
        assert status["circuit_state"] == "CLOSED"
        assert status["active_engine"] == "PRIMARY_FYERS"


@pytest.mark.asyncio
async def test_canary_probe_failure_trips_circuit_back_to_open():
    """When canary probe fails, system trips back to OPEN with a new cooldown without raising."""
    MarketDataService.mark_fyers_token_expired("Initial failure")
    MarketDataService._fyers_cooldown_until = time.time() - 1.0

    mock_fyers = MagicMock()
    mock_fyers.quotes.return_value = {
        "s": "error",
        "code": -15,
        "message": "Token expired or invalid"
    }

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock) as mock_get_client:
        mock_get_client.return_value = mock_fyers

        success = await MarketDataService.probe_fyers_canary("NSE:NIFTY50-INDEX")

        assert success is False
        assert MarketDataService._fyers_token_valid is False
        assert MarketDataService._active_engine == "BACKUP_YAHOO"
        # Assert cooldown was tripped back into future (300s)
        assert MarketDataService._fyers_cooldown_until > time.time() + 200.0
        status = MarketDataService.get_feed_status()
        assert status["circuit_state"] == "OPEN"


@pytest.mark.asyncio
async def test_fetch_quote_triggers_canary_and_recovers_seamlessly():
    """Calling fetch_quote during HALF_OPEN automatically executes canary probe and restores Fyers."""
    MarketDataService.mark_fyers_token_expired("Expired")
    MarketDataService._fyers_cooldown_until = time.time() - 5.0  # Cooldown elapsed

    mock_fyers = MagicMock()
    mock_fyers.quotes.return_value = {
        "s": "ok",
        "d": [
            {
                "n": "NSE:RELIANCE-EQ",
                "v": {
                    "lp": 2850.0,
                    "prev_close_price": 2800.0,
                    "ch": 50.0,
                    "chp": 1.78,
                    "volume": 2000000
                }
            }
        ]
    }

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock) as mock_get_client, \
         patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("backend.services.market_data.cache_set", new_callable=AsyncMock):

        mock_get_client.return_value = mock_fyers

        quote = await MarketDataService.fetch_quote("RELIANCE.NS")

        assert quote is not None
        assert quote["price"] == 2850.0
        assert quote["source"] == "Fyers API"
        assert MarketDataService._fyers_token_valid is True
        assert MarketDataService._active_engine == "PRIMARY_FYERS"


# ---------------------------------------------------------------------------
# 4. Dynamic Credential Hot-Swap Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dynamic_credential_hotswap_redis():
    """Detecting updated credentials in Redis triggers health reset without backend restart."""
    MarketDataService.mark_fyers_token_expired("Old token expired")
    MarketDataService._last_loaded_token = "expired_token_123"
    MarketDataService._last_token_check_time = 0.0

    new_creds = {"client_id": "CLIENT_NEW_ID", "access_token": "valid_token_xyz_999"}

    with patch("backend.core.cache.cache_get", new_callable=AsyncMock) as mock_cache_get, \
         patch("backend.core.database.AsyncSessionLocal", side_effect=Exception("No DB")):

        mock_cache_get.return_value = new_creds

        changed = await MarketDataService.check_credentials_changed()

        assert changed is True
        assert MarketDataService._last_loaded_token == "valid_token_xyz_999"
        assert MarketDataService._fyers_token_valid is True
        assert MarketDataService._active_engine == "PRIMARY_FYERS"
        assert MarketDataService._fyers_cooldown_until == 0.0


# ---------------------------------------------------------------------------
# 5. WebSocket Reconnection Handshake Restoration Tests
# ---------------------------------------------------------------------------

def test_websocket_on_open_restores_primary_feed():
    """WebSocket _on_open callback restores primary Fyers health and resets circuit breaker."""
    MarketDataService.mark_fyers_token_expired("WebSocket disconnected")
    assert MarketDataService._fyers_token_valid is False
    assert MarketDataService._active_engine == "BACKUP_YAHOO"

    stream = FyersStreamService.get_instance()
    stream._on_open()

    assert MarketDataService._fyers_token_valid is True
    assert MarketDataService._active_engine == "PRIMARY_FYERS"
    assert MarketDataService.get_feed_status()["circuit_state"] == "CLOSED"


# ---------------------------------------------------------------------------
# 6. Settings -300 Bad Request Decoupling Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_settings_code_300_does_not_expire_fyers_token():
    """Fyers code -300 (invalid symbol) in settings check must NOT mark broker session expired."""
    from backend.api.settings import get_fyers_status

    mock_db = AsyncMock()
    mock_db.execute.side_effect = Exception("No DB")
    mock_user = MagicMock()

    mock_fyers_instance = MagicMock()
    mock_fyers_instance.get_profile.return_value = {
        "s": "error",
        "code": -300,
        "message": "Input symbol parameter is invalid"
    }

    with patch("backend.api.settings.settings") as mock_settings, \
         patch("backend.api.settings.fyersModel.FyersModel", return_value=mock_fyers_instance), \
         patch("backend.core.cache.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("backend.core.cache.cache_set", new_callable=AsyncMock):

        mock_settings.FYERS_CLIENT_ID = "XC12345"
        mock_settings.FYERS_ACCESS_TOKEN = "valid_access_token_12345"

        result = await get_fyers_status(force_refresh=True, db=mock_db, current_user=mock_user)

        # Token must NOT be marked expired
        assert MarketDataService._fyers_token_valid is True
        assert MarketDataService._active_engine == "PRIMARY_FYERS"
        assert result.get("token_status") != "EXPIRED"


# ---------------------------------------------------------------------------
# 7. Milestone 1 Iteration 2 Remediation Regression Tests
# ---------------------------------------------------------------------------

def test_normalise_yf_symbol_underscores_and_edge_cases():
    """Validates underscore variants of sectoral indices and guards against bare prefix/whitespace corruption."""
    norm = MarketDataService._normalise_yf_symbol

    # Underscored sectoral & benchmark indices
    assert norm("NIFTY_AUTO") == "^CNXAUTO"
    assert norm("NIFTY_IT") == "^CNXIT"
    assert norm("NIFTY_BANK") == "^NSEBANK"
    assert norm("NIFTY_MIDCAP50") == "^NSEMDCP50"
    assert norm("NIFTY_FIN_SERVICE") == "^CNXFIN"
    assert norm("NIFTY_METAL") == "^CNXMETAL"
    assert norm("NIFTY_FMCG") == "^CNXFMCG"
    assert norm("NIFTY_PHARMA") == "^CNXPHARMA"
    assert norm("NIFTY_REALTY") == "^CNXREALTY"
    assert norm("NIFTY_ENERGY") == "^CNXENERGY"

    # Whitespace and bare exchange prefix guards
    assert norm("   ") == ""
    assert norm("") == ""
    assert norm(None) == ""
    assert norm("NSE:") == ""
    assert norm("BSE:") == ""


def test_reset_fyers_health_preserves_cached_token():
    """reset_fyers_health() must NOT wipe _last_loaded_token, preventing spurious flapping."""
    MarketDataService._last_loaded_token = "token_persisted_active"
    MarketDataService._last_loaded_client_id = "client_persisted_active"

    MarketDataService.reset_fyers_health()

    assert MarketDataService._last_loaded_token == "token_persisted_active"
    assert MarketDataService._last_loaded_client_id == "client_persisted_active"
    assert MarketDataService._fyers_token_valid is True
    assert MarketDataService._active_engine == "PRIMARY_FYERS"
    assert MarketDataService._circuit_state == "CLOSED"


@pytest.mark.asyncio
async def test_fetch_quote_network_error_trips_to_open_cooldown():
    """TimeoutError or 502 Bad Gateway during CLOSED state trips a 60s cooldown to BACKUP_YAHOO."""
    MarketDataService.reset_fyers_health()
    assert MarketDataService.get_feed_status()["circuit_state"] == "CLOSED"

    mock_fyers = MagicMock()
    mock_fyers.quotes.side_effect = TimeoutError("Connection to Fyers timed out after 5.0s")

    mock_yahoo_quote = {
        "symbol": "RELIANCE.NS",
        "price": 2800.0,
        "previous_close": 2790.0,
        "change": 10.0,
        "change_pct": 0.36,
        "volume": 50000,
        "market_cap": 0,
        "52w_high": 3000.0,
        "52w_low": 2200.0,
        "timestamp": "2026-10-29T09:00:00Z",
        "data_status": "delayed",
        "source": "Backup (Yahoo Chart API)",
    }

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock, return_value=mock_fyers), \
         patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("backend.services.market_data.cache_set", new_callable=AsyncMock), \
         patch.object(MarketDataService, "_parse_yahoo_chart_meta", return_value=mock_yahoo_quote), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_httpx_get:

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"chart": {"result": [{"meta": {}}]}}
        mock_httpx_get.return_value = mock_resp

        quote = await MarketDataService.fetch_quote("RELIANCE.NS")

        assert quote is not None
        assert quote.get("source") in ("Backup", "Backup (Yahoo Chart API)")
        status = MarketDataService.get_feed_status()
        assert status["circuit_state"] == "OPEN"
        assert status["active_engine"] == "BACKUP_YAHOO"
        assert status["fyers_cooldown_remaining"] > 0


@pytest.mark.asyncio
async def test_fetch_quotes_bulk_502_error_trips_to_open_cooldown():
    """Fyers code 502 or bad gateway during bulk quotes trips 60s cooldown to BACKUP_YAHOO."""
    MarketDataService.reset_fyers_health()
    assert MarketDataService.get_feed_status()["circuit_state"] == "CLOSED"

    mock_fyers = MagicMock()
    mock_fyers.quotes.return_value = {"s": "error", "code": 502, "message": "Bad Gateway"}

    mock_yahoo_quote = {
        "symbol": "RELIANCE.NS",
        "price": 2800.0,
        "previous_close": 2790.0,
        "change": 10.0,
        "change_pct": 0.36,
        "volume": 50000,
        "market_cap": 0,
        "52w_high": 3000.0,
        "52w_low": 2200.0,
        "timestamp": "2026-10-29T09:00:00Z",
        "data_status": "delayed",
        "source": "Backup (Yahoo Chart API)",
    }

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock, return_value=mock_fyers), \
         patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("backend.services.market_data.cache_set", new_callable=AsyncMock), \
         patch.object(MarketDataService, "_parse_yahoo_chart_meta", return_value=mock_yahoo_quote), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_httpx_get:

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"chart": {"result": [{"meta": {}}]}}
        mock_httpx_get.return_value = mock_resp

        quotes = await MarketDataService.fetch_quotes_bulk(["RELIANCE.NS"])

        assert "RELIANCE.NS" in quotes
        status = MarketDataService.get_feed_status()
        assert status["circuit_state"] == "OPEN"
        assert status["active_engine"] == "BACKUP_YAHOO"
        assert status["fyers_cooldown_remaining"] > 0


def test_feed_status_interface_conformance():
    """get_feed_status() returns both fyers_valid and fyers_token_valid, plus rate_budget_available."""
    status = MarketDataService.get_feed_status()
    assert "fyers_valid" in status
    assert "fyers_token_valid" in status
    assert status["fyers_valid"] == status["fyers_token_valid"]
    assert "rate_budget_available" in status
    assert isinstance(status["rate_budget_available"], int)
    assert "active_engine" in status
    assert "circuit_state" in status

