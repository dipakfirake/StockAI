"""
Industrial Token Bucket Rate Limiter for Financial APIs.

Implements token bucket algorithm with:
- Multi-tier rate limiting (Auth, Trading, AI Analytics, General)
- Dual identification: Per-IP and Per-User (when authenticated)
- Compliant HTTP 429 responses with standard IETF headers (Retry-After, X-RateLimit-*)
- Memory-safe periodic garbage collection of idle buckets
"""

import time
import asyncio
from typing import Dict, Tuple, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


class RateLimitTier:
    """Rate limit configuration for an endpoint tier."""
    def __init__(self, capacity: int, refill_rate_per_sec: float, name: str):
        self.capacity = capacity              # Maximum burst tokens
        self.refill_rate = refill_rate_per_sec  # Tokens replenished per second
        self.name = name


# Predefined industrial tiers
TIERS = {
    "AUTH": RateLimitTier(capacity=10, refill_rate_per_sec=10 / 60.0, name="AUTH"),         # 10 req/min (anti-bruteforce)
    "TRADING": RateLimitTier(capacity=20, refill_rate_per_sec=30 / 60.0, name="TRADING"),    # 30 req/min (anti-replay/spam)
    "AI": RateLimitTier(capacity=15, refill_rate_per_sec=30 / 60.0, name="AI"),              # 30 req/min (heavy compute)
    "PRESENCE": RateLimitTier(capacity=200, refill_rate_per_sec=240 / 60.0, name="PRESENCE"), # 240 req/min (high-frequency heartbeats)
    "GENERAL": RateLimitTier(capacity=100, refill_rate_per_sec=120 / 60.0, name="GENERAL"), # 120 req/min (standard)
}


class TokenBucket:
    """Thread-safe token bucket instance."""
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill_rate = refill_rate
        self.last_updated = time.monotonic()
        self.last_accessed = time.time()

    def consume(self, tokens: float = 1.0) -> Tuple[bool, float, float]:
        """
        Attempt to consume tokens.
        Returns:
            (allowed: bool, remaining_tokens: float, wait_time_seconds: float)
        """
        now = time.monotonic()
        elapsed = now - self.last_updated
        self.last_updated = now
        self.last_accessed = time.time()

        # Replenish tokens up to capacity
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True, self.tokens, 0.0
        else:
            needed = tokens - self.tokens
            wait_time = needed / self.refill_rate if self.refill_rate > 0 else 60.0
            return False, self.tokens, wait_time


class TokenBucketRateLimiter:
    """Central registry and evaluator of token buckets."""
    def __init__(self):
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()
        self._last_cleanup = time.time()
        self.cleanup_interval = 600  # Clean idle buckets every 10 min
        self.bucket_ttl = 900        # Expire buckets unused for 15 min

    def _get_client_ip(self, request: Request) -> str:
        """Extract trusted client IP address."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # First IP in chain is the original client
            return forwarded.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    def determine_tier(self, path: str) -> str:
        """Map URL path to appropriate rate limit tier."""
        p = path.lower()
        if p.startswith("/api/auth"):
            return "AUTH"
        elif p.startswith("/api/paper-trades") or p.startswith("/api/portfolio"):
            return "TRADING"
        elif p.startswith("/api/ai") or p.startswith("/api/backtest") or p.startswith("/api/ml"):
            return "AI"
        elif p.startswith("/api/presence"):
            return "PRESENCE"
        return "GENERAL"

    async def check_rate_limit(self, request: Request) -> Optional[Tuple[bool, dict, float]]:
        """
        Check whether the incoming request is within token bucket limits.
        Returns:
            None if skipped (e.g. docs, health, options),
            or (allowed: bool, headers: dict, wait_seconds: float).
        """
        # Skip health checks, docs, static files, and CORS preflight
        if request.method == "OPTIONS":
            return None
        path = request.url.path
        if path in ("/", "/health", "/docs", "/redoc", "/openapi.json"):
            return None

        tier_key = self.determine_tier(path)
        tier = TIERS[tier_key]
        client_ip = self._get_client_ip(request)

        # Check for Authorization token to limit per-user if present
        auth_header = request.headers.get("Authorization", "")
        client_key = f"{tier_key}:{client_ip}"
        if auth_header.startswith("Bearer "):
            # Hash or truncate token to form a stable key without leaking raw token
            token_fingerprint = str(hash(auth_header))
            client_key = f"{tier_key}:user:{token_fingerprint[:16]}"

        async with self._lock:
            # Periodic cleanup of idle buckets to avoid memory leaks
            now_wall = time.time()
            if now_wall - self._last_cleanup > self.cleanup_interval:
                stale_keys = [
                    k for k, b in self._buckets.items()
                    if now_wall - b.last_accessed > self.bucket_ttl
                ]
                for k in stale_keys:
                    del self._buckets[k]
                self._last_cleanup = now_wall

            if client_key not in self._buckets:
                self._buckets[client_key] = TokenBucket(tier.capacity, tier.refill_rate)

            bucket = self._buckets[client_key]
            allowed, remaining, wait_time = bucket.consume(1.0)

        headers = {
            "X-RateLimit-Limit": str(tier.capacity),
            "X-RateLimit-Remaining": str(max(0, int(remaining))),
            "X-RateLimit-Reset": str(int(wait_time) if wait_time > 0 else 0),
            "X-RateLimit-Tier": tier.name,
        }

        return allowed, headers, wait_time


rate_limiter = TokenBucketRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware to enforce Token Bucket rate limits across all routes."""
    async def dispatch(self, request: Request, call_next):
        res = await rate_limiter.check_rate_limit(request)
        if res is not None:
            allowed, headers, wait_time = res
            if not allowed:
                retry_after = max(1, int(wait_time))
                headers["Retry-After"] = str(retry_after)
                logger.warning(
                    f"[RateLimit] 429 Blocked: {request.method} {request.url.path} "
                    f"from {request.client.host if request.client else 'unknown'} "
                    f"(Tier: {headers.get('X-RateLimit-Tier')}, Retry-After: {retry_after}s)"
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "Too Many Requests",
                        "detail": f"Rate limit exceeded for {headers.get('X-RateLimit-Tier')} tier. Please retry in {retry_after} seconds.",
                        "retry_after": retry_after,
                        "tier": headers.get("X-RateLimit-Tier"),
                    },
                    headers=headers,
                )

            # Request allowed; attach headers to response
            response = await call_next(request)
            for k, v in headers.items():
                response.headers[k] = v
            return response

        return await call_next(request)
