"""
ML & NLP API router — Phase 9 & 10.
"""

from fastapi import APIRouter, Depends
from backend.core.auth import get_current_user, require_pro_tier
from backend.data.ingestion.news_scraper import fetch_stock_news
from backend.services.nlp_engine import nlp_engine_service

router = APIRouter()

@router.get("/sentiment/{symbol}")
async def get_news_sentiment(
    symbol: str,
    current_user=Depends(require_pro_tier)
):
    """
    Fetch recent news for a stock and analyze sentiment.
    """
    articles = await fetch_stock_news(symbol)
    sentiment_result = nlp_engine_service.analyze_headlines(articles)
    
    return {
        "symbol": symbol,
        "sentiment": sentiment_result
    }
