"""
Real-time user presence tracking service using Redis Sorted Sets with a sliding-window TTL.
Tracks active user sessions across desktop and mobile devices.
Provides immediate decrement when users switch to background/recents or close the tab,
and automatic pruning for dropped connections or crashed browsers.
"""

import time
import asyncio
from typing import Optional
from backend.core.cache import get_redis
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# Sessions inactive for more than 25 seconds are pruned automatically
PRESENCE_TTL_SECONDS = 25
PRESENCE_REDIS_KEY = "presence:active_sessions"


class PresenceService:
    """Manages active user sessions in Redis with an in-memory resilient fallback."""

    def __init__(self):
        self._local_sessions: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def record_heartbeat(self, session_id: str) -> int:
        """
        Record a heartbeat for an active session.
        Adds/refreshes the session in Redis with the current timestamp score,
        prunes stale sessions, and returns the current active count.
        """
        now = time.time()
        try:
            r = await get_redis()
            if r is not None:
                pipe = r.pipeline()
                pipe.zadd(PRESENCE_REDIS_KEY, {session_id: now})
                pipe.zremrangebyscore(PRESENCE_REDIS_KEY, "-inf", now - PRESENCE_TTL_SECONDS)
                pipe.zcard(PRESENCE_REDIS_KEY)
                results = await pipe.execute()
                count = results[2]
                return max(1, int(count))
        except Exception as exc:
            logger.debug(f"[Presence] Redis unavailable for heartbeat ({exc}), using local fallback.")

        # Local in-memory fallback
        async with self._lock:
            self._local_sessions[session_id] = now
            cutoff = now - PRESENCE_TTL_SECONDS
            self._local_sessions = {
                sid: ts for sid, ts in self._local_sessions.items() if ts > cutoff
            }
            return max(1, len(self._local_sessions))

    async def record_leave(self, session_id: str) -> int:
        """
        Record that a user session has left (tab closed, hidden, or moved to mobile recent apps).
        Immediately removes the session from Redis and returns the updated count.
        """
        now = time.time()
        try:
            r = await get_redis()
            if r is not None:
                pipe = r.pipeline()
                pipe.zrem(PRESENCE_REDIS_KEY, session_id)
                pipe.zremrangebyscore(PRESENCE_REDIS_KEY, "-inf", now - PRESENCE_TTL_SECONDS)
                pipe.zcard(PRESENCE_REDIS_KEY)
                results = await pipe.execute()
                count = results[2]
                return max(0, int(count))
        except Exception as exc:
            logger.debug(f"[Presence] Redis unavailable for leave ({exc}), using local fallback.")

        # Local in-memory fallback
        async with self._lock:
            self._local_sessions.pop(session_id, None)
            cutoff = now - PRESENCE_TTL_SECONDS
            self._local_sessions = {
                sid: ts for sid, ts in self._local_sessions.items() if ts > cutoff
            }
            return max(0, len(self._local_sessions))

    async def get_active_count(self) -> int:
        """
        Retrieve the current number of active sessions after pruning expired ones.
        """
        now = time.time()
        try:
            r = await get_redis()
            if r is not None:
                pipe = r.pipeline()
                pipe.zremrangebyscore(PRESENCE_REDIS_KEY, "-inf", now - PRESENCE_TTL_SECONDS)
                pipe.zcard(PRESENCE_REDIS_KEY)
                results = await pipe.execute()
                count = results[1]
                return max(0, int(count))
        except Exception as exc:
            logger.debug(f"[Presence] Redis unavailable for get_count ({exc}), using local fallback.")

        # Local in-memory fallback
        async with self._lock:
            cutoff = now - PRESENCE_TTL_SECONDS
            self._local_sessions = {
                sid: ts for sid, ts in self._local_sessions.items() if ts > cutoff
            }
            return max(0, len(self._local_sessions))


presence_service = PresenceService()
