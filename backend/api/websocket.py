"""WebSocket router for real-time alert and market data delivery."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.core.logging_config import get_logger
from backend.core.config import settings
from jose import JWTError, jwt
import json

logger = get_logger(__name__)

ws_router = APIRouter()

# Connected WebSocket clients: user_id -> websocket
_alert_connections: dict[str, WebSocket] = {}

# Market data subscriptions: connection_id -> {websocket, symbols: set()}
_market_connections: dict[str, dict] = {}
MAX_SUBSCRIPTIONS_PER_CONNECTION = 50


@ws_router.websocket("/ws")
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
                        # Append .NS for normalization if needed, but not for index symbols starting with ^
                        norm_symbol = symbol if "." in symbol or symbol.startswith("^") else symbol + ".NS"
                        subscriptions = _market_connections[conn_id]["symbols"]
                        if len(subscriptions) >= MAX_SUBSCRIPTIONS_PER_CONNECTION and norm_symbol not in subscriptions:
                            await websocket.send_text(json.dumps({"type": "error", "message": "Subscription limit reached"}))
                            continue
                        subscriptions.add(norm_symbol)
                        logger.info(f"{conn_id} subscribed to {norm_symbol}")
                        
                        # Dynamically wire to Fyers Data Socket for sub-second event-driven stream
                        try:
                            from backend.services.fyers_stream import fyers_stream_service
                            asyncio.create_task(fyers_stream_service.subscribe_symbols([norm_symbol]))
                        except Exception:
                            pass
            except:
                if data == "ping":
                    await websocket.send_text("pong")
    except WebSocketDisconnect:
        _market_connections.pop(conn_id, None)
        logger.info(f"WebSocket disconnected: {conn_id}")

import asyncio
from backend.services.market_data import market_data_service

async def poll_market_data():
    """
    Autonomous Dual-Engine real-time market data streaming loop.
    - If Fyers WebSocket push stream is active: operates as an auxiliary synchronizer (every 4s).
    - If Fyers is expired / disconnected: operates as the primary live ticker using Yahoo Finance
      Backup Engine (every 3s), broadcasting live ticking prices to charts and dashboards.
    """
    from backend.services.fyers_stream import fyers_stream_service
    from backend.services.market_data import MarketDataService

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
                    # ZERO REST CALLS: Fyers Data Socket (WebSocket V3) is connected & streaming!
                    # Dynamically register active symbols so Fyers pushes sub-100ms ticks on price changes.
                    # _on_tick in fyers_stream.py automatically broadcasts ticks to all connected clients and updates Redis.
                    await fyers_stream_service.subscribe_symbols(list(symbols))
                else:
                    # Autonomous Dual Failover Engine: Active ONLY when Fyers is expired / disconnected.
                    # Smoothly polls Yahoo Finance Backup every 3s and broadcasts ticks to all clients with zero price freeze.
                    quotes_map = await market_data_service.fetch_quotes_bulk(list(symbols), use_fallback=True)
                    for symbol, quote in quotes_map.items():
                        if quote and quote.get("price", 0) > 0:
                            await broadcast_market_update(
                                symbol=symbol,
                                price=quote["price"],
                                change=quote.get("change", 0.0),
                                change_pct=quote.get("change_pct", 0.0),
                                volume=quote.get("volume", 0),
                                timestamp=quote.get("timestamp"),
                                open_price=quote.get("open"),
                                high_price=quote.get("high"),
                                low_price=quote.get("low"),
                                source=quote.get("source", "Backup (Yahoo Finance)"),
                                data_status=quote.get("data_status", "live_backup")
                            )
        except Exception as e:
            logger.error(f"Error in dual-engine market data streaming poller: {e}")
        
        # Dual-Engine smart polling intervals:
        # In Fyers push mode: 4.0s keep-alive interval
        # In Yahoo backup mode: 3.0s interval for smooth ticking without hitting 429 rate limits
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

    disconnected = []
    for conn_id, conn_data in list(_market_connections.items()):
        if user_id is not None and conn_data.get("user_id") != user_id:
            continue
        try:
            await conn_data["ws"].send_text(json.dumps(envelope))
        except Exception:
            disconnected.append(conn_id)

    for conn_id in disconnected:
        _market_connections.pop(conn_id, None)


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
):
    """Broadcast market updates to subscribed clients."""
    clean_sym = symbol.replace(".NS", "").replace(".BO", "")
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
    disconnected = []
    for conn_id, conn_data in list(_market_connections.items()):
        conn_symbols = conn_data.get("symbols", set())
        if symbol in conn_symbols or f"{clean_sym}.NS" in conn_symbols or f"{clean_sym}.BO" in conn_symbols or clean_sym in conn_symbols:
            try:
                await conn_data["ws"].send_text(json.dumps(payload))
            except Exception:
                disconnected.append(conn_id)

    for conn_id in disconnected:
        _market_connections.pop(conn_id, None)
