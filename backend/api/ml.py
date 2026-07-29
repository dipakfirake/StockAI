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

from backend.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

@router.get("/ensemble/predict", dependencies=[Depends(get_current_user)])
async def get_ensemble_prediction(
    symbol: str, 
    db: AsyncSession = Depends(get_db)
):
    """Get weighted ensemble prediction (LightGBM + Rules + Sentiment)."""
    try:
        from backend.services.ml.ensemble import ensemble_predictor
        from backend.models.prediction_archive import PredictionArchive
        
        result = await ensemble_predictor.predict(symbol)
        
        # Archive the prediction
        archive = PredictionArchive(
            symbol=symbol,
            prediction_type="ensemble",
            predicted_value=result["direction"],
            confidence=result["confidence"],
            features_snapshot=result["features_snapshot"]
        )
        db.add(archive)
        await db.commit()
        
        return result
    except Exception as e:
        import logging
        logging.error(f"Ensemble prediction error: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Prediction failed")

@router.get("/regime/lstm", dependencies=[Depends(get_current_user)])
async def get_lstm_regime(
    symbol: str,
    db: AsyncSession = Depends(get_db)
):
    """Get market regime from LSTM sequence model."""
    try:
        from backend.services.market_data import market_data_service
        from backend.services.ml.lstm_model import lstm_predictor
        import pandas as pd
        
        candles = await market_data_service.fetch_candles(symbol, limit=60)
        df = pd.DataFrame(candles)
        
        result = lstm_predictor.predict(df)
        
        # Archive it
        from backend.models.prediction_archive import PredictionArchive
        archive = PredictionArchive(
            symbol=symbol,
            prediction_type="lstm_regime",
            predicted_value=result["regime"],
            confidence=result["confidence"],
            features_snapshot={"last_price": float(df["Close"].iloc[-1]) if len(df) else None}
        )
        db.add(archive)
        await db.commit()
        
        return result
    except Exception as e:
        import logging
        logging.error(f"LSTM regime error: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="LSTM failed")
