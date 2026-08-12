"""
News Scraper Module — Fetches recent headlines for a stock ticker via Google News RSS.
"""

from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import feedparser
from urllib.parse import quote_plus
from backend.core.logging_config import get_logger
from backend.core.cache import cache_get, cache_set
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
    if cached:
        return cached

    try:
        # Run feedparser in a thread since it does blocking HTTP requests
        feed = await asyncio.wait_for(asyncio.to_thread(feedparser.parse, rss_url), timeout=5.0)
        
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
                # If we cannot verify the date, skip it to be safe
                continue

            articles.append({
                "title": entry.title,
                "link": entry.link,
                "published": pub_date_str,
                "source": source
            })
            
            if len(articles) >= 10:
                break
            
        # Cache for 2 hours
        await cache_set(cache_key, articles, ttl=7200)
        return articles
        
    except Exception as e:
        logger.error(f"Failed to fetch news for {symbol}: {e}")
        return []
