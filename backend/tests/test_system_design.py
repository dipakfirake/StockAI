"""
Unit & Integration Tests for Enterprise System Design Architecture.

Verifies:
- Asynchronous Domain Event Bus (Publish/Subscribe, Concurrency, Error Isolation)
- State-Machine Circuit Breaker (CLOSED -> OPEN -> HALF_OPEN, Fallback Execution)
- Multi-Tier Caching Engine & Single-Flight Cache Stampede Coalescing
- Enterprise Telemetry, Prometheus Metrics, Liveness & Readiness Probes
- Lifecycle Graceful Shutdown
"""

import time
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from backend.core.event_bus import (
    EventBus,
    DomainEvent,
    OrderPlacedEvent,
    OrderClosedEvent,
)
from backend.core.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpenException,
)
from backend.core.cache_manager import (
    L1MemoryCache,
    SingleFlightGroup,
    Tier1CacheManager,
)
from backend.core.telemetry import MetricsRegistry
from backend.main import app


# ==============================================================================
# 1. Event Bus & Domain Event Architecture Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_event_bus_publish_subscribe():
    """Verify event bus publishes and invokes typed subscribers."""
    bus = EventBus()
    received_events = []

    async def on_order_placed(event: OrderPlacedEvent):
        received_events.append(event)

    bus.subscribe(OrderPlacedEvent, on_order_placed)

    event = OrderPlacedEvent(
        user_id="user-123",
        trade_id="trade-456",
        symbol="TCS.NS",
        direction="BUY",
        quantity=50,
        order_type="MARKET",
        price=3500.0,
    )
    await bus.publish(event)

    assert len(received_events) == 1
    assert received_events[0].symbol == "TCS.NS"
    assert received_events[0].quantity == 50


@pytest.mark.asyncio
async def test_event_bus_error_isolation():
    """Verify failing subscriber does not crash publisher or block other subscribers."""
    bus = EventBus()
    successful_invocations = []

    async def failing_subscriber(event: OrderPlacedEvent):
        raise RuntimeError("Downstream alert service failure!")

    async def successful_subscriber(event: OrderPlacedEvent):
        successful_invocations.append(event.symbol)

    bus.subscribe(OrderPlacedEvent, failing_subscriber)
    bus.subscribe(OrderPlacedEvent, successful_subscriber)

    event = OrderPlacedEvent(symbol="RELIANCE.NS")
    # Should not raise exception
    await bus.publish(event)

    assert len(successful_invocations) == 1
    assert successful_invocations[0] == "RELIANCE.NS"


# ==============================================================================
# 2. State-Machine Circuit Breaker Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_circuit_breaker_transitions_to_open():
    """Verify circuit trips OPEN after failure threshold and fast-fails."""
    cb = CircuitBreaker("test_breaker", failure_threshold=3, recovery_timeout_seconds=0.2)
    assert cb.state == CircuitState.CLOSED

    async def failing_api():
        raise ConnectionError("Broker API unreachable")

    # 3 failures -> trips to OPEN
    for _ in range(3):
        with pytest.raises(ConnectionError):
            await cb.call(failing_api)

    assert cb.state == CircuitState.OPEN

    # Subsequent call fast-fails with CircuitBreakerOpenException without invoking callable
    called = False
    async def probe():
        nonlocal called
        called = True

    with pytest.raises(CircuitBreakerOpenException):
        await cb.call(probe)
    assert called is False


@pytest.mark.asyncio
async def test_circuit_breaker_fallback_execution():
    """Verify circuit executes fallback cleanly when OPEN."""
    cb = CircuitBreaker("test_fallback", failure_threshold=1, recovery_timeout_seconds=5.0)

    async def failing_api():
        raise ConnectionError("Down")

    # Trip breaker
    with pytest.raises(ConnectionError):
        await cb.call(failing_api)
    assert cb.state == CircuitState.OPEN

    # Call with fallback
    async def fallback_api():
        return {"price": 100.0, "source": "cached_fallback"}

    result = await cb.call(failing_api, fallback=fallback_api)
    assert result == {"price": 100.0, "source": "cached_fallback"}


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery():
    """Verify circuit transitions to HALF_OPEN after cooldown and recovers to CLOSED."""
    cb = CircuitBreaker("test_recovery", failure_threshold=2, recovery_timeout_seconds=0.1, half_open_success_threshold=1)

    async def failing_api():
        raise ConnectionError("Down")

    for _ in range(2):
        with pytest.raises(ConnectionError):
            await cb.call(failing_api)
    assert cb.state == CircuitState.OPEN

    # Wait for recovery timeout
    await asyncio.sleep(0.15)

    async def healthy_api():
        return "SUCCESS"

    # Next call transitions to HALF_OPEN and succeeds -> transitions to CLOSED
    res = await cb.call(healthy_api)
    assert res == "SUCCESS"
    assert cb.state == CircuitState.CLOSED


# ==============================================================================
# 3. Multi-Tier Cache & Single-Flight Stampede Protection Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_l1_memory_cache_ttl():
    """Verify L1 memory cache handles values and expires TTL correctly."""
    cache = L1MemoryCache(max_items=10)
    await cache.set("test_key", {"price": 2500.0}, ttl=1)

    val = await cache.get("test_key")
    assert val == {"price": 2500.0}

    # Wait for expiration
    await asyncio.sleep(1.05)
    expired_val = await cache.get("test_key")
    assert expired_val is None


@pytest.mark.asyncio
async def test_single_flight_stampede_coalescing():
    """
    Verify Single-Flight coalesces 10 concurrent requests for a cold key
    into exactly 1 factory execution.
    """
    sf = SingleFlightGroup()
    call_count = 0

    async def expensive_upstream_fetch():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)  # Simulate network latency
        return {"symbol": "INFY.NS", "price": 1850.0}

    # Fire 10 concurrent requests simultaneously
    tasks = [sf.execute("quote:INFY.NS", expensive_upstream_fetch) for _ in range(10)]
    results = await asyncio.gather(*tasks)

    # All 10 callers received identical correct data
    assert len(results) == 10
    for r in results:
        assert r["price"] == 1850.0

    # But the expensive upstream factory was executed EXACTLY ONCE!
    assert call_count == 1


# ==============================================================================
# 4. Telemetry, Prometheus Metrics & Health Probes Tests
# ==============================================================================

def test_metrics_registry_prometheus_format():
    """Verify Prometheus text format generation."""
    reg = MetricsRegistry()
    reg.inc_request("GET", "/api/market/indices", 200)
    reg.inc_request("POST", "/api/paper-trades", 200)
    reg.inc_order("BUY", "MARKET", "OPEN")
    reg.set_ws_connections(12)

    text = reg.generate_prometheus_text()
    assert "stockai_uptime_seconds" in text
    assert "stockai_active_websocket_connections 12" in text
    assert 'stockai_http_requests_total{method="GET",path="/api/market/indices",status="200"} 1' in text
    assert 'stockai_orders_total{direction="BUY",type="MARKET",status="OPEN"} 1' in text


def test_telemetry_probes_endpoints():
    """Verify /health/live, /health/ready, and /metrics endpoints via TestClient."""
    with patch("backend.main.create_db_tables", new_callable=AsyncMock):
        with TestClient(app, raise_server_exceptions=False) as client:
            # 1. Liveness
            live_resp = client.get("/health/live")
            assert live_resp.status_code == 200
            assert live_resp.json()["status"] == "alive"

            # 2. Readiness
            ready_resp = client.get("/health/ready")
            assert ready_resp.status_code in (200, 503)
            assert "checks" in ready_resp.json()

            # 3. Prometheus metrics
            metrics_resp = client.get("/metrics")
            assert metrics_resp.status_code == 200
            assert "stockai_uptime_seconds" in metrics_resp.text
