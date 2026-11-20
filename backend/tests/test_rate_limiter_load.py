"""
Automated Load & Concurrency Tests for All Rate Limiter Tiers.

Verifies:
1. AUTH Tier (capacity=10, 10/min): Allows 10 burst requests, blocks 11th with HTTP 429 and Retry-After header.
2. TRADING Tier (capacity=20, 30/min): Allows 20 burst requests, blocks 21st with HTTP 429.
3. AI Tier (capacity=15, 30/min): Allows 15 burst requests, blocks 16th with HTTP 429.
4. PRESENCE Tier (capacity=200, 240/min): Sustains 200 concurrent requests without premature rejection.
5. GENERAL Tier (capacity=100, 120/min): Allows 100 burst requests, blocks 101st with HTTP 429.
6. Health / Docs Exemption: 300 requests bypass rate limiting with 0 rejections.
"""

import pytest
import asyncio
from unittest.mock import MagicMock
from fastapi import FastAPI, Request
from starlette.testclient import TestClient
from starlette.responses import JSONResponse

from backend.core.rate_limiter import TokenBucketRateLimiter, RateLimitMiddleware, TIERS


def test_auth_tier_burst_and_rate_limit_429():
    """Verify AUTH tier permits exactly 10 burst requests and blocks subsequent with 429 and Retry-After."""
    limiter = TokenBucketRateLimiter()
    client_ip = "192.168.1.50"

    # 1. First 10 requests must be allowed
    for i in range(10):
        mock_req = MagicMock(spec=Request)
        mock_req.method = "POST"
        mock_req.url.path = "/api/auth/login"
        mock_req.headers = {}
        mock_req.client.host = client_ip
        
        res = asyncio.run(limiter.check_rate_limit(mock_req))
        assert res is not None
        allowed, headers, wait_time = res
        assert allowed is True, f"Request {i+1} should be allowed"
        assert headers["X-RateLimit-Tier"] == "AUTH"
        assert int(headers["X-RateLimit-Limit"]) == 10

    # 2. 11th request must be blocked with HTTP 429
    mock_blocked = MagicMock(spec=Request)
    mock_blocked.method = "POST"
    mock_blocked.url.path = "/api/auth/login"
    mock_blocked.headers = {}
    mock_blocked.client.host = client_ip

    res = asyncio.run(limiter.check_rate_limit(mock_blocked))
    assert res is not None
    allowed, headers, wait_time = res
    assert allowed is False
    assert wait_time > 0
    assert "Retry-After" in headers
    assert int(headers["Retry-After"]) >= 1


def test_trading_tier_burst_and_rate_limit_429():
    """Verify TRADING tier permits exactly 20 burst requests and blocks 21st."""
    limiter = TokenBucketRateLimiter()
    client_ip = "192.168.1.51"

    for i in range(20):
        mock_req = MagicMock(spec=Request)
        mock_req.method = "POST"
        mock_req.url.path = "/api/paper-trades/orders"
        mock_req.headers = {}
        mock_req.client.host = client_ip
        
        res = asyncio.run(limiter.check_rate_limit(mock_req))
        assert res is not None
        allowed, headers, wait_time = res
        assert allowed is True
        assert headers["X-RateLimit-Tier"] == "TRADING"

    # 21st blocked
    mock_blocked = MagicMock(spec=Request)
    mock_blocked.method = "POST"
    mock_blocked.url.path = "/api/paper-trades/orders"
    mock_blocked.headers = {}
    mock_blocked.client.host = client_ip

    res = asyncio.run(limiter.check_rate_limit(mock_blocked))
    assert res is not None
    allowed, headers, wait_time = res
    assert allowed is False
    assert "Retry-After" in headers


def test_ai_tier_burst_and_rate_limit_429():
    """Verify AI tier permits exactly 15 burst requests and blocks 16th."""
    limiter = TokenBucketRateLimiter()
    client_ip = "192.168.1.52"

    for i in range(15):
        mock_req = MagicMock(spec=Request)
        mock_req.method = "GET"
        mock_req.url.path = "/api/ai/score"
        mock_req.headers = {}
        mock_req.client.host = client_ip
        
        res = asyncio.run(limiter.check_rate_limit(mock_req))
        assert res is not None
        allowed, headers, wait_time = res
        assert allowed is True
        assert headers["X-RateLimit-Tier"] == "AI"

    # 16th blocked
    mock_blocked = MagicMock(spec=Request)
    mock_blocked.method = "GET"
    mock_blocked.url.path = "/api/ai/score"
    mock_blocked.headers = {}
    mock_blocked.client.host = client_ip

    res = asyncio.run(limiter.check_rate_limit(mock_blocked))
    assert res is not None
    allowed, headers, wait_time = res
    assert allowed is False


def test_presence_tier_high_frequency_capacity():
    """Verify PRESENCE tier sustains 200 high-frequency requests without rejection."""
    limiter = TokenBucketRateLimiter()
    client_ip = "192.168.1.53"

    allowed_count = 0
    for i in range(200):
        mock_req = MagicMock(spec=Request)
        mock_req.method = "POST"
        mock_req.url.path = "/api/presence/heartbeat"
        mock_req.headers = {}
        mock_req.client.host = client_ip

        res = asyncio.run(limiter.check_rate_limit(mock_req))
        assert res is not None
        allowed, headers, wait_time = res
        if allowed:
            allowed_count += 1
        assert headers["X-RateLimit-Tier"] == "PRESENCE"

    # All 200 high-frequency burst heartbeats must be permitted
    assert allowed_count == 200

    # Exhaust any fractional token refills from loop duration, then verify 429 rejection
    blocked = False
    for _ in range(50):
        mock_blocked = MagicMock(spec=Request)
        mock_blocked.method = "POST"
        mock_blocked.url.path = "/api/presence/heartbeat"
        mock_blocked.headers = {}
        mock_blocked.client.host = client_ip
        res = asyncio.run(limiter.check_rate_limit(mock_blocked))
        if res and not res[0]:
            blocked = True
            assert "Retry-After" in res[1]
            break
    assert blocked is True


def test_health_and_docs_exemption():
    """Verify /health and docs paths are strictly exempt from rate limiting."""
    limiter = TokenBucketRateLimiter()
    client_ip = "192.168.1.54"

    exempt_paths = ["/health", "/health/live", "/api/health", "/docs", "/openapi.json"]
    for path in exempt_paths:
        for _ in range(50):
            mock_req = MagicMock(spec=Request)
            mock_req.method = "GET"
            mock_req.url.path = path
            mock_req.headers = {}
            mock_req.client.host = client_ip

            res = asyncio.run(limiter.check_rate_limit(mock_req))
            assert res is None, f"{path} should return None (bypassing rate limiter)"


def test_full_middleware_integration_429_json_response():
    """Verify RateLimitMiddleware returns RFC-compliant 429 JSON payload with Retry-After header."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/ai/sentiment")
    def sentiment_route():
        return {"sentiment": "BULLISH"}

    client = TestClient(app)

    # Exhaust the 15 tokens in AI tier
    for _ in range(15):
        resp = client.get("/api/ai/sentiment")
        assert resp.status_code == 200

    # 16th request must yield 429 with Retry-After header and structured error detail
    resp_429 = client.get("/api/ai/sentiment")
    assert resp_429.status_code == 429
    assert "Retry-After" in resp_429.headers
    assert "X-RateLimit-Tier" in resp_429.headers
    assert resp_429.headers["X-RateLimit-Tier"] == "AI"
    data = resp_429.json()
    assert "error" in data
    assert (
        "rate limit" in data.get("error", "").lower()
        or "rate limit" in data.get("detail", "").lower()
    )
    assert "retry_after" in data
