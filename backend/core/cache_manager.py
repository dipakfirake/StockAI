"""
Enterprise Multi-Layer Caching Engine with Cache Stampede Protection.

Architecture:
- L1: In-Process Microsecond Memory Cache with TTL & LRU eviction.
- L2: Distributed Redis Cache with graceful offline fallback.
- Single-Flight Request Coalescing (Prevents Thundering Herd on cold/expired keys).
"""

import time
import json
import asyncio
from typing import Any, Optional, Callable, Dict
from collections import OrderedDict
from backend.core.cache import cache_get, cache_set, cache_delete
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


class L1MemoryCache:
    """Thread-safe in-memory LRU cache with per-item TTL."""
    def __init__(self, max_items: int = 2000):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_items = max_items
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._cache:
                return None
            val, expiry = self._cache[key]
            if time.time() > expiry:
                del self._cache[key]
                return None
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return val

    async def set(self, key: str, value: Any, ttl: int = 60):
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
            elif len(self._cache) >= self._max_items:
                # Evict least recently used (first item)
                self._cache.popitem(last=False)
            self._cache[key] = (value, time.time() + ttl)

    async def delete(self, key: str):
        async with self._lock:
            if key in self._cache:
                del self._cache[key]


class SingleFlightGroup:
    """
    Coalesces duplicate concurrent lookups so only one outbound worker executes.
    All concurrent callers for the same key await the single inflight task.
    """
    def __init__(self):
        self._inflight: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def execute(self, key: str, factory: Callable[[], Any]) -> Any:
        async with self._lock:
            if key in self._inflight:
                # Another task is already computing this key; await its result
                fut = self._inflight[key]
                need_wait = True
            else:
                loop = asyncio.get_running_loop()
                fut = loop.create_future()
                self._inflight[key] = fut
                need_wait = False

        if need_wait:
            return await fut

        # Current task is the worker that computes the value
        try:
            if asyncio.iscoroutinefunction(factory):
                val = await factory()
            else:
                val = factory()
            fut.set_result(val)
            return val
        except Exception as exc:
            fut.set_exception(exc)
            raise
        finally:
            async with self._lock:
                if key in self._inflight:
                    del self._inflight[key]


class Tier1CacheManager:
    """Enterprise multi-tier cache manager."""
    def __init__(self):
        self.l1 = L1MemoryCache(max_items=3000)
        self.single_flight = SingleFlightGroup()

    async def get(self, key: str) -> Optional[Any]:
        """Check L1 memory first, then L2 Redis."""
        # 1. L1 lookup (sub-millisecond)
        l1_val = await self.l1.get(key)
        if l1_val is not None:
            return l1_val

        # 2. L2 lookup (Redis)
        l2_val = await cache_get(key)
        if l2_val is not None:
            # Promote to L1
            await self.l1.set(key, l2_val, ttl=30)
            return l2_val

        return None

    async def set(self, key: str, value: Any, ttl: int = 60):
        """Write to both L1 and L2 concurrently."""
        await self.l1.set(key, value, ttl=min(ttl, 60))
        await cache_set(key, value, ttl=ttl)

    async def get_or_compute(self, key: str, factory: Callable[[], Any], ttl: int = 60) -> Any:
        """
        Cache-Aside with Single-Flight Stampede Protection.
        Guarantees that multiple concurrent callers for cold keys only trigger ONE factory call.
        """
        cached = await self.get(key)
        if cached is not None:
            return cached

        # Wrap in single-flight coalescer
        async def _compute_and_cache():
            # Double-check cache in case another task populated it
            c = await self.get(key)
            if c is not None:
                return c
            result = await factory() if asyncio.iscoroutinefunction(factory) else factory()
            if result is not None:
                await self.set(key, result, ttl=ttl)
            return result

        return await self.single_flight.execute(key, _compute_and_cache)

    async def delete(self, key: str):
        """Invalidate across all cache tiers."""
        await self.l1.delete(key)
        await cache_delete(key)


cache_manager = Tier1CacheManager()
