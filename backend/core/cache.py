"""Redis cache client."""

import json
import redis.asyncio as redis

from backend.core.config import settings
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def cache_get(key: str):
    r = await get_redis()
    value = await r.get(key)
    if value:
        return json.loads(value)
    return None


async def cache_set(key: str, value, ttl: int = 60):
    r = await get_redis()
    await r.setex(key, ttl, json.dumps(value, default=str))


async def cache_delete(key: str):
    r = await get_redis()
    await r.delete(key)
