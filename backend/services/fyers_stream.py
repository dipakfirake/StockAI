"""
Real-time tick streaming service utilizing Fyers Data Socket (WebSocket V3).

Connects to Fyers HSM WebSocket cluster for zero-rate-limit, push-driven
market updates. Ticks are ingested, stored in Redis, and broadcast to
connected React clients in real time (<100ms latency).
"""

import asyncio
import os
import sys
import types
from datetime import datetime
from typing import Optional, Set, Dict, List, Any

# Ensure pkg_resources compatibility on modern Python (3.11+ / 3.12+)
if "pkg_resources" not in sys.modules:
    try:
        import pkg_resources  # noqa: F401
    except ImportError:
        pkg_mod = types.ModuleType("pkg_resources")

        def _res_filename(pkg: str, res: str) -> str:
            import importlib.util
            spec = importlib.util.find_spec(pkg)
            if spec and spec.submodule_search_locations:
                return os.path.join(list(spec.submodule_search_locations)[0], res)
            return os.path.join(os.path.dirname(__file__), res)

        pkg_mod.resource_filename = _res_filename
        sys.modules["pkg_resources"] = pkg_mod

from backend.core.logging_config import get_logger
from backend.core.config import settings

logger = get_logger(__name__)

# FyersDataSocket import with graceful fallback
try:
    from fyers_apiv3.FyersWebsocket import data_ws
    FyersDataSocket = data_ws.FyersDataSocket
except Exception as e:
    FyersDataSocket = None
    logger.warning(f"FyersDataSocket import failed or not available: {e}")


class FyersStreamService:
    """
    Singleton service managing the background Fyers WebSocket tick stream.
    """
    _instance: Optional["FyersStreamService"] = None

    def __init__(self):
        self._socket: Any = None
        self._is_connected: bool = False
        self._is_running: bool = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._subscribed_symbols: Set[str] = set()
        self._symbol_map: Dict[str, str] = {}  # Fyers symbol -> Target symbol (e.g. NSE:RELIANCE-EQ -> RELIANCE.NS)
        self._lock = asyncio.Lock()

        # Pre-seed default core indices and high-activity equity symbols
        self._default_indices = [
            "NSE:NIFTY50-INDEX",
            "NSE:NIFTYBANK-INDEX",
            "BSE:SENSEX-INDEX",
            "NSE:INDIAVIX-INDEX",
            "NSE:NIFTYIT-INDEX",
            "NSE:NIFTYMIDCAP50-INDEX",
            "NSE:PCJEWELLER-EQ",
            "NSE:RELIANCE-EQ",
            "NSE:HDFCBANK-EQ",
            "NSE:INFY-EQ",
            "NSE:TCS-EQ",
            "NSE:ICICIBANK-EQ",
            "NSE:SBIN-EQ",
            "NSE:KOTAKBANK-EQ",
            "NSE:BHARTIARTL-EQ",
            "NSE:ITC-EQ",
        ]
        for fyers_sym in self._default_indices:
            self._subscribed_symbols.add(fyers_sym)

    @classmethod
    def get_instance(cls) -> "FyersStreamService":
        if cls._instance is None:
            cls._instance = FyersStreamService()
        return cls._instance

    @property
    def is_connected(self) -> bool:
        """Returns True if the Fyers WebSocket connection is live and streaming."""
        if not self._is_connected or self._socket is None:
            return False
        try:
            return bool(self._socket.is_connected())
        except Exception:
            return self._is_connected

    async def start(self) -> bool:
        """
        Initializes credentials and establishes the background WebSocket connection.
        Returns True if connected, or False if credentials are unavailable/expired.
        """
        if FyersDataSocket is None:
            logger.info("FyersDataSocket library unavailable. Operating in autonomous polling mode.")
            return False

        if self.is_connected:
            return True

        self._loop = asyncio.get_running_loop()

        # Discover credentials from settings, database, or environment
        from backend.services.market_data import MarketDataService
        client_id = settings.FYERS_CLIENT_ID
        access_token = settings.FYERS_ACCESS_TOKEN

        try:
            from backend.core.cache import cache_get
            cached_creds = await cache_get("fyers_creds")
            if cached_creds and cached_creds.get("access_token"):
                client_id = cached_creds.get("client_id", client_id)
                access_token = cached_creds.get("access_token", access_token)
        except Exception:
            pass

        try:
            from backend.core.database import AsyncSessionLocal
            from backend.models.settings import SystemSettings
            from sqlalchemy import select

            async with AsyncSessionLocal() as db:
                fyers_client_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_client_id"))).scalar_one_or_none()
                fyers_token_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_access_token"))).scalar_one_or_none()
                if fyers_client_obj and fyers_client_obj.value:
                    client_id = fyers_client_obj.value
                if fyers_token_obj and fyers_token_obj.value:
                    access_token = fyers_token_obj.value
        except Exception as e:
            logger.debug(f"Database settings query skipped: {e}")

        # Check environment dynamic cache
        if hasattr(MarketDataService, "_env_cache") and MarketDataService._env_cache:
            if MarketDataService._env_cache.get("FYERS_CLIENT_ID"):
                client_id = MarketDataService._env_cache["FYERS_CLIENT_ID"]
            if MarketDataService._env_cache.get("FYERS_ACCESS_TOKEN") and not access_token:
                access_token = MarketDataService._env_cache["FYERS_ACCESS_TOKEN"]

        if not client_id or not access_token:
            logger.info("Fyers WebSocket stream not started: credentials not configured. Operating in autonomous polling fallback mode.")
            return False

        # Clean tokens
        client_id = str(client_id).strip()
        access_token = str(access_token).strip()

        # Fyers requires 'client_id:access_token' or 'access_token' format
        formatted_token = f"{client_id}:{access_token}" if ":" not in access_token else access_token

        try:
            logger.info("Initializing Fyers Data Socket (WebSocket V3) real-time tick stream...")
            self._socket = FyersDataSocket(
                access_token=formatted_token,
                log_path=None,
                litemode=False,        # Full Mode for tick accuracy, OHLC, volume, and exact price changes
                write_to_file=False,
                reconnect=True,
                on_connect=self._on_open,
                on_close=self._on_close,
                on_error=self._on_error,
                on_message=self._on_tick
            )
            self._socket.connect()
            self._is_running = True
            logger.info("Fyers Data Socket initialization dispatched.")
            return True
        except Exception as err:
            logger.warning(f"Fyers Data Socket connection failed: {err}. Falling back to 1-second poller.")
            self._is_connected = False
            return False

    def _on_open(self) -> None:
        """Callback when Fyers WebSocket handshake completes."""
        self._is_connected = True
        logger.info("Fyers Data Socket CONNECTED successfully. Subscribing to active market symbols...")
        try:
            # Prepare symbol mappings
            from backend.services.market_data import MarketDataService
            for f_sym in list(self._subscribed_symbols):
                self._symbol_map[f_sym] = MarketDataService._normalise_yf_symbol(f_sym)

            # Subscribe to initial symbols
            if self._socket and self._subscribed_symbols:
                symbols_list = list(self._subscribed_symbols)
                # Chunk into groups of 50 (Fyers batch limit per message)
                for i in range(0, len(symbols_list), 50):
                    chunk = symbols_list[i : i + 50]
                    self._socket.subscribe(symbols=chunk, data_type="SymbolUpdate")
                logger.info(f"Fyers WebSocket subscribed to {len(symbols_list)} symbols: {symbols_list[:5]}...")
        except Exception as e:
            logger.error(f"Error subscribing symbols on Fyers open: {e}")

    def _on_close(self, message: Any) -> None:
        """Callback when Fyers WebSocket closes."""
        self._is_connected = False
        logger.warning(f"Fyers Data Socket closed: {message}")
        try:
            from backend.services.market_data import MarketDataService
            msg_str = str(message).lower()
            if "token" in msg_str or "auth" in msg_str or "expire" in msg_str or "invalid" in msg_str:
                MarketDataService.mark_fyers_token_expired(f"WebSocket closed: {message}")
        except Exception:
            pass

    def _on_error(self, message: Any) -> None:
        """Callback when Fyers WebSocket encounters an error."""
        logger.warning(f"Fyers Data Socket error: {message}")
        try:
            from backend.services.market_data import MarketDataService
            msg_str = str(message).lower()
            if "token" in msg_str or "auth" in msg_str or "expire" in msg_str or "invalid" in msg_str:
                MarketDataService.mark_fyers_token_expired(f"WebSocket error: {message}")
        except Exception:
            pass

    def _on_tick(self, message: dict) -> None:
        """
        High-throughput callback executing on Fyers worker thread when a tick arrives.
        Parses tick and dispatches to FastAPI WebSocket clients.
        """
        try:
            if not isinstance(message, dict):
                return

            fyers_sym = message.get("symbol")
            if not fyers_sym:
                return

            ltp = message.get("ltp")
            if ltp is None or float(ltp) <= 0:
                return

            import time
            from backend.services.market_data import MarketDataService

            now_ts = time.time()
            MarketDataService._last_fyers_tick_time = now_ts
            MarketDataService._fyers_token_valid = True
            MarketDataService._active_engine = "PRIMARY_FYERS"
            MarketDataService._fyers_cooldown_until = 0.0

            price = round(float(ltp), 2)
            calc_change = float(message.get("ch", 0.0) or 0.0)
            calc_change_pct = float(message.get("chp", 0.0) or 0.0)
            volume = int(message.get("vol_traded_today", message.get("volume", 0)) or 0)
            prev_close = float(message.get("prev_close_price", 0.0) or 0.0)
            open_price = float(message["open_price"]) if "open_price" in message and message["open_price"] is not None else None
            high_price = float(message["high_price"]) if "high_price" in message and message["high_price"] is not None else None
            low_price = float(message["low_price"]) if "low_price" in message and message["low_price"] is not None else None
            timestamp = str(message.get("timestamp") or datetime.now(timezone.utc).isoformat())

            if calc_change != 0.0 and (prev_close <= 0.0 or abs(prev_close - price) < 1e-4):
                prev_close = round(price - calc_change, 2)
            elif prev_close <= 0.0:
                prev_close = price

            if calc_change == 0.0 and calc_change_pct != 0.0 and prev_close > 0.0:
                calc_change = round(price - prev_close, 2)
            elif calc_change_pct == 0.0 and calc_change != 0.0 and prev_close > 0.0:
                calc_change_pct = round((calc_change / prev_close) * 100.0, 2)

            # Resolve mapped symbol (e.g., NSE:NIFTY50-INDEX -> ^NSEI, NSE:PCJEWELLER-EQ -> PCJEWELLER.NS)
            target_symbol = self._symbol_map.get(fyers_sym) or MarketDataService._normalise_yf_symbol(fyers_sym)
            clean_symbol = target_symbol.replace(".NS", "").replace(".BO", "").replace("^", "").strip().upper()

            # Update in-memory Redis cache asynchronously
            if self._loop and self._loop.is_running():
                from backend.api.websocket import broadcast_market_update
                from backend.core.cache import cache_set

                # 1. Dispatch WebSocket broadcast to all connected web clients
                asyncio.run_coroutine_threadsafe(
                    broadcast_market_update(
                        symbol=target_symbol,
                        price=price,
                        change=round(calc_change, 2),
                        change_pct=round(calc_change_pct, 2),
                        volume=volume,
                        timestamp=timestamp,
                        open_price=open_price,
                        high_price=high_price,
                        low_price=low_price,
                        source="Fyers WebSocket Stream",
                        data_status="realtime"
                    ),
                    self._loop
                )

                # 2. Update cache key under both target_symbol and original format so REST requests get instant cache hit
                cached_quote = {
                    "symbol": target_symbol,
                    "price": price,
                    "previous_close": round(prev_close, 2),
                    "change": round(calc_change, 2),
                    "change_pct": round(calc_change_pct, 2),
                    "volume": volume,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "52w_high": high_price if high_price else 0.0,
                    "52w_low": low_price if low_price else 0.0,
                    "timestamp": timestamp,
                    "source": "Fyers API",
                    "data_status": "realtime"
                }

                # Store with 15s TTL so fast subsequent REST requests hit cache directly without hitting Fyers REST 50 req/min limit
                for key_alias in (target_symbol, fyers_sym, clean_symbol):
                    asyncio.run_coroutine_threadsafe(
                        cache_set(f"quote:{key_alias}", cached_quote, ttl=15),
                        self._loop
                    )

        except Exception as e:
            logger.debug(f"Error handling Fyers tick: {e}")

    async def subscribe_symbols(self, symbols: List[str]) -> None:
        """
        Dynamically subscribe to a list of symbols (e.g. when a user navigates to a chart).
        """
        if not symbols:
            return

        from backend.services.market_data import MarketDataService

        new_fyers_symbols = []
        async with self._lock:
            for s in symbols:
                if not s:
                    continue
                f_sym = MarketDataService._normalise_symbol(s)
                yf_sym = MarketDataService._normalise_yf_symbol(f_sym)
                self._symbol_map[f_sym] = yf_sym

                if f_sym not in self._subscribed_symbols:
                    self._subscribed_symbols.add(f_sym)
                    new_fyers_symbols.append(f_sym)

        # If currently connected to Fyers, send subscription packet
        if new_fyers_symbols and self._socket and self.is_connected:
            try:
                for i in range(0, len(new_fyers_symbols), 50):
                    chunk = new_fyers_symbols[i : i + 50]
                    self._socket.subscribe(symbols=chunk, data_type="SymbolUpdate")
                logger.info(f"Fyers WebSocket dynamically subscribed to: {new_fyers_symbols}")
            except Exception as e:
                logger.warning(f"Error in dynamic Fyers subscription: {e}")

    async def stop(self) -> None:
        """Cleanly closes the WebSocket connection."""
        self._is_running = False
        self._is_connected = False
        if self._socket:
            try:
                self._socket.close_connection()
            except Exception as e:
                logger.debug(f"Error closing FyersDataSocket: {e}")
            self._socket = None
        logger.info("Fyers Data Socket closed.")


# Global singleton instance
fyers_stream_service = FyersStreamService.get_instance()
