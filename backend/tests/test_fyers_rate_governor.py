"""
Unit tests for FyersRateGovernor: pacing, single-flight coalescing, priority scheduling, and adaptive backoff.
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch

from backend.services.fyers_rate_governor import (
    FyersRateGovernor,
    PRIORITY_USER_ACTION,
    PRIORITY_INTERACTIVE,
    PRIORITY_BACKGROUND,
)


@pytest.fixture
def fresh_governor():
    """Create a new isolated governor instance with fast 0.05s pacing for unit tests."""
    gov = FyersRateGovernor(min_spacing_seconds=0.05)
    return gov


@pytest.mark.asyncio
async def test_governor_enforces_spacing(fresh_governor):
    """Verify sequential requests are spaced by at least min_spacing seconds."""
    timestamps = []

    async def mock_call():
        timestamps.append(time.monotonic())
        return {"s": "ok"}

    # Fire 3 requests through the governor
    t0 = time.monotonic()
    await fresh_governor.execute(mock_call)
    await fresh_governor.execute(mock_call)
    await fresh_governor.execute(mock_call)
    elapsed = time.monotonic() - t0

    # 3 calls with 0.05s spacing should take at least ~0.09s total
    assert len(timestamps) == 3
    assert elapsed >= 0.09
    assert timestamps[1] - timestamps[0] >= 0.04
    assert timestamps[2] - timestamps[1] >= 0.04


@pytest.mark.asyncio
async def test_single_flight_coalescing(fresh_governor):
    """Verify concurrent identical requests only execute the underlying call once."""
    call_count = 0

    async def slow_mock_call():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.06)
        return {"price": 2500.5, "symbol": "NSE:RELIANCE-EQ"}

    # Dispatch 4 concurrent requests for the exact same coalescing_key
    tasks = [
        fresh_governor.execute(slow_mock_call, priority=PRIORITY_USER_ACTION, coalescing_key="quote:RELIANCE")
        for _ in range(4)
    ]
    results = await asyncio.gather(*tasks)

    # Underlying function should only execute ONCE
    assert call_count == 1
    # All 4 callers receive the exact identical result
    assert len(results) == 4
    for res in results:
        assert res["price"] == 2500.5
        assert res["symbol"] == "NSE:RELIANCE-EQ"

    # Coalesced hit metric should be incremented (3 coalesced hits)
    metrics = fresh_governor.get_metrics()
    assert metrics["coalesced_hits"] == 3
    assert metrics["total_dispatched"] == 1


@pytest.mark.asyncio
async def test_adaptive_backoff_on_429(fresh_governor):
    """Verify governor pauses and retries when Fyers responds with -360/429 rate limit."""
    call_attempts = 0

    async def rate_limited_call():
        nonlocal call_attempts
        call_attempts += 1
        if call_attempts == 1:
            return {"code": -360, "message": "Plan rate limit reached"}
        return {"s": "ok", "d": [{"v": {"lp": 100.0}}]}

    # Mock trigger_backoff duration to be short for tests
    with patch.object(fresh_governor, "trigger_backoff") as mock_backoff:
        res = await fresh_governor.execute(rate_limited_call, priority=PRIORITY_USER_ACTION)
        assert mock_backoff.called
        # Should have retried and returned successful second attempt
        assert call_attempts == 2
        assert res["s"] == "ok"


@pytest.mark.asyncio
async def test_governor_telemetry_metrics(fresh_governor):
    """Verify get_metrics provides accurate live observability."""
    async def fast_call():
        return {"s": "ok"}

    await fresh_governor.execute(fast_call)
    await fresh_governor.execute(fast_call)

    metrics = fresh_governor.get_metrics()
    assert metrics["total_dispatched"] == 2
    assert metrics["min_spacing_ms"] == 50
    assert metrics["backoff_active"] is False
    assert metrics["inflight_count"] == 0
