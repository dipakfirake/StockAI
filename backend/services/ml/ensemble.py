"""
Ensemble Meta-Learner: LightGBM + BiLSTM + Temporal Transformer.

Stacking strategy:
  - LightGBM produces 3-class probabilities from tabular features
  - BiLSTM produces 3-class probabilities from 60-bar sequence
  - Transformer produces 3-class probabilities from 60-bar sequence
  - Final output = weighted average (weights defined in ENSEMBLE_WEIGHTS)

Weights are chosen so DL models get higher weight when available:
  all-available:  LGBMx0.30 + LSTMx0.40 + Transformerx0.30
  no-DL:          LGBM only  (100%)
  no-transformer: LGBMx0.40 + LSTMx0.60

The ensemble degrades gracefully — if DL models are not trained yet,
it returns LightGBM predictions unchanged.
"""

from __future__ import annotations

import numpy as np
import logging

logger = logging.getLogger(__name__)

# Default ensemble weights (sum to 1.0)
ENSEMBLE_WEIGHTS = {
    "lgb":         0.30,
    "lstm":        0.40,
    "transformer": 0.30,
}


class EnsemblePredictor:
    """
    Combines LightGBM, LSTM, and Transformer predictions into a single
    calibrated 3-class probability vector [sell, hold, buy].
    """

    def predict(
        self,
        lgb_probs: np.ndarray | None,
        lstm_probs: np.ndarray | None,
        transformer_probs: np.ndarray | None,
    ) -> np.ndarray:
        """
        Combine sub-model probability vectors.

        Args:
            lgb_probs: (3,) array [sell, hold, buy] from LightGBM, or None
            lstm_probs: (3,) array from BiLSTM, or None
            transformer_probs: (3,) array from Transformer, or None

        Returns:
            ensemble_probs: (3,) normalized probability array [sell, hold, buy]
        """
        available = {}

        if lgb_probs is not None and len(lgb_probs) == 3:
            available["lgb"] = np.array(lgb_probs, dtype=np.float64)
        if lstm_probs is not None and len(lstm_probs) == 3:
            available["lstm"] = np.array(lstm_probs, dtype=np.float64)
        if transformer_probs is not None and len(transformer_probs) == 3:
            available["transformer"] = np.array(transformer_probs, dtype=np.float64)

        if not available:
            # Completely blind — uniform distribution
            return np.array([1 / 3, 1 / 3, 1 / 3], dtype=np.float32)

        if len(available) == 1:
            # Only one model available — return its probabilities directly
            return list(available.values())[0].astype(np.float32)

        # Weighted average using configured weights, renormalised by available models
        weights = {k: ENSEMBLE_WEIGHTS.get(k, 0.33) for k in available}
        total_weight = sum(weights.values())
        combined = np.zeros(3, dtype=np.float64)
        for k, probs in available.items():
            combined += (weights[k] / total_weight) * probs

        # Normalise to ensure it sums to exactly 1.0
        combined = combined / (combined.sum() + 1e-8)
        return combined.astype(np.float32)

    def decode(self, probs: np.ndarray) -> tuple[str, float]:
        """
        Convert probability vector to direction label and confidence.

        Returns:
            direction: "BUY", "HOLD", or "SELL"
            confidence: float in [0, 1]
        """
        labels = ["SELL", "HOLD", "BUY"]
        idx = int(np.argmax(probs))
        return labels[idx], float(probs[idx])

    def format_result(
        self,
        symbol: str,
        probs: np.ndarray,
        model_keys: list[str],
        explanations: list[dict] | None = None,
    ) -> dict:
        """
        Build the standard AI score response dict used by ai_engine.py.
        """
        direction, confidence = self.decode(probs)
        return {
            "symbol": symbol,
            "score": direction,
            "probabilities": {
                "sell": round(float(probs[0]), 4),
                "hold": round(float(probs[1]), 4),
                "buy": round(float(probs[2]), 4),
            },
            "confidence": round(confidence, 4),
            "model": f"ensemble({'_'.join(model_keys)})",
            "explanation": explanations or [],
        }


# Singleton instance
ensemble_predictor = EnsemblePredictor()
