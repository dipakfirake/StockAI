"""
AI scoring engine — Phase 11 (Multi-Cap LightGBM + SHAP).
Predicts 5-day forward return probabilities natively supporting penny stocks vs large caps.
"""

from __future__ import annotations
import os
import numpy as np
import pandas as pd
import lightgbm as lgb
import shap
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
MODEL_LARGE_PATH = os.path.join(MODEL_DIR, "lgb_model_largecap.txt")
MODEL_SMALL_PATH = os.path.join(MODEL_DIR, "lgb_model_smallcap.txt")

FEATURES = [
    'rsi_14', 'rsi_z', 'macd_hist', 'stoch_k', 'cci_20',
    'atr_pct', 'bb_pct_b', 'bb_width_norm',
    'ema9_ratio', 'ema21_ratio', 'ema_cross', 'golden_death',
    'adx_14', 'price_return_5d', 'price_return_20d', 'vol_ratio'
]

# Quick heuristic to map common stocks to Large vs Small if market cap API fails
LARGE_CAP_SYMBOLS = {"RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "HINDUNILVR.NS", "LT.NS"}

class AIEngineService:
    def __init__(self):
        self.models = {}
        self.explainers = {}
        self._load_models()

    def _load_models(self):
        try:
            if os.path.exists(MODEL_LARGE_PATH):
                self.models["large"] = lgb.Booster(model_file=MODEL_LARGE_PATH)
                self.explainers["large"] = shap.TreeExplainer(self.models["large"])
                
            if os.path.exists(MODEL_SMALL_PATH):
                self.models["small"] = lgb.Booster(model_file=MODEL_SMALL_PATH)
                self.explainers["small"] = shap.TreeExplainer(self.models["small"])
                
            logger.info(f"Loaded {len(self.models)} ML models (Large/Small cap routing active).")
        except Exception as e:
            logger.error(f"Failed to load LightGBM models: {e}")

    def score(self, indicators: dict, symbol: str = "", market_cap: float = 0) -> dict:
        """
        Compute ML AI score using LightGBM with robust scale-independent features.
        Routes to the SmallCap or LargeCap model based on symbol/cap.
        """
        # Determine model to use
        model_key = "small"
        if symbol in LARGE_CAP_SYMBOLS or market_cap > 500000000000: # 50,000 Cr+
            model_key = "large"
            
        model = self.models.get(model_key) or self.models.get("large") or self.models.get("small")
        explainer = self.explainers.get(model_key) or self.explainers.get("large") or self.explainers.get("small")
        
        if model is None or not all(k in indicators for k in ['rsi_14', 'macd', 'ema_9']):
            return self._neutral_response(symbol, indicators)
            
        try:
            def _safe_float(val, default=0.0):
                try:
                    return float(val) if val is not None else default
                except (ValueError, TypeError):
                    return default

            # Safely extract and compute normalized features
            price = _safe_float(indicators.get("close", 1.0), 1.0)
            if price == 0: price = 1.0
            
            rsi_14 = _safe_float(indicators.get("rsi_14", 50.0), 50.0)
            rsi_z = (rsi_14 - 50.0) / 15.0
            
            macd_dict = indicators.get("macd") or {}
            macd_hist = _safe_float(macd_dict.get("histogram", 0.0))
            stoch_k = _safe_float(indicators.get("stoch_k", 50.0), 50.0)
            cci_20 = _safe_float(indicators.get("cci_20", 0.0))
            
            atr = _safe_float(indicators.get("atr_14", price * 0.02), price * 0.02)
            atr_pct = atr / price
            
            bb = indicators.get("bb") or {}
            bb_upper = _safe_float(bb.get("upper", price * 1.05), price * 1.05)
            bb_lower = _safe_float(bb.get("lower", price * 0.95), price * 0.95)
            bb_mid = _safe_float(bb.get("middle", price), price)
            bb_pct_b = (price - bb_lower) / (bb_upper - bb_lower + 1e-8)
            bb_width_norm = (bb_upper - bb_lower) / (bb_mid + 1e-8)
            
            ema_9 = _safe_float(indicators.get("ema_9", price), price)
            ema_21 = _safe_float(indicators.get("ema_21", price), price)
            ema_50 = _safe_float(indicators.get("ema_50", price), price)
            sma_200 = _safe_float(indicators.get("sma_200", price), price)
            
            ema9_ratio = price / (ema_9 + 1e-8) - 1
            ema21_ratio = price / (ema_21 + 1e-8) - 1
            ema_cross = ema_9 / (ema_21 + 1e-8) - 1
            golden_death = 1 if ema_50 > sma_200 else -1
            
            adx_14 = _safe_float(indicators.get("adx_14", 20.0), 20.0)
            
            # Since we don't have historical arrays here, we mock the momentum for real-time inference
            price_return_5d = ema9_ratio * 2.0  # Approximation
            price_return_20d = ema21_ratio * 1.5 # Approximation
            
            vol = _safe_float(indicators.get("volume", 0.0))
            vol_sma20 = _safe_float(indicators.get("vol_sma_20", 1.0), 1.0)
            if vol_sma20 == 0: vol_sma20 = 1.0
            vol_ratio = vol / vol_sma20
            
            feature_vector = [
                rsi_14, rsi_z, macd_hist, stoch_k, cci_20,
                atr_pct, bb_pct_b, bb_width_norm,
                ema9_ratio, ema21_ratio, ema_cross, golden_death,
                adx_14, price_return_5d, price_return_20d, vol_ratio
            ]
            
            X = pd.DataFrame([feature_vector], columns=FEATURES)
            prob_up = float(model.predict(X)[0])
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
            confidence = max(probs.values())

            # SHAP Explanations
            shap_values = explainer.shap_values(X)
            if isinstance(shap_values, list): 
                shap_vals = shap_values[1][0]
            else:
                shap_vals = shap_values[0]

            explanations = []
            for i, feature in enumerate(FEATURES):
                contrib = float(shap_vals[i])
                if abs(contrib) > 0.01:
                    explanations.append({
                        "feature": feature.upper(),
                        "value": round(float(X.iloc[0, i]), 4),
                        "contribution": round(abs(contrib), 4),
                        "direction": "bullish" if contrib > 0 else "bearish",
                        "reason": f"{model_key.capitalize()}Cap Model identified {feature} as {'bullish' if contrib > 0 else 'bearish'}"
                    })

            explanations = sorted(explanations, key=lambda x: x["contribution"], reverse=True)[:5]

            return {
                "symbol": symbol,
                "score": direction,
                "probabilities": probs,
                "confidence": round(confidence, 4),
                "model": f"lightgbm_v3_{model_key}cap",
                "explanation": explanations,
            }
        except Exception as e:
            logger.error(f"Error in ML scoring for {symbol}: {e}")
            return self._neutral_response(symbol, indicators)

    def _neutral_response(self, symbol: str, indicators: dict = None) -> dict:
        if indicators is None:
            indicators = {}
            
        rsi = float(indicators.get('rsi_14', 50))
        z_rsi = (rsi - 50) / 15.0
        
        price = float(indicators.get("close", 1))
        ema9 = float(indicators.get('ema_9', price))
        ema21 = float(indicators.get('ema_21', price))
        
        z_ema = 1.5 if ema9 > ema21 else -1.5
        
        total_z = (z_rsi + z_ema) / 2.0
        
        import math
        prob_up = 1.0 / (1.0 + math.exp(-total_z))
        prob_down = 1.0 - prob_up
        
        if prob_up > 0.60:
            direction = "BUY"
        elif prob_down > 0.60:
            direction = "SELL"
        else:
            direction = "HOLD"
            
        return {
            "symbol": symbol,
            "score": direction,
            "probabilities": {"buy": round(prob_up, 4), "hold": round(1.0 - abs(prob_up - prob_down), 4), "sell": round(prob_down, 4)},
            "confidence": round(max(prob_up, prob_down), 4),
            "model": "math_zscore_fallback",
            "explanation": [
                {"feature": "RSI_Z", "value": round(z_rsi, 2), "contribution": abs(z_rsi), "direction": "bullish" if z_rsi > 0 else "bearish", "reason": "RSI momentum"},
                {"feature": "EMA_Z", "value": round(z_ema, 2), "contribution": abs(z_ema), "direction": "bullish" if z_ema > 0 else "bearish", "reason": "Short-term trend"}
            ],
        }

ai_engine_service = AIEngineService()
