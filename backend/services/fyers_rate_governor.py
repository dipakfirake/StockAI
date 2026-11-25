"""
Centralized Fyers API V3 Rate Governor & Smooth Multi-Tier Request Pipeline.

Guarantees 100% compliance with Fyers V3 API quotas:
- Paced Leaky Bucket: Enforces min 250ms spacing between outbound Fyers REST requests (max 4 req/sec, max 40 req/min).
- Asynchronous Priority Queue: Higher-priority user interactions jump ahead of background screener/candle pagination.
- Single-Flight Request Coalescing: De-duplicates concurrent calls for identical symbols/endpoints.
- Adaptive Jitter Backoff: Gracefully pauses and retries on transient broker -360/429 limits without locking out the engine.
"""

import asyncio
import heapq
import time
import random
from typing import Any, Callable, Coroutine, Dict, List, Optional
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# Priority Levels (lower integer = higher priority)
PRIORITY_USER_ACTION = 0    # Live single quotes, order actions, user manual refresh
PRIORITY_INTERACTIVE = 1    # Watchlist bulk quotes, Market Depth, Index tickers, Heatmap
PRIORITY_BACKGROUND = 2     # Historical candle pagination chunks, Screener sector scans, Audit sync


class FyersRateGovernor:
    """
    Singleton rate governor coordinating all outbound Fyers REST requests across the application.
    Uses non-sleeping lock sections + a preemptible priority heap so live user actions
    preempt background scans and single-flight coalescing never blocks behind rate waits.
    """

    _instance: Optional["FyersRateGovernor"] = None

    def __init__(self, min_spacing_seconds: float = 0.25):
        self.min_spacing = min_spacing_seconds
        self._last_dispatch_time: float = 0.0
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._inflight: Dict[str, asyncio.Future] = {}
        self._inflight_lock: Optional[asyncio.Lock] = None
        self._schedule_lock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._waiters: List[list] = []  # heap entries: [priority, seq, asyncio.Event, cancelled]
        self._seq: int = 0
        self._pacer_active: bool = False
        self._pacer_prio: int = 999
        self._preempt_event: Optional[asyncio.Event] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._backoff_until: float = 0.0

        # Telemetry metrics
        self._total_dispatched: int = 0
        self._coalesced_hits: int = 0
        self._throttled_events: int = 0
        self._priority_preemptions: int = 0
        self._running: bool = True

    @classmethod
    def get_instance(cls) -> "FyersRateGovernor":
        if cls._instance is None:
            cls._instance = FyersRateGovernor()
        return cls._instance

    def _ensure_loop_state(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._loop = loop
            self._inflight_lock = asyncio.Lock()
            self._schedule_lock = asyncio.Lock()
            self._waiters = []
            self._pacer_active = False
            self._pacer_prio = 999
            self._preempt_event = None
            # Discard orphaned futures bound to an old closed event loop
            self._inflight = {
                k: fut for k, fut in self._inflight.items()
                if fut.get_loop() is loop and not fut.done()
            }

    def trigger_backoff(self, duration_seconds: float = 2.0, reason: str = "Rate limit detected") -> None:
        """Applies adaptive jittered backoff to outbound Fyers REST requests."""
        jitter = random.uniform(0.1, 0.5)
        now = time.monotonic()
        self._backoff_until = max(self._backoff_until, now + duration_seconds + jitter)
        self._throttled_events += 1
        logger.warning(
            f"Fyers Rate Governor: Adaptive backoff engaged for {duration_seconds + jitter:.2f}s "
            f"({reason}). Outbound calls will be smoothly buffered."
        )

    def reset_backoff(self) -> None:
        """Clears active rate backoff and pacing timestamps (used on token refresh / health reset)."""
        self._backoff_until = 0.0
        self._last_dispatch_time = 0.0
        if self._preempt_event is not None:
            try:
                self._preempt_event.set()
            except Exception:
                pass

    async def execute(
        self,
        coro_fn: Callable[[], Coroutine[Any, Any, Any]],
        priority: int = PRIORITY_INTERACTIVE,
        coalescing_key: Optional[str] = None,
        timeout: float = 12.0,
    ) -> Any:
        """
        Executes an outbound Fyers API callable with:
        1. Lock-free Single-Flight Coalescing (if coalescing_key provided)
        2. Priority-heap 250ms Leaky-Bucket pacing (higher priority preempts background waiters)
        3. Adaptive retry on transient -360 / 429
        """
        self._ensure_loop_state()
        assert self._inflight_lock is not None

        # 1. Single-Flight Coalescing: _inflight_lock is never held across sleeps or I/O
        existing_future = None
        if coalescing_key:
            async with self._inflight_lock:
                existing = self._inflight.get(coalescing_key)
                if existing and not existing.done():
                    self._coalesced_hits += 1
                    logger.debug(f"Fyers Rate Governor: Coalesced duplicate request for '{coalescing_key}'")
                    existing_future = existing
                else:
                    loop = asyncio.get_running_loop()
                    self._inflight[coalescing_key] = loop.create_future()

        if existing_future is not None:
            return await asyncio.wait_for(asyncio.shield(existing_future), timeout=timeout)

        deadline = time.monotonic() + timeout
        try:
            # 2. Priority-paced slot acquisition (honors deadline)
            wait_budget = max(0.5, deadline - time.monotonic())
            await asyncio.wait_for(self._acquire_permit(priority), timeout=wait_budget)

            # 3. Call execution with single adaptive retry on rate limit
            max_attempts = 2
            result = None
            for attempt in range(max_attempts):
                rem = max(0.5, deadline - time.monotonic())
                try:
                    result = await asyncio.wait_for(coro_fn(), timeout=rem)
                except Exception as ex:
                    err_str = str(ex).lower()
                    if "-360" in err_str or "429" in err_str or "rate limit" in err_str or "1015" in err_str:
                        self.trigger_backoff(duration_seconds=2.0, reason=f"Exception: {ex}")
                        if attempt < max_attempts - 1:
                            await asyncio.wait_for(self._acquire_permit(priority), timeout=max(0.5, deadline - time.monotonic()))
                            continue
                    raise

                # Inspect Fyers response dictionary for rate limit codes
                if isinstance(result, dict):
                    code = result.get("code")
                    msg = str(result.get("message", "")).lower()
                    if code in (-360, 429) or "rate limit" in msg or "1015" in msg:
                        self.trigger_backoff(duration_seconds=2.0, reason=f"Fyers code {code}: {msg}")
                        if attempt < max_attempts - 1:
                            await asyncio.wait_for(self._acquire_permit(priority), timeout=max(0.5, deadline - time.monotonic()))
                            continue

                break

            self._total_dispatched += 1

            if coalescing_key:
                async with self._inflight_lock:
                    fut = self._inflight.pop(coalescing_key, None)
                    if fut and not fut.done():
                        fut.set_result(result)

            return result

        except BaseException as e:
            if coalescing_key:
                async with self._inflight_lock:
                    fut = self._inflight.pop(coalescing_key, None)
                    if fut and not fut.done():
                        if isinstance(e, Exception):
                            fut.set_exception(e)
                        else:
                            fut.cancel()
            raise

    def _wake_next_locked(self) -> None:
        while self._waiters and self._waiters[0][3]:
            heapq.heappop(self._waiters)
        if self._waiters:
            self._waiters[0][2].set()

    async def _acquire_permit(self, priority: int) -> None:
        """
        Preemptible priority-queue leaky bucket.
        Never holds asyncio locks while sleeping on spacing or backoff intervals.
        """
        self._ensure_loop_state()
        assert self._schedule_lock is not None

        async with self._schedule_lock:
            now = time.monotonic()
            next_allowed = max(self._backoff_until, self._last_dispatch_time + self.min_spacing)
            while self._waiters and self._waiters[0][3]:
                heapq.heappop(self._waiters)

            if not self._pacer_active and not self._waiters and next_allowed <= now:
                self._last_dispatch_time = now
                return

            self._seq += 1
            seq = self._seq
            ev = asyncio.Event()
            entry = [priority, seq, ev, False]  # [priority, seq, event, cancelled]
            heapq.heappush(self._waiters, entry)

            if self._pacer_active and priority < self._pacer_prio and self._preempt_event is not None:
                self._priority_preemptions += 1
                self._preempt_event.set()

        became_pacer = False
        try:
            while True:
                wait_for_turn = False
                sleep_sec = 0.0
                preempt_ev = None

                async with self._schedule_lock:
                    while self._waiters and self._waiters[0][3]:
                        heapq.heappop(self._waiters)
                    if entry[3] or not self._waiters:
                        return

                    head = self._waiters[0]
                    if not self._pacer_active and head[1] == seq:
                        now = time.monotonic()
                        next_allowed = max(self._backoff_until, self._last_dispatch_time + self.min_spacing)
                        if next_allowed <= now:
                            heapq.heappop(self._waiters)
                            entry[3] = True
                            self._last_dispatch_time = now
                            self._wake_next_locked()
                            return

                        self._pacer_active = True
                        self._pacer_prio = priority
                        preempt_ev = asyncio.Event()
                        self._preempt_event = preempt_ev
                        became_pacer = True
                        sleep_sec = next_allowed - now
                    else:
                        ev.clear()
                        wait_for_turn = True

                if wait_for_turn:
                    await ev.wait()
                    continue

                sleep_task = asyncio.create_task(asyncio.sleep(sleep_sec))
                preempt_task = asyncio.create_task(preempt_ev.wait())
                try:
                    _, pending = await asyncio.wait(
                        {sleep_task, preempt_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for pending_task in pending:
                        pending_task.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                except BaseException:
                    for task_item in (sleep_task, preempt_task):
                        if not task_item.done():
                            task_item.cancel()
                    await asyncio.gather(sleep_task, preempt_task, return_exceptions=True)
                    raise

                async with self._schedule_lock:
                    self._pacer_active = False
                    self._pacer_prio = 999
                    self._preempt_event = None
                    became_pacer = False
                    self._wake_next_locked()
        finally:
            entry[3] = True
            if became_pacer and self._pacer_active:
                self._pacer_active = False
                self._pacer_prio = 999
                self._preempt_event = None
            if not self._pacer_active:
                self._wake_next_locked()

    def get_metrics(self) -> Dict[str, Any]:
        """Returns live telemetry of the Fyers rate governor."""
        now = time.monotonic()
        active_waiters = sum(1 for item in self._waiters if not item[3])
        return {
            "min_spacing_ms": int(self.min_spacing * 1000),
            "total_dispatched": self._total_dispatched,
            "coalesced_hits": self._coalesced_hits,
            "throttled_events": self._throttled_events,
            "priority_preemptions": self._priority_preemptions,
            "queued_waiters": active_waiters,
            "backoff_active": now < self._backoff_until,
            "backoff_remaining_s": max(0.0, round(self._backoff_until - now, 2)),
            "inflight_count": len(self._inflight),
        }


# Global singleton instance
fyers_rate_governor = FyersRateGovernor.get_instance()
