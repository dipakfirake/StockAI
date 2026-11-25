"""
News Scraper Module — Fetches recent headlines for a stock ticker via Google News RSS.
"""

from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import feedparser
import httpx
from urllib.parse import quote_plus
from backend.core.logging_config import get_logger
from backend.core.cache import cache_get, cache_set
from backend.core.cache_manager import cache_manager
from backend.core.executors import run_in_scraper_executor
import asyncio

logger = get_logger(__name__)

TRUSTED_SOURCES = [
    "Moneycontrol",
    "The Economic Times",
    "Economic Times",
    "Livemint",
    "Mint",
    "CNBC TV18",
    "CNBC",
    "NDTV Profit",
    "Business Standard",
    "Reuters",
    "Bloomberg",
    "Financial Express",
    "BQ Prime",
    "Zee Business",
    "The Hindu Business Line",
    "BusinessLine",
    "Capital Market",
    "Trendlyne",
    "Screener",
    "Business Today",
    "Yahoo Finance",
    "Investing.com"
]

async def fetch_stock_news(symbol: str) -> list[dict]:
    """
    Fetch recent news headlines for a given stock symbol using Google News RSS.
    Filters out unreliable sources and news older than 30 days.
    """
    clean_symbol = symbol.replace('.NS', '').replace('.BO', '')
    query = quote_plus(f'"{clean_symbol}" stock AND NSE')
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    cache_key = f"news_v3:{clean_symbol}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    async def _fetch_once() -> list[dict]:
        inner_cached = await cache_get(cache_key)
        if inner_cached is not None:
            return inner_cached

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; StockAI/1.0)",
                "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
            }
            async with httpx.AsyncClient(headers=headers, timeout=2.5, follow_redirects=True) as client:
                resp = await client.get(rss_url)
                if resp.status_code != 200 or not resp.text:
                    await cache_set(cache_key, [], ttl=300)
                    return []
                rss_body = resp.text

            # Offload XML/RSS parsing to bounded scraper executor
            feed = await asyncio.wait_for(
                run_in_scraper_executor(feedparser.parse, rss_body),
                timeout=2.5,
            )

            articles = []
            now = datetime.now(timezone.utc)

            for entry in feed.entries:
                source = getattr(entry, "source", {}).get("title", "Google News")

                # 1. Trusted Source Check
                if not any(trusted.lower() in source.lower() for trusted in TRUSTED_SOURCES):
                    continue

                # 2. Recency Check (Exclude news older than 30 days)
                pub_date_str = getattr(entry, "published", "")
                if not pub_date_str:
                    continue

                try:
                    pub_date = parsedate_to_datetime(pub_date_str)
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                    if (now - pub_date) > timedelta(days=30):
                        continue
                except Exception:
                    continue

                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "published": pub_date_str,
                    "source": source,
                })

                if len(articles) >= 10:
                    break

            # Cache hits for 2 hours, empty responses for 10 min to prevent RSS spam
            ttl = 7200 if articles else 600
            await cache_set(cache_key, articles, ttl=ttl)
            return articles

        except Exception as e:
            logger.debug(f"Failed to fetch news for {symbol}: {e}")
            try:
                await cache_set(cache_key, [], ttl=300)
            except Exception:
                pass
            return []

    return await cache_manager.single_flight.execute(f"sf:{cache_key}", _fetch_once)
