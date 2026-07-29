"""Ensemble Model combining LightGBM, Rules, and NLP Sentiment."""

import pandas as pd
from backend.services.ml.model import ml_engine
from backend.services.ml.calibration import calibrator
from backend.services.market_data import market_data_service
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

class EnsemblePredictor:
    def __init__(self):
        # Weights for the ensemble members
        self.weights = {
            "lightgbm": 0.5,
            "rules": 0.3,
            "sentiment": 0.2
        }

    async def predict(self, symbol: str) -> dict:
        """
        Runs the full ensemble prediction for a given symbol.
        """
        logger.info(f"Running ensemble prediction for {symbol}")
        
        # 1. Get LightGBM Base Prediction
        lgbm_result = await ml_engine.predict_stock(symbol)
        
        # 2. Get Rules Base Prediction (from the dataframe indicators)
        candles = await market_data_service.fetch_candles(symbol, limit=60)
        df = pd.DataFrame(candles)
        
        rule_score = 0.5 # Neutral
        if len(df) > 14:
            from ta.momentum import RSIIndicator
            from ta.trend import MACD
            df["rsi"] = RSIIndicator(df["Close"], window=14).rsi()
            macd = MACD(df["Close"])
            df["macd_diff"] = macd.macd_diff()
            
            last_rsi = df["rsi"].iloc[-1]
            last_macd = df["macd_diff"].iloc[-1]
            
            # Simple rule mapping to 0.0 - 1.0 probability
            if last_rsi < 30 and last_macd > 0:
                rule_score = 0.8
            elif last_rsi > 70 and last_macd < 0:
                rule_score = 0.2
            else:
                rule_score = 0.5 + (last_macd * 0.1) # slight bias
                rule_score = max(0.0, min(1.0, rule_score))
                
        # 3. Get NLP Sentiment (mocking real NLP call for now)
        sentiment_score = 0.5
        news = await market_data_service.fetch_news(symbol)
        if news:
            sentiments = [n.get("sentiment_score", 0.5) for n in news]
            sentiment_score = sum(sentiments) / len(sentiments)
            
        # 4. Ensemble Voting (Weighted Average)
        raw_lgbm_prob = lgbm_result.get("probability", 0.5) if lgbm_result.get("direction") == "BULLISH" else (1 - lgbm_result.get("probability", 0.5))
        
        raw_ensemble_prob = (
            raw_lgbm_prob * self.weights["lightgbm"] +
            rule_score * self.weights["rules"] +
            sentiment_score * self.weights["sentiment"]
        )
        
        # 5. Calibration
        calibrated_prob = calibrator.calibrate(raw_ensemble_prob)
        
        direction = "BULLISH" if calibrated_prob > 0.55 else "BEARISH" if calibrated_prob < 0.45 else "NEUTRAL"
        confidence = abs(calibrated_prob - 0.5) * 2 # scale 0 to 1
        
        return {
            "symbol": symbol,
            "direction": direction,
            "confidence": round(confidence, 3),
            "calibrated_probability": round(calibrated_prob, 3),
            "breakdown": {
                "lightgbm_prob": round(raw_lgbm_prob, 3),
                "rule_prob": round(rule_score, 3),
                "sentiment_prob": round(sentiment_score, 3)
            },
            "features_snapshot": {
                "lgbm_features": lgbm_result.get("features", {}),
                "last_price": float(df["Close"].iloc[-1]) if len(df) else None
            }
        }

ensemble_predictor = EnsemblePredictor()
