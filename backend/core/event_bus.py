"""
Enterprise Event Bus & Domain-Driven Event Architecture.

Implements an asynchronous, thread-safe publish-subscribe Event Bus for decoupling
core transaction processing from downstream side-effects (WebSockets, Audit Trails,
Telemetry Metrics, Notification alerts).
"""

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Coroutine, Dict, List, Type, Any, Optional
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class DomainEvent:
    """Base class for all domain events in the financial platform."""
    event_id: str = field(default_factory=lambda: str(datetime.now(timezone.utc).timestamp()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def event_name(self) -> str:
        return self.__class__.__name__


@dataclass
class OrderPlacedEvent(DomainEvent):
    user_id: str = ""
    trade_id: str = ""
    symbol: str = ""
    direction: str = ""
    quantity: int = 0
    order_type: str = ""
    price: float = 0.0


@dataclass
class OrderExecutedEvent(DomainEvent):
    user_id: str = ""
    trade_id: str = ""
    symbol: str = ""
    direction: str = ""
    quantity: int = 0
    execution_price: float = 0.0
    slippage: float = 0.0


@dataclass
class OrderClosedEvent(DomainEvent):
    user_id: str = ""
    trade_id: str = ""
    symbol: str = ""
    exit_price: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class MarketTickEvent(DomainEvent):
    symbol: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    volume: int = 0


@dataclass
class SystemAlertEvent(DomainEvent):
    user_id: str = ""
    severity: str = "INFO"  # INFO, WARNING, CRITICAL
    title: str = ""
    message: str = ""


EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    """
    High-performance Asynchronous In-Memory Event Bus with error isolation.
    """
    def __init__(self):
        self._subscribers: Dict[Type[DomainEvent], List[EventHandler]] = {}
        self._global_subscribers: List[EventHandler] = []
        self._lock = asyncio.Lock()
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

    def subscribe(self, event_type: Type[DomainEvent], handler: EventHandler):
        """Register a subscriber handler for a specific domain event."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            logger.debug(f"[EventBus] Subscribed {handler.__name__} to {event_type.__name__}")

    def subscribe_all(self, handler: EventHandler):
        """Register a global subscriber that receives every event."""
        if handler not in self._global_subscribers:
            self._global_subscribers.append(handler)

    async def publish(self, event: DomainEvent):
        """
        Publish an event immediately to all registered subscribers.
        Executes subscribers concurrently with strict error isolation.
        """
        handlers = self._subscribers.get(type(event), []).copy()
        handlers.extend(self._global_subscribers)

        if not handlers:
            return

        tasks = []
        for handler in handlers:
            tasks.append(self._safe_invoke(handler, event))

        # Run all subscriber side-effects concurrently
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_invoke(self, handler: EventHandler, event: DomainEvent):
        """Execute a single handler, catching and logging any errors to isolate side-effects."""
        try:
            if inspect.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception as e:
            logger.error(
                f"[EventBus] Error in subscriber {getattr(handler, '__name__', str(handler))} "
                f"while processing {event.event_name}: {e}",
                exc_info=True,
            )


# Global singleton instance
event_bus = EventBus()
