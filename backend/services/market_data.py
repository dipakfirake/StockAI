"""Market data service — yfinance-based OHLCV ingestion for NSE/BSE."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

from backend.core.config import settings
from backend.core.logging_config import get_logger
from backend.core.cache import cache_get, cache_set

logger = get_logger(__name__)

VALID_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "1d", "1w", "1mo"}
YFINANCE_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "1d": "1d", "1w": "1wk", "1mo": "1mo"
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
        
        # Map common index names to Yahoo Finance tickers
        index_map = {
            "NIFTY.NS": "^NSEI",
            "NIFTY": "^NSEI",
            "BANKNIFTY.NS": "^NSEBANK",
            "BANKNIFTY": "^NSEBANK",
            "SENSEX.BO": "^BSESN",
            "SENSEX": "^BSESN",
            "INDIAVIX": "^INDIAVIX",
            "FINNIFTY.NS": "NIFTY_FIN_SERVICE.NS" # YF doesn't have finnifty easily, but just in case
        }
        if symbol in index_map:
            return index_map[symbol]
            
        # Index symbols like ^NSEI, ^BSESN, ^INDIAVIX don't need a suffix
        if symbol.startswith("^"):
            return symbol
        if "." not in symbol:
            symbol += settings.DEFAULT_EXCHANGE_SUFFIX
        return symbol

    @staticmethod
    async def fetch_quote(symbol: str) -> Optional[dict]:
        """Fetch live quote with caching (TTL: 60s)."""
        symbol = MarketDataService._normalise_symbol(symbol)
        cache_key = f"quote:{symbol}"
        cached = await cache_get(cache_key)
        if cached:
            logger.debug(f"Quote cache hit: {symbol}")
            return cached

        # Attempt to get real-time NSE data first
        try:
            from backend.data.ingestion.nse_scraper import NSEScraper
            rt_quote = await NSEScraper.fetch_realtime_quote(symbol)
            if rt_quote:
                await cache_set(cache_key, rt_quote, ttl=settings.CACHE_TTL_QUOTE)
                return rt_quote
        except Exception as e:
            logger.debug(f"NSE Real-time fetch failed for {symbol}, falling back to yfinance: {e}")

        try:
            import requests
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})
            ticker = await asyncio.to_thread(yf.Ticker, symbol, session=session)
            try:
                import math
                def _sf(v):
                    try:
                        fv = float(v or 0)
                        return 0 if math.isnan(fv) else fv
                    except: return 0
                
                # Try fast_info first
                data = await asyncio.wait_for(asyncio.to_thread(lambda: ticker.fast_info), timeout=5.0)
                last_price = _sf(getattr(data, "last_price", 0))
                prev_close = _sf(getattr(data, "previous_close", 0))
                volume_avg = int(_sf(getattr(data, "three_month_average_volume", 0)))
                market_cap = int(_sf(getattr(data, "market_cap", 0)))
                year_high = round(_sf(getattr(data, "year_high", 0)), 2)
                year_low = round(_sf(getattr(data, "year_low", 0)), 2)
            except Exception as e:
                logger.debug(f"fast_info failed for {symbol}: {e}")
                last_price, prev_close, volume_avg, market_cap, year_high, year_low = 0, 0, 0, 0, 0, 0

            # Fallback to history if fast_info provides zeroed/stale reference data.
            # Index feeds occasionally omit previous_close while still returning price.
            hist = pd.DataFrame()
            if last_price == 0 or prev_close == 0:
                try:
                    hist = await asyncio.wait_for(asyncio.to_thread(ticker.history, period="5d"), timeout=5.0)
                except Exception:
                    pass
                if not hist.empty:
                    hist = hist.ffill().bfill().fillna(0)
                    last_price = float(hist["Close"].iloc[-1])
                    prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last_price

            if prev_close <= 0:
                calc_change = 0.0
                calc_change_pct = 0.0
            else:
                calc_change = last_price - prev_close
                calc_change_pct = (calc_change / prev_close) * 100

            quote = {
                "symbol": symbol,
                "price": round(last_price, 2),
                "previous_close": round(prev_close, 2),
                "change": round(calc_change, 2),
                "change_pct": round(calc_change_pct, 2),
                "volume": volume_avg,
                "market_cap": market_cap,
                "52w_high": year_high,
                "52w_low": year_low,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data_status": "provider_delayed_or_realtime",
                "source": "Yahoo Finance provider feed",
            }

            await cache_set(cache_key, quote, ttl=settings.CACHE_TTL_QUOTE)
            return quote

        except Exception as e:
            logger.error(f"Failed to fetch quote for {symbol}: {e}.")
            return None

    @staticmethod
    async def fetch_candles(
        symbol: str,
        timeframe: str = "1d",
        limit: int = 200,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch OHLCV candles from yfinance.
        Results are cached: 60s for intraday, 3600s for daily+.
        """
        if timeframe not in VALID_TIMEFRAMES:
            raise ValueError(f"Invalid timeframe '{timeframe}'. Valid: {VALID_TIMEFRAMES}")

        symbol = MarketDataService._normalise_symbol(symbol)        
        cache_key = f"candles:{symbol}:{timeframe}:{limit}"
        cached = await cache_get(cache_key)
        if cached:
            logger.debug(f"Candle cache hit: {symbol} {timeframe}")
            return cached

        yf_interval = YFINANCE_INTERVAL_MAP[timeframe]

        # Determine date range or period
        if start_date and end_date:
            period = None
        else:
            # Strictly valid yfinance periods: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
            # Intraday limits: 1m max 7d, 2m-90m max 60d, 1h max 730d
            period_map = {
                "1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d",
                "1h": "730d", "1d": "max", "1w": "max", "1mo": "max"
            }
            period = period_map.get(timeframe, "max")
            start_date = None
            end_date = None

        # Dual-fetch strategy for robust India market data:
        # 1. Try fetching .NS equivalent if it's a .BO stock (NSE data is cleaner for auto_adjust)
        # 2. If it fails (e.g., BSE-only stock), fallback to the original symbol with auto_adjust=False
        
        yf_symbol_primary = symbol.replace('.BO', '.NS') if symbol.endswith('.BO') else symbol
        
        try:
            import requests
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            
            # Primary Fetch (NSE / original)
            ticker = await asyncio.to_thread(yf.Ticker, yf_symbol_primary, session=session)
            kwargs = {"interval": yf_interval, "auto_adjust": True}
            if period: kwargs["period"] = period
            else: kwargs["start"] = start_date; kwargs["end"] = end_date
                
            df: pd.DataFrame = await asyncio.wait_for(asyncio.to_thread(ticker.history, **kwargs), timeout=15.0)
            
            if df.empty and yf_symbol_primary != symbol:
                # Fallback Fetch (BSE-only stock)
                logger.debug(f"Primary fetch failed for {yf_symbol_primary}, trying original {symbol} without auto_adjust")
                ticker = await asyncio.to_thread(yf.Ticker, symbol, session=session)
                kwargs["auto_adjust"] = False
                df = await asyncio.wait_for(asyncio.to_thread(ticker.history, **kwargs), timeout=15.0)
                
            if df.empty:
                # Direct Chart API Fallback (bypasses quoteSummary 404s)
                try:
                    logger.debug(f"Ticker history empty for {yf_symbol_primary}, trying yf.download fallback")
                    dl_kwargs = {"interval": yf_interval, "progress": False}
                    if period: dl_kwargs["period"] = period
                    else: dl_kwargs["start"] = start_date; dl_kwargs["end"] = end_date
                    df = await asyncio.wait_for(asyncio.to_thread(yf.download, yf_symbol_primary, **dl_kwargs), timeout=15.0)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                except Exception as dl_err:
                    logger.debug(f"yf.download fallback failed: {dl_err}")
                
            if df.empty:
                logger.warning(f"Empty candle data returned for {symbol} {timeframe}. Raising error to trigger mock fallback.")
                raise ValueError("Insufficient dataframe returned by yfinance")
            
            df = df.ffill().bfill().fillna(0)

            df = df.tail(limit)
            candles = []
            for ts, row in df.iterrows():
                candles.append({
                    "timestamp": ts.isoformat(),
                    "open": round(float(row["Open"]), 4),
                    "high": round(float(row["High"]), 4),
                    "low": round(float(row["Low"]), 4),
                    "close": round(float(row["Close"]), 4),
                    "volume": int(row["Volume"]),
                })

            ttl = settings.CACHE_TTL_INTRADAY if timeframe in ("1m", "5m", "15m", "30m") else settings.CACHE_TTL_DAILY_CANDLES
            await cache_set(cache_key, candles, ttl=ttl)
            return candles

        except Exception as e:
            logger.warning(f"yfinance failed for {symbol} {timeframe}: {e}. Trying Jugaad NSE Fallback...")
            
            # --- JUGAAD NSE FALLBACK ---
            # If Yahoo Finance is blocked, we scrape directly from the NSE India website using their unofficial API.
            try:
                import requests
                from datetime import datetime, timedelta
                session = requests.Session()
                # NSE requires strict browser headers to bypass block
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Origin": "https://www.nseindia.com",
                    "Referer": "https://www.nseindia.com/"
                })
                # First hit homepage to get cookies
                session.get("https://www.nseindia.com", timeout=10)
                
                # Fetch historical data
                nse_symbol = symbol.replace('.NS', '').replace('.BO', '')
                url = f"https://www.nseindia.com/api/historical/cm/equity?symbol={nse_symbol}&series=[%22EQ%22]&from={(datetime.now()-timedelta(days=180)).strftime('%d-%m-%Y')}&to={datetime.now().strftime('%d-%m-%Y')}"
                res = session.get(url, timeout=10)
                if res.status_code == 200:
                    data = res.json().get('data', [])
                    if data:
                        candles = []
                        # NSE returns newest first, so we reverse it
                        for row in reversed(data):
                            try:
                                ts = datetime.strptime(row['CH_TIMESTAMP'], '%Y-%m-%d').isoformat()
                                candles.append({
                                    "timestamp": ts,
                                    "open": float(row['CH_OPENING_PRICE']),
                                    "high": float(row['CH_TRADE_HIGH_PRICE']),
                                    "low": float(row['CH_TRADE_LOW_PRICE']),
                                    "close": float(row['CH_CLOSING_PRICE']),
                                    "volume": int(row['CH_TOT_TRADED_QTY'])
                                })
                            except Exception:
                                pass
                        if candles:
                            logger.info(f"Successfully used Jugaad NSE Fallback for {symbol}")
                            await cache_set(cache_key, candles[-limit:], ttl=3600)
                            return candles[-limit:]
            except Exception as nse_e:
                logger.error(f"Jugaad NSE Fallback also failed for {symbol}: {nse_e}")
                
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
    async def get_stock_info(symbol: str) -> Optional[dict]:
        """Fetch full company info."""
        symbol = MarketDataService._normalise_symbol(symbol)
        cache_key = f"info:{symbol}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        try:
            import requests
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})
            ticker = await asyncio.to_thread(yf.Ticker, symbol, session=session)
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
            await cache_set(cache_key, result, ttl=3600 * 6)  # 6 hours
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
        symbol = MarketDataService._normalise_symbol(symbol)
        cache_key = f"news:{symbol}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        try:
            import requests
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})
            ticker = await asyncio.to_thread(yf.Ticker, symbol, session=session)
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
        symbol = MarketDataService._normalise_symbol(symbol)
        cache_key = f"events:v2:{symbol}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        events = {"earnings_date": None, "dividends": []}
        try:
            import requests
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})
            ticker = await asyncio.to_thread(yf.Ticker, symbol, session=session)
            
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
