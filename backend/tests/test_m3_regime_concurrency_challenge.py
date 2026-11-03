"""
Milestone 3 Iteration 2 Adversarial Challenge: Double-Checked Lock & Event Loop Lag Stress Suite
Author: Challenger 1 (Empirical Concurrency & Latency Challenger)

Tests:
1. Double-checked lock stampede coalescing: 20 concurrent requests to /api/market/regime
   with cold cache must trigger EXACTLY ONE calculation of indicator_service.compute_all.
2. Concurrent regime + candle indicator storm: Real indicator calculations under concurrency
   to measure event loop lag and confirm absence of GIL freezing or deadlocks.
3. Multi-run consistency of rapid navigation concurrency test.
"""

import asyncio
import datetime
import time
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.core.auth import get_current_user
from backend.models.user import User
from backend.services.market_data import MarketDataService
from backend.services.indicators import indicator_service
from backend.services.signals import signal_engine
from backend.api import market


@pytest.fixture(autouse=True)
def reset_market_regime_state():
    market._regime_lock = None
    market._regime_lock_loop = None
    yield
    market._regime_lock = None
    market._regime_lock_loop = None


@pytest.mark.asyncio
async def test_regime_double_checked_lock_coalesces_concurrent_stampede():
    """
    Empirically verifies that _get_regime_lock() and the double-checked cache read
    prevent stampede / redundant CPU calculations when 20 requests hit /api/market/regime
    simultaneously on a cold cache.
    """
    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.email = "test@example.com"
    app.dependency_overrides[get_current_user] = lambda: mock_user

    in_memory_cache = {}

    async def mock_cache_get(k):
        return in_memory_cache.get(k)

    async def mock_cache_set(k, v, ttl=60):
        in_memory_cache[k] = v

    # Mock candles (250 candles)
    base_dt = datetime.datetime(2026, 1, 1, 9, 15)
    mock_candles = [
        {
            "timestamp": (base_dt + datetime.timedelta(days=i)).isoformat(),
            "open": 24000.0 + i,
            "high": 24100.0 + i,
            "low": 23900.0 + i,
            "close": 24050.0 + i,
            "volume": 500000 + i * 100,
        }
        for i in range(250)
    ]

    compute_call_count = 0
    orig_compute_all = indicator_service.compute_all

    def tracked_compute_all(candles):
        nonlocal compute_call_count
        compute_call_count += 1
        # Add slight delay to simulate CPU work and increase race condition window
        time.sleep(0.02)
        return orig_compute_all(candles)

    transport = ASGITransport(app=app)
    try:
        with patch.object(MarketDataService, "fetch_candles", new_callable=AsyncMock, return_value=mock_candles), \
             patch("backend.api.market.cache_get", side_effect=mock_cache_get), \
             patch("backend.api.market.cache_set", side_effect=mock_cache_set), \
             patch.object(indicator_service, "compute_all", side_effect=tracked_compute_all):

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                # Dispatch 20 simultaneous requests on cold cache
                t0 = time.perf_counter()
                tasks = [client.get("/api/market/regime") for _ in range(20)]
                responses = await asyncio.gather(*tasks)
                duration = time.perf_counter() - t0

            # All 20 requests must succeed with 200 OK
            assert len(responses) == 20
            for i, resp in enumerate(responses):
                assert resp.status_code == 200, f"Request {i} failed: {resp.text}"
                data = resp.json()
                assert "regime" in data
                assert "indicators" in data

            # CRITICAL ASSERTION:
            # Without double-checked lock, compute_call_count would be 20.
            # With double-checked lock, it must be EXACTLY 1!
            print(f"\n[STAMPEDE RESULT] 20 concurrent requests took {duration*1000:.1f}ms. compute_all calls: {compute_call_count}")
            assert compute_call_count == 1, (
                f"Double-checked lock failed: compute_all was called {compute_call_count} times instead of 1!"
            )

    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_regime_and_candles_concurrency_event_loop_lag():
    """
    Stress-tests event loop lag during concurrent /api/market/regime and /api/stocks/{symbol}/candles
    requests with real CPU-bound indicator calculations.
    """
    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.email = "test@example.com"
    app.dependency_overrides[get_current_user] = lambda: mock_user

    in_memory_cache = {}

    async def mock_cache_get(k):
        return in_memory_cache.get(k)

    async def mock_cache_set(k, v, ttl=60):
        in_memory_cache[k] = v

    base_dt = datetime.datetime(2026, 1, 1, 9, 15)
    mock_candles = [
        {
            "timestamp": (base_dt + datetime.timedelta(days=i)).isoformat(),
            "open": 2400.0 + (i % 10),
            "high": 2420.0 + (i % 10),
            "low": 2390.0 + (i % 10),
            "close": 2410.0 + (i % 10),
            "volume": 100000 + (i * 50),
        }
        for i in range(250)
    ]

    mock_quote = {
        "symbol": "RELIANCE.NS",
        "price": 2410.0,
        "change": 10.0,
        "percent_change": 0.42,
        "market_cap": 1600000000000,
    }

    max_loop_lag = 0.0
    lag_samples = []
    lag_monitor_running = True

    async def loop_lag_monitor():
        nonlocal max_loop_lag
        while lag_monitor_running:
            t0 = time.perf_counter()
            await asyncio.sleep(0.01)
            lag = (time.perf_counter() - t0) - 0.01
            lag_samples.append(lag)
            if lag > max_loop_lag:
                max_loop_lag = lag

    monitor_task = asyncio.create_task(loop_lag_monitor())
    transport = ASGITransport(app=app)

    try:
        with patch.object(MarketDataService, "fetch_candles", new_callable=AsyncMock, return_value=mock_candles), \
             patch.object(MarketDataService, "fetch_quote", new_callable=AsyncMock, return_value=mock_quote), \
             patch("backend.api.market.cache_get", side_effect=mock_cache_get), \
             patch("backend.api.market.cache_set", side_effect=mock_cache_set), \
             patch("backend.api.stocks.cache_get", side_effect=mock_cache_get), \
             patch("backend.api.stocks.cache_set", side_effect=mock_cache_set):

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                t0 = time.perf_counter()
                tasks = [
                    # 10 regime requests
                    *(client.get("/api/market/regime") for _ in range(10)),
                    # 5 candle series requests
                    *(client.get("/api/stocks/RELIANCE.NS/candles?timeframe=1d&limit=250") for _ in range(5)),
                    # 5 stock detail / quote requests
                    *(client.get("/api/stocks/RELIANCE.NS/quote") for _ in range(5)),
                ]
                responses = await asyncio.gather(*tasks)
                duration = time.perf_counter() - t0

        lag_monitor_running = False
        await monitor_task

        assert len(responses) == 20
        for i, resp in enumerate(responses):
            assert resp.status_code == 200, f"Request {i} failed: {resp.text}"

        mean_lag = sum(lag_samples) / max(len(lag_samples), 1)
        print(f"\n[CONCURRENCY STRESS] 20 mixed requests took {duration*1000:.1f}ms.")
        print(f"Max loop lag: {max_loop_lag*1000:.2f}ms | Mean loop lag: {mean_lag*1000:.2f}ms | Samples: {len(lag_samples)}")

        assert duration < 1.5, f"Requests took too long: {duration:.2f}s"
        assert max_loop_lag < 0.120, f"Max loop lag exceeded 120ms: {max_loop_lag*1000:.1f}ms"

    finally:
        lag_monitor_running = False
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_rapid_navigation_concurrency_multi_run_consistency():
    """
    Executes the exact navigation concurrency test 5 times consecutively to prove
    consistent passage and absence of intermittent timer spikes or race conditions.
    """
    from backend.tests.test_e2e_token_navigation_simulation import (
        test_e2e_rapid_component_navigation_concurrency_no_deadlocks,
        MockDbSession,
    )

    admin_user = MagicMock(spec=User)
    admin_user.id = uuid.uuid4()
    admin_user.email = "admin@example.com"
    admin_user.is_admin = True

    lags = []
    for iteration in range(5):
        # Run test
        await test_e2e_rapid_component_navigation_concurrency_no_deadlocks(admin_user)
        print(f"[ITERATION {iteration + 1}/5] PASSED cleanly.")
