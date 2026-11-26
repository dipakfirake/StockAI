"""Redis cache client with high-capacity connection pooling and graceful fallback."""

import json
import asyncio
from typing import Optional, Dict, Tuple
import redis.asyncio as redis

from backend.core.config import settings
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# Cache clients partitioned by asyncio event loop instance to eliminate multi-loop leaks
# Stores {loop_id: (loop_ref, redis_client)} so reused loop addresses never return stale pools.
_redis_clients: Dict[int, Tuple[Optional[asyncio.AbstractEventLoop], redis.Redis]] = {}


def _evict_closed_loop_clients() -> None:
    """Drop Redis clients whose originating event loop has been closed."""
    for lid, (loop_ref, _) in list(_redis_clients.items()):
        if loop_ref is not None and loop_ref.is_closed():
            _redis_clients.pop(lid, None)


async def get_redis() -> redis.Redis:
    global _redis_clients
    try:
        current_loop = asyncio.get_running_loop()
        current_loop_id = id(current_loop)
    except RuntimeError:
        current_loop = None
        current_loop_id = 0

    _evict_closed_loop_clients()

    entry = _redis_clients.get(current_loop_id)
    if entry is not None:
        stored_loop, stored_client = entry
        if stored_loop is current_loop:
            return stored_client
        _redis_clients.pop(current_loop_id, None)

    client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=500,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
        health_check_interval=30,
    )
    _redis_clients[current_loop_id] = (current_loop, client)
    return client


async def close_redis():
    """Cleanly close all active Redis client connection pools."""
    global _redis_clients
    for lid, (loop_ref, client) in list(_redis_clients.items()):
        try:
            if loop_ref is None or not loop_ref.is_closed():
                await client.aclose()
        except Exception:
            pass
    _redis_clients.clear()


async def cache_get(key: str):
    try:
        r = await get_redis()
        value = await r.get(key)
        if value:
            return json.loads(value)
    except (redis.RedisError, json.JSONDecodeError) as exc:
        # Caching is an optimization: a Redis outage or saturation must not crash callers.
        logger.debug("Cache read unavailable for %s: %s", key, exc)
    except Exception as exc:
        logger.debug("Unexpected error during cache read for %s: %s", key, exc)
    return None


async def cache_set(key: str, value, ttl: int = 60):
    try:
        r = await get_redis()
        await r.set(key, json.dumps(value, default=str), ex=ttl)
    except (redis.RedisError, TypeError, ValueError) as exc:
        logger.debug("Cache write unavailable for %s: %s", key, exc)
    except Exception as exc:
        logger.debug("Unexpected error during cache write for %s: %s", key, exc)


async def cache_delete(key: str):
    try:
        r = await get_redis()
        await r.delete(key)
    except (redis.RedisError, Exception) as exc:
        logger.debug("Cache delete unavailable for %s: %s", key, exc)
