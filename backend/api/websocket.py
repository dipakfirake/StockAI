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
    Sub-second / 1-second real-time market data streaming loop.
    Fetches real-time quotes via Fyers bulk quotes in a single sub-100ms request
    and broadcasts live ticks to all connected chart and dashboard WebSocket clients.
    """
    while True:
        try:
            import time
            # If Fyers rate limit cooldown is active, back off so the limit can reset
            if time.time() < market_data_service._fyers_cooldown_until:
                await asyncio.sleep(5.0)
                continue

            # Collect all active subscribed symbols across all connections
            symbols = set()
            for conn in _market_connections.values():
                symbols.update(conn.get("symbols", set()))
            
            if symbols:
                quotes_map = await market_data_service.fetch_quotes_bulk(list(symbols), use_fallback=False)
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
                            low_price=quote.get("low")
                        )
        except Exception as e:
            logger.error(f"Error in real-time market data streaming poller: {e}")
        
        # Real-time tick broadcast frequency (1 second per Fyers quota guidelines)
        await asyncio.sleep(1.0)


async def broadcast_alert(alert_payload: dict, user_id: str | None = None):
    """Deliver an alert only to its owner when a recipient is provided."""
    disconnected = []
    for conn_id, conn_data in list(_market_connections.items()):
        if user_id is not None and conn_data.get("user_id") != user_id:
            continue
        try:
            await conn_data["ws"].send_text(json.dumps(alert_payload))
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
    low_price: float | None = None
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
        "low": low_price
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

async def broadcast_alert(message: dict):
    """Broadcast custom alert toast notifications to all connected clients."""
    payload = {
        "type": "alert_toast",
        "data": message
    }
    disconnected = []
    # Send to all general connections (we can reuse _market_connections since it holds all connected ws clients)
    for conn_id, conn_data in list(_market_connections.items()):
        try:
            await conn_data["ws"].send_text(json.dumps(payload))
        except Exception:
            disconnected.append(conn_id)
            
    for conn_id in disconnected:
        _market_connections.pop(conn_id, None)
