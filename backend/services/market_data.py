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
    def _normalise_symbol(symbol: str) -> str:
        """Ensure symbol has exchange suffix. Index symbols (^) are returned as-is."""
        symbol = symbol.upper().strip()
        
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
            
            cached_creds = await cache_get("fyers_creds")
            if cached_creds:
                client_id = cached_creds.get("client_id", client_id)
                access_token = cached_creds.get("access_token", access_token)
            else:
                async with AsyncSessionLocal() as db:
                    fyers_client_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_client_id"))).scalar_one_or_none()
                    fyers_token_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_access_token"))).scalar_one_or_none()
                    
                    if fyers_client_obj and fyers_client_obj.value:
                        client_id = fyers_client_obj.value
                    if fyers_token_obj and fyers_token_obj.value:
                        access_token = fyers_token_obj.value
                        
                if client_id and access_token:
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
                    if MarketDataService._env_cache.get("FYERS_ACCESS_TOKEN"):
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
    async def fetch_quote(symbol: str) -> Optional[dict]:
        """Fetch live quote with caching (TTL: 60s) via Fyers."""
        import time
        now = time.time()
        original_symbol = symbol
        fyers_symbol = MarketDataService._normalise_symbol(symbol)
        cache_key = f"quote:{original_symbol}"
        
        cached = await cache_get(cache_key)
        if cached and cached.get("price", 0) > 0:
            logger.debug(f"Quote cache hit: {original_symbol}")
            return cached

        if now >= MarketDataService._fyers_cooldown_until:
            try:
                fyers = await MarketDataService._get_fyers_client()
                data = {"symbols": fyers_symbol}
                
                response = await asyncio.to_thread(fyers.quotes, data)
                if response.get("s") == "ok" and response.get("d"):
                    quote_data = response["d"][0]["v"]
                    
                    last_price = quote_data.get("lp", 0.0)
                    prev_close = quote_data.get("prev_close_price", last_price)
                    calc_change = quote_data.get("ch", 0.0)
                    calc_change_pct = quote_data.get("chp", 0.0)
                    
                    quote = {
                        "symbol": original_symbol,
                        "price": round(float(last_price), 2),
                        "previous_close": round(float(prev_close), 2),
                        "change": round(float(calc_change), 2),
                        "change_pct": round(float(calc_change_pct), 2),
                        "volume": int(quote_data.get("volume", 0)),
                        "market_cap": 0,
                        "52w_high": 0.0,
                        "52w_low": 0.0,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "data_status": "realtime",
                        "source": "Fyers API",
                    }

                    if float(last_price) > 0:
                        await cache_set(cache_key, quote, ttl=settings.CACHE_TTL_QUOTE)
                        return quote
                    elif fyers_symbol.startswith("BSE:"):
                        return await MarketDataService.fetch_quote(original_symbol.replace(".BO", ".NS"))
                    else:
                        logger.warning(f"Fyers returned zero price for {fyers_symbol}, falling through to backup")
                elif response.get("code") == 429:
                    MarketDataService._fyers_cooldown_until = now + 45.0
                    logger.warning("Fyers rate limit (429) hit in single quote. Entering 45s cooldown.")
                elif fyers_symbol.startswith("BSE:"):
                    return await MarketDataService.fetch_quote(original_symbol.replace(".BO", ".NS"))
                else:
                    err_msg = str(response)
                    if "429" in err_msg or "rate limit" in err_msg.lower() or "1015" in err_msg:
                        MarketDataService._fyers_cooldown_until = now + 45.0
                        logger.warning("Fyers WAF rate limit hit in single quote. Entering 45s cooldown.")
                    logger.warning(f"Fyers quote returned non-ok for {fyers_symbol}: {response}")

            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate limit" in err_str.lower() or "1015" in err_str:
                    MarketDataService._fyers_cooldown_until = now + 45.0
                    logger.warning("Fyers WAF rate limit exception. Entering 45s cooldown.")
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
                        last_price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
                        if last_price:
                            prev_close = meta.get("chartPreviousClose") or last_price
                            calc_change = last_price - prev_close
                            calc_change_pct = (calc_change / prev_close) * 100 if prev_close else 0.0
                            fallback_quote = {
                                "symbol": original_symbol,
                                "price": round(float(last_price), 2),
                                "previous_close": round(float(prev_close), 2),
                                "change": round(float(calc_change), 2),
                                "change_pct": round(float(calc_change_pct), 2),
                                "volume": int(meta.get("regularMarketVolume") or 0),
                                "market_cap": 0,
                                "52w_high": round(float(meta.get("fiftyTwoWeekHigh") or 0.0), 2),
                                "52w_low": round(float(meta.get("fiftyTwoWeekLow") or 0.0), 2),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "data_status": "delayed",
                                "source": "Backup (Yahoo Chart API)",
                            }
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
        fyers_to_orig: dict[str, list[str]] = {}
        for s in symbols:
            norm = MarketDataService._normalise_symbol(s)
            fyers_to_orig.setdefault(norm, []).append(s)
            # In Fyers, BSE cash equities (e.g. BSE:PCJEWELLER-EQ) error with -300 invalid symbol.
            # Add the liquid NSE equivalent (NSE:PCJEWELLER-EQ) so Fyers returns real-time quotes.
            if norm.startswith("BSE:") and not norm.endswith("-INDEX"):
                nse_norm = norm.replace("BSE:", "NSE:")
                fyers_to_orig.setdefault(nse_norm, []).append(s)

        fyers_symbols_str = ",".join(fyers_to_orig.keys())
        
        quotes_dict = {}
        if now >= MarketDataService._fyers_cooldown_until:
            try:
                fyers = await MarketDataService._get_fyers_client()
                data = {"symbols": fyers_symbols_str}
                response = await asyncio.to_thread(fyers.quotes, data)
                
                if response.get("s") == "ok" and "d" in response:
                    for item in response["d"]:
                        fyers_sym = item.get("n", "")
                        quote_data = item.get("v", {})
                        orig_symbols = fyers_to_orig.get(fyers_sym, [fyers_sym])
                        
                        last_price = quote_data.get("lp", 0.0)
                        prev_close = quote_data.get("prev_close_price", last_price)
                        calc_change = quote_data.get("ch", 0.0)
                        calc_change_pct = quote_data.get("chp", 0.0)
                        
                        if float(last_price) > 0:
                            for orig_sym in orig_symbols:
                                quotes_dict[orig_sym] = {
                                    "symbol": orig_sym,
                                    "price": round(float(last_price), 2),
                                    "previous_close": round(float(prev_close), 2),
                                    "change": round(float(calc_change), 2),
                                    "change_pct": round(float(calc_change_pct), 2),
                                    "volume": int(quote_data.get("volume", 0)),
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "data_status": "realtime",
                                    "source": "Fyers API",
                                }
                elif response.get("code") == 429:
                    MarketDataService._fyers_cooldown_until = now + 45.0
                    logger.warning("Fyers rate limit (429) hit in bulk quotes. Entering 45s cooldown.")
                else:
                    err_msg = str(response)
                    if "429" in err_msg or "rate limit" in err_msg.lower() or "1015" in err_msg:
                        MarketDataService._fyers_cooldown_until = now + 45.0
                        logger.warning("Fyers WAF rate limit detected in bulk quotes. Entering 45s cooldown.")
                    logger.error(f"Fyers bulk quote returned non-ok: {response}")
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate limit" in err_str.lower() or "1015" in err_str:
                    MarketDataService._fyers_cooldown_until = now + 45.0
                    logger.warning("Fyers WAF rate limit exception in bulk quotes. Entering 45s cooldown.")
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
                            last_price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
                            if last_price and float(last_price) > 0:
                                prev_close = meta.get("chartPreviousClose") or last_price
                                calc_change = float(last_price) - float(prev_close)
                                calc_change_pct = (calc_change / float(prev_close)) * 100 if float(prev_close) else 0.0
                                return sym, {
                                    "symbol": sym,
                                    "price": round(float(last_price), 2),
                                    "previous_close": round(float(prev_close), 2),
                                    "change": round(float(calc_change), 2),
                                    "change_pct": round(float(calc_change_pct), 2),
                                    "volume": int(meta.get("regularMarketVolume") or 0),
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "data_status": "delayed",
                                    "source": "Backup (Yahoo Chart API)",
                                }
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

        try:
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
                    
                    # If authentication fails (-16), rate limited (429), symbol is invalid (-300), or no data exists (pre-IPO), skip immediately without retry delay
                    if response.get("code") in [-16, -300, 429] or response.get("s") in ["no_data", "error"]:
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

                ttl = settings.CACHE_TTL_INTRADAY if timeframe in ("1m", "5m", "15m", "30m") else settings.CACHE_TTL_DAILY_CANDLES
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
                        await cache_set(cache_key, nse_candles, ttl=300)
                        return nse_candles

                if fallback_candles:
                    await cache_set(cache_key, fallback_candles, ttl=300)
                    return fallback_candles
            elif original_symbol.endswith(".BO"):
                nse_candles = await MarketDataService.fetch_candles(f"{clean_sym}.NS", timeframe, limit, start_date, end_date)
                if nse_candles:
                    await cache_set(cache_key, nse_candles, ttl=300)
                    return nse_candles
        except Exception:
            pass

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
    async def get_stock_info(symbol: str) -> dict:
        """Fetch fundamental company information and valuation metrics."""
        yf_symbol = MarketDataService._normalise_yf_symbol(symbol)
        clean_sym = symbol.replace("NSE:", "").replace("BSE:", "").replace("-EQ", "").replace("-INDEX", "").replace(".BO", "").replace(".NS", "").replace("^", "").strip().upper()
        
        cache_key = f"info:{clean_sym}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        try:
            import requests
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            ticker = await asyncio.to_thread(yf.Ticker, yf_symbol, session=session)
            info = await asyncio.wait_for(asyncio.to_thread(lambda: ticker.info), timeout=15.0)
            
            # Removed extremely slow balance_sheet and financials fetches (they were unused anyway)

            result = {
                "symbol": symbol,
                "name": info.get("longName", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "eps": info.get("trailingEps"),
                "dividend_yield": info.get("dividendYield"),
                "description": info.get("longBusinessSummary", ""),
                
                # Fundamentals Phase 13
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "book_value": info.get("bookValue"),
                "price_to_book": info.get("priceToBook"),
                "debt_to_equity": info.get("debtToEquity"),
                "total_revenue": info.get("totalRevenue"),
                "revenue_growth": info.get("revenueGrowth"),
                "ebitda": info.get("ebitda"),
                "free_cashflow": info.get("freeCashflow"),
                "current_ratio": info.get("currentRatio"),
            }
            # Only cache for 6 hours if we got actual fundamental data. 
            # If market_cap is 0, it means yfinance likely returned an empty dict due to throttling, 
            # or it's an index. In that case, cache for only 5 minutes so it can retry later.
            ttl = 3600 * 6 if result["market_cap"] > 0 else 300
            await cache_set(cache_key, result, ttl=ttl)
            # return result handled below
        except Exception as e:
            logger.error(f"Failed to fetch info for {symbol}: {e}.")
            result = {
                "symbol": symbol,
                "name": symbol.replace(".NS", "").replace("^", ""),
                "sector": "N/A",
                "industry": "N/A",
                "market_cap": 0,
                "pe_ratio": None,
                "forward_pe": None,
                "eps": None,
                "dividend_yield": None,
                "description": "Detailed company information is not available for this symbol.",
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

        # Tertiary fallback: Scrape Screener.in if Yahoo Finance failed to get market_cap
        if result.get("market_cap") in (0, None) and not symbol.startswith("^") and not symbol.endswith("-INDEX"):
            try:
                import httpx
                from bs4 import BeautifulSoup
                url = f"https://www.screener.in/company/{clean_sym}/"
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                async with httpx.AsyncClient(headers=headers, timeout=5.0) as client:
                    r = await client.get(url)
                    if r.status_code == 200:
                        soup = BeautifulSoup(r.text, 'html.parser')
                        for li in soup.find_all('li', class_='flex'):
                            if 'Market Cap' in li.text:
                                val_span = li.find('span', class_='number')
                                if val_span:
                                    val_str = val_span.text.replace(',', '').strip()
                                    try:
                                        mcap = float(val_str) * 10_000_000
                                        result["market_cap"] = mcap
                                        # Also cache the updated result to prevent hitting screener constantly
                                        await cache_set(cache_key, result, ttl=3600*6)
                                    except ValueError:
                                        pass
            except Exception as e:
                logger.debug(f"Screener.in fallback failed for {clean_sym}: {e}")

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
