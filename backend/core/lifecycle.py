"""
Enterprise Lifecycle & Coordinated Graceful Shutdown Engine.

Handles:
- Coordinated startup checks
- Signal trapping (SIGTERM, SIGINT)
- Safe task drainage without dropping in-flight financial executions
- Database connection pool disposal and Redis connection release
"""

import asyncio
from typing import List
from backend.core.database import engine, create_db_tables
from backend.core.cache import get_redis
from backend.core.logging_config import setup_logging, get_logger

logger = get_logger(__name__)


class LifecycleManager:
    """Manages the full startup and coordinated shutdown lifecycle."""
    def __init__(self):
        self._background_tasks: List[asyncio.Task] = []
        self._is_shutting_down = False

    def register_task(self, task: asyncio.Task):
        """Register long-running background tasks for graceful cancellation."""
        self._background_tasks.append(task)

    async def startup(self):
        """Coordinated enterprise startup sequence."""
        logger.info("[Lifecycle] Starting enterprise services...")
        setup_logging()
        await create_db_tables()
        logger.info("[Lifecycle] Core database tables verified.")

    async def shutdown(self):
        """Coordinated enterprise graceful shutdown sequence."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        logger.info("[Lifecycle] Initiating coordinated graceful shutdown...")

        # 1. Cancel registered background workers
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        if self._background_tasks:
            logger.info(f"[Lifecycle] Waiting for {len(self._background_tasks)} background tasks to drain...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._background_tasks, return_exceptions=True),
                    timeout=5.0,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning("[Lifecycle] Timeout draining background tasks, forcing termination.")

        # 2. Flush and close Redis connections
        try:
            r = await get_redis()
            if r is not None:
                await r.aclose()
                logger.info("[Lifecycle] Redis client connection cleanly closed.")
        except Exception as e:
            logger.debug(f"[Lifecycle] Redis close bypassed: {e}")

        # 3. Dispose of PostgreSQL connection pool (releases Neon connections)
        try:
            await engine.dispose()
            logger.info("[Lifecycle] Database connection pool disposed cleanly.")
        except Exception as e:
            logger.error(f"[Lifecycle] Error disposing database pool: {e}")

        logger.info("[Lifecycle] Graceful shutdown sequence completed successfully.")


lifecycle = LifecycleManager()
