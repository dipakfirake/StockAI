"""WebSocket router for real-time alert and market data delivery."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.core.logging_config import get_logger
import json

logger = get_logger(__name__)

ws_router = APIRouter()

# Connected WebSocket clients: user_id -> websocket
_alert_connections: dict[str, WebSocket] = {}

# Market data subscriptions: connection_id -> {websocket, symbols: set()}
_market_connections: dict[str, dict] = {}


@ws_router.websocket("/ws")
async def general_websocket(websocket: WebSocket, token: str = ""):
    """
    General WebSocket for market data and alerts.
    """
    await websocket.accept()
    conn_id = str(id(websocket))
    _market_connections[conn_id] = {"ws": websocket, "symbols": set()}
    logger.info(f"WebSocket connected: {conn_id}")

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "subscribe" and msg.get("channel") == "market_data":
                    symbol = msg.get("symbol")
                    if symbol:
                        # Append .NS for normalization if needed
                        norm_symbol = symbol if "." in symbol else symbol + ".NS"
                        _market_connections[conn_id]["symbols"].add(norm_symbol)
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
                        symbol.replace(".NS", ""), 
                        quote["price"], 
                        quote.get("change", 0.0), 
                        quote.get("change_percent", 0.0)
                    )
        except Exception as e:
            logger.error(f"Error in poll_market_data: {e}")
        await asyncio.sleep(5)


async def broadcast_alert(alert_payload: dict):
    """Broadcast an alert to all connected WebSocket clients."""
    disconnected = []
    for conn_id, conn_data in _market_connections.items():
        try:
            await conn_data["ws"].send_text(json.dumps(alert_payload))
        except Exception:
            disconnected.append(conn_id)

    for conn_id in disconnected:
        _market_connections.pop(conn_id, None)

async def broadcast_market_update(symbol: str, price: float, change: float, change_percent: float):
    """Broadcast market updates to subscribed clients."""
    payload = {
        "type": "market_update",
        "symbol": symbol,
        "price": price,
        "change": change,
        "change_percent": change_percent
    }
    disconnected = []
    for conn_id, conn_data in _market_connections.items():
        if symbol in conn_data["symbols"] or not conn_data["symbols"]: # if no symbols, broadcast to all for now
            try:
                await conn_data["ws"].send_text(json.dumps(payload))
            except Exception:
                disconnected.append(conn_id)

    for conn_id in disconnected:
        _market_connections.pop(conn_id, None)
