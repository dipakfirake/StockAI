"""
NLP Engine — Market Sentiment Analysis using VADER.
Phase 10: Extracts sentiment polarity from news headlines to augment ML models.
"""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

class NLPEngineService:
    def __init__(self):
        self.analyzer = SentimentIntensityAnalyzer()
        
        # Add custom financial domain lexicons for better accuracy
        custom_lexicon = {
            "bullish": 2.0, "bearish": -2.0,
            "surge": 1.5, "plunge": -1.5,
            "rally": 1.5, "crash": -2.0,
            "upgrade": 1.0, "downgrade": -1.0,
            "outperform": 1.5, "underperform": -1.5,
            "beat": 1.0, "miss": -1.0,
            "dividend": 0.5, "buyback": 1.0,
            "profit": 1.0, "loss": -1.0,
            "default": -2.0, "bankruptcy": -3.0
        }
        self.analyzer.lexicon.update(custom_lexicon)

    def analyze_headlines(self, articles: list[dict]) -> dict:
        """
        Analyze sentiment for a list of news articles.
        Returns aggregate sentiment metrics and individual article scores.
        """
        if not articles:
            return {
                "overall_sentiment": "NEUTRAL",
                "compound_score": 0.0,
                "scored_articles": []
            }

        scored_articles = []
        total_compound = 0.0

        for article in articles:
            text = article.get("title", "")
            scores = self.analyzer.polarity_scores(text)
            compound = scores["compound"]
            total_compound += compound
            
            # Map compound to label
            if compound >= 0.05:
                label = "POSITIVE"
            elif compound <= -0.05:
                label = "NEGATIVE"
            else:
                label = "NEUTRAL"
                
            scored_articles.append({
                **article,
                "sentiment_score": round(compound, 3),
                "sentiment_label": label
            })

        avg_compound = total_compound / len(articles)
        
        if avg_compound >= 0.15:
            overall = "BULLISH"
        elif avg_compound <= -0.15:
            overall = "BEARISH"
        else:
            overall = "NEUTRAL"

        return {
            "overall_sentiment": overall,
            "compound_score": round(avg_compound, 3),
            "scored_articles": scored_articles
        }

nlp_engine_service = NLPEngineService()
