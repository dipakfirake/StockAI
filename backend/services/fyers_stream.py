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
from datetime import datetime, timezone
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
    data_ws = None
    FyersDataSocket = None
    logger.warning(f"FyersDataSocket import failed or not available: {e}")

# In-memory fast cache for resolved HSM tokens: {fyers_symbol: {"fyToken": ..., "symbol": ...}}
_HSM_TOKEN_MEMORY_CACHE: Dict[str, dict] = {}


def _patch_fyers_symbol_conversion():
    """
    Patches SymbolConversion.symbol_to_hsmtoken in fyers_apiv3 to:
    1. Check local in-memory cache to eliminate redundant HTTP calls.
    2. Add strict 3.0s timeout to requests.get so it never freezes worker threads.
    3. Pass correct Authorization and version headers.
    4. Handle network and timeout errors gracefully without raising unhandled exceptions.
    """
    if data_ws is None or not hasattr(data_ws, "SymbolConversion"):
        return

    if getattr(data_ws.SymbolConversion, "_is_stockai_patched", False):
        return

    import json
    import urllib.parse
    import requests

    original_method = getattr(data_ws.SymbolConversion, "symbol_to_hsmtoken", None)

    # Load mapper once
    try:
        if "pkg_resources" in sys.modules:
            file_path = sys.modules["pkg_resources"].resource_filename('fyers_apiv3.FyersWebsocket', 'map.json')
        else:
            file_path = os.path.join(os.path.dirname(data_ws.__file__), 'map.json')
        with open(file_path, "r") as f:
            mapper = json.load(f)
        index_dict = mapper.get("index_dict", {})
        exch_seg_dict = mapper.get("exch_seg_dict", {})
    except Exception as e:
        logger.warning(f"Could not load Fyers map.json for symbol conversion: {e}")
        index_dict = {}
        exch_seg_dict = {}

    def patched_symbol_to_hsmtoken(self, symbols: list):
        if not symbols:
            return ({}, [], False)

        try:
            # Check which symbols need network resolution
            uncached = [s for s in symbols if s not in _HSM_TOKEN_MEMORY_CACHE]

            if uncached:
                symbols_query = ",".join(uncached)
                data = {"symbols": symbols_query}
                url_params = urllib.parse.urlencode(data)
                URL = self.quotes_url + "?" + url_params

                auth_header = self.access_token
                try:
                    stream_inst = FyersStreamService.get_instance()
                    if stream_inst._client_id and stream_inst._access_token:
                        auth_header = f"{stream_inst._client_id}:{stream_inst._access_token}"
                except Exception:
                    pass

                headers = {
                    "Authorization": auth_header,
                    "Content-Type": "application/json",
                    "version": "3",
                }

                try:
                    response = requests.get(url=URL, headers=headers, timeout=3.0)
                    quote_data = response.json()
                    if "d" in quote_data:
                        for item in quote_data["d"]:
                            if item.get("s") == "ok" and "v" in item:
                                sym_name = item["v"].get("symbol")
                                if sym_name:
                                    _HSM_TOKEN_MEMORY_CACHE[sym_name] = item["v"]
                except Exception as err:
                    logger.warning(f"Fyers HSM token HTTP lookup notice (3.0s guard): {err}")

            # Reconstruct mapping using cached and newly fetched tokens
            datadict = {}
            wrong_symbol = []
            dp_index_flag = False

            for s in symbols:
                val = _HSM_TOKEN_MEMORY_CACHE.get(s)
                if not val or "fyToken" not in val:
                    wrong_symbol.append(s)
                    continue

                fy_token = str(val["fyToken"])
                sym = val.get("symbol", s)
                key = fy_token[:4]
                if key not in exch_seg_dict:
                    wrong_symbol.append(sym)
                    continue

                segment = exch_seg_dict[key]
                parts = sym.split("-")
                update_dict = True

                if len(parts) > 1 and parts[-1] == "INDEX" and self.data_type != "DepthUpdate":
                    if sym in index_dict:
                        ex_token = index_dict[sym]
                    else:
                        ex_token = sym.split(":")[1].split("-")[0] if ":" in sym else sym
                    sub_symbol = f"if|{segment}|{ex_token}"
                elif self.data_type == "DepthUpdate" and parts[-1] != "INDEX":
                    ex_token = fy_token[10:]
                    sub_symbol = f"dp|{segment}|{ex_token}"
                elif self.data_type == "SymbolUpdate":
                    ex_token = fy_token[10:]
                    sub_symbol = f"sf|{segment}|{ex_token}"
                elif self.data_type == "DepthUpdate" and parts[-1] == "INDEX":
                    update_dict = False
                    dp_index_flag = True
                else:
                    sub_symbol = f"sf|{segment}|{fy_token[10:]}"

                if update_dict:
                    datadict[sub_symbol] = sym

            return (datadict, wrong_symbol, dp_index_flag)
        except Exception as e:
            logger.warning(f"Error in patched symbol_to_hsmtoken: {e}")
            if original_method:
                try:
                    return original_method(self, symbols)
                except Exception:
                    pass
            return ({}, symbols, False)

    data_ws.SymbolConversion.symbol_to_hsmtoken = patched_symbol_to_hsmtoken
    data_ws.SymbolConversion._is_stockai_patched = True
    logger.info("StockAI non-blocking guarded patch applied to Fyers SymbolConversion.symbol_to_hsmtoken.")


if FyersDataSocket is not None:
    try:
        _patch_fyers_symbol_conversion()
    except Exception as _patch_err:
        logger.warning(f"Could not apply Fyers symbol conversion patch: {_patch_err}")



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
        self.__lock: Optional[asyncio.Lock] = None
        self.__lifecycle_lock: Optional[asyncio.Lock] = None
        self._client_id: Optional[str] = None
        self._access_token: Optional[str] = None

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

    @property
    def _lifecycle_lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self.__lifecycle_lock is None:
            self.__lifecycle_lock = asyncio.Lock()
        elif loop is not None and getattr(self.__lifecycle_lock, "_loop", None) not in (None, loop):
            self.__lifecycle_lock = asyncio.Lock()
        return self.__lifecycle_lock

    @_lifecycle_lock.setter
    def _lifecycle_lock(self, val: Any) -> None:
        self.__lifecycle_lock = val

    @property
    def _lock(self) -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self.__lock is None:
            self.__lock = asyncio.Lock()
        elif loop is not None and getattr(self.__lock, "_loop", None) not in (None, loop):
            self.__lock = asyncio.Lock()
        return self.__lock

    @_lock.setter
    def _lock(self, val: Any) -> None:
        self.__lock = val

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

    @property
    def is_running(self) -> bool:
        """Returns True if the Fyers WebSocket stream runner is active."""
        return self._is_running

    async def start(self) -> bool:
        """
        Acquires lifecycle lock and initializes credentials and background connection.
        Guarantees non-blocking execution via asyncio.to_thread with 3.0s timeout.
        Returns True if connected, or False if credentials unavailable or connection failed.
        """
        async with self._lifecycle_lock:
            return await self._start_internal()

    async def _start_internal(self) -> bool:
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
            from backend.core.database import AsyncSessionLocal
            from backend.models.settings import SystemSettings
            from sqlalchemy import select

            db = AsyncSessionLocal()
            try:
                fyers_client_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_client_id"))).scalar_one_or_none()
                fyers_token_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_access_token"))).scalar_one_or_none()
                if fyers_client_obj and fyers_client_obj.value and len(fyers_client_obj.value.strip()) > 3:
                    client_id = fyers_client_obj.value.strip()
                if fyers_token_obj and fyers_token_obj.value and len(fyers_token_obj.value.strip()) > 10:
                    access_token = fyers_token_obj.value.strip()
            finally:
                await asyncio.shield(db.close())
        except Exception as e:
            logger.debug(f"Database settings query skipped: {e}")

        if not access_token or not client_id:
            try:
                from backend.core.cache import cache_get
                cached_creds = await cache_get("fyers_creds")
                if cached_creds:
                    if not client_id and cached_creds.get("client_id"):
                        client_id = cached_creds["client_id"]
                    if not access_token and cached_creds.get("access_token"):
                        access_token = cached_creds["access_token"]
            except Exception:
                pass

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
        self._client_id = client_id
        self._access_token = access_token

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
            # Offload socket connect to worker thread guarded by strict 3.0s timeout
            if hasattr(self._socket, "connect"):
                await asyncio.wait_for(
                    asyncio.to_thread(self._socket.connect),
                    timeout=3.0
                )
            self._is_running = True
            logger.info("Fyers Data Socket initialization dispatched.")
            return True
        except asyncio.TimeoutError:
            logger.warning("Fyers Data Socket connect timed out after 3.0s. Falling back to autonomous polling mode.")
            self._is_connected = False
            self._is_running = False
            return False
        except Exception as err:
            logger.warning(f"Fyers Data Socket connection failed: {err}. Falling back to 1-second poller.")
            self._is_connected = False
            self._is_running = False
            return False

    def _on_open(self) -> None:
        """Callback when Fyers WebSocket handshake completes."""
        self._is_connected = True
        logger.info("Fyers Data Socket CONNECTED successfully. Restoring primary feed status and subscribing to active market symbols...")
        try:
            from backend.services.market_data import MarketDataService
            MarketDataService.reset_fyers_health()
        except Exception as e:
            logger.error(f"Error restoring primary feed health on Fyers open: {e}")

        try:
            # Prepare symbol mappings
            from backend.services.market_data import MarketDataService
            for f_sym in list(self._subscribed_symbols):
                self._symbol_map[f_sym] = MarketDataService._normalise_yf_symbol(f_sym)

            # Schedule chunked non-blocking subscription onto the running event loop
            symbols_list = list(self._subscribed_symbols)
            if self._socket and symbols_list:
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self._subscribe_chunks(symbols_list),
                        self._loop
                    )
                else:
                    for i in range(0, len(symbols_list), 20):
                        chunk = symbols_list[i : i + 20]
                        if hasattr(self._socket, "subscribe"):
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

    async def _resolve_and_cache_hsm_tokens(self, symbols: List[str]) -> None:
        """
        Pre-warms HSM tokens from Redis (24h TTL) and populates _HSM_TOKEN_MEMORY_CACHE.
        Offloads any external HTTP calls to asyncio.to_thread with strict 3.0s timeout
        and proper headers, then caches resolved values in Redis ('fyers:hsm_token:{symbol}')
        with 86400s TTL.
        """
        if not symbols:
            return

        # 1. Check Redis for any symbols not yet in local memory cache
        missing_in_memory = [s for s in symbols if s not in _HSM_TOKEN_MEMORY_CACHE]
        if missing_in_memory:
            try:
                from backend.core.cache import cache_get
                for s in missing_in_memory:
                    val = await cache_get(f"fyers:hsm_token:{s}")
                    if val and isinstance(val, dict) and "fyToken" in val:
                        _HSM_TOKEN_MEMORY_CACHE[s] = val
            except Exception as e:
                logger.debug(f"Redis HSM cache read notice: {e}")

        # 2. For symbols still missing, perform offloaded HTTP query with 3.0s timeout
        still_missing = [s for s in symbols if s not in _HSM_TOKEN_MEMORY_CACHE]
        if still_missing and self._access_token:
            auth_header = f"{self._client_id}:{self._access_token}" if self._client_id else self._access_token
            resolved = await asyncio.to_thread(self._fetch_hsm_tokens_http, still_missing, auth_header)
            if resolved:
                try:
                    from backend.core.cache import cache_set
                    for sym, data_val in resolved.items():
                        _HSM_TOKEN_MEMORY_CACHE[sym] = data_val
                        await cache_set(f"fyers:hsm_token:{sym}", data_val, ttl=86400)
                except Exception as e:
                    logger.debug(f"Redis HSM cache write notice: {e}")

    @staticmethod
    def _fetch_hsm_tokens_http(symbols: List[str], auth_header: str) -> Dict[str, dict]:
        """Synchronous HTTP call to Fyers quotes endpoint guarded by 3.0s timeout."""
        import urllib.parse
        import requests
        results = {}
        try:
            symbols_query = ",".join(symbols)
            data = {"symbols": symbols_query}
            url = f"https://api-t1.fyers.in/data/quotes?{urllib.parse.urlencode(data)}"
            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/json",
                "version": "3",
            }
            resp = requests.get(url, headers=headers, timeout=3.0)
            payload = resp.json()
            if "d" in payload:
                for item in payload["d"]:
                    if item.get("s") == "ok" and "v" in item:
                        sym_name = item["v"].get("symbol")
                        if sym_name:
                            results[sym_name] = item["v"]
        except Exception as e:
            logger.warning(f"External HSM token HTTP fetch error: {e}")
        return results

    async def _subscribe_chunks(self, symbols: List[str]) -> None:
        """
        Chunks symbols into batches of 20 and executes self._socket.subscribe()
        inside asyncio.to_thread guarded by 3.0s timeout. Paces chunks to prevent
        exceeding broker burst limits.
        """
        if not symbols or not self._socket or not self.is_connected:
            return

        # Pre-resolve and warm HSM tokens in Redis & memory
        await self._resolve_and_cache_hsm_tokens(symbols)

        # Batch into chunks of 20 as per interface contract
        chunk_size = 20
        total_chunks = (len(symbols) + chunk_size - 1) // chunk_size

        for idx, i in enumerate(range(0, len(symbols), chunk_size)):
            chunk = symbols[i : i + chunk_size]
            if idx > 0:
                # Pacing delay between chunks to respect broker burst limits
                await asyncio.sleep(0.1)

            try:
                if hasattr(self._socket, "subscribe"):
                    await asyncio.wait_for(
                        asyncio.to_thread(self._socket.subscribe, symbols=chunk, data_type="SymbolUpdate"),
                        timeout=3.0
                    )
            except asyncio.TimeoutError:
                logger.warning(f"Socket subscribe chunk timed out after 3.0s for chunk {idx + 1}/{total_chunks}")
            except Exception as e:
                logger.warning(f"Error subscribing chunk {chunk}: {e}")

        logger.info(f"Fyers WebSocket subscribed to {len(symbols)} symbols in {total_chunks} chunk(s).")

    async def subscribe_symbols(self, symbols: List[str]) -> None:
        """
        Dynamically subscribe to a list of symbols (e.g. when a user navigates to a chart or watchlist).
        Serialized symbol tracking, HSM token caching, non-blocking chunked subscriptions.
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

        # If currently connected to Fyers, send subscription packets non-blockingly
        if new_fyers_symbols and self._socket and self.is_connected:
            await self._subscribe_chunks(new_fyers_symbols)

    async def stop(self) -> None:
        """
        Acquires lifecycle lock and cleanly closes the WebSocket connection.
        Offloads thread joins to worker thread guarded by 3.0s timeout to prevent loop freezing.
        """
        async with self._lifecycle_lock:
            await self._stop_internal()

    async def _stop_internal(self) -> None:
        self._is_running = False
        self._is_connected = False
        sock = self._socket
        self._socket = None
        if sock:
            try:
                if hasattr(sock, "close_connection"):
                    await asyncio.wait_for(
                        asyncio.to_thread(sock.close_connection),
                        timeout=3.0
                    )
            except asyncio.TimeoutError:
                logger.warning("Fyers Data Socket close_connection timed out after 3.0s (thread join delayed). Cleanly abandoning socket reference.")
            except Exception as e:
                logger.debug(f"Error closing FyersDataSocket: {e}")
        logger.info("Fyers Data Socket closed.")

    async def restart(self) -> bool:
        """
        Acquires lifecycle lock, stops existing socket cleanly, and re-initiates connection.
        Serialized through _lifecycle_lock to prevent race conditions or duplicate socket allocations.
        """
        async with self._lifecycle_lock:
            logger.info("Restarting Fyers Data Socket stream with updated credentials (lifecycle locked)...")
            await self._stop_internal()
            return await self._start_internal()


# Global singleton instance
fyers_stream_service = FyersStreamService.get_instance()
