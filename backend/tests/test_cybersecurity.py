"""
Unit tests for Cybersecurity & Financial Risk Defenses.

Verifies:
- Token Bucket Rate Limiting (capacity, consumption, refill, 429 status)
- Financial Idempotency Key Manager (replay protection, race condition prevention)
- Financial Risk Controls & Fat-Finger Circuit Breakers (quantity, notional value, price deviation)
- Security Headers & Payload Size Limits (X-Frame-Options, HSTS, 413 limit)
- Auth Hardening & Brute-Force IP Lockout
- Structured Security Audit Trail
"""

import os
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from starlette.requests import Request
from starlette.datastructures import Headers

from backend.core.rate_limiter import TokenBucket, TokenBucketRateLimiter, TIERS
from backend.core.idempotency import IdempotencyManager
from backend.core.auth_security import validate_password_strength, BruteForceProtector
from backend.core.audit_logger import log_security_event, AUDIT_LOG_PATH
from backend.services.paper_trading import (
    PaperTradingService,
    MAX_QUANTITY_PER_ORDER,
    MAX_NOTIONAL_VALUE_PER_ORDER,
    MAX_PRICE_DEVIATION_PCT,
)


# ==============================================================================
# 1. Token Bucket Rate Limiting Tests
# ==============================================================================

def test_token_bucket_consume_and_exhaust():
    """Verify token bucket decreases and blocks when capacity is exhausted."""
    bucket = TokenBucket(capacity=3, refill_rate=0.1)
    
    # 1st request: allowed
    allowed, remaining, wait = bucket.consume(1.0)
    assert allowed is True
    assert remaining == pytest.approx(2.0, abs=0.1)

    # 2nd request: allowed
    allowed, remaining, wait = bucket.consume(1.0)
    assert allowed is True
    assert remaining == pytest.approx(1.0, abs=0.1)

    # 3rd request: allowed
    allowed, remaining, wait = bucket.consume(1.0)
    assert allowed is True
    assert remaining == pytest.approx(0.0, abs=0.1)

    # 4th request: blocked (429)
    allowed, remaining, wait = bucket.consume(1.0)
    assert allowed is False
    assert wait > 0


def test_token_bucket_refill():
    """Verify token bucket refills tokens over elapsed time."""
    bucket = TokenBucket(capacity=2, refill_rate=10.0)  # 10 tokens per second
    
    # Consume all tokens
    bucket.consume(2.0)
    assert bucket.tokens == 0.0

    # Simulate 0.2s elapsed -> 2.0 tokens refilled
    time.sleep(0.2)
    allowed, remaining, _ = bucket.consume(1.0)
    assert allowed is True


def test_rate_limiter_tier_mapping():
    """Verify paths map to correct security tiers."""
    limiter = TokenBucketRateLimiter()
    assert limiter.determine_tier("/api/auth/login") == "AUTH"
    assert limiter.determine_tier("/api/auth/register") == "AUTH"
    assert limiter.determine_tier("/api/paper-trades") == "TRADING"
    assert limiter.determine_tier("/api/portfolio") == "TRADING"
    assert limiter.determine_tier("/api/ai/predict") == "AI"
    assert limiter.determine_tier("/api/stocks/RELIANCE/insight") == "GENERAL"


# ==============================================================================
# 2. Financial Idempotency Tests (Anti-Replay / Double-Execution)
# ==============================================================================

@pytest.mark.asyncio
async def test_idempotency_lifecycle():
    """Verify new key, race detection, and cached replay execution."""
    mgr = IdempotencyManager(ttl_seconds=10)
    key = "order-test-uuid-12345"

    # 1. First attempt: NEW
    status, rec = await mgr.get_or_create(key)
    assert status == "NEW"
    assert rec.status == "IN_PROGRESS"

    # 2. Concurrent second attempt while first is in progress: IN_PROGRESS (Conflict 409)
    status2, rec2 = await mgr.get_or_create(key)
    assert status2 == "IN_PROGRESS"

    # 3. Mark completed with response data
    await mgr.mark_completed(key, 200, {"trade_id": "T-100", "status": "OPEN"})

    # 4. Third attempt after completion: COMPLETED with exact stored response
    status3, rec3 = await mgr.get_or_create(key)
    assert status3 == "COMPLETED"
    assert rec3.response_body == {"trade_id": "T-100", "status": "OPEN"}


# ==============================================================================
# 3. Financial Risk & Fat-Finger Circuit Breaker Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_order_risk_quantity_limit():
    """Verify orders exceeding maximum allowable quantity are rejected."""
    mock_db = AsyncMock()
    with pytest.raises(ValueError, match="exceeds the maximum allowable single-order risk limit"):
        await PaperTradingService.place_order(
            db=mock_db,
            user_id="00000000-0000-0000-0000-000000000001",
            symbol="INFY.NS",
            direction="BUY",
            quantity=MAX_QUANTITY_PER_ORDER + 1,
        )


@pytest.mark.asyncio
async def test_order_risk_notional_value_limit():
    """Verify orders exceeding ₹1 Crore notional limit are blocked."""
    mock_db = AsyncMock()
    with patch("backend.services.market_data.market_data_service.fetch_quote", new_callable=AsyncMock) as mock_quote:
        # Mock price of ₹5,000 per share; 3,000 shares = ₹1.5 Crore (> ₹1 Crore limit)
        mock_quote.return_value = {"price": 5000.0}
        with pytest.raises(ValueError, match="exceeds the maximum allowable limit of ₹10,000,000.00"):
            await PaperTradingService.place_order(
                db=mock_db,
                user_id="00000000-0000-0000-0000-000000000001",
                symbol="MRF.NS",
                direction="BUY",
                quantity=3000,
            )


@pytest.mark.asyncio
async def test_fat_finger_limit_price_circuit_breaker():
    """Verify limit price deviating >30% from market is rejected."""
    mock_db = AsyncMock()
    with patch("backend.services.market_data.market_data_service.fetch_quote", new_callable=AsyncMock) as mock_quote:
        # Market price ₹100. Limit price ₹150 (+50% deviation) -> Reject
        mock_quote.return_value = {"price": 100.0}
        with pytest.raises(ValueError, match="Fat-finger circuit breaker triggered"):
            await PaperTradingService.place_order(
                db=mock_db,
                user_id="00000000-0000-0000-0000-000000000001",
                symbol="TCS.NS",
                direction="BUY",
                quantity=10,
                order_type="LIMIT",
                limit_price=150.0,
            )


@pytest.mark.asyncio
async def test_symbol_injection_sanitization():
    """Verify malicious or script-injection symbols are blocked."""
    mock_db = AsyncMock()
    with pytest.raises(ValueError, match="Invalid symbol format"):
        await PaperTradingService.place_order(
            db=mock_db,
            user_id="00000000-0000-0000-0000-000000000001",
            symbol="TCS<script>alert(1)</script>",
            direction="BUY",
            quantity=10,
        )


# ==============================================================================
# 4. Auth Security & Brute-Force Lockout Tests
# ==============================================================================

def test_password_strength_validation():
    """Verify weak passwords are systematically rejected."""
    # Too short (< 8 chars)
    with pytest.raises(ValueError, match="at least 8 characters"):
        validate_password_strength("Ab1!")

    # No alphabet
    with pytest.raises(ValueError, match="alphabetic character"):
        validate_password_strength("1234567890!")

    # No digit or special char
    with pytest.raises(ValueError, match="digit or special character"):
        validate_password_strength("abcdefghijkl")

    # Valid strong password
    validate_password_strength("StrongPass123!")


def test_brute_force_lockout():
    """Verify 5 consecutive failed logins trigger a 15-minute temporary lockout."""
    protector = BruteForceProtector()
    ip = "192.168.1.100"
    email = "target@financial.com"

    # Initial state: not locked out
    protector.check_lockout(ip, email)

    # 4 failures: still under threshold
    for _ in range(4):
        protector.record_failure(ip, email)
    protector.check_lockout(ip, email)

    # 5th failure: triggers lockout
    protector.record_failure(ip, email)
    with pytest.raises(HTTPException) as exc:
        protector.check_lockout(ip, email)
    assert exc.value.status_code == 429
    assert "temporarily locked" in exc.value.detail.lower()

    # Success resets lockout for another user/after recovery
    protector.record_success(ip, email)
    protector.check_lockout(ip, email)


# ==============================================================================
# 5. Security Audit Logging Test
# ==============================================================================

def test_security_audit_logger_redaction():
    """Verify audit logger writes structured JSON and redacts sensitive parameters."""
    log_security_event(
        event_type="TEST_SECURITY_EVENT",
        severity="WARNING",
        ip_address="10.0.0.1",
        user_id="user-999",
        details={
            "password": "SuperSecretPassword123!",
            "token": "secret-jwt-token",
            "action": "test_verification",
        },
    )
    # Check that audit log file exists and contains the event
    assert os.path.exists(AUDIT_LOG_PATH)
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
        last_line = lines[-1]
        assert "TEST_SECURITY_EVENT" in last_line
        assert "[REDACTED]" in last_line
        assert "SuperSecretPassword123!" not in last_line


# ==============================================================================
# 6. End-to-End Security Middleware Integration Tests
# ==============================================================================

def test_security_headers_injection():
    """Verify banking security headers are injected on live requests."""
    from fastapi.testclient import TestClient
    from backend.main import app
    
    with patch("backend.main.create_db_tables", new_callable=AsyncMock):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.headers.get("X-Frame-Options") in ("DENY", "SAMEORIGIN")
            assert resp.headers.get("X-Content-Type-Options") == "nosniff"
            assert resp.headers.get("Strict-Transport-Security") is not None
            assert resp.headers.get("X-Request-ID") is not None


def test_payload_too_large_413_guard():
    """Verify payloads exceeding 1MB are rejected with HTTP 413."""
    from fastapi.testclient import TestClient
    from backend.main import app
    
    with patch("backend.main.create_db_tables", new_callable=AsyncMock):
        with TestClient(app, raise_server_exceptions=False) as client:
            headers = {"content-length": str(2 * 1024 * 1024)}
            resp = client.post("/api/auth/login", data="x", headers=headers)
            assert resp.status_code == 413
            assert "Payload Too Large" in resp.json().get("error", "")


def test_rate_limit_headers_on_api_route():
    """Verify Token Bucket rate limit headers are attached to API responses."""
    from fastapi.testclient import TestClient
    from backend.main import app
    
    with patch("backend.main.create_db_tables", new_callable=AsyncMock):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/market/indices")
            assert "X-RateLimit-Limit" in resp.headers
            assert "X-RateLimit-Remaining" in resp.headers
            assert resp.headers.get("X-RateLimit-Tier") == "GENERAL"


def test_global_exception_handler_sanitization():
    """Verify internal unhandled errors do not leak database passwords or paths."""
    from fastapi.testclient import TestClient
    from backend.main import app
    
    @app.get("/api/test-crash-unhandled")
    def crash_route():
        raise RuntimeError("Secret DB Password exposed: postgresql://stockuser:secretpass@localhost/db")

    with patch("backend.main.create_db_tables", new_callable=AsyncMock):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/test-crash-unhandled")
            assert resp.status_code == 500
            body = resp.json()
            assert body["error"] == "Internal Server Error"
            assert "postgresql" not in resp.text
            assert "secretpass" not in resp.text
            assert "trace_id" in body

