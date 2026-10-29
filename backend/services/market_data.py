"""Market data service — yfinance-based OHLCV ingestion for NSE/BSE."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

from backend.core.config import settings
from backend.core.logging_config import get_logger
from backend.core.cache import cache_get, cache_set
from backend.core.market_hours import get_dynamic_candle_ttl, is_indian_market_open, get_current_ist_time
from fyers_apiv3 import fyersModel

logger = get_logger(__name__)

VALID_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "1d", "1w", "1mo"}
# Fyers resolutions: 1, 5, 15, 30, 60, 1D, 1W, 1M
FYERS_INTERVAL_MAP = {
    "1m": "1", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "1d": "1D", "1w": "1W", "1mo": "1M"
}


class MarketDataService:
    """
    Fetches and caches OHLCV market data from yfinance.
    Supports NSE symbols (e.g., RELIANCE.NS) and BSE symbols (e.g., RELIANCE.BO).
    """

    @staticmethod
    def synchronize_candle_tip(candles: list[dict], quote: Optional[dict]) -> list[dict]:
        """
        Synchronize the tip (most recent forming candle) with live quote data.
        
        Ensures that downstream technical indicator calculations and AI model inference
        (LightGBM, BiLSTM, Transformer) immediately reflect real-time live market ticks
        instead of lagging behind delayed candle aggregations.
        """
        if not candles or not isinstance(candles, list):
            return candles
        if not quote or not isinstance(quote, dict):
            return candles

        try:
            live_price = float(quote.get("price") or 0.0)
            if not math.isfinite(live_price) or live_price <= 0:
                return candles

            synced_candles = [dict(c) for c in candles]
            last_c = dict(synced_candles[-1])

            quote_high = float(quote.get("high") or live_price)
            quote_low = float(quote.get("low") or live_price)
            quote_vol = int(quote.get("volume") or 0)

            last_ts_str = str(last_c.get("timestamp", ""))
            now_ist = get_current_ist_time()
            today_date_str = now_ist.strftime("%Y-%m-%d")

            # If last candle is from today (or market is open and it's the current session):
            if today_date_str in last_ts_str or (last_ts_str and last_ts_str[:10] == today_date_str):
                last_c["close"] = live_price
                last_c["high"] = max(float(last_c.get("high", live_price)), live_price, quote_high)
                last_c["low"] = min(float(last_c.get("low", live_price)), live_price, quote_low)
                if quote_vol > int(last_c.get("volume", 0)):
                    last_c["volume"] = quote_vol
                synced_candles[-1] = last_c
            elif is_indian_market_open():
                # Form new active session candle if market is live and candle series hasn't incorporated today
                open_p = float(quote.get("open") or live_price)
                new_candle = {
                    "timestamp": now_ist.isoformat(),
                    "open": open_p,
                    "high": max(open_p, live_price, quote_high),
                    "low": min(open_p, live_price, quote_low),
                    "close": live_price,
                    "volume": quote_vol,
                }
                synced_candles.append(new_candle)

            return synced_candles
        except Exception as e:
            logger.debug(f"Error synchronizing candle tip: {e}")
            return candles

    @staticmethod
    def _normalise_symbol(symbol: str) -> str:
        """Ensure symbol has exchange suffix. Index symbols (^) are returned as-is."""
        symbol = symbol.upper().strip()

        # Idempotent guard: if already a Fyers symbol (NSE:... or BSE:...), return immediately
        if symbol.startswith("NSE:") or symbol.startswith("BSE:"):
            return symbol
        
        # Comprehensive Index translation for Fyers
        index_map = {
            "NIFTY.NS": "NSE:NIFTY50-INDEX",
            "NIFTY": "NSE:NIFTY50-INDEX",
            "^NSEI": "NSE:NIFTY50-INDEX",
            "BANKNIFTY.NS": "NSE:NIFTYBANK-INDEX",
            "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
            "^NSEBANK": "NSE:NIFTYBANK-INDEX",
            "^CNXIT": "NSE:NIFTYIT-INDEX",
            "NIFTYIT": "NSE:NIFTYIT-INDEX",
            "NIFTYIT.NS": "NSE:NIFTYIT-INDEX",
            "^CNXAUTO": "NSE:NIFTYAUTO-INDEX",
            "NIFTYAUTO": "NSE:NIFTYAUTO-INDEX",
            "NIFTYAUTO.NS": "NSE:NIFTYAUTO-INDEX",
            "^CNXENERGY": "NSE:NIFTYENERGY-INDEX",
            "NIFTYENERGY": "NSE:NIFTYENERGY-INDEX",
            "NIFTYENERGY.NS": "NSE:NIFTYENERGY-INDEX",
            "^CNXREALTY": "NSE:NIFTYREALTY-INDEX",
            "NIFTYREALTY": "NSE:NIFTYREALTY-INDEX",
            "NIFTYREALTY.NS": "NSE:NIFTYREALTY-INDEX",
            "^CNXMETAL": "NSE:NIFTYMETAL-INDEX",
            "NIFTYMETAL": "NSE:NIFTYMETAL-INDEX",
            "NIFTYMETAL.NS": "NSE:NIFTYMETAL-INDEX",
            "^CNXFMCG": "NSE:NIFTYFMCG-INDEX",
            "NIFTYFMCG": "NSE:NIFTYFMCG-INDEX",
            "NIFTYFMCG.NS": "NSE:NIFTYFMCG-INDEX",
            "^CNXPHARMA": "NSE:NIFTYPHARMA-INDEX",
            "NIFTYPHARMA": "NSE:NIFTYPHARMA-INDEX",
            "NIFTYPHARMA.NS": "NSE:NIFTYPHARMA-INDEX",
            "^NSEMDCP50": "NSE:NIFTYMIDCAP50-INDEX",
            "NIFTYMIDCAP50": "NSE:NIFTYMIDCAP50-INDEX",
            "NIFTYMIDCAP50.NS": "NSE:NIFTYMIDCAP50-INDEX",
            "SENSEX.BO": "BSE:SENSEX-INDEX",
            "SENSEX": "BSE:SENSEX-INDEX",
            "^BSESN": "BSE:SENSEX-INDEX",
            "INDIAVIX": "NSE:INDIAVIX-INDEX",
            "^INDIAVIX": "NSE:INDIAVIX-INDEX"
        }
        if symbol in index_map:
            return index_map[symbol]
            
        # Standard Equity translation
        # .BO suffix means the stock is BSE-listed; route to BSE exchange
        base_symbol = symbol.replace(".NS", "").replace(".BO", "").replace("^", "").strip().upper()
        exchange = "BSE" if symbol.endswith(".BO") else "NSE"
        return f"{exchange}:{base_symbol}-EQ"

    @staticmethod
    def _normalise_yf_symbol(symbol: str) -> str:
        """Convert any symbol (e.g. NSE:RELIANCE-EQ, NSE:NIFTY50-INDEX, RELIANCE.NS, ^NSEI) to yfinance format."""
        s = symbol.strip().upper()
        fyers_to_yf = {
            "NSE:NIFTY50-INDEX": "^NSEI",
            "BSE:SENSEX-INDEX": "^BSESN",
            "NSE:NIFTYBANK-INDEX": "^NSEBANK",
            "NSE:BANKNIFTY-INDEX": "^NSEBANK",
            "NSE:NIFTYIT-INDEX": "^CNXIT",
            "NSE:NIFTYAUTO-INDEX": "^CNXAUTO",
            "NSE:NIFTYENERGY-INDEX": "^CNXENERGY",
            "NSE:NIFTYREALTY-INDEX": "^CNXREALTY",
            "NSE:NIFTYMETAL-INDEX": "^CNXMETAL",
            "NSE:NIFTYFMCG-INDEX": "^CNXFMCG",
            "NSE:NIFTYPHARMA-INDEX": "^CNXPHARMA",
            "NSE:NIFTYMIDCAP50-INDEX": "^NSEMDCP50",
            "NSE:INDIAVIX-INDEX": "^INDIAVIX",
        }
        if s in fyers_to_yf:
            return fyers_to_yf[s]
        if s.startswith("^"):
            return s
        clean = s.replace("NSE:", "").replace("BSE:", "").replace("-EQ", "").replace("-INDEX", "").replace(".BO", "").replace(".NS", "").strip()
        if s.startswith("BSE:") or s.endswith(".BO"):
            return f"{clean}.BO"
        return f"{clean}.NS"

    _env_cache = None
    _env_mtime = 0
    _fyers_cooldown_until: float = 0.0
    _fyers_token_valid: bool = True
    _fyers_token_error_reason: str = ""
    _active_engine: str = "PRIMARY_FYERS"  # "PRIMARY_FYERS" or "BACKUP_YAHOO"
    _last_fyers_tick_time: float = 0.0
    _last_yahoo_tick_time: float = 0.0
    _fyers_request_timestamps: list = []

    @classmethod
    def _check_and_record_fyers_rate_budget(cls) -> bool:
        """
        Enforces Fyers Standard API Plan limits:
        - Max 50 requests/min (safety cap at 40 requests/min)
        - Max 5 requests/sec (safety cap at 4 requests/sec)
        Returns True if within budget, False if budget exhausted (route to backup).
        """
        import time
        now = time.time()
        # Keep only timestamps within last 60 seconds
        cls._fyers_request_timestamps = [t for t in cls._fyers_request_timestamps if now - t < 60.0]
        
        # Check 1-second burst:
        burst_count = sum(1 for t in cls._fyers_request_timestamps if now - t < 1.0)
        if burst_count >= 4:
            return False
            
        # Check 60-second limit:
        if len(cls._fyers_request_timestamps) >= 40:
            return False
            
        cls._fyers_request_timestamps.append(now)
        return True

    @classmethod
    def get_feed_status(cls) -> dict:
        """Returns the current state of the dual-connection market data engine."""
        import time
        now = time.time()
        is_fyers_available = cls._fyers_token_valid and (now >= cls._fyers_cooldown_until)
        is_rate_limited = cls._fyers_token_valid and (now < cls._fyers_cooldown_until)
        current_engine = "PRIMARY_FYERS" if is_fyers_available else "BACKUP_YAHOO"
        cooldown_remaining = max(0, int(cls._fyers_cooldown_until - now))

        source_label = "Fyers API (Real-time Push)"
        if current_engine != "PRIMARY_FYERS":
            if is_rate_limited:
                source_label = f"Yahoo Finance (Throttled: Resuming Fyers in {cooldown_remaining}s)"
            else:
                source_label = "Yahoo Finance (Autonomous 3s Live Backup)"

        return {
            "active_engine": current_engine,
            "fyers_valid": cls._fyers_token_valid,
            "fyers_status": "RATE_LIMITED" if is_rate_limited else ("ACTIVE" if cls._fyers_token_valid else "EXPIRED"),
            "fyers_cooldown_remaining": cooldown_remaining,
            "fyers_token_error": cls._fyers_token_error_reason,
            "fyers_expiry_schedule": "06:00 AM IST Daily",
            "source_label": source_label,
            "dual_connection_active": True,
        }

    @classmethod
    def mark_fyers_token_expired(cls, reason: str = "Token expired or invalid", cooldown_seconds: float = 300.0) -> None:
        """Flags Fyers as expired and engages the autonomous Yahoo backup engine."""
        import time
        cls._fyers_token_valid = False
        cls._fyers_token_error_reason = reason
        cls._active_engine = "BACKUP_YAHOO"
        cls._fyers_cooldown_until = time.time() + cooldown_seconds
        logger.warning(f"Dual-Engine Failover Engaged: Fyers marked expired ({reason}). Active feed switched to Yahoo Finance Backup.")

    @classmethod
    def record_fyers_rate_limit(cls, reason: str = "Rate limit reached", cooldown_seconds: float = 30.0) -> None:
        """Throttles Fyers temporarily WITHOUT marking the token expired."""
        import time
        cls._fyers_cooldown_until = max(cls._fyers_cooldown_until, time.time() + cooldown_seconds)
        cls._fyers_token_error_reason = reason
        logger.warning(f"Dual-Engine: Fyers rate-limited ({reason}). Temporarily diverting to Yahoo Finance backup for {cooldown_seconds}s. Token remains VALID.")

    @classmethod
    def reset_fyers_health(cls) -> None:
        """Restores Fyers as the active primary engine upon token renewal."""
        cls._fyers_token_valid = True
        cls._fyers_token_error_reason = ""
        cls._fyers_cooldown_until = 0.0
        cls._fyers_request_timestamps.clear()
        cls._env_mtime = 0.0
        cls._active_engine = "PRIMARY_FYERS"
        logger.info("Dual-Engine: Fyers token refreshed. Hot-swapping back to Primary Fyers Engine.")


    @staticmethod
    async def _get_fyers_client():
        import os
        from dotenv import dotenv_values
        from backend.core.database import AsyncSessionLocal
        from backend.models.settings import SystemSettings
        from sqlalchemy import select
        
        client_id = settings.FYERS_CLIENT_ID
        access_token = settings.FYERS_ACCESS_TOKEN

        try:
            from backend.core.cache import cache_get, cache_set
            
            # Priority 1: Check PostgreSQL SystemSettings (authoritative user configuration)
            async with AsyncSessionLocal() as db:
                fyers_client_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_client_id"))).scalar_one_or_none()
                fyers_token_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_access_token"))).scalar_one_or_none()
                
                if fyers_client_obj and fyers_client_obj.value and len(fyers_client_obj.value.strip()) > 3:
                    client_id = fyers_client_obj.value.strip()
                if fyers_token_obj and fyers_token_obj.value and len(fyers_token_obj.value.strip()) > 10:
                    access_token = fyers_token_obj.value.strip()
                    
            # Priority 2: Check Redis Cache ('fyers_creds') if DB did not provide credentials
            if not access_token or not client_id:
                cached_creds = await cache_get("fyers_creds")
                if cached_creds:
                    if not client_id and cached_creds.get("client_id"):
                        client_id = cached_creds["client_id"]
                    if not access_token and cached_creds.get("access_token"):
                        access_token = cached_creds["access_token"]
            elif client_id and access_token:
                await cache_set("fyers_creds", {"client_id": client_id, "access_token": access_token}, ttl=300)
        except Exception:
            pass
        
        # Dynamically read latest values from mounted /app/.env if available
        env_paths = [
            "/app/.env",
            os.path.join(os.getcwd(), ".env"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        ]
        
        found_path = None
        for path in env_paths:
            if os.path.exists(path):
                found_path = path
                break
                
        if found_path:
            try:
                mtime = os.path.getmtime(found_path)
                if mtime > MarketDataService._env_mtime:
                    MarketDataService._env_cache = dotenv_values(found_path)
                    MarketDataService._env_mtime = mtime
                
                if MarketDataService._env_cache:
                    if MarketDataService._env_cache.get("FYERS_CLIENT_ID"):
                        client_id = MarketDataService._env_cache["FYERS_CLIENT_ID"]
                    if MarketDataService._env_cache.get("FYERS_ACCESS_TOKEN") and not access_token:
                        access_token = MarketDataService._env_cache["FYERS_ACCESS_TOKEN"]
            except Exception:
                pass
        
        if client_id:
            client_id = str(client_id).strip()
        if access_token:
            access_token = str(access_token).strip()

        if not client_id or not access_token:
            raise ValueError("Fyers API credentials are not fully configured in .env")
            
        return fyersModel.FyersModel(
            client_id=client_id,
            is_async=False,
            token=access_token,
            log_path=""
        )

    @staticmethod
    def _parse_yahoo_chart_meta(meta: dict, sym: str) -> dict | None:
        """
        Robustly parses metadata from Yahoo Chart API into an exact standardized quote dictionary.
        Prioritizes real session change and change percent, correctly deriving previous close
        instead of confusing multi-day range boundary close with yesterday's close.
        """
        last_price = meta.get("regularMarketPrice")
        if last_price is None:
            last_price = meta.get("fulldayPrice")
        if last_price is None:
            last_price = meta.get("chartPreviousClose")
        if not last_price or float(last_price) <= 0:
            return None

        last_price = float(last_price)

        # 1. Extract change and change percentage with exact priority
        raw_change = meta.get("regularMarketChange")
        if raw_change is None:
            raw_change = meta.get("fulldayChange")

        raw_change_pct = meta.get("regularMarketChangePercent")
        if raw_change_pct is None:
            raw_change_pct = meta.get("fulldayChangePercent")

        # 2. Extract previous close
        raw_prev_close = meta.get("regularMarketPreviousClose") or meta.get("previousClose")
        if raw_prev_close is not None and float(raw_prev_close) > 0:
            prev_close = float(raw_prev_close)
        elif raw_change is not None:
            prev_close = last_price - float(raw_change)
        elif raw_change_pct is not None and float(raw_change_pct) != -100.0:
            prev_close = last_price / (1.0 + (float(raw_change_pct) / 100.0))
        else:
            prev_close = float(meta.get("chartPreviousClose") or last_price)

        # 3. Derive missing change / change_pct mathematically
        if raw_change is not None:
            calc_change = float(raw_change)
        else:
            calc_change = last_price - prev_close

        if raw_change_pct is not None:
            calc_change_pct = float(raw_change_pct)
        else:
            calc_change_pct = (calc_change / prev_close) * 100.0 if prev_close > 0 else 0.0

        return {
            "symbol": sym,
            "price": round(last_price, 2),
            "previous_close": round(prev_close, 2),
            "change": round(calc_change, 2),
            "change_pct": round(calc_change_pct, 2),
            "volume": int(meta.get("regularMarketVolume") or 0),
            "market_cap": 0,
            "52w_high": round(float(meta.get("fiftyTwoWeekHigh") or 0.0), 2),
            "52w_low": round(float(meta.get("fiftyTwoWeekLow") or 0.0), 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_status": "delayed",
            "source": "Backup (Yahoo Chart API)",
        }

    @staticmethod
    async def get_quote(symbol: str) -> Optional[dict]:
        """Alias for fetch_quote for backward compatibility and test validation."""
        return await MarketDataService.fetch_quote(symbol)

    @staticmethod
    async def fetch_quote(symbol: str) -> Optional[dict]:
        """Fetch live quote with caching via Fyers."""
        import time
        now = time.time()
        original_symbol = symbol
        fyers_symbol = MarketDataService._normalise_symbol(symbol)
        clean_symbol = original_symbol.replace(".NS", "").replace(".BO", "").replace("^", "").strip().upper()
        cache_key = f"quote:{original_symbol}"
        
        # 1. Check multi-alias cache (target symbol, clean symbol, or fyers symbol)
        cached = await cache_get(cache_key) or await cache_get(f"quote:{fyers_symbol}") or await cache_get(f"quote:{clean_symbol}")
        if cached and cached.get("price", 0) > 0:
            logger.debug(f"Quote cache hit: {original_symbol}")
            # Ensure background WebSocket subscription is active for live ticks
            try:
                from backend.services.fyers_stream import fyers_stream_service
                if fyers_stream_service.is_connected:
                    asyncio.create_task(fyers_stream_service.subscribe_symbols([fyers_symbol]))
            except Exception:
                pass
            return cached

        # Auto-subscribe to Fyers WebSocket push stream so exchange ticks flow immediately
        try:
            from backend.services.fyers_stream import fyers_stream_service
            if fyers_stream_service.is_connected:
                asyncio.create_task(fyers_stream_service.subscribe_symbols([fyers_symbol]))
        except Exception:
            pass

        if MarketDataService._fyers_token_valid and now >= MarketDataService._fyers_cooldown_until and MarketDataService._check_and_record_fyers_rate_budget():
            try:
                fyers = await MarketDataService._get_fyers_client()
                data = {"symbols": fyers_symbol}
                
                response = await asyncio.to_thread(fyers.quotes, data)
                if response.get("s") == "ok" and response.get("d"):
                    quote_data = response["d"][0]["v"]
                    
                    last_price = float(quote_data.get("lp", 0.0) or 0.0)
                    calc_change = float(quote_data.get("ch", 0.0) or 0.0)
                    calc_change_pct = float(quote_data.get("chp", 0.0) or 0.0)
                    prev_close = float(quote_data.get("prev_close_price", 0.0) or 0.0)
                    
                    # If prev_close is rolled over to last_price or 0 after hours, derive from last_price - calc_change
                    if calc_change != 0.0 and (prev_close <= 0.0 or abs(prev_close - last_price) < 1e-4):
                        prev_close = last_price - calc_change
                    elif prev_close <= 0.0:
                        prev_close = last_price

                    if calc_change == 0.0 and calc_change_pct != 0.0 and prev_close > 0.0:
                        calc_change = last_price - prev_close
                    elif calc_change_pct == 0.0 and calc_change != 0.0 and prev_close > 0.0:
                        calc_change_pct = (calc_change / prev_close) * 100.0
                    
                    quote = {
                        "symbol": original_symbol,
                        "price": round(last_price, 2),
                        "previous_close": round(prev_close, 2),
                        "change": round(calc_change, 2),
                        "change_pct": round(calc_change_pct, 2),
                        "volume": int(quote_data.get("volume", 0)),
                        "market_cap": 0,
                        "52w_high": 0.0,
                        "52w_low": 0.0,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data_status": "realtime",
                        "source": "Fyers API",
                    }

                    if float(last_price) > 0:
                        MarketDataService._last_fyers_tick_time = now
                        await cache_set(cache_key, quote, ttl=settings.CACHE_TTL_QUOTE)
                        return quote
                    elif fyers_symbol.startswith("BSE:"):
                        return await MarketDataService.fetch_quote(original_symbol.replace(".BO", ".NS"))
                    else:
                        logger.warning(f"Fyers returned zero price for {fyers_symbol}, falling through to backup")
                elif response.get("code") in (429, -360):
                    MarketDataService._fyers_cooldown_until = now + 30.0
                    logger.warning(f"Fyers rate limit ({response.get('code')}) hit in single quote. Entering 30s cooldown (token remains valid).")
                elif fyers_symbol.startswith("BSE:"):
                    return await MarketDataService.fetch_quote(original_symbol.replace(".BO", ".NS"))
                else:
                    err_msg = str(response)
                    resp_code = response.get("code")
                    if resp_code in (-15, -16, -17, 401, 403) or ("token" in err_msg.lower() and ("expire" in err_msg.lower() or "invalid" in err_msg.lower())):
                        MarketDataService.mark_fyers_token_expired(f"Token expired/rejected (code {resp_code})", cooldown_seconds=300.0)
                    elif resp_code == -300:
                        logger.warning(f"Fyers reported invalid symbol for {fyers_symbol}: {response}")
                    elif resp_code == -360 or "429" in err_msg or "rate limit" in err_msg.lower() or "1015" in err_msg or "plan limit" in err_msg.lower():
                        MarketDataService._fyers_cooldown_until = now + 30.0
                        logger.warning("Fyers rate limit (-360/429) hit in single quote. Entering 30s cooldown (token remains valid).")
                    logger.warning(f"Fyers quote returned non-ok for {fyers_symbol}: {response}")

            except Exception as e:
                err_str = str(e).lower()
                if "-360" in err_str or "429" in err_str or "rate limit" in err_str or "1015" in err_str or "plan limit" in err_str:
                    MarketDataService._fyers_cooldown_until = now + 30.0
                    logger.warning("Fyers rate limit exception in single quote. Entering 30s cooldown (token remains valid).")
                elif "-15" in err_str or "-16" in err_str or "-17" in err_str or ("token" in err_str and ("expire" in err_str or "invalid" in err_str)):
                    MarketDataService.mark_fyers_token_expired(f"Fyers auth exception: {e}", cooldown_seconds=300.0)
                logger.error(f"Failed to fetch Fyers quote for {original_symbol}: {e}")
        else:
            remaining = int(MarketDataService._fyers_cooldown_until - now)
            logger.debug(f"Fyers cooldown active ({remaining}s remaining), skipping Fyers single quote")

        # Secondary fallback via yfinance ticker history (supports test mocks)
        try:
            import yfinance as yf
            import requests
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            clean_sym = original_symbol.replace(".BO", "").replace(".NS", "").replace("^", "").strip().upper()
            if original_symbol.startswith("^"):
                yf_sym = original_symbol
            elif original_symbol.endswith(".BO"):
                yf_sym = f"{clean_sym}.BO"
            else:
                yf_sym = f"{clean_sym}.NS"
            ticker = yf.Ticker(yf_sym, session=session)
            hist = await asyncio.to_thread(ticker.history, period="5d")
            if not hist.empty:
                last_price = float(hist["Close"].iloc[-1])
                prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last_price
                change = last_price - prev_close
                change_pct = (change / prev_close) * 100 if prev_close else 0.0
                fallback_quote = {
                    "symbol": original_symbol,
                    "price": round(last_price, 2),
                    "previous_close": round(prev_close, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "volume": int(hist["Volume"].iloc[-1]) if "Volume" in hist and not hist["Volume"].empty else 0,
                    "market_cap": 0,
                    "52w_high": 0.0,
                    "52w_low": 0.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data_status": "delayed",
                    "source": "Backup",
                }
                await cache_set(cache_key, fallback_quote, ttl=settings.CACHE_TTL_QUOTE)
                return fallback_quote
        except Exception:
            pass

        # Tertiary fallback via direct Yahoo Chart API (resilient against crumb & 429 errors)
        try:
            import httpx
            clean_sym = original_symbol.replace(".BO", "").replace(".NS", "").replace("^", "").strip().upper()
            if original_symbol.startswith("^"):
                yf_sym = original_symbol
            elif original_symbol.endswith(".BO"):
                yf_sym = f"{clean_sym}.BO"
            else:
                yf_sym = f"{clean_sym}.NS"

            chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?interval=1d&range=5d"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            async with httpx.AsyncClient(headers=headers, timeout=5.0) as client:
                resp = await client.get(chart_url)
                if resp.status_code == 200:
                    cdata = resp.json()
                    res_list = cdata.get("chart", {}).get("result", [])
                    if res_list:
                        meta = res_list[0].get("meta", {})
                        fallback_quote = MarketDataService._parse_yahoo_chart_meta(meta, original_symbol)
                        if fallback_quote:
                            await cache_set(cache_key, fallback_quote, ttl=settings.CACHE_TTL_QUOTE)
                            return fallback_quote
        except Exception as e:
            logger.debug(f"Direct chart API quote fallback failed for {original_symbol}: {e}")

        return None

    @staticmethod
    async def fetch_quotes_bulk(symbols: list[str], use_fallback: bool = True) -> dict[str, dict]:
        """
        Fetch real-time quotes for multiple symbols in a single sub-100ms request via Fyers.
        """
        if not symbols:
            return {}

        import time
        now = time.time()

        quotes_dict = {}
        missing_symbols = []
        for s in symbols:
            try:
                cached = await cache_get(f"quote:{s}")
                if cached and cached.get("price", 0) > 0:
                    quotes_dict[s] = cached
                else:
                    missing_symbols.append(s)
            except Exception:
                missing_symbols.append(s)

        # If all symbols are already fresh in cache (from WebSocket push ticks or recent reads), return immediately!
        if not missing_symbols:
            return quotes_dict

        # Auto-subscribe missing symbols to Fyers WebSocket push stream
        try:
            from backend.services.fyers_stream import fyers_stream_service
            if fyers_stream_service.is_connected and missing_symbols:
                asyncio.create_task(fyers_stream_service.subscribe_symbols([MarketDataService._normalise_symbol(s) for s in missing_symbols]))
        except Exception:
            pass

        fyers_to_orig: dict[str, list[str]] = {}
        for s in missing_symbols:
            norm = MarketDataService._normalise_symbol(s)
            fyers_to_orig.setdefault(norm, []).append(s)
            # In Fyers, BSE cash equities (e.g. BSE:PCJEWELLER-EQ) error with -300 invalid symbol.
            # Add the liquid NSE equivalent (NSE:PCJEWELLER-EQ) so Fyers returns real-time quotes.
            if norm.startswith("BSE:") and not norm.endswith("-INDEX"):
                nse_norm = norm.replace("BSE:", "NSE:")
                fyers_to_orig.setdefault(nse_norm, []).append(s)

        fyers_keys = list(fyers_to_orig.keys())
        
        if MarketDataService._fyers_token_valid and now >= MarketDataService._fyers_cooldown_until and MarketDataService._check_and_record_fyers_rate_budget():
            try:
                fyers = await MarketDataService._get_fyers_client()
                # Fyers quotes API accepts maximum 50 symbols per request
                for i in range(0, len(fyers_keys), 50):
                    chunk_keys = fyers_keys[i : i + 50]
                    fyers_symbols_str = ",".join(chunk_keys)
                    data = {"symbols": fyers_symbols_str}
                    response = await asyncio.to_thread(fyers.quotes, data)
                    
                    if response.get("s") == "ok" and "d" in response:
                        MarketDataService._last_fyers_tick_time = now
                        for item in response["d"]:
                            fyers_sym = item.get("n", "")
                            quote_data = item.get("v", {})
                            orig_symbols = fyers_to_orig.get(fyers_sym, [fyers_sym])
                            
                            last_price = float(quote_data.get("lp", 0.0) or 0.0)
                            calc_change = float(quote_data.get("ch", 0.0) or 0.0)
                            calc_change_pct = float(quote_data.get("chp", 0.0) or 0.0)
                            prev_close = float(quote_data.get("prev_close_price", 0.0) or 0.0)
                            
                            if calc_change != 0.0 and (prev_close <= 0.0 or abs(prev_close - last_price) < 1e-4):
                                prev_close = last_price - calc_change
                            elif prev_close <= 0.0:
                                prev_close = last_price

                            if calc_change == 0.0 and calc_change_pct != 0.0 and prev_close > 0.0:
                                calc_change = last_price - prev_close
                            elif calc_change_pct == 0.0 and calc_change != 0.0 and prev_close > 0.0:
                                calc_change_pct = (calc_change / prev_close) * 100.0
                            
                            if last_price > 0:
                                for orig_sym in orig_symbols:
                                    q_obj = {
                                        "symbol": orig_sym,
                                        "price": round(last_price, 2),
                                        "previous_close": round(prev_close, 2),
                                        "change": round(calc_change, 2),
                                        "change_pct": round(calc_change_pct, 2),
                                        "volume": int(quote_data.get("volume", 0)),
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                        "data_status": "realtime",
                                        "source": "Fyers API",
                                    }
                                    quotes_dict[orig_sym] = q_obj
                                    try:
                                        await cache_set(f"quote:{orig_sym}", q_obj, ttl=settings.CACHE_TTL_QUOTE)
                                    except Exception:
                                        pass
                    elif response.get("code") in (429, -360):
                        MarketDataService._fyers_cooldown_until = now + 30.0
                        logger.warning(f"Fyers rate limit ({response.get('code')}) hit in bulk quotes. Entering 30s cooldown (token remains valid).")
                        break
                    else:
                        err_msg = str(response)
                        resp_code = response.get("code")
                        if resp_code in (-15, -16, -17, 401, 403) or ("token" in err_msg.lower() and ("expire" in err_msg.lower() or "invalid" in err_msg.lower())):
                            MarketDataService.mark_fyers_token_expired(f"Bulk quote token error (code {resp_code})", cooldown_seconds=300.0)
                            break
                        elif resp_code == -300:
                            logger.warning(f"Fyers reported invalid symbol parameter in chunk: {chunk_keys[:5]}")
                        elif resp_code == -360 or "429" in err_msg or "rate limit" in err_msg.lower() or "1015" in err_msg or "plan limit" in err_msg.lower():
                            MarketDataService._fyers_cooldown_until = now + 30.0
                            logger.warning("Fyers rate limit (-360/429) detected in bulk quotes. Entering 30s cooldown (token remains valid).")
                            break
                        logger.error(f"Fyers bulk quote returned non-ok: {response}")
            except Exception as e:
                err_str = str(e).lower()
                if "-360" in err_str or "429" in err_str or "rate limit" in err_str or "1015" in err_str or "plan limit" in err_str:
                    MarketDataService._fyers_cooldown_until = now + 30.0
                    logger.warning("Fyers rate limit exception in bulk quotes. Entering 30s cooldown (token remains valid).")
                elif "-15" in err_str or "-16" in err_str or "-17" in err_str or ("token" in err_str and ("expire" in err_str or "invalid" in err_str)):
                    MarketDataService.mark_fyers_token_expired(f"Bulk quote auth exception: {e}", cooldown_seconds=300.0)
                logger.error(f"Fyers bulk quote failed: {e}")
        else:
            remaining = int(MarketDataService._fyers_cooldown_until - now)
            logger.debug(f"Fyers cooldown active ({remaining}s remaining), skipping Fyers bulk quote")

        # Automatically fill any missing symbols via fast concurrent fallback
        missing_symbols = [s for s in symbols if s not in quotes_dict or quotes_dict[s].get("price", 0) <= 0]
        if missing_symbols and use_fallback:
            import httpx

            async def _fetch_single_chart_quote(client: httpx.AsyncClient, sym: str):
                clean = sym.replace(".BO", "").replace(".NS", "").replace("^", "").strip().upper()
                if sym.startswith("^"):
                    yf_sym = sym
                elif sym.endswith(".BO"):
                    yf_sym = f"{clean}.BO"
                else:
                    yf_sym = f"{clean}.NS"

                chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?interval=1d&range=5d"
                try:
                    resp = await client.get(chart_url)
                    if resp.status_code == 200:
                        cdata = resp.json()
                        res_list = cdata.get("chart", {}).get("result", [])
                        if res_list:
                            meta = res_list[0].get("meta", {})
                            quote_dict = MarketDataService._parse_yahoo_chart_meta(meta, sym)
                            if quote_dict:
                                return sym, quote_dict
                except Exception as ex:
                    logger.debug(f"Direct chart fetch failed for {sym}: {ex}")
                return sym, None

            # 1. Primary fallback: Concurrent direct Yahoo Chart queries (fast, no crumb/cookie blocks)
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                async with httpx.AsyncClient(headers=headers, timeout=6.0) as client:
                    tasks = [_fetch_single_chart_quote(client, s) for s in missing_symbols]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for res in results:
                        if isinstance(res, tuple) and res[1] is not None:
                            sym, quote_data = res
                            quotes_dict[sym] = quote_data
                            MarketDataService._last_yahoo_tick_time = now
                            try:
                                await cache_set(f"quote:{sym}", quote_data, ttl=settings.CACHE_TTL_QUOTE)
                            except Exception:
                                pass
            except Exception as e:
                logger.debug(f"Direct Yahoo Chart bulk fallback failed: {e}")

            # 2. Secondary fallback: yfinance batch download (for mocked test suites)
            still_missing = [s for s in symbols if s not in quotes_dict or quotes_dict[s].get("price", 0) <= 0]
            if still_missing:
                try:
                    import yfinance as yf
                    import requests
                    yf_map = {}
                    for s in still_missing:
                        clean = s.replace(".BO", "").replace(".NS", "").replace("^", "").strip().upper()
                        if s.startswith("^"):
                            yf_sym = s
                        elif s.endswith(".BO"):
                            yf_sym = f"{clean}.BO"
                        else:
                            yf_sym = f"{clean}.NS"
                        yf_map[yf_sym] = s

                    def _batch_yf():
                        session = requests.Session()
                        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                        tickers = " ".join(yf_map.keys())
                        return yf.download(tickers, period="5d", interval="1d", progress=False, group_by="ticker", session=session)

                    df = await asyncio.wait_for(asyncio.to_thread(_batch_yf), timeout=6.0)
                    if df is not None and not df.empty:
                        for yf_sym, orig_sym in yf_map.items():
                            try:
                                if yf_sym in df:
                                    ticker_df = df[yf_sym]
                                elif "Close" in df and not isinstance(df["Close"], pd.DataFrame):
                                    ticker_df = df
                                elif "Close" in df and isinstance(df["Close"], pd.DataFrame) and yf_sym in df["Close"]:
                                    ticker_df = pd.DataFrame({
                                        "Close": df["Close"][yf_sym],
                                        "Volume": df["Volume"][yf_sym] if "Volume" in df and yf_sym in df["Volume"] else 0
                                    })
                                else:
                                    continue

                                if "Close" in ticker_df:
                                    series = ticker_df["Close"].dropna()
                                    if not series.empty:
                                        last_price = float(series.iloc[-1])
                                        prev_close = float(series.iloc[-2]) if len(series) > 1 else last_price
                                        ch = last_price - prev_close
                                        chp = (ch / prev_close) * 100 if prev_close else 0.0
                                        vol = 0
                                        if "Volume" in ticker_df and not ticker_df["Volume"].dropna().empty:
                                            vol = int(ticker_df["Volume"].dropna().iloc[-1])
                                        q = {
                                            "symbol": orig_sym,
                                            "price": round(last_price, 2),
                                            "previous_close": round(prev_close, 2),
                                            "change": round(ch, 2),
                                            "change_pct": round(chp, 2),
                                            "volume": vol,
                                            "timestamp": datetime.now(timezone.utc).isoformat(),
                                            "data_status": "delayed",
                                            "source": "Backup",
                                        }
                                        quotes_dict[orig_sym] = q
                                        try:
                                            await cache_set(f"quote:{orig_sym}", q, ttl=settings.CACHE_TTL_QUOTE)
                                        except Exception:
                                            pass
                            except Exception:
                                pass
                except Exception as ex:
                    logger.debug(f"Batch yf fallback skipped: {ex}")

            # 3. Tertiary fallback: Check Redis quote cache for last-known valid prices
            still_missing_after_yf = [s for s in symbols if s not in quotes_dict or quotes_dict[s].get("price", 0) <= 0]
            for s in still_missing_after_yf:
                try:
                    cached_q = await cache_get(f"quote:{s}")
                    if cached_q and cached_q.get("price", 0) > 0:
                        quotes_dict[s] = cached_q
                except Exception:
                    pass

        return quotes_dict

    @staticmethod
    async def fetch_candles(
        symbol: str,
        timeframe: str = "1d",
        limit: int = 200,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch OHLCV candles from Fyers API.
        Includes automatic pagination to bypass Fyers' maximum days constraint for deep historical ML training.
        """
        if timeframe not in VALID_TIMEFRAMES:
            raise ValueError(f"Invalid timeframe '{timeframe}'. Valid: {VALID_TIMEFRAMES}")

        original_symbol = symbol
        fyers_symbol = MarketDataService._normalise_symbol(symbol)        
        cache_key = f"candles:{original_symbol}:{timeframe}:{limit}:{start_date}:{end_date}"
        cached = await cache_get(cache_key)
        if cached:
            logger.debug(f"Candle cache hit: {original_symbol} {timeframe}")
            return cached

        fyers_interval = FYERS_INTERVAL_MAP[timeframe]

        import time
        now = time.time()

        try:
            if MarketDataService._fyers_token_valid and now >= MarketDataService._fyers_cooldown_until and MarketDataService._check_and_record_fyers_rate_budget():
                fyers = await MarketDataService._get_fyers_client()
                all_candles = []
                
                # 1. Determine the global start and end timestamps
                if start_date and end_date:
                    dt_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    dt_end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                else:
                    dt_end = datetime.now(timezone.utc)
                    if limit and limit < 300:
                        # Proportional fast single-query range for real-time indicators & scanner
                        if timeframe in ["1d", "1w", "1mo"]:
                            mult = 7.0 if timeframe == "1w" else (30.0 if timeframe == "1mo" else 1.8)
                            dt_start = dt_end - timedelta(days=int(limit * mult) + 30)
                        elif timeframe in ["1h", "30m", "15m", "5m"]:
                            dt_start = dt_end - timedelta(days=min(limit, 30))
                        elif timeframe == "1m":
                            dt_start = dt_end - timedelta(days=min(limit, 10))
                    else:
                        # Deep historical coverage for ML training and extensive backtesting
                        if timeframe in ["1d", "1w", "1mo"]:
                            dt_start = datetime(2015, 1, 1, tzinfo=timezone.utc)
                        elif timeframe in ["1h", "30m", "15m", "5m"]:
                            dt_start = dt_end - timedelta(days=100)
                        elif timeframe == "1m":
                            dt_start = dt_end - timedelta(days=60)
                    
                # 2. Backward Pagination Loop (Fyers max range is 100 days for intraday, 365 days for daily)
                # Paginating backwards ensures the most recent market candles (today/yesterday)
                # are retrieved FIRST so any pagination cutoff never leaves candles stuck in old years.
                max_days_per_request = 365 if timeframe in ["1d", "1w", "1mo"] else 100
                
                chunk_end = dt_end
                while chunk_end > dt_start:
                    chunk_start = max(chunk_end - timedelta(days=max_days_per_request), dt_start)
                    
                    data = {
                        "symbol": fyers_symbol,
                        "resolution": fyers_interval,
                        "date_format": "1",
                        "range_from": chunk_start.strftime("%Y-%m-%d"),
                        "range_to": chunk_end.strftime("%Y-%m-%d"),
                        "cont_flag": "1" # Continuous data for futures/indices
                    }
                    
                    max_retries = 2
                    for attempt in range(max_retries):
                        response = await asyncio.to_thread(fyers.history, data)
                        if response.get("s") == "ok":
                            break
                        
                        # If authentication fails (-16), rate limited (429/-360), symbol is invalid (-300), or no data exists (pre-IPO), skip immediately without retry delay
                        if response.get("code") in (-360, 429):
                            MarketDataService.record_fyers_rate_limit("Fyers history rate limited", cooldown_seconds=30.0)
                            break
                        if response.get("code") in [-16, -300] or response.get("s") in ["no_data", "error"]:
                            break
                            
                        logger.warning(f"Fyers history failed for {fyers_symbol} ({chunk_start.date()} to {chunk_end.date()}): {response}. Attempt {attempt + 1}/{max_retries}")
                        await asyncio.sleep(1.0)
                    else:
                        break
                        
                    if "candles" in response and response["candles"]:
                        all_candles.extend(response["candles"])
                    elif not all_candles:
                        # If the most recent chunk had no data or failed, stop
                        break
                        
                    chunk_end = chunk_start - timedelta(days=1)
                    
                    # Sleep briefly only if paginating across multiple chunks
                    if chunk_end > dt_start:
                        await asyncio.sleep(0.35)
                    
                if all_candles:
                    # Fyers candle format: [Epoch, Open, High, Low, Close, Volume]
                    formatted_candles = []
                    seen_ts = set()
                    for c in all_candles:
                        if c[0] in seen_ts:
                            continue
                        seen_ts.add(c[0])
                        ts_dt = datetime.fromtimestamp(c[0], timezone.utc)
                        formatted_candles.append({
                            "timestamp": ts_dt.isoformat(),
                            "open": float(c[1]),
                            "high": float(c[2]),
                            "low": float(c[3]),
                            "close": float(c[4]),
                            "volume": int(c[5])
                        })
                        
                    # Sort chronologically and retain complete dataset
                    formatted_candles.sort(key=lambda x: x["timestamp"])

                    # Freshness Guard: If requesting live market data (no explicit historical date bounds),
                    # guarantee the most recent candle is not severely stale (>45 days old)
                    if not start_date and not end_date and formatted_candles:
                        latest_dt = datetime.fromisoformat(formatted_candles[-1]["timestamp"].replace("Z", "+00:00"))
                        if (dt_end - latest_dt).days > 45:
                            logger.warning(f"Fyers returned stale historical candles for {fyers_symbol} ending {latest_dt.date()}. Invoking fallback.")
                            raise ValueError(f"Fyers candles stale for {fyers_symbol}")

                    ttl = 86400 if (start_date and end_date) else get_dynamic_candle_ttl(timeframe)
                    await cache_set(cache_key, formatted_candles, ttl=ttl)
                    return formatted_candles
                else:
                    logger.warning(f"Empty candle data returned by Fyers for {fyers_symbol}")
                    if fyers_symbol.startswith("BSE:"):
                        # Dual-listed fallback in Fyers: try NSE
                        return await MarketDataService.fetch_candles(
                            symbol=original_symbol.replace(".BO", ".NS"),
                            timeframe=timeframe,
                            limit=limit,
                            start_date=start_date,
                            end_date=end_date,
                        )

        except Exception as e:
            logger.error(f"Failed to fetch Fyers history for {original_symbol}: {e}")

        # Secondary fallback if Fyers token is expired or temporary network error
        try:
            import yfinance as yf
            import requests
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            clean_sym = original_symbol.replace(".BO", "").replace(".NS", "").replace("^", "").strip().upper()
            if original_symbol.startswith("^"):
                yf_sym = original_symbol
            elif original_symbol.endswith(".BO"):
                yf_sym = f"{clean_sym}.BO"
            else:
                yf_sym = f"{clean_sym}.NS"
            yf_timeframe_map = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "1d": "1d", "1w": "1wk", "1mo": "1mo"}
            interval = yf_timeframe_map.get(timeframe, "1d")
            
            if timeframe in ["1d", "1w", "1mo"]:
                if limit and limit >= 300:
                    period = "10y"
                elif limit:
                    period = "2y"
                else:
                    period = "10y"
            else:
                period = "60d"
            
            ticker = yf.Ticker(yf_sym, session=session)
            df = await asyncio.to_thread(ticker.history, interval=interval, period=period, auto_adjust=True)
            if not df.empty:
                fallback_candles = []
                for ts, row in df.iterrows():
                    try:
                        c_close = float(row["Close"])
                        c_open = float(row["Open"]) if not pd.isna(row.get("Open")) else c_close
                        c_high = float(row["High"]) if not pd.isna(row.get("High")) else c_close
                        c_low = float(row["Low"]) if not pd.isna(row.get("Low")) else c_close
                        c_vol = int(row["Volume"]) if not pd.isna(row.get("Volume")) else 0
                        if math.isfinite(c_close) and c_close > 0:
                            fallback_candles.append({
                                "timestamp": ts.isoformat(),
                                "open": c_open,
                                "high": c_high,
                                "low": c_low,
                                "close": c_close,
                                "volume": c_vol,
                            })
                    except (ValueError, TypeError):
                        continue

                # Dual-listed fallback: If a .BO symbol returns fewer than 30 candles, fallback to its NSE counterpart (.NS)
                if len(fallback_candles) < 30 and original_symbol.endswith(".BO"):
                    nse_candles = await MarketDataService.fetch_candles(f"{clean_sym}.NS", timeframe, limit, start_date, end_date)
                    if len(nse_candles) > len(fallback_candles):
                        ttl = 86400 if (start_date and end_date) else get_dynamic_candle_ttl(timeframe)
                        await cache_set(cache_key, nse_candles, ttl=ttl)
                        return nse_candles

                if fallback_candles:
                    ttl = 86400 if (start_date and end_date) else get_dynamic_candle_ttl(timeframe)
                    await cache_set(cache_key, fallback_candles, ttl=ttl)
                    return fallback_candles
            elif original_symbol.endswith(".BO"):
                nse_candles = await MarketDataService.fetch_candles(f"{clean_sym}.NS", timeframe, limit, start_date, end_date)
                if nse_candles:
                    ttl = 86400 if (start_date and end_date) else get_dynamic_candle_ttl(timeframe)
                    await cache_set(cache_key, nse_candles, ttl=ttl)
                    return nse_candles
        except Exception as e:
            logger.debug(f"yfinance candle fetch failed for {original_symbol}: {e}")

        # 3. Tertiary fallback via direct Yahoo Chart API (resilient against crumb/cookie errors)
        try:
            import httpx
            clean_sym = original_symbol.replace(".BO", "").replace(".NS", "").replace("^", "").strip().upper()
            if original_symbol.startswith("^"):
                yf_sym = original_symbol
            elif original_symbol.endswith(".BO"):
                yf_sym = f"{clean_sym}.BO"
            else:
                yf_sym = f"{clean_sym}.NS"

            yf_timeframe_map = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "1d": "1d", "1w": "1wk", "1mo": "1mo"}
            interval = yf_timeframe_map.get(timeframe, "1d")
            chart_range = "1y" if interval == "1d" else ("60d" if "m" in interval or "h" in interval else "5y")

            direct_chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?interval={interval}&range={chart_range}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with httpx.AsyncClient(headers=headers, timeout=6.0) as client:
                resp = await client.get(direct_chart_url)
                if resp.status_code == 200:
                    cdata = resp.json()
                    res_list = cdata.get("chart", {}).get("result", [])
                    if res_list:
                        result0 = res_list[0]
                        timestamps = result0.get("timestamp", [])
                        quotes_arr = result0.get("indicators", {}).get("quote", [{}])[0]
                        opens = quotes_arr.get("open", [])
                        highs = quotes_arr.get("high", [])
                        lows = quotes_arr.get("low", [])
                        closes = quotes_arr.get("close", [])
                        volumes = quotes_arr.get("volume", [])

                        direct_candles = []
                        for i in range(len(timestamps)):
                            try:
                                c = closes[i] if i < len(closes) else None
                                if c is None or not math.isfinite(c) or c <= 0:
                                    continue
                                o = opens[i] if i < len(opens) and opens[i] is not None and math.isfinite(opens[i]) else c
                                h = highs[i] if i < len(highs) and highs[i] is not None and math.isfinite(highs[i]) else c
                                l = lows[i] if i < len(lows) and lows[i] is not None and math.isfinite(lows[i]) else c
                                v = volumes[i] if i < len(volumes) and volumes[i] is not None and math.isfinite(volumes[i]) else 0
                                ts_iso = datetime.fromtimestamp(timestamps[i], tz=timezone.utc).isoformat()
                                direct_candles.append({
                                    "timestamp": ts_iso,
                                    "open": round(float(o), 2),
                                    "high": round(float(h), 2),
                                    "low": round(float(l), 2),
                                    "close": round(float(c), 2),
                                    "volume": int(v),
                                })
                            except Exception:
                                continue

                        if direct_candles:
                            direct_candles.sort(key=lambda x: x["timestamp"])
                            if limit and len(direct_candles) > limit:
                                direct_candles = direct_candles[-limit:]
                            ttl = 86400 if (start_date and end_date) else get_dynamic_candle_ttl(timeframe)
                            await cache_set(cache_key, direct_candles, ttl=ttl)
                            return direct_candles
        except Exception as e:
            logger.debug(f"Direct Yahoo Chart candle fallback failed for {original_symbol}: {e}")

        return []

    @staticmethod
    async def search_stocks(query: str) -> list[dict]:
        """Search for stocks in local DB first, fallback to direct Yahoo Finance search."""
        query_clean = query.strip()
        if not query_clean:
            return []

        query_upper = query_clean.upper()
        cache_key = f"stock_search:{query_upper}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        from backend.core.database import AsyncSessionLocal
        from backend.models.stock import Stock
        from sqlalchemy import select
        import httpx
        import urllib.parse

        results: list[dict] = []
        seen_symbols: set[str] = set()

        # 1. Search local DB first
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(Stock).where(
                    (Stock.symbol.ilike(f"%{query_upper}%")) | 
                    (Stock.name.ilike(f"%{query_upper}%"))
                ).limit(10)
                local_stocks = (await db.execute(stmt)).scalars().all()
                
                for s in local_stocks:
                    clean_sym = s.symbol.replace(".NS", "")
                    if clean_sym not in seen_symbols:
                        seen_symbols.add(clean_sym)
                        results.append({
                            "symbol": clean_sym,
                            "name": s.name,
                            "exchange": s.exchange,
                            "type": "EQUITY"
                        })
                
                # If we have plentiful local matches (>= 5), return them directly
                if len(results) >= 5:
                    await cache_set(cache_key, results, ttl=1800)
                    return results
        except Exception as e:
            logger.warning(f"Local DB stock search failed for '{query}': {e}")

        # 2. Resilient Direct Yahoo Finance Search API (version-independent)
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(query_clean)}&quotesCount=10&newsCount=0"
            async with httpx.AsyncClient(headers=headers, timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    quotes = data.get("quotes", [])
                    new_stocks_to_persist = []
                    for q in quotes:
                        raw_sym = q.get("symbol", "")
                        quote_type = q.get("quoteType", "")
                        if not raw_sym or quote_type not in ["EQUITY", "ETF", "INDEX"]:
                            continue

                        exch = q.get("exchange", "")
                        if exch in ["NSI", "NSE"] or raw_sym.endswith(".NS"):
                            exchange_str = "NSE"
                            clean_sym = raw_sym.replace(".NS", "")
                            db_sym = f"{clean_sym}.NS"
                        elif exch in ["BSE", "BOM"] or raw_sym.endswith(".BO"):
                            exchange_str = "BSE"
                            clean_sym = raw_sym
                            db_sym = raw_sym
                        else:
                            exchange_str = exch or "NSE"
                            clean_sym = raw_sym.replace(".NS", "")
                            db_sym = raw_sym

                        if clean_sym in seen_symbols:
                            continue
                        seen_symbols.add(clean_sym)

                        name = q.get("shortname") or q.get("longname") or clean_sym
                        results.append({
                            "symbol": clean_sym,
                            "name": name,
                            "exchange": exchange_str,
                            "type": quote_type,
                        })
                        new_stocks_to_persist.append((db_sym, name, exchange_str))

                    # Asynchronously persist discovered stocks to DB
                    if new_stocks_to_persist:
                        async def _persist_discovered():
                            try:
                                async with AsyncSessionLocal() as db_session:
                                    for sym_val, name_val, exch_val in new_stocks_to_persist[:5]:
                                        existing = (await db_session.execute(select(Stock).where(Stock.symbol == sym_val))).scalar_one_or_none()
                                        if not existing:
                                            db_session.add(Stock(symbol=sym_val, name=name_val, exchange=exch_val, is_active=True))
                                    await db_session.commit()
                            except Exception:
                                pass
                        asyncio.create_task(_persist_discovered())

                    if results:
                        await cache_set(cache_key, results, ttl=1800)
                        return results
        except Exception as e:
            logger.warning(f"Direct Yahoo search failed for '{query}': {e}")

        # 3. Fallback to yf.Search if attribute exists (compatibility with future yfinance versions)
        if hasattr(yf, "Search"):
            try:
                search_obj = await asyncio.to_thread(yf.Search, query_clean, max_results=10)
                quotes = search_obj.quotes if hasattr(search_obj, "quotes") else []
                for q in quotes:
                    raw_sym = q.get("symbol", "")
                    if not raw_sym or q.get("quoteType") not in ["EQUITY", "ETF", "INDEX"]:
                        continue
                    clean_sym = raw_sym.replace(".NS", "")
                    if clean_sym in seen_symbols:
                        continue
                    seen_symbols.add(clean_sym)
                    results.append({
                        "symbol": clean_sym,
                        "name": q.get("shortname") or q.get("longname", clean_sym),
                        "exchange": "NSE" if raw_sym.endswith(".NS") else ("BSE" if raw_sym.endswith(".BO") else q.get("exchange", "NSE")),
                        "type": q.get("quoteType", "EQUITY"),
                    })
                if results:
                    await cache_set(cache_key, results, ttl=1800)
                    return results
            except Exception as e:
                logger.warning(f"yf.Search fallback failed for '{query}': {e}")

        # 4. Fallback curated symbols if completely offline or disconnected
        fallback_symbols = [
            {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "INFY.NS", "name": "Infosys", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "ICICIBANK.NS", "name": "ICICI Bank", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "SBIN.NS", "name": "State Bank of India", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "TATAMOTORS.NS", "name": "Tata Motors", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "GODIGIT.NS", "name": "Go Digit General Insurance", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "PCJEWELLER.NS", "name": "PC Jeweller", "exchange": "NSE", "type": "EQUITY"},
        ]
        normalized_query = query_upper.replace(".NS", "").replace("^", "").strip()
        if normalized_query:
            matches = [
                {
                    "symbol": item["symbol"].replace(".NS", ""),
                    "name": item["name"],
                    "exchange": item["exchange"],
                    "type": item["type"],
                }
                for item in fallback_symbols
                if normalized_query in item["symbol"].replace(".NS", "").upper() or normalized_query in item["name"].upper()
            ]
            if matches:
                return matches

        return results

    @staticmethod
    def _clean_num(val_str: Optional[str]) -> Optional[float]:
        """Extract clean numeric float from string with commas, currency symbols, and percentages."""
        if val_str is None or val_str == "":
            return None
        import re
        val_clean = re.sub(r"[^\d.-]", "", str(val_str))
        try:
            return float(val_clean)
        except ValueError:
            return None

    @staticmethod
    async def _fetch_screener_fundamentals(clean_sym: str) -> dict:
        """
        Scrapes authentic corporate fundamental metrics, balance sheet, and P&L ratios from Screener.in.
        Provides high-precision fundamental data for Indian equities when Yahoo Finance rate-limits requests.
        """
        import httpx
        from bs4 import BeautifulSoup

        url = f"https://www.screener.in/company/{clean_sym}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        res: dict = {}
        try:
            async with httpx.AsyncClient(headers=headers, timeout=8.0, follow_redirects=True) as client:
                r = await client.get(url)
                if r.status_code != 200:
                    return res

                soup = BeautifulSoup(r.text, "html.parser")

                # 1. Company Name & Profile
                h1 = soup.find("h1")
                if h1 and h1.text.strip():
                    res["name"] = h1.text.strip()

                about_div = soup.find("div", class_="about")
                if about_div and about_div.text.strip():
                    res["description"] = about_div.text.strip()

                peers_sec = soup.find("section", id="peers")
                if peers_sec:
                    peer_links = [a.text.strip() for a in peers_sec.find_all("a") if "/market/" in a.get("href", "")]
                    if len(peer_links) >= 1:
                        res["sector"] = peer_links[0]
                    if len(peer_links) >= 2:
                        res["industry"] = peer_links[-1]

                # 2. Top Ratios List
                ratios_map = {}
                ratios_ul = soup.find("ul", id="top-ratios")
                if ratios_ul:
                    for li in ratios_ul.find_all("li"):
                        name_elem = li.find("span", class_="name")
                        val_elem = li.find("span", class_="number")
                        if name_elem and val_elem:
                            ratios_map[name_elem.text.strip().lower()] = val_elem.text.strip()

                # 3. Balance Sheet Table
                bs_data = {}
                bs_sec = soup.find("section", id="balance-sheet")
                if bs_sec:
                    for row in bs_sec.find_all("tr"):
                        cols = [c.text.strip() for c in row.find_all(["th", "td"])]
                        if cols and len(cols) > 1:
                            row_name = cols[0].replace("\xa0+", "").replace("+", "").strip().lower()
                            bs_data[row_name] = cols[-1]

                # 4. Profit & Loss Table
                pl_data = {}
                pl_sec = soup.find("section", id="profit-loss")
                if pl_sec:
                    for row in pl_sec.find_all("tr"):
                        cols = [c.text.strip() for c in row.find_all(["th", "td"])]
                        if cols and len(cols) > 1:
                            row_name = cols[0].replace("\xa0+", "").replace("+", "").strip().lower()
                            pl_data[row_name] = cols[-1]
                            if len(cols) > 2:
                                pl_data["prev_" + row_name] = cols[-2]

                # Map extracted values
                mcap_cr = MarketDataService._clean_num(ratios_map.get("market cap"))
                if mcap_cr is not None:
                    res["market_cap"] = mcap_cr * 10_000_000.0

                pe = MarketDataService._clean_num(ratios_map.get("stock p/e"))
                if pe is not None:
                    res["pe_ratio"] = pe
                    res["forward_pe"] = pe

                curr_price = MarketDataService._clean_num(ratios_map.get("current price"))
                bv = MarketDataService._clean_num(ratios_map.get("book value"))
                if bv is not None:
                    res["book_value"] = bv
                    if curr_price and bv > 0:
                        res["price_to_book"] = round(curr_price / bv, 2)

                roe_val = MarketDataService._clean_num(ratios_map.get("roe"))
                if roe_val is not None:
                    res["roe"] = round(roe_val / 100.0, 4)

                roce_val = MarketDataService._clean_num(ratios_map.get("roce"))
                if roce_val is not None:
                    res["roa"] = round(roce_val / 100.0, 4)

                div_yield = MarketDataService._clean_num(ratios_map.get("dividend yield"))
                if div_yield is not None:
                    res["dividend_yield"] = round(div_yield / 100.0, 4)

                # Debt to Equity: Borrowings / (Equity Capital + Reserves)
                borrowings = MarketDataService._clean_num(bs_data.get("borrowings"))
                equity = MarketDataService._clean_num(bs_data.get("equity capital"))
                reserves = MarketDataService._clean_num(bs_data.get("reserves"))
                if borrowings is not None and equity is not None and reserves is not None:
                    net_worth = equity + reserves
                    if net_worth > 0:
                        res["debt_to_equity"] = round(borrowings / net_worth, 2)
                    elif borrowings == 0:
                        res["debt_to_equity"] = 0.0

                # Total Revenue & Revenue Growth
                sales_cr = MarketDataService._clean_num(pl_data.get("sales"))
                if sales_cr is not None:
                    res["total_revenue"] = sales_cr * 10_000_000.0
                    prev_sales_cr = MarketDataService._clean_num(pl_data.get("prev_sales"))
                    if prev_sales_cr and prev_sales_cr > 0:
                        res["revenue_growth"] = round((sales_cr - prev_sales_cr) / prev_sales_cr, 4)

                op_profit_cr = MarketDataService._clean_num(pl_data.get("operating profit"))
                if op_profit_cr is not None:
                    res["ebitda"] = op_profit_cr * 10_000_000.0

                # Current Ratio approximation
                other_liab = MarketDataService._clean_num(bs_data.get("other liabilities"))
                tot_liab = MarketDataService._clean_num(bs_data.get("total liabilities"))
                if other_liab and other_liab > 0 and tot_liab:
                    res["current_ratio"] = round(min(5.0, max(0.5, (tot_liab - (borrowings or 0)) / (other_liab * 2.5))), 2)

        except Exception as e:
            logger.debug(f"Screener.in fundamentals extraction failed for {clean_sym}: {e}")

        return res

    @staticmethod
    async def get_stock_info(symbol: str) -> dict:
        """Fetch fundamental company information, balance sheet, and valuation metrics."""
        yf_symbol = MarketDataService._normalise_yf_symbol(symbol)
        clean_sym = symbol.replace("NSE:", "").replace("BSE:", "").replace("-EQ", "").replace("-INDEX", "").replace(".BO", "").replace(".NS", "").replace("^", "").strip().upper()
        
        # Check cache: only treat as hit if real corporate ratios exist or it's an explicit index
        cache_key = f"info:{clean_sym}"
        cached = await cache_get(cache_key)
        if cached and (cached.get("pe_ratio") is not None or cached.get("roe") is not None or cached.get("is_index")):
            return cached

        # Check if index
        is_index = symbol.startswith("^") or symbol.endswith("-INDEX") or clean_sym in ("NIFTY50", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX")
        if is_index:
            result = {
                "symbol": symbol,
                "name": clean_sym,
                "sector": "Broad Market Index",
                "industry": "Benchmark Basket",
                "market_cap": 0,
                "is_index": True,
                "pe_ratio": None,
                "forward_pe": None,
                "eps": None,
                "dividend_yield": None,
                "description": f"{clean_sym} is an aggregated benchmark market index tracking exchange components.",
                "roe": None,
                "roa": None,
                "book_value": None,
                "price_to_book": None,
                "debt_to_equity": None,
                "total_revenue": None,
                "revenue_growth": None,
                "ebitda": None,
                "free_cashflow": None,
                "current_ratio": None,
            }
            await cache_set(cache_key, result, ttl=3600 * 24)
            return result

        result = {
            "symbol": symbol,
            "name": clean_sym,
            "sector": "N/A",
            "industry": "N/A",
            "market_cap": 0,
            "is_index": False,
            "pe_ratio": None,
            "forward_pe": None,
            "eps": None,
            "dividend_yield": None,
            "description": "Detailed company information is being updated.",
            "roe": None,
            "roa": None,
            "book_value": None,
            "price_to_book": None,
            "debt_to_equity": None,
            "total_revenue": None,
            "revenue_growth": None,
            "ebitda": None,
            "free_cashflow": None,
            "current_ratio": None,
        }

        # 1. Primary extractor: Screener.in for authentic Indian corporate balance sheets & valuations
        screener_data = await MarketDataService._fetch_screener_fundamentals(clean_sym)
        if screener_data:
            result.update(screener_data)

        # 2. Secondary fallback / enrichment: Yahoo Finance (if fields still missing)
        if result.get("pe_ratio") is None or result.get("market_cap") == 0 or result.get("sector") == "N/A":
            try:
                import requests
                session = requests.Session()
                session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                ticker = await asyncio.to_thread(yf.Ticker, yf_symbol, session=session)
                info = await asyncio.wait_for(asyncio.to_thread(lambda: ticker.info), timeout=4.0)
                if isinstance(info, dict) and info.get("marketCap"):
                    if not result.get("name") or result["name"] == clean_sym:
                        result["name"] = info.get("longName", result["name"])
                    if result.get("sector") in ("N/A", ""):
                        result["sector"] = info.get("sector", "N/A")
                    if result.get("industry") in ("N/A", ""):
                        result["industry"] = info.get("industry", "N/A")
                    if not result.get("market_cap"):
                        result["market_cap"] = info.get("marketCap", 0)
                    if result.get("pe_ratio") is None:
                        result["pe_ratio"] = info.get("trailingPE")
                    if result.get("forward_pe") is None:
                        result["forward_pe"] = info.get("forwardPE")
                    if result.get("eps") is None:
                        result["eps"] = info.get("trailingEps")
                    if result.get("dividend_yield") is None:
                        result["dividend_yield"] = info.get("dividendYield")
                    if result.get("description") == "Detailed company information is being updated.":
                        result["description"] = info.get("longBusinessSummary", result["description"])
                    if result.get("roe") is None:
                        result["roe"] = info.get("returnOnEquity")
                    if result.get("roa") is None:
                        result["roa"] = info.get("returnOnAssets")
                    if result.get("book_value") is None:
                        result["book_value"] = info.get("bookValue")
                    if result.get("price_to_book") is None:
                        result["price_to_book"] = info.get("priceToBook")
                    if result.get("debt_to_equity") is None:
                        result["debt_to_equity"] = info.get("debtToEquity")
                    if result.get("total_revenue") is None:
                        result["total_revenue"] = info.get("totalRevenue")
                    if result.get("revenue_growth") is None:
                        result["revenue_growth"] = info.get("revenueGrowth")
                    if result.get("ebitda") is None:
                        result["ebitda"] = info.get("ebitda")
                    if result.get("current_ratio") is None:
                        result["current_ratio"] = info.get("currentRatio")
            except Exception as e:
                logger.debug(f"Yahoo Finance ticker.info omitted for {symbol}: {e}")

        # Cache valid corporate data for 12 hours (balance sheets do not change intraday)
        ttl = 3600 * 12 if (result.get("pe_ratio") is not None or result.get("roe") is not None) else 300
        await cache_set(cache_key, result, ttl=ttl)
        return result


    @staticmethod
    async def fetch_news(symbol: str) -> list[dict]:
        """Fetch recent news articles for a given symbol."""
        yf_symbol = MarketDataService._normalise_yf_symbol(symbol)
        cache_key = f"news:{yf_symbol}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        try:
            import requests
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})
            ticker = await asyncio.to_thread(yf.Ticker, yf_symbol, session=session)
            news_items = await asyncio.wait_for(asyncio.to_thread(lambda: ticker.news), timeout=15.0)
            
            articles = []
            for item in news_items[:10]:
                articles.append({
                    "title": item.get("title", ""),
                    "publisher": item.get("publisher", ""),
                    "link": item.get("link", ""),
                    "providerPublishTime": item.get("providerPublishTime", 0),
                    "type": item.get("type", "STORY")
                })
                
            await cache_set(cache_key, articles, ttl=3600)  # 1 hour cache
            return articles
        except Exception as e:
            logger.error(f"Failed to fetch news for {symbol}: {e}.")
            return []
            
    @staticmethod
    async def fetch_corporate_events(symbol: str) -> dict:
        """Fetch corporate events: upcoming earnings date and recent dividends/splits."""
        yf_symbol = MarketDataService._normalise_yf_symbol(symbol)
        cache_key = f"events:v2:{yf_symbol}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        events = {"earnings_date": None, "dividends": []}
        try:
            import requests
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})
            ticker = await asyncio.to_thread(yf.Ticker, yf_symbol, session=session)
            
            # Fetch Calendar for Earnings Date
            try:
                cal = await asyncio.wait_for(asyncio.to_thread(lambda: ticker.calendar), timeout=5.0)
                if isinstance(cal, dict) and "Earnings Date" in cal:
                    dates = cal["Earnings Date"]
                    if len(dates) > 0:
                        events["earnings_date"] = str(dates[0])
                elif hasattr(cal, "empty") and not cal.empty:
                    # Older yfinance returns DataFrame
                    events["earnings_date"] = str(cal.iloc[0, 0])
            except Exception as e:
                logger.debug(f"Failed to fetch calendar for {symbol}: {e}")

            # Fetch Dividends
            try:
                divs = await asyncio.wait_for(asyncio.to_thread(lambda: ticker.dividends), timeout=5.0)
                if not divs.empty:
                    # Get last 2 years of dividends
                    import pandas as pd
                    two_years_ago = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=730)
                    
                    if divs.index.tz is None:
                        two_years_ago = two_years_ago.tz_localize(None)
                    else:
                        two_years_ago = two_years_ago.tz_convert(divs.index.tz)
                        
                    recent_divs = divs[divs.index > two_years_ago]
                    for date, amount in recent_divs.items():
                        events["dividends"].append({
                            "date": date.isoformat() if hasattr(date, 'isoformat') else str(date),
                            "amount": float(amount)
                        })
            except Exception as e:
                logger.debug(f"Failed to fetch dividends for {symbol}: {e}")
                
            await cache_set(cache_key, events, ttl=86400) # cache for 24h
            return events
        except Exception as e:
            logger.error(f"Failed to fetch events for {symbol}: {e}")
            return events


market_data_service = MarketDataService()
