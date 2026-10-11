"""
Industrial State-Machine Circuit Breaker (Hystrix / Resilience4j Pattern).

Guarantees system resilience against failing external brokers and upstream market data feeds.
States:
- CLOSED: Requests pass through normally.
- OPEN: Failures exceed threshold; fail-fast immediately without outbound calls.
- HALF_OPEN: Cooldown elapsed; canary trial requests probe recovery.
"""

import time
import asyncio
from enum import Enum
from typing import Callable, Any, Optional
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""
    pass


class CircuitBreaker:
    """
    Thread-safe & async-safe Circuit Breaker state machine.
    """
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        half_open_success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.half_open_success_threshold = half_open_success_threshold

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float = 0.0
        self.last_state_change: float = time.monotonic()
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args, fallback: Optional[Callable] = None, **kwargs) -> Any:
        """
        Execute an async or sync callable protected by the circuit breaker.
        If OPEN and a fallback is provided, executes fallback instead.
        """
        async with self._lock:
            now = time.monotonic()

            # Check if circuit should transition from OPEN to HALF_OPEN
            if self.state == CircuitState.OPEN:
                if now - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self.last_state_change = now
                    logger.info(f"[CircuitBreaker:{self.name}] Transitioned to HALF_OPEN (probing upstream health)")
                else:
                    if fallback is not None:
                        return await self._invoke_fallback(fallback, *args, **kwargs)
                    raise CircuitBreakerOpenException(
                        f"Circuit breaker '{self.name}' is OPEN. Fast-failing upstream call."
                    )

        # Attempt call execution
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await self._on_success()
            return result

        except Exception as exc:
            await self._on_failure(exc)
            if fallback is not None:
                return await self._invoke_fallback(fallback, *args, **kwargs)
            raise

    async def _on_success(self):
        """Record successful call."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.half_open_success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.last_state_change = time.monotonic()
                    logger.info(f"[CircuitBreaker:{self.name}] Fully recovered. Circuit CLOSED.")
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    async def _on_failure(self, exc: Exception):
        """Record failed call and trip breaker if threshold exceeded."""
        async with self._lock:
            self.last_failure_time = time.monotonic()
            self.failure_count += 1

            if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.last_state_change = self.last_failure_time
                logger.warning(
                    f"[CircuitBreaker:{self.name}] Tripped to OPEN ({self.failure_count} failures, error: {exc}). "
                    f"Cooldown: {self.recovery_timeout}s"
                )

    async def _invoke_fallback(self, fallback: Callable, *args, **kwargs) -> Any:
        """Safely execute fallback callable."""
        logger.debug(f"[CircuitBreaker:{self.name}] Executing fallback due to OPEN state.")
        if asyncio.iscoroutinefunction(fallback):
            return await fallback(*args, **kwargs)
        return fallback(*args, **kwargs)

    @property
    def status_summary(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failures": self.failure_count,
            "uptime_in_state": round(time.monotonic() - self.last_state_change, 2),
        }


# Global registry of circuit breakers for core services
circuit_breakers = {
    "fyers_api": CircuitBreaker("fyers_api", failure_threshold=5, recovery_timeout_seconds=30.0),
    "market_data": CircuitBreaker("market_data", failure_threshold=5, recovery_timeout_seconds=20.0),
    "neon_db": CircuitBreaker("neon_db", failure_threshold=3, recovery_timeout_seconds=15.0),
}
