"""
NSE data scraper — scrapes NSE website for:
- FII/DII flow data
- Market breadth (advance/decline)
- India VIX
- Corporate actions
- NSE holiday calendar
- Delivery percentage data

All scraping is done respectfully with delays and User-Agent headers.
NSE official website: https://www.nseindia.com/
"""

from __future__ import annotations

import asyncio
from datetime import datetime, date, timezone
from typing import Optional

import aiohttp
from backend.core.logging_config import get_logger
from backend.core.cache import cache_get, cache_set
from backend.services.time_sync import time_sync

logger = get_logger(__name__)

NSE_BASE_URL = "https://www.nseindia.com"
NSE_API_URL = "https://www.nseindia.com/api"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# NSE market holidays 2024-2026 (approximate — update annually)
NSE_HOLIDAYS_2026 = [
    "2026-01-26",  # Republic Day
    "2026-03-02",  # Holi
    "2026-03-30",  # Good Friday
    "2026-04-14",  # Ambedkar Jayanti / Ugadi (if applicable)
    "2026-05-01",  # Maharashtra Day
    "2026-08-15",  # Independence Day
    "2026-10-02",  # Gandhi Jayanti
    "2026-10-20",  # Diwali (Muhurat trading only)
    "2026-11-04",  # Gurunanak Jayanti
    "2026-12-25",  # Christmas
]


class NSEScraper:
    """
    Scrapes NSE website for Indian market data not available via yfinance.
    All methods cache results aggressively to avoid hammering the NSE site.
    """
    _session: Optional[aiohttp.ClientSession] = None
    
    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            cls._session = aiohttp.ClientSession(headers=NSE_HEADERS)
            # Fetch base URL once to acquire cookies required for API access
            try:
                await cls._session.get(NSE_BASE_URL, timeout=10)
            except Exception as e:
                logger.error(f"Failed to acquire NSE cookies: {e}")
        return cls._session

    @staticmethod
    def is_market_open(dt: Optional[datetime] = None) -> bool:
        """Check if NSE market is open at the given datetime (IST), using synced time to prevent Docker drift."""
        import pytz
        tz = pytz.timezone("Asia/Kolkata")
        now = dt or time_sync.get_true_now(tz)
        if hasattr(now, "tzinfo") and now.tzinfo is None:
            now = tz.localize(now)

        # Weekday check (Mon=0, Sun=6)
        if now.weekday() >= 5:
            return False

        # Holiday check
        today_str = now.strftime("%Y-%m-%d")
        if today_str in NSE_HOLIDAYS_2026:
            return False

        # Time check: 09:15 – 15:30 IST
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open <= now <= market_close

    @staticmethod
    def is_trading_day(d: Optional[date] = None) -> bool:
        """Check if a given date is a trading day."""
        d = d or date.today()
        if d.weekday() >= 5:
            return False
        return d.strftime("%Y-%m-%d") not in NSE_HOLIDAYS_2026

    @staticmethod
    async def fetch_india_vix() -> Optional[dict]:
        """Fetch India VIX from yfinance (^INDIAVIX)."""
        cache_key = "india_vix"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        try:
            import yfinance as yf
            ticker = await asyncio.to_thread(yf.Ticker, "^INDIAVIX")
            info = await asyncio.to_thread(lambda: ticker.fast_info)
            vix = float(info.last_price or 0)

            # VIX interpretation for Indian markets
            if vix < 12:
                sentiment = "VERY_LOW_FEAR"
                regime_signal = "bullish"
            elif vix < 18:
                sentiment = "LOW_FEAR"
                regime_signal = "bullish"
            elif vix < 25:
                sentiment = "MODERATE_FEAR"
                regime_signal = "neutral"
            elif vix < 35:
                sentiment = "HIGH_FEAR"
                regime_signal = "bearish"
            else:
                sentiment = "EXTREME_FEAR"
                regime_signal = "bearish"

            result = {
                "vix": round(vix, 2),
                "sentiment": sentiment,
                "regime_signal": regime_signal,
                "interpretation": f"India VIX at {vix:.1f} — {sentiment.replace('_', ' ').title()}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await cache_set(cache_key, result, ttl=300)  # 5 min cache
            return result
        except Exception as e:
            logger.error(f"Failed to fetch India VIX: {e}")
            return None

    @staticmethod
    async def fetch_realtime_quote(symbol: str) -> Optional[dict]:
        """Fetch 100% real-time quote directly from NSE to bypass Yahoo Finance 15m delay."""
        if not symbol.endswith(".NS") and "." in symbol:
            return None  # Only attempt for NSE stocks, not BSE (.BO) or indices
            
        clean_symbol = symbol.replace('.NS', '').upper()
        
        try:
            session = await NSEScraper.get_session()
            url = f"{NSE_API_URL}/quote-equity?symbol={clean_symbol}"
            
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if "priceInfo" in data:
                        price_info = data["priceInfo"]
                        last_price = float(price_info.get("lastPrice", 0))
                        prev_close = float(price_info.get("previousClose", 0))
                        
                        if last_price > 0:
                            return {
                                "symbol": symbol,
                                "price": round(last_price, 2),
                                "previous_close": round(prev_close, 2),
                                "change": round(last_price - prev_close, 2),
                                "change_pct": round(float(price_info.get("pChange", 0)), 2),
                                "volume": int(data.get("preOpenMarket", {}).get("totalTradedVolume", 0) or 0),
                                "market_cap": 0, # NSE doesn't provide this here
                                "52w_high": float(price_info.get("weekHighLow", {}).get("max", 0) or 0),
                                "52w_low": float(price_info.get("weekHighLow", {}).get("min", 0) or 0),
                                "timestamp": data.get("metadata", {}).get("lastUpdateTime") or time_sync.get_true_now().isoformat(),
                                "data_status": "realtime",
                                "source": "NSE Real-Time API",
                            }
                return None
        except Exception as e:
            logger.debug(f"Failed to fetch real-time quote for {symbol} from NSE: {e}")
            return None

    @staticmethod
    async def fetch_index_quotes() -> dict[str, dict]:
        """Fetch official NSE index values when the public NSE endpoint is available."""
        cache_key = "nse:index_quotes"
        cached = await cache_get(cache_key)
        if cached:
            return cached
        try:
            session = await NSEScraper.get_session()
            async with session.get(f"{NSE_API_URL}/allIndices", timeout=10) as response:
                if response.status != 200:
                    logger.warning("NSE index endpoint returned status %s", response.status)
                    return {}
                payload = await response.json()
            output: dict[str, dict] = {}
            for item in payload.get("data", []):
                name = str(item.get("index", "")).upper()
                if name not in {"NIFTY 50", "NIFTY BANK"}:
                    continue
                try:
                    price = float(item.get("last", 0) or 0)
                    previous_close = float(item.get("previousClose", 0) or 0)
                    change = float(item.get("variation", price - previous_close) or 0)
                    change_pct = float(item.get("percentChange", (change / previous_close * 100 if previous_close else 0)) or 0)
                except (TypeError, ValueError):
                    continue
                if price <= 0:
                    continue
                output[name] = {
                    "price": round(price, 2),
                    "previous_close": round(previous_close, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "timestamp": item.get("lastUpdateTime") or datetime.now(timezone.utc).isoformat(),
                    "data_status": "exchange_feed",
                    "source": "NSE public index feed",
                }
            await cache_set(cache_key, output, ttl=15)
            return output
        except Exception as exc:
            logger.warning("Official NSE index feed unavailable: %s", exc)
            return {}

    @staticmethod
    async def fetch_market_breadth() -> Optional[dict]:
        """
        Estimate market breadth from Nifty 500 stocks.
        Returns advance/decline ratio and % stocks above key EMAs.
        """
        cache_key = "market_breadth"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        # Simplified: use a subset of Nifty 50 for MVP
        SAMPLE_SYMBOLS = [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
            "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BAJFINANCE.NS", "KOTAKBANK.NS",
            "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS",
            "TITAN.NS", "NTPC.NS", "POWERGRID.NS", "ULTRACEMCO.NS", "WIPRO.NS",
        ]

        try:
            import yfinance as yf
            import pandas as pd

            advancing = 0
            declining = 0
            above_200ema = 0
            total = 0

            for sym in SAMPLE_SYMBOLS:
                try:
                    ticker = yf.Ticker(sym)
                    hist = await asyncio.to_thread(ticker.history, period="1y", interval="1d")
                    if len(hist) < 10:
                        continue

                    close = hist["Close"]
                    ema200 = close.ewm(span=200).mean().iloc[-1]
                    latest = close.iloc[-1]
                    prev = close.iloc[-2]

                    if latest > prev:
                        advancing += 1
                    elif latest < prev:
                        declining += 1

                    if latest > ema200:
                        above_200ema += 1

                    total += 1
                    await asyncio.sleep(0.2)
                except Exception:
                    continue

            result = {
                "advancing": advancing,
                "declining": declining,
                "unchanged": total - advancing - declining,
                "advance_decline_ratio": round(advancing / declining, 2) if declining > 0 else float("inf"),
                "pct_above_200ema": round(above_200ema / total * 100, 1) if total > 0 else 0,
                "breadth_signal": "bullish" if advancing > declining else "bearish",
                "sample_size": total,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await cache_set(cache_key, result, ttl=1800)  # 30 min cache
            return result
        except Exception as e:
            logger.error(f"Failed to compute market breadth: {e}")
            return None

    @staticmethod
    async def fetch_sector_performance() -> list[dict]:
        """Fetch performance of major NSE sector indices."""
        cache_key = "sector_performance"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        SECTOR_INDICES = {
            "Nifty Bank": "^NSEBANK",
            "Nifty IT": "^CNXIT",
            "Nifty Pharma": "^CNXPHARMA",
            "Nifty Auto": "^CNXAUTO",
            "Nifty FMCG": "^CNXFMCG",
            "Nifty Metal": "^CNXMETAL",
            "Nifty Realty": "^CNXREALTY",
            "Nifty Energy": "^CNXENERGY",
            "Nifty Infra": "^CNXINFRA",
        }

        try:
            import yfinance as yf
            result = []
            for name, sym in SECTOR_INDICES.items():
                try:
                    ticker = yf.Ticker(sym)
                    info = await asyncio.to_thread(lambda: ticker.fast_info)
                    price = float(info.last_price or 0)
                    prev_close = float(info.previous_close or 0)
                    change_pct = (price - prev_close) / prev_close * 100 if prev_close else 0

                    result.append({
                        "name": name,
                        "symbol": sym,
                        "price": round(price, 2),
                        "change_pct": round(change_pct, 2),
                        "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
                    })
                    await asyncio.sleep(0.1)
                except Exception:
                    continue

            # Sort by performance
            result.sort(key=lambda x: x["change_pct"], reverse=True)
            await cache_set(cache_key, result, ttl=300)
            return result
        except Exception as e:
            logger.error(f"Failed to fetch sector performance: {e}")
            return []

    @staticmethod
    def get_nse_holidays() -> list[str]:
        """Return list of NSE holidays for 2026."""
        return NSE_HOLIDAYS_2026.copy()

    @staticmethod
    async def fetch_fii_dii_flows() -> Optional[dict]:
        """Fetch FII/DII provisional flow data."""
        cache_key = "fii_dii_flows"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        try:
            session = await NSEScraper.get_session()
            url = f"{NSE_API_URL}/fiidiiTradeReact"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    await cache_set(cache_key, data, ttl=3600)  # 1 hour cache
                    return data
                else:
                    logger.warning(f"FII/DII flow returned status {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Failed to fetch FII/DII flow: {e}")
            return None

    @staticmethod
    async def fetch_delivery_data(symbol: str) -> Optional[dict]:
        """Fetch delivery percentage data for a symbol from NSE."""
        clean_symbol = symbol.replace('.NS', '').upper()
        cache_key = f"delivery_{clean_symbol}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        try:
            session = await NSEScraper.get_session()
            url = f"{NSE_API_URL}/quote-equity?symbol={clean_symbol}&section=trade_info"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    security_info = data.get("securityWiseDP", {})
                    result = {
                        "symbol": symbol,
                        "quantity_traded": security_info.get("quantityTraded", 0),
                        "delivery_quantity": security_info.get("deliveryQuantity", 0),
                        "delivery_percentage": security_info.get("deliveryToTradedQuantity", 0),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    await cache_set(cache_key, result, ttl=3600)
                    return result
                return None
        except Exception as e:
            logger.error(f"Failed to fetch delivery data for {symbol}: {e}")
            return None

    @staticmethod
    async def fetch_corporate_actions(symbol: str) -> Optional[dict]:
        """Fetch dividends and splits using yfinance."""
        cache_key = f"actions_{symbol}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            actions = await asyncio.to_thread(lambda: ticker.actions)
            
            if actions is None or actions.empty:
                return {"dividends": [], "splits": []}
            
            # Convert DataFrame to list of dicts, parsing timestamps
            dividends = []
            splits = []
            
            for index, row in actions.iterrows():
                date_str = index.strftime("%Y-%m-%d") if hasattr(index, "strftime") else str(index)
                if 'Dividends' in row and row['Dividends'] > 0:
                    dividends.append({"date": date_str, "amount": float(row['Dividends'])})
                if 'Stock Splits' in row and row['Stock Splits'] > 0:
                    splits.append({"date": date_str, "ratio": float(row['Stock Splits'])})

            result = {
                "symbol": symbol,
                "dividends": sorted(dividends, key=lambda x: x["date"], reverse=True),
                "splits": sorted(splits, key=lambda x: x["date"], reverse=True),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await cache_set(cache_key, result, ttl=86400)  # 24 hour cache
            return result
        except Exception as e:
            logger.error(f"Failed to fetch corporate actions for {symbol}: {e}")
            return None


nse_scraper = NSEScraper()
