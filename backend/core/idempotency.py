"""
Financial Idempotency Key Manager.

Prevents double-spending, order replay attacks, and duplicate trade execution.
Ensures that if network retries or rapid double-clicks submit the same order,
it is executed exactly once within a configurable idempotency window.
"""

import time
import asyncio
from typing import Dict, Any, Optional, Tuple
from fastapi import Request, HTTPException, status
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


class IdempotencyRecord:
    def __init__(self):
        self.status = "IN_PROGRESS"  # "IN_PROGRESS" | "COMPLETED" | "FAILED"
        self.created_at = time.time()
        self.response_status_code: int = 200
        self.response_body: Optional[Any] = None


class IdempotencyManager:
    """In-memory thread-safe store for financial idempotency keys."""
    def __init__(self, ttl_seconds: int = 300):
        self._store: Dict[str, IdempotencyRecord] = {}
        self._lock = asyncio.Lock()
        self.ttl_seconds = ttl_seconds
        self._last_cleanup = time.time()

    async def get_or_create(self, key: str) -> Tuple[str, Optional[IdempotencyRecord]]:
        """
        Check idempotency status of a key.
        Returns:
            ("NEW", record) if this is the first time seeing this key.
            ("IN_PROGRESS", record) if currently being executed by another concurrent request.
            ("COMPLETED", record) if already processed.
        """
        async with self._lock:
            now = time.time()
            # Periodic cleanup
            if now - self._last_cleanup > 120:
                stale = [k for k, r in self._store.items() if now - r.created_at > self.ttl_seconds]
                for k in stale:
                    del self._store[k]
                self._last_cleanup = now

            if key in self._store:
                rec = self._store[key]
                if now - rec.created_at > self.ttl_seconds:
                    # Key expired, treat as new
                    rec = IdempotencyRecord()
                    self._store[key] = rec
                    return "NEW", rec
                if rec.status == "IN_PROGRESS":
                    return "IN_PROGRESS", rec
                return "COMPLETED", rec

            # Brand new key
            rec = IdempotencyRecord()
            self._store[key] = rec
            return "NEW", rec

    async def mark_completed(self, key: str, status_code: int, response_body: Any):
        """Mark record as completed with stored response."""
        async with self._lock:
            if key in self._store:
                self._store[key].status = "COMPLETED"
                self._store[key].response_status_code = status_code
                self._store[key].response_body = response_body

    async def mark_failed(self, key: str):
        """Remove or mark failed key so caller can safely retry."""
        async with self._lock:
            if key in self._store:
                del self._store[key]


idempotency_manager = IdempotencyManager(ttl_seconds=300)
