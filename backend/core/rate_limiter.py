"""
Industrial Token Bucket Rate Limiter for Financial APIs.

Implements token bucket algorithm with:
- Multi-tier rate limiting (Auth, Trading, AI Analytics, General)
- Dual identification: Per-IP and Per-User (when authenticated)
- Compliant HTTP 429 responses with standard IETF headers (Retry-After, X-RateLimit-*)
- Memory-safe periodic garbage collection of idle buckets
- Thread-safe, non-deadlocking synchronization compatible with single/multi-worker Uvicorn
- Disconnect-safe middleware handling (catches Starlette BaseHTTPMiddleware client disconnects)
"""

import asyncio
import hashlib
import time
import threading
from typing import Dict, Tuple, Optional
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

_REDIS_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil or ts == nil then
    tokens = capacity
    ts = now
else
    local elapsed = math.max(0, now - ts)
    tokens = math.min(capacity, tokens + elapsed * refill_rate)
    ts = now
end

local allowed = 0
local wait_time = 0
if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
else
    local needed = cost - tokens
    if refill_rate > 0 then
        wait_time = needed / refill_rate
    else
        wait_time = 60
    end
end

redis.call('HSET', key, 'tokens', tostring(tokens), 'ts', tostring(ts))
redis.call('EXPIRE', key, ttl)
return {allowed, tostring(tokens), tostring(wait_time)}
"""


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
        self._lock = threading.Lock()
        self._last_cleanup = time.time()
        self.cleanup_interval = 600  # Clean idle buckets every 10 min
        self.bucket_ttl = 900        # Expire buckets unused for 15 min
        self._redis_down_until = 0.0
        self._last_get_redis_ref = None

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
        if path in ("/", "/health", "/docs", "/redoc", "/openapi.json") or path.startswith("/health") or path.startswith("/api/health"):
            return None

        tier_key = self.determine_tier(path)
        tier = TIERS[tier_key]
        client_ip = self._get_client_ip(request)

        # Check for Authorization Bearer token or HttpOnly session cookie (deterministic SHA-256 key)
        auth_header = request.headers.get("Authorization", "")
        cookies = getattr(request, "cookies", None) or {}
        cookie_tok = cookies.get("stockai_access_token") if isinstance(cookies, dict) or hasattr(cookies, "get") else None
        client_key = f"{tier_key}:{client_ip}"
        identity_secret = auth_header if auth_header.startswith("Bearer ") else (f"cookie:{cookie_tok}" if cookie_tok else "")
        if identity_secret:
            token_fingerprint = hashlib.sha256(identity_secret.encode("utf-8")).hexdigest()[:16]
            client_key = f"{tier_key}:user:{token_fingerprint}"

        # Prefer atomic distributed Redis token bucket across workers; seamlessly fall back to local memory
        used_redis = False
        allowed = True
        remaining = float(tier.capacity)
        wait_time = 0.0
        try:
            from backend.core.cache import get_redis

            now_mono = time.monotonic()
            if not (now_mono < self._redis_down_until and self._last_get_redis_ref is get_redis):
                async def _redis_consume():
                    r = await get_redis()
                    return await r.eval(
                        _REDIS_TOKEN_BUCKET_LUA,
                        1,
                        f"rl:{client_key}",
                        str(tier.capacity),
                        str(tier.refill_rate),
                        str(time.time()),
                        "1.0",
                        str(self.bucket_ttl),
                    )

                try:
                    res = await asyncio.wait_for(_redis_consume(), timeout=0.05)
                    if res and len(res) >= 3:
                        self._redis_down_until = 0.0
                        self._last_get_redis_ref = get_redis
                        allowed = bool(int(res[0]))
                        remaining = float(res[1])
                        wait_time = float(res[2])
                        used_redis = True
                except Exception:
                    self._last_get_redis_ref = get_redis
                    self._redis_down_until = time.monotonic() + 5.0
                    used_redis = False
        except Exception:
            used_redis = False

        if not used_redis:
            with self._lock:
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
        if not allowed:
            headers["Retry-After"] = str(max(1, int(wait_time)))

        return allowed, headers, wait_time


rate_limiter = TokenBucketRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware to enforce Token Bucket rate limits across all routes."""
    async def dispatch(self, request: Request, call_next):
        try:
            res = await rate_limiter.check_rate_limit(request)
        except Exception as exc:
            logger.error(f"[RateLimit] Fail-open on rate limit check error: {exc}")
            res = None

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
            try:
                response = await call_next(request)
            except RuntimeError as exc:
                if "No response returned" in str(exc):
                    # Client disconnected before response was generated
                    return Response(status_code=status.HTTP_204_NO_CONTENT)
                raise

            for k, v in headers.items():
                response.headers[k] = v
            return response

        try:
            return await call_next(request)
        except RuntimeError as exc:
            if "No response returned" in str(exc):
                return Response(status_code=status.HTTP_204_NO_CONTENT)
            raise
