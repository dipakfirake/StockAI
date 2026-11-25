"""
Segregated ThreadPool Executors & CPU Concurrency Guardrails.

Prevents slow external scrapers (yfinance, feedparser, BeautifulSoup) and
PyTorch/LightGBM CPU-bound scoring from starving the single Uvicorn asyncio
event loop or blocking fast control-plane paths (broker profile checks, auth,
health checks) on 1-OCPU / low-core cloud hosts.
"""

from __future__ import annotations

import asyncio
import functools
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from backend.core.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

_cpu_count = os.cpu_count() or 1

# 1. Fast Control-Plane Executor: exclusively for broker token checks, auth/bcrypt,
#    and quick health probes — never shared with scrapers or ML inference.
fast_control_executor = ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="fast-ctrl",
)

# 2. External Scraper / Network I/O Executor: isolates blocking yfinance, RSS,
#    and HTML parser calls so runaway external sockets cannot starve auth or health.
scraper_io_executor = ThreadPoolExecutor(
    max_workers=6,
    thread_name_prefix="scraper-io",
)

# 3. ML & Technical Compute Executor: bounds concurrent PyTorch/LightGBM work to
#    avoid OpenMP/GIL thrashing on 1-2 vCPU hosts while keeping event loop responsive.
ml_compute_executor = ThreadPoolExecutor(
    max_workers=2 if _cpu_count <= 2 else 4,
    thread_name_prefix="ml-cpu",
)

_ml_runtime_configured = False


def configure_ml_runtime() -> None:
    """
    Pin PyTorch intra-op and inter-op thread counts to 1 so concurrent ML scoring
    inside worker threads does not oversubscribe 1-OCPU containers or starve Uvicorn.
    """
    global _ml_runtime_configured
    if _ml_runtime_configured:
        return
    _ml_runtime_configured = True

    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

    try:
        import torch

        torch.set_num_threads(1)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            # Already initialized after parallel work started
            pass
        logger.info(
            f"[Executors] ML runtime configured: cpu_count={_cpu_count}, "
            f"torch_threads={torch.get_num_threads()}"
        )
    except Exception as exc:
        logger.debug(f"[Executors] PyTorch runtime tuning skipped: {exc}")


async def run_in_fast_executor(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run a quick control-plane blocking function on the isolated fast executor."""
    loop = asyncio.get_running_loop()
    call = functools.partial(func, *args, **kwargs) if kwargs else functools.partial(func, *args)
    return await loop.run_in_executor(fast_control_executor, call)


async def run_in_scraper_executor(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run an external scraper / HTML parser function on the isolated scraper executor."""
    loop = asyncio.get_running_loop()
    call = functools.partial(func, *args, **kwargs) if kwargs else functools.partial(func, *args)
    return await loop.run_in_executor(scraper_io_executor, call)


async def run_in_ml_executor(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run CPU-bound indicator or ML ensemble scoring on the bounded ML executor."""
    loop = asyncio.get_running_loop()
    call = functools.partial(func, *args, **kwargs) if kwargs else functools.partial(func, *args)
    return await loop.run_in_executor(ml_compute_executor, call)


def shutdown_executors() -> None:
    """Shut down segregated thread pools cleanly on application termination."""
    for name, pool in (
        ("fast_control_executor", fast_control_executor),
        ("scraper_io_executor", scraper_io_executor),
        ("ml_compute_executor", ml_compute_executor),
    ):
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            pool.shutdown(wait=False)
        except Exception as exc:
            logger.debug(f"[Executors] Shutdown error for {name}: {exc}")
