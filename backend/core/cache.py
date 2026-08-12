"""Redis cache client."""

import json
import redis.asyncio as redis

from backend.core.config import settings
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

import asyncio
_redis_client: redis.Redis | None = None
_redis_loop_id: int | None = None

async def get_redis() -> redis.Redis:
    global _redis_client, _redis_loop_id
    try:
        current_loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        current_loop_id = None

    if _redis_client is None or _redis_loop_id != current_loop_id:
        if _redis_client is not None:
            try:
                await _redis_client.aclose()
            except Exception:
                pass
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        _redis_loop_id = current_loop_id
    return _redis_client


async def cache_get(key: str):
    try:
        r = await get_redis()
        value = await r.get(key)
        if value:
            return json.loads(value)
    except (redis.RedisError, json.JSONDecodeError) as exc:
        # Caching is an optimization: a Redis outage must not take down market data.
        logger.warning("Cache read unavailable for %s: %s", key, exc)
    return None


async def cache_set(key: str, value, ttl: int = 60):
    try:
        r = await get_redis()
        await r.setex(key, ttl, json.dumps(value, default=str))
    except (redis.RedisError, TypeError, ValueError) as exc:
        logger.warning("Cache write unavailable for %s: %s", key, exc)


async def cache_delete(key: str):
    try:
        r = await get_redis()
        await r.delete(key)
    except redis.RedisError as exc:
        logger.warning("Cache delete unavailable for %s: %s", key, exc)
