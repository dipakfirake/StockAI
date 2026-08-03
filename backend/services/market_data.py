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

VALID_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "1d", "1w"}
YFINANCE_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "1d": "1d", "1w": "1wk",
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
                data = await asyncio.to_thread(lambda: ticker.fast_info)
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
                hist = await asyncio.to_thread(ticker.history, period="5d")
                if not hist.empty:
                    hist = hist.fillna(0)
                    last_price = float(hist["Close"].iloc[-1])
                    prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last_price

            quote = {
                "symbol": symbol,
                "price": round(last_price, 2),
                "previous_close": round(prev_close, 2),
                "change": round(last_price - prev_close, 2),
                "change_pct": round(((last_price - prev_close) / prev_close * 100) if prev_close else 0, 2),
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
            logger.error(f"Failed to fetch quote for {symbol}: {e}")
            await cache_set(cache_key, {"error": "unavailable"}, ttl=60)
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
            period_map = {
                "1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d",
                "1h": "730d", "1d": "max", "1w": "max", "1mo": "max"
            }
            period = period_map.get(timeframe, "max")
            start_date = None
            end_date = None

        try:
            import requests
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            ticker = await asyncio.to_thread(yf.Ticker, symbol, session=session)
            kwargs = {
                "interval": yf_interval,
                "auto_adjust": True,
            }
            if period:
                kwargs["period"] = period
            else:
                kwargs["start"] = start_date
                kwargs["end"] = end_date
                
            df: pd.DataFrame = await asyncio.to_thread(
                ticker.history,
                **kwargs
            )

            if df.empty:
                logger.warning(f"No candle data returned for {symbol} {timeframe}")
                await cache_set(cache_key, [], ttl=60)
                return []
            
            df = df.fillna(0)

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
            logger.error(f"Failed to fetch candles for {symbol} {timeframe}: {e}")
            await cache_set(cache_key, [], ttl=60)
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
            info = await asyncio.to_thread(lambda: ticker.info)
            
            # Fetch balance sheet and financials if available
            try:
                bs = await asyncio.to_thread(lambda: ticker.balance_sheet)
                fin = await asyncio.to_thread(lambda: ticker.financials)
            except Exception:
                bs, fin = None, None

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
            logger.error(f"Failed to fetch info for {symbol}: {e}")
            return None


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
            news_items = await asyncio.to_thread(lambda: ticker.news)
            
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
            logger.error(f"Failed to fetch news for {symbol}: {e}")
            return []


market_data_service = MarketDataService()
