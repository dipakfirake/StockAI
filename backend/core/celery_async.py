"""
Persistent per-process event loop runner for Celery tasks.

Calling ``asyncio.run()`` repeatedly inside long-lived Celery prefork worker
processes creates and tears down thousands of event loops, leaking open Redis
``ConnectionPool`` TCP sockets and file descriptors until ``ulimit -n`` is
exhausted (``OSError: [Errno 24] Too many open files``).

This module maintains one persistent ``asyncio`` event loop per worker PID
(fork-safe via ``os.getpid()``) and disposes Redis/SQLAlchemy resources cleanly
on worker process shutdown.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
from typing import Any, Coroutine, Dict, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Map PID -> persistent event loop so forked workers never inherit a parent loop
_worker_loops: Dict[int, asyncio.AbstractEventLoop] = {}


def _get_or_create_worker_loop() -> asyncio.AbstractEventLoop:
    pid = os.getpid()
    loop = _worker_loops.get(pid)
    if loop is None or loop.is_closed():
        # Discard stale loops from ancestor PIDs after fork()
        for old_pid in [p for p in list(_worker_loops.keys()) if p != pid]:
            _worker_loops.pop(old_pid, None)
        loop = asyncio.new_event_loop()
        _worker_loops[pid] = loop
    asyncio.set_event_loop(loop)
    return loop


def run_in_worker_loop(coro: Coroutine[Any, Any, T]) -> T:
    """
    Execute an async coroutine on the worker process's persistent event loop.

    If called inside an already-running event loop (for example in an async test),
    offloads execution safely to a dedicated single-thread runner.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = _get_or_create_worker_loop()
        return loop.run_until_complete(coro)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()


def close_worker_loops() -> None:
    """Gracefully close cached Redis pools, DB engine, and worker event loop on shutdown."""
    pid = os.getpid()
    loop = _worker_loops.pop(pid, None)
    if loop is None or loop.is_closed():
        return

    async def _cleanup():
        try:
            from backend.core.cache import close_redis
            await close_redis()
        except Exception as exc:
            logger.debug("Worker Redis shutdown notice: %s", exc)
        try:
            from backend.core.database import engine
            await engine.dispose()
        except Exception as exc:
            logger.debug("Worker DB engine dispose notice: %s", exc)

    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_cleanup())
    except Exception as exc:
        logger.debug("Worker loop cleanup notice: %s", exc)
    finally:
        try:
            loop.close()
        except Exception:
            pass
