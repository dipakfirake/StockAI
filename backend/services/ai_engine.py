"""
AI scoring engine — Phase 9 (LightGBM + SHAP).
Predicts 5-day forward return probabilities and provides SHAP feature contributions.
"""

from __future__ import annotations
import os
import numpy as np
import pandas as pd
import lightgbm as lgb
import shap
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "lgb_model.txt")
FEATURES = ['rsi_14', 'macd', 'macd_hist', 'ema_9', 'ema_21', 'ema_50', 'bb_width', 'adx_14']

class AIEngineService:
    def __init__(self):
        self.model = None
        self.explainer = None
        self._load_model()

    def _load_model(self):
        if os.path.exists(MODEL_PATH):
            try:
                self.model = lgb.Booster(model_file=MODEL_PATH)
                self.explainer = shap.TreeExplainer(self.model)
                logger.info("LightGBM model and SHAP explainer loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load LightGBM model: {e}")
        else:
            logger.warning("LightGBM model not found. Using fallback neutral logic.")

    def score(self, indicators: dict, symbol: str = "") -> dict:
        """
        Compute ML AI score from indicator dict using LightGBM.
        Returns probabilities, confidence, and SHAP-style explanation.
        """
        if self.model is None or not all(k in indicators for k in ['rsi_14', 'macd', 'ema_9', 'ema_21', 'ema_50', 'bb']):
            return self._neutral_response(symbol, indicators)
        
        try:
            # Extract features matching the training script
            feature_vector = [
                indicators.get('rsi_14', 50),
                indicators.get('macd', {}).get('macd', 0),
                indicators.get('macd', {}).get('histogram', 0),
                indicators.get('ema_9', 0),
                indicators.get('ema_21', 0),
                indicators.get('ema_50', 0),
                self._compute_bb_width(indicators.get('bb', {})),
                indicators.get('adx_14', 20)
            ]
            
            # Predict
            X = pd.DataFrame([feature_vector], columns=FEATURES)
            prob_up = float(self.model.predict(X)[0])
            prob_down = 1.0 - prob_up
            
            # Score logic
            if prob_up > 0.60:
                direction = "BUY"
            elif prob_down > 0.60:
                direction = "SELL"
            else:
                direction = "HOLD"

            probs = {
                "buy": round(prob_up * 0.8, 4), 
                "hold": round(0.2, 4), 
                "sell": round(prob_down * 0.8, 4)
            }
            confidence = max(probs.values())

            # SHAP Explanations
            shap_values = self.explainer.shap_values(X)
            if isinstance(shap_values, list): # depending on SHAP version/objective
                shap_vals = shap_values[1][0]
            else:
                shap_vals = shap_values[0]

            explanations = []
            for i, feature in enumerate(FEATURES):
                contrib = float(shap_vals[i])
                if abs(contrib) > 0.05: # Only show meaningful features
                    explanations.append({
                        "feature": feature.upper(),
                        "value": round(float(X.iloc[0, i]), 4),
                        "contribution": round(abs(contrib), 4),
                        "direction": "bullish" if contrib > 0 else "bearish",
                        "reason": f"Model identified {feature} as {'bullish' if contrib > 0 else 'bearish'}"
                    })

            # Sort by absolute contribution
            explanations = sorted(explanations, key=lambda x: x["contribution"], reverse=True)[:5]

            return {
                "symbol": symbol,
                "score": direction,
                "probabilities": probs,
                "confidence": round(confidence, 4),
                "model": "lightgbm_v1",
                "explanation": explanations,
            }
        except Exception as e:
            logger.error(f"Error in ML scoring for {symbol}: {e}")
            return self._neutral_response(symbol, indicators)

    def _compute_bb_width(self, bb: dict) -> float:
        upper = bb.get('upper', 0)
        lower = bb.get('lower', 1)
        if lower == 0: return 0
        return (upper - lower) / lower

    def _neutral_response(self, symbol: str, indicators: dict = None) -> dict:
        if indicators is None:
            indicators = {}
            
        # Probabilistic Z-Score Fallback Model
        rsi = indicators.get('rsi_14', 50)
        ema9 = indicators.get('ema_9', 0)
        ema21 = indicators.get('ema_21', 0)
        
        # Calculate approximate Z-scores
        z_rsi = (rsi - 50) / 15.0
        z_ema = 1.5 if (ema9 and ema21 and ema9 > ema21) else -1.5 if (ema9 and ema21) else 0.0
        
        total_z = (z_rsi + z_ema) / 2.0
        
        # Sigmoid to get probability
        import math
        prob_up = 1.0 / (1.0 + math.exp(-total_z))
        prob_down = 1.0 - prob_up
        
        if prob_up > 0.60:
            direction = "BUY"
        elif prob_down > 0.60:
            direction = "SELL"
        else:
            direction = "HOLD"
            
        probs = {
            "buy": round(prob_up, 4), 
            "hold": round(1.0 - abs(prob_up - prob_down), 4), 
            "sell": round(prob_down, 4)
        }
        
        # Normalize probs
        total = sum(probs.values())
        probs = {k: round(v/total, 4) for k, v in probs.items()}
        
        confidence = max(probs.values())

        return {
            "symbol": symbol,
            "score": direction,
            "probabilities": probs,
            "confidence": round(confidence, 4),
            "model": "probabilistic_zscore_fallback",
            "explanation": [
                {"feature": "RSI_Z", "value": round(z_rsi, 2), "contribution": abs(z_rsi), "direction": "bullish" if z_rsi > 0 else "bearish", "reason": "RSI momentum probability"},
                {"feature": "EMA_Z", "value": round(z_ema, 2), "contribution": abs(z_ema), "direction": "bullish" if z_ema > 0 else "bearish", "reason": "Short-term trend probability"}
            ],
        }

ai_engine_service = AIEngineService()
