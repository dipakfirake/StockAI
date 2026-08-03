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
                        # Append .NS for normalization if needed
                        norm_symbol = symbol if "." in symbol else symbol + ".NS"
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
    while True:
        try:
            # Collect all subscribed symbols
            symbols = set()
            for conn in _market_connections.values():
                symbols.update(conn["symbols"])
            
            # Fetch quotes
            for symbol in symbols:
                quote = await market_data_service.fetch_quote(symbol)
                if quote and quote.get("price"):
                    await broadcast_market_update(
                        symbol,
                        quote["price"], 
                        quote.get("change", 0.0), 
                        quote.get("change_pct", 0.0)
                    )
        except Exception as e:
            logger.error(f"Error in poll_market_data: {e}")
        await asyncio.sleep(5)


async def broadcast_alert(alert_payload: dict, user_id: str | None = None):
    """Deliver an alert only to its owner when a recipient is provided."""
    disconnected = []
    for conn_id, conn_data in _market_connections.items():
        if user_id is not None and conn_data["user_id"] != user_id:
            continue
        try:
            await conn_data["ws"].send_text(json.dumps(alert_payload))
        except Exception:
            disconnected.append(conn_id)

    for conn_id in disconnected:
        _market_connections.pop(conn_id, None)

async def broadcast_market_update(symbol: str, price: float, change: float, change_pct: float):
    """Broadcast market updates to subscribed clients."""
    payload = {
        "type": "market_update",
        "symbol": symbol,
        "price": price,
        "change": change,
        "change_pct": change_pct,
    }
    disconnected = []
    for conn_id, conn_data in _market_connections.items():
        if symbol in conn_data["symbols"]:
            try:
                await conn_data["ws"].send_text(json.dumps(payload))
            except Exception:
                disconnected.append(conn_id)

    for conn_id in disconnected:
        _market_connections.pop(conn_id, None)
