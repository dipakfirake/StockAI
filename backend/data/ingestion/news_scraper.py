"""
News Scraper Module — Fetches recent headlines for a stock ticker via Google News RSS.
"""

import feedparser
from urllib.parse import quote_plus
from backend.core.logging_config import get_logger
from backend.core.cache import cache_get, cache_set
import asyncio

logger = get_logger(__name__)

async def fetch_stock_news(symbol: str) -> list[dict]:
    """
    Fetch recent news headlines for a given stock symbol using Google News RSS.
    Returns a list of dicts with 'title', 'link', 'published', and 'source'.
    """
    clean_symbol = symbol.replace('.NS', '').replace('.BO', '')
    query = quote_plus(f'"{clean_symbol}" stock AND NSE')
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    cache_key = f"news:{clean_symbol}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    try:
        # Run feedparser in a thread since it does blocking HTTP requests
        feed = await asyncio.to_thread(feedparser.parse, rss_url)
        
        articles = []
        for entry in feed.entries[:10]:  # Top 10 recent articles
            articles.append({
                "title": entry.title,
                "link": entry.link,
                "published": getattr(entry, "published", ""),
                "source": getattr(entry, "source", {}).get("title", "Google News")
            })
            
        # Cache for 2 hours (news doesn't change every minute)
        await cache_set(cache_key, articles, ttl=7200)
        return articles
        
    except Exception as e:
        logger.error(f"Failed to fetch news for {symbol}: {e}")
        return []
