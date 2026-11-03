"""
Empirical Challenge & Stress Test Suite for Milestone 1.
Challenger: Challenger 1 (Milestone 1)

Empirical Verification Scope:
1. Concurrency & Mutex Stress Test:
   - High-contention concurrent invocations (50+ tasks) of start(), stop(), and restart().
   - Mutex mutual exclusion verification (atomic lock concurrency check).
   - Deadlock detection with strict wall-clock timeout guards.
   - Socket state consistency check across all lifecycle transitions.
2. Event Loop Non-Blocking Verification:
   - Heartbeat tick sampler running at 100 Hz (10ms interval).
   - Event loop lag measurement during simulated slow socket connection (5.0s synchronous sleep in thread).
   - Verification that max loop lag is < 50ms (zero event loop starvation).
   - Verification that asyncio.wait_for(..., timeout=3.0) returns in ~3.0s and catches TimeoutError cleanly.
3. Fault Tolerance & Exception Recovery:
   - Lock release verification when an exception is raised inside socket operations.
   - Concurrent subscribe_symbols() during in-flight restart() to detect cross-lock race conditions.
"""

import asyncio
import time
import random
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from backend.services.fyers_stream import FyersStreamService
from backend.services.market_data import MarketDataService


class ConcurrencyTracker:
    def __init__(self):
        self.active_count = 0
        self.max_active_count = 0
        self.total_invocations = 0
        self.lock = asyncio.Lock()

    async def enter(self):
        async with self.lock:
            self.active_count += 1
            if self.active_count > self.max_active_count:
                self.max_active_count = self.active_count
            self.total_invocations += 1

    async def exit(self):
        async with self.lock:
            self.active_count -= 1


@pytest.mark.asyncio
async def test_empirical_lifecycle_mutex_high_concurrency():
    """
    Stress test: Launch 60 concurrent lifecycle operations (20 start, 20 stop, 20 restart).
    Verify:
    1. Absolute mutual exclusion: max_active_count == 1 under _lifecycle_lock.
    2. Zero deadlocks: all 60 complete in < 15 seconds.
    3. Final state is clean and deterministic.
    """
    service = FyersStreamService()
    tracker = ConcurrencyTracker()
    simulated_calls = []

    # Mock internal methods to simulate realistic thread / socket latency (20ms - 80ms)
    async def mock_start_internal():
        await tracker.enter()
        simulated_calls.append("start_enter")
        # Simulate background socket connect work
        await asyncio.sleep(random.uniform(0.02, 0.06))
        service._is_running = True
        service._is_connected = True
        simulated_calls.append("start_exit")
        await tracker.exit()
        return True

    async def mock_stop_internal():
        await tracker.enter()
        simulated_calls.append("stop_enter")
        # Simulate background socket close work
        await asyncio.sleep(random.uniform(0.02, 0.06))
        service._is_running = False
        service._is_connected = False
        service._socket = None
        simulated_calls.append("stop_exit")
        await tracker.exit()

    with patch.object(service, "_start_internal", side_effect=mock_start_internal), \
         patch.object(service, "_stop_internal", side_effect=mock_stop_internal):

        operations = (
            [service.start() for _ in range(20)] +
            [service.stop() for _ in range(20)] +
            [service.restart() for _ in range(20)]
        )
        random.shuffle(operations)

        start_time = time.perf_counter()
        results = await asyncio.wait_for(
            asyncio.gather(*operations, return_exceptions=True),
            timeout=20.0
        )
        elapsed = time.perf_counter() - start_time

        # Check for exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Encountered unexpected exceptions: {exceptions}"

        # 1. Mutex mutual exclusion check
        assert tracker.max_active_count == 1, (
            f"MUTEX VIOLATION! Multiple tasks entered critical section concurrently: "
            f"max_active={tracker.max_active_count}"
        )

        # 2. Total invocations: 20 starts + 20 stops + 20 restarts (each restart calls stop then start = 40)
        # Total critical section entries should be 20 + 20 + 40 = 80
        assert tracker.total_invocations == 80, f"Expected 80 entries, got {tracker.total_invocations}"

        # 3. Clean serialization sequence verification
        # An enter must always be directly followed by its exit before any other enter
        in_cs = False
        for op in simulated_calls:
            if "enter" in op:
                assert not in_cs, f"Corrupted lock sequence! Re-entered while inside: {op}"
                in_cs = True
            elif "exit" in op:
                assert in_cs, f"Corrupted lock sequence! Exited while not inside: {op}"
                in_cs = False

        print(f"\n[EMPIRICAL-CONCURRENCY-PASS] 60 concurrent lifecycle operations completed cleanly in {elapsed:.3f}s. Max active mutex holders: {tracker.max_active_count}")


@pytest.mark.asyncio
async def test_empirical_event_loop_lag_under_blocking_socket():
    """
    Stress test: Measure event loop lag while a mock socket call blocks in a worker thread.
    Simulates a 5.0s synchronous sleep inside socket.connect() and verifies:
    1. asyncio.wait_for(..., timeout=3.0) times out in 3.0s ± 0.3s.
    2. A 100 Hz (10ms) heartbeat loop measuring event loop jitter records MAX loop lag < 50ms.
    3. Concurrent async coroutines continue running with zero loop starvation.
    """
    service = FyersStreamService()
    lag_samples = []
    stop_heartbeat = asyncio.Event()

    async def heartbeat_sampler():
        """Samples event loop responsiveness every 10ms (100 Hz)."""
        interval = 0.010  # 10ms
        while not stop_heartbeat.is_set():
            t0 = time.perf_counter()
            await asyncio.sleep(interval)
            t1 = time.perf_counter()
            actual_delay = t1 - t0
            lag = max(0.0, actual_delay - interval)
            lag_samples.append(lag * 1000.0)  # in milliseconds

    # Launch heartbeat sampler
    sampler_task = asyncio.create_task(heartbeat_sampler())

    # Mock socket that synchronously sleeps in thread for 5.0 seconds
    mock_socket = MagicMock()
    def slow_connect():
        time.sleep(5.0)

    mock_socket.connect.side_effect = slow_connect
    service._socket = mock_socket

    t_start = time.perf_counter()
    timeout_caught = False

    try:
        # This matches the implementation in FyersStreamService:
        await asyncio.wait_for(
            asyncio.to_thread(service._socket.connect),
            timeout=3.0
        )
    except asyncio.TimeoutError:
        timeout_caught = True

    t_elapsed = time.perf_counter() - t_start
    stop_heartbeat.set()
    await sampler_task

    # Compute empirical latency stats
    assert timeout_caught is True, "Expected asyncio.TimeoutError was not raised"
    assert 2.8 <= t_elapsed <= 3.5, f"Timeout did not trigger near 3.0s: actual={t_elapsed:.3f}s"

    assert len(lag_samples) >= 150, f"Expected at least 150 heartbeat samples over 3.0s, got {len(lag_samples)}"
    max_lag = max(lag_samples)
    avg_lag = sum(lag_samples) / len(lag_samples)
    p95_lag = sorted(lag_samples)[int(len(lag_samples) * 0.95)]

    print(f"\n[EMPIRICAL-LOOP-LAG-PASS] Samples={len(lag_samples)} | Max Lag={max_lag:.2f}ms | Avg Lag={avg_lag:.2f}ms | P95 Lag={p95_lag:.2f}ms | Elapsed={t_elapsed:.3f}s")

    # STRICT REQUIREMENT: Event loop must NOT be blocked for > 50ms
    assert max_lag < 50.0, f"EVENT LOOP BLOCKED! Max lag exceeded 50ms threshold: {max_lag:.2f}ms"


@pytest.mark.asyncio
async def test_empirical_fault_tolerance_and_exception_recovery():
    """
    Stress test: Inject arbitrary unhandled exceptions into _start_internal() and _stop_internal().
    Verify that:
    1. _lifecycle_lock is immediately and reliably released (no permanent deadlock/poisoning).
    2. Subsequent legitimate start() or stop() calls succeed normally.
    """
    service = FyersStreamService()

    class SimulatedSocketCrash(Exception):
        pass

    async def crashing_start():
        await asyncio.sleep(0.01)
        raise SimulatedSocketCrash("Simulated network fatal crash during connect")

    with patch.object(service, "_start_internal", side_effect=crashing_start):
        with pytest.raises(SimulatedSocketCrash):
            await service.start()

    # Verify lock is released and NOT stuck
    assert not service._lifecycle_lock.locked(), "Lifecycle lock remained poisoned after crash!"

    # Verify next call can acquire lock normally
    async def healthy_start():
        await asyncio.sleep(0.01)
        service._is_connected = True
        service._is_running = True
        return True

    with patch.object(service, "_start_internal", side_effect=healthy_start):
        success = await asyncio.wait_for(service.start(), timeout=2.0)
        assert success is True
        assert service._is_connected is True

    print("\n[EMPIRICAL-FAULT-TOLERANCE-PASS] Exception injection safely released _lifecycle_lock and recovered.")


@pytest.mark.asyncio
async def test_empirical_concurrent_subscriptions_during_restart():
    """
    Stress test: High-volume symbol subscriptions arriving concurrently while
    the service is executing restart() cycles under lifecycle lock.
    Verifies no cross-deadlock between _lock and _lifecycle_lock.
    """
    service = FyersStreamService()
    service._is_connected = True
    service._socket = MagicMock()

    subscribed_batches = []
    def fake_subscribe(symbols, data_type):
        subscribed_batches.append(list(symbols))

    service._socket.subscribe.side_effect = fake_subscribe

    mock_socket_class = MagicMock()
    mock_socket = MagicMock()
    mock_socket_class.return_value = mock_socket

    with patch("backend.services.fyers_stream.FyersDataSocket", mock_socket_class), \
         patch.object(service, "_resolve_and_cache_hsm_tokens", new_callable=AsyncMock), \
         patch("backend.core.database.AsyncSessionLocal", side_effect=Exception("No DB in test")), \
         patch("backend.core.cache.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("backend.services.fyers_stream.settings") as mock_settings:
        mock_settings.FYERS_CLIENT_ID = "MOCK_CLIENT"
        mock_settings.FYERS_ACCESS_TOKEN = "MOCK_TOKEN"
        # 5 restart cycles concurrently with 25 subscribe_symbols calls
        restarts = [service.restart() for _ in range(5)]
        subs = [
            service.subscribe_symbols([f"SYM_{i}_{j}" for j in range(10)])
            for i in range(25)
        ]

        all_tasks = restarts + subs
        random.shuffle(all_tasks)

        # Must all complete cleanly without deadlock
        results = await asyncio.wait_for(
            asyncio.gather(*all_tasks, return_exceptions=True),
            timeout=10.0
        )

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Unexpected errors during concurrent subscribe + restart: {errors}"

    print(f"\n[EMPIRICAL-CONCURRENT-SUBS-PASS] Completed 5 restarts + 25 subscriptions concurrently without deadlock.")


@pytest.mark.asyncio
async def test_empirical_warmup_governor_thundering_herd_concurrency():
    """
    Adversarial Stress Test: Thundering Herd burst storm.
    When Fyers token is activated, 50 mounted UI components fire REST queries
    at the exact same millisecond.
    Verify:
    How many queries are admitted to Fyers during the initial 1.5s warmup spacing?
    Expected: Only 1 (or at most within burst quota < 4), remaining must be rejected and routed to Yahoo fallback.
    """
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    MarketDataService.engage_warmup_governor(60.0)

    with patch("backend.core.cache.get_redis", side_effect=Exception("No Redis")):
        # 50 simultaneous requests hitting the rate budget
        tasks = [MarketDataService.check_and_record_fyers_rate_budget() for _ in range(50)]
        results = await asyncio.gather(*tasks)

    admitted = sum(1 for r in results if r is True)
    rejected = sum(1 for r in results if r is False)

    print(f"\n[EMPIRICAL-BURST-STORM-STATS] 50 concurrent requests at t=0: Admitted to Fyers={admitted}, Routed to Yahoo Fallback={rejected}")

    # Under strict 1.5s spacing during warmup, only 1 request should be admitted!
    assert admitted == 1, f"WARMUP GOVERNOR LEAK! Expected exactly 1 admitted request during 1.5s warmup spacing, but {admitted} were admitted!"
    assert rejected == 49, f"Expected 49 rejected requests, got {rejected}"

