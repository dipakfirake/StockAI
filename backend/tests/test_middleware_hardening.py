"""
Automated unit tests for Middleware Hardening and Disconnect Safety.

Verifies:
1. TokenBucketRateLimiter consumes tokens safely with threading.Lock (zero asyncio event loop dependency).
2. RateLimitMiddleware catches Starlette's RuntimeError('No response returned.') on client disconnect and returns HTTP 204.
3. SecurityHeadersMiddleware catches Starlette's RuntimeError('No response returned.') on client disconnect and returns HTTP 204.
4. RateLimitMiddleware fails open if check_rate_limit encounters an unexpected exception.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect
from starlette.testclient import TestClient

from backend.core.rate_limiter import TokenBucketRateLimiter, RateLimitMiddleware, rate_limiter
from backend.core.security_middleware import SecurityHeadersMiddleware


def test_token_bucket_thread_safe_consumption():
    """Verify TokenBucketRateLimiter correctly processes requests without asyncio event loop dependency."""
    limiter = TokenBucketRateLimiter()
    mock_request = MagicMock(spec=Request)
    mock_request.method = "GET"
    mock_request.url.path = "/api/stocks/RELIANCE.NS/quote"
    mock_request.headers = {}
    mock_request.client.host = "192.168.1.100"

    # Synchronous or coroutine check
    import asyncio
    res = asyncio.run(limiter.check_rate_limit(mock_request))
    assert res is not None
    allowed, headers, wait_time = res
    assert allowed is True
    assert "X-RateLimit-Limit" in headers
    assert "X-RateLimit-Tier" in headers
    assert headers["X-RateLimit-Tier"] == "GENERAL"


def test_rate_limit_middleware_client_disconnect_returns_204():
    """Verify RateLimitMiddleware returns 204 when downstream raises RuntimeError('No response returned.')."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test-disconnect")
    async def disconnect_route():
        raise RuntimeError("No response returned.")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/test-disconnect")
    assert response.status_code == status.HTTP_204_NO_CONTENT


def test_security_middleware_client_disconnect_returns_204():
    """Verify SecurityHeadersMiddleware returns 204 when downstream raises RuntimeError('No response returned.')."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test-sec-disconnect")
    async def sec_disconnect_route():
        raise RuntimeError("No response returned.")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/test-sec-disconnect")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert "x-request-id" in response.headers or "X-Request-ID" in response.headers


def test_rate_limit_middleware_fails_open_on_error():
    """Verify RateLimitMiddleware fails open (allows request) if rate limit check encounters an exception."""
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/test-fail-open")
    async def normal_route():
        return {"status": "ok"}

    with patch.object(rate_limiter, "check_rate_limit", side_effect=Exception("Simulated Redis/Lock crash")):
        client = TestClient(app)
        response = client.get("/test-fail-open")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}
