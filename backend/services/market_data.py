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
        # .BO suffix means the stock is BSE-listed; route to BSE exchange in Fyers
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
    def _get_fyers_client():
        import os
        from dotenv import dotenv_values
        
        client_id = settings.FYERS_CLIENT_ID
        access_token = settings.FYERS_ACCESS_TOKEN
        
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
                fyers = MarketDataService._get_fyers_client()
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
                    MarketDataService._fyers_cooldown_until = now + 30.0
                    logger.warning("Fyers rate limit (429) hit in single quote. Entering 30s cooldown.")
                elif fyers_symbol.startswith("BSE:"):
                    return await MarketDataService.fetch_quote(original_symbol.replace(".BO", ".NS"))
                else:
                    logger.warning(f"Fyers quote returned non-ok for {fyers_symbol}: {response}")

            except Exception as e:
                logger.error(f"Failed to fetch Fyers quote for {original_symbol}: {e}")
        else:
            remaining = int(MarketDataService._fyers_cooldown_until - now)
            logger.debug(f"Fyers cooldown active ({remaining}s remaining), skipping Fyers single quote")

        # Secondary fallback if Fyers token is expired or temporary connectivity glitch
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
        fyers_to_orig = {MarketDataService._normalise_symbol(s): s for s in symbols}
        fyers_symbols_str = ",".join(fyers_to_orig.keys())
        
        quotes_dict = {}
        if now >= MarketDataService._fyers_cooldown_until:
            try:
                fyers = MarketDataService._get_fyers_client()
                data = {"symbols": fyers_symbols_str}
                response = await asyncio.to_thread(fyers.quotes, data)
                
                if response.get("s") == "ok" and "d" in response:
                    for item in response["d"]:
                        fyers_sym = item.get("n", "")
                        quote_data = item.get("v", {})
                        orig_sym = fyers_to_orig.get(fyers_sym, fyers_sym)
                        
                        last_price = quote_data.get("lp", 0.0)
                        prev_close = quote_data.get("prev_close_price", last_price)
                        calc_change = quote_data.get("ch", 0.0)
                        calc_change_pct = quote_data.get("chp", 0.0)
                        
                        if float(last_price) > 0:
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
                    MarketDataService._fyers_cooldown_until = now + 30.0
                    logger.warning("Fyers rate limit (429) hit in bulk quotes. Entering 30s cooldown.")
                else:
                    logger.error(f"Fyers bulk quote returned non-ok: {response}")
            except Exception as e:
                logger.error(f"Fyers bulk quote failed: {e}")
        else:
            remaining = int(MarketDataService._fyers_cooldown_until - now)
            logger.debug(f"Fyers cooldown active ({remaining}s remaining), skipping Fyers bulk quote")

        # Automatically fill any missing symbols via fast concurrent fallback
        missing_symbols = [s for s in symbols if s not in quotes_dict or quotes_dict[s].get("price", 0) <= 0]
        if missing_symbols and use_fallback:
            try:
                import yfinance as yf
                import requests
                yf_map = {}
                for s in missing_symbols:
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

                df = await asyncio.wait_for(asyncio.to_thread(_batch_yf), timeout=10.0)
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
                                    quotes_dict[orig_sym] = {
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
                        except Exception:
                            pass
            except Exception as ex:
                logger.debug(f"Batch fallback skipped: {ex}")

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
            fyers = MarketDataService._get_fyers_client()
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
                
            # 2. Pagination Loop (Fyers max range is 100 days for intraday, 365 days for daily)
            max_days_per_request = 365 if timeframe in ["1d", "1w", "1mo"] else 100
            
            current_start = dt_start
            while current_start < dt_end:
                current_end = min(current_start + timedelta(days=max_days_per_request), dt_end)
                
                data = {
                    "symbol": fyers_symbol,
                    "resolution": fyers_interval,
                    "date_format": "1",
                    "range_from": current_start.strftime("%Y-%m-%d"),
                    "range_to": current_end.strftime("%Y-%m-%d"),
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
                        
                    logger.warning(f"Fyers history failed for {fyers_symbol} ({current_start.date()} to {current_end.date()}): {response}. Attempt {attempt + 1}/{max_retries}")
                    await asyncio.sleep(1.0)
                else:
                    break
                    
                if "candles" in response and response["candles"]:
                    all_candles.extend(response["candles"])
                    
                current_start = current_end + timedelta(days=1)
                
                # Sleep briefly only if paginating across multiple years
                if current_start < dt_end:
                    await asyncio.sleep(0.35)
                
            if all_candles:
                # Fyers candle format: [Epoch, Open, High, Low, Close, Volume]
                formatted_candles = []
                for c in all_candles:
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
        """Search for stocks in local DB first, fallback to yfinance."""
        from backend.core.database import AsyncSessionLocal
        from backend.models.stock import Stock
        from sqlalchemy import select

        query_upper = query.upper()
        
        async with AsyncSessionLocal() as db:
            stmt = select(Stock).where(
                (Stock.symbol.ilike(f"%{query_upper}%")) | 
                (Stock.name.ilike(f"%{query_upper}%"))
            ).limit(10)
            local_stocks = (await db.execute(stmt)).scalars().all()
            
            if local_stocks:
                return [
                    {
                        "symbol": s.symbol.replace(".NS", ""),
                        "name": s.name,
                        "exchange": s.exchange,
                        "type": "EQUITY"
                    }
                    for s in local_stocks
                ]

        fallback_symbols = [
            {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "INFY.NS", "name": "Infosys", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "ICICIBANK.NS", "name": "ICICI Bank", "exchange": "NSE", "type": "EQUITY"},
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

        # Fallback to yfinance
        try:
            results = await asyncio.to_thread(yf.Search, query, max_results=10)
            quotes = results.quotes if hasattr(results, "quotes") else []
            return [
                {
                    "symbol": q.get("symbol", "").replace(".NS", ""),
                    "name": q.get("shortname") or q.get("longname", ""),
                    "exchange": q.get("exchange", ""),
                    "type": q.get("quoteType", ""),
                }
                for q in quotes
                if q.get("quoteType") == "EQUITY"
            ]
        except Exception as e:
            logger.error(f"Stock search failed for '{query}': {e}")
            return []

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
            info = await asyncio.wait_for(asyncio.to_thread(lambda: ticker.info), timeout=5.0)
            
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
            return result
        except Exception as e:
            logger.error(f"Failed to fetch info for {symbol}: {e}.")
            return {
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
            news_items = await asyncio.wait_for(asyncio.to_thread(lambda: ticker.news), timeout=5.0)
            
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
