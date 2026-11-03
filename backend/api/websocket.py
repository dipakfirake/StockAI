"""WebSocket router for real-time alert and market data delivery with zero-REST streaming and micro-tick fluidity."""

import asyncio
import json
import time
from typing import Optional, Set, Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from backend.core.logging_config import get_logger
from backend.core.config import settings
from backend.core.market_hours import is_indian_market_open

logger = get_logger(__name__)

ws_router = APIRouter()

# Connected WebSocket clients: user_id -> websocket
_alert_connections: dict[str, WebSocket] = {}

# Market data subscriptions: connection_id -> {websocket, symbols: set(), user_id: str}
_market_connections: dict[str, dict] = {}

# Inverted subscription index for O(1) subscriber lookup: symbol -> set of connection_ids
_symbol_subscribers: dict[str, set[str]] = {}

MAX_SUBSCRIPTIONS_PER_CONNECTION = 50


def quantize_tick(price: float, tick_size: float = 0.05) -> float:
    """Quantize price to the nearest valid exchange tick size (₹0.05 for NSE equities)."""
    if price <= 0:
        return price
    return round(round(price / tick_size) * tick_size, 2)


def _get_subscribers_for_symbol(symbol: str) -> set[str]:
    """Retrieve connection IDs subscribed to symbol using the inverted index, with test fallback."""
    clean_sym = symbol.replace(".NS", "").replace(".BO", "").replace("^", "")
    aliases = {symbol, f"{clean_sym}.NS", f"{clean_sym}.BO", clean_sym, f"^{clean_sym}"}

    matched: set[str] = set()
    for alias in aliases:
        if alias in _symbol_subscribers:
            matched.update(_symbol_subscribers[alias])

    # Ensure backwards compatibility for tests that directly modify _market_connections
    for cid, cdata in _market_connections.items():
        if cid not in matched:
            conn_syms = cdata.get("symbols", set())
            if any(a in conn_syms for a in aliases):
                matched.add(cid)
                for cs in conn_syms:
                    _symbol_subscribers.setdefault(cs, set()).add(cid)

    return matched


def _register_subscription(conn_id: str, symbol: str) -> None:
    """Registers symbol subscription in both the connection map and the inverted index."""
    if conn_id not in _market_connections:
        return
    norm_symbol = symbol if "." in symbol or symbol.startswith("^") else symbol + ".NS"
    clean_sym = norm_symbol.replace(".NS", "").replace(".BO", "").replace("^", "")

    _market_connections[conn_id]["symbols"].add(norm_symbol)
    _symbol_subscribers.setdefault(norm_symbol, set()).add(conn_id)
    _symbol_subscribers.setdefault(clean_sym, set()).add(conn_id)
    _symbol_subscribers.setdefault(symbol, set()).add(conn_id)


def _unregister_connection(conn_id: str) -> None:
    """Removes a disconnected client from the connection registry and inverted subscription index."""
    conn_data = _market_connections.pop(conn_id, None)
    if conn_data:
        syms = conn_data.get("symbols", set())
        for s in syms:
            clean = s.replace(".NS", "").replace(".BO", "").replace("^", "")
            if s in _symbol_subscribers:
                _symbol_subscribers[s].discard(conn_id)
            if clean in _symbol_subscribers:
                _symbol_subscribers[clean].discard(conn_id)

    # Clean any dangling references in the inverted index
    for subscribers in _symbol_subscribers.values():
        subscribers.discard(conn_id)


class HighFrequencyFluidityEngine:
    """
    High-frequency micro-tick fluidity engine delivering rapid price fluidity (>= 3 Hz).

    SEBI Anti-Fabrication Compliance:
    - 0 fake volume (volume strictly mirrors broker-confirmed volume).
    - 0 price drift (clamped within [min, max] and day [low, high] circuit limits).
    - NSE equity tick size quantization (₹0.05).
    - Fully suspended when market is closed (is_indian_market_open() == False).
    - Transparent labeling with data_status="realtime_interpolated".
    """

    def __init__(self):
        self._last_ticks: dict[str, dict] = {}
        self._active_tasks: dict[str, asyncio.Task] = {}

    def get_last_tick(self, symbol: str) -> Optional[dict]:
        return self._last_ticks.get(symbol)

    def record_tick(self, symbol: str, price: float, volume: int = 0, change: float = 0.0, change_pct: float = 0.0) -> None:
        self._last_ticks[symbol] = {
            "price": price,
            "volume": volume,
            "change": change,
            "change_pct": change_pct,
            "time": time.monotonic(),
        }

    async def schedule_micro_ticks(
        self,
        symbol: str,
        start_price: float,
        target_price: float,
        volume: int,
        prev_close: float,
        open_price: Optional[float] = None,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
        source: str = "Live Market Feed",
        duration: float = 0.3,
        steps: int = 3,
    ) -> Optional[asyncio.Task]:
        """
        Emits quantized micro-ticks (NSE ₹0.05 tick size) bridging discrete jumps
        across a 300ms window at 3 to 10 Hz.
        """
        if not is_indian_market_open():
            return None

        # Cancel any active running interpolation for this symbol
        if symbol in self._active_tasks and not self._active_tasks[symbol].done():
            self._active_tasks[symbol].cancel()

        interval = duration / max(steps, 1)
        price_step = (target_price - start_price) / max(steps, 1)

        async def _run():
            try:
                for i in range(1, steps + 1):
                    await asyncio.sleep(interval)
                    if not is_indian_market_open():
                        break

                    is_final = (i == steps)
                    raw_price = start_price + price_step * i
                    quantized = quantize_tick(raw_price)

                    # Clamping strictly within trade boundaries and daily limits
                    min_p = min(start_price, target_price)
                    max_p = max(start_price, target_price)
                    if low_price is not None:
                        min_p = max(min_p, low_price)
                    if high_price is not None:
                        max_p = min(max_p, high_price)

                    clamped_price = max(min_p, min(max_p, quantized))
                    clamped_price = quantize_tick(clamped_price)

                    change = round(clamped_price - prev_close, 2)
                    change_pct = round((change / prev_close) * 100.0, 2) if prev_close else 0.0

                    await broadcast_market_update(
                        symbol=symbol,
                        price=clamped_price,
                        change=change,
                        change_pct=change_pct,
                        volume=volume,  # 0 fake volume: strictly broker-confirmed
                        open_price=open_price,
                        high_price=high_price,
                        low_price=low_price,
                        source=source,
                        data_status="realtime" if is_final else "realtime_interpolated",
                        auto_interpolate=False,
                    )
            except asyncio.CancelledError:
                pass
            finally:
                self._active_tasks.pop(symbol, None)

        task = asyncio.create_task(_run())
        self._active_tasks[symbol] = task
        return task


fluidity_engine = HighFrequencyFluidityEngine()


@ws_router.websocket("/ws")
@ws_router.websocket("/ws/")
async def general_websocket(websocket: WebSocket, token: str = ""):
    """
    General WebSocket for market data and alerts.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = str(payload["sub"])
    except (JWTError, KeyError):
        await websocket.close(code=1008, reason="Authentication required")
        return
    await websocket.accept()
    conn_id = str(id(websocket))
    _market_connections[conn_id] = {"ws": websocket, "symbols": set(), "user_id": user_id}
    logger.info(f"WebSocket connected: {conn_id}")

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if len(data) > 4096:
                    await websocket.close(code=1009, reason="Message too large")
                    break
                if msg.get("type") == "subscribe" and msg.get("channel") == "market_data":
                    symbol = msg.get("symbol")
                    if symbol:
                        norm_symbol = symbol if "." in symbol or symbol.startswith("^") else symbol + ".NS"
                        subscriptions = _market_connections[conn_id]["symbols"]
                        if len(subscriptions) >= MAX_SUBSCRIPTIONS_PER_CONNECTION and norm_symbol not in subscriptions:
                            await websocket.send_text(json.dumps({"type": "error", "message": "Subscription limit reached"}))
                            continue
                        _register_subscription(conn_id, norm_symbol)
                        logger.info(f"{conn_id} subscribed to {norm_symbol}")

                        # Dynamically wire to Fyers Data Socket for zero-rate-limit stream
                        try:
                            from backend.services.fyers_stream import fyers_stream_service
                            asyncio.create_task(fyers_stream_service.subscribe_symbols([norm_symbol]))
                        except Exception:
                            pass
            except Exception:
                if data == "ping":
                    await websocket.send_text("pong")
    except WebSocketDisconnect:
        _unregister_connection(conn_id)
        logger.info(f"WebSocket disconnected: {conn_id}")


async def poll_market_data():
    """
    Autonomous Dual-Engine real-time market data streaming loop.
    - If Fyers WebSocket push stream is active: operates as an auxiliary synchronizer (every 4s).
    - If Fyers is expired / disconnected: operates as the primary live ticker using Yahoo Finance
      Backup Engine (every 3s), broadcasting live ticking prices to charts and dashboards.
    """
    from backend.services.fyers_stream import fyers_stream_service
    from backend.services.market_data import MarketDataService, market_data_service

    while True:
        try:
            # Collect all active subscribed symbols across all connections
            symbols = set()
            for conn in _market_connections.values():
                symbols.update(conn.get("symbols", set()))

            # If clients are connected, ensure major indices are also kept fresh
            if _market_connections and not symbols:
                symbols.update(["^NSEI", "^NSEBANK"])

            fyers_connected = fyers_stream_service.is_connected and MarketDataService._fyers_token_valid

            if symbols:
                if fyers_connected:
                    # ZERO REST CALLS: Fyers Data Socket (WebSocket V3) is connected & streaming
                    await fyers_stream_service.subscribe_symbols(list(symbols))
                else:
                    # Autonomous Dual Failover Engine: Active ONLY when Fyers is expired / disconnected.
                    quotes_map = await market_data_service.fetch_quotes_bulk(list(symbols), use_fallback=True)
                    now = time.monotonic()
                    for symbol, quote in quotes_map.items():
                        if quote and quote.get("price", 0) > 0:
                            q_price = float(quote["price"])
                            last_tick = fluidity_engine.get_last_tick(symbol)
                            prev_price = last_tick["price"] if last_tick else None
                            elapsed = (now - last_tick["time"]) if last_tick else 999.0

                            # Micro-tick fluidity: If tick pause > 333ms during market hours and price changed >= 0.10
                            if (
                                prev_price is not None
                                and abs(q_price - prev_price) >= 0.10
                                and elapsed >= 0.333
                                and is_indian_market_open()
                            ):
                                prev_close = quote.get("previous_close", q_price - quote.get("change", 0.0))
                                await fluidity_engine.schedule_micro_ticks(
                                    symbol=symbol,
                                    start_price=prev_price,
                                    target_price=q_price,
                                    volume=quote.get("volume", 0),
                                    prev_close=prev_close,
                                    open_price=quote.get("open"),
                                    high_price=quote.get("high"),
                                    low_price=quote.get("low"),
                                    source=quote.get("source", "Backup (Yahoo Finance)"),
                                )
                            else:
                                await broadcast_market_update(
                                    symbol=symbol,
                                    price=q_price,
                                    change=quote.get("change", 0.0),
                                    change_pct=quote.get("change_pct", 0.0),
                                    volume=quote.get("volume", 0),
                                    timestamp=quote.get("timestamp"),
                                    open_price=quote.get("open"),
                                    high_price=quote.get("high"),
                                    low_price=quote.get("low"),
                                    source=quote.get("source", "Backup (Yahoo Finance)"),
                                    data_status=quote.get("data_status", "live_backup"),
                                    auto_interpolate=False,
                                )
        except Exception as e:
            logger.error(f"Error in dual-engine market data streaming poller: {e}")

        try:
            fyers_connected = fyers_stream_service.is_connected and MarketDataService._fyers_token_valid
            poll_interval = 4.0 if fyers_connected else 3.0
        except Exception:
            poll_interval = 3.0

        await asyncio.sleep(poll_interval)


async def broadcast_alert(alert_payload: dict, user_id: str | None = None):
    """Deliver an alert toast notification to its owner (or all connected clients if user_id is None)."""
    if "type" not in alert_payload:
        envelope = {
            "type": "alert_toast",
            "data": alert_payload
        }
    else:
        envelope = alert_payload

    payload_str = json.dumps(envelope)
    tasks = []
    active_conn_ids = []

    for conn_id, conn_data in list(_market_connections.items()):
        if user_id is not None and conn_data.get("user_id") != user_id:
            continue
        ws = conn_data.get("ws")
        if ws:
            tasks.append(ws.send_text(payload_str))
            active_conn_ids.append(conn_id)

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for conn_id, res in zip(active_conn_ids, results):
            if isinstance(res, Exception):
                _unregister_connection(conn_id)


async def broadcast_market_update(
    symbol: str, 
    price: float, 
    change: float, 
    change_pct: float,
    volume: int = 0,
    timestamp: str | None = None,
    open_price: float | None = None,
    high_price: float | None = None,
    low_price: float | None = None,
    source: str | None = None,
    data_status: str | None = None,
    auto_interpolate: bool = False,
):
    """
    Broadcast market updates to subscribed clients with O(1) inverted index lookup,
    single JSON serialization, and concurrent asyncio.gather fan-out.
    """
    # Record tick in fluidity engine state
    fluidity_engine.record_tick(symbol, price, volume, change, change_pct)

    payload = {
        "type": "market_update",
        "symbol": symbol,
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "volume": volume,
        "timestamp": timestamp,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "source": source or "Live Market Feed",
        "data_status": data_status or "realtime"
    }
    payload_str = json.dumps(payload)

    target_conn_ids = _get_subscribers_for_symbol(symbol)
    if not target_conn_ids:
        return

    tasks = []
    active_conn_ids = []
    for conn_id in list(target_conn_ids):
        conn_data = _market_connections.get(conn_id)
        if not conn_data:
            _unregister_connection(conn_id)
            continue
        ws = conn_data.get("ws")
        if ws:
            tasks.append(ws.send_text(payload_str))
            active_conn_ids.append(conn_id)

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for conn_id, res in zip(active_conn_ids, results):
            if isinstance(res, Exception):
                _unregister_connection(conn_id)
