"""
AI scoring engine — Phase 12 (Ensemble: LightGBM + BiLSTM + Temporal Transformer).

Architecture:
  Primary:   Ensemble of LightGBM (tabular) + BiLSTM + Transformer (sequential)
  Fallback:  LightGBM-only when DL models not yet trained
  Emergency: Z-score math formula when no models loaded

Supports:
  - 3-class output (SELL / HOLD / BUY) — no more binary binary hack
  - 30 features (17 original + 13 new: Williams %R, MFI, OBV ratio, gaps, etc.)
  - SHAP explanations for LightGBM sub-model
  - Sequence-based DL inference when candles history is provided
"""

from __future__ import annotations
import os
import numpy as np
import pandas as pd
import lightgbm as lgb

from backend.core.logging_config import get_logger
from backend.services.ml.calibration import calibrator
from backend.services.ml.ensemble import ensemble_predictor
from backend.services.ml.lstm_model import lstm_predictor
from backend.services.ml.transformer_model import transformer_predictor
from backend.services.ml.feature_engineering import (
    FEATURE_NAMES, N_FEATURES, SEQUENCE_LENGTH,
    engineer_features, compute_target_3class, build_sequences
)

logger = get_logger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
MODEL_LARGE_PATH = os.path.join(MODEL_DIR, "lgb_model_largecap.txt")
MODEL_SMALL_PATH = os.path.join(MODEL_DIR, "lgb_model_smallcap.txt")

# Legacy 17-feature list kept for backward compat when loading old models
LEGACY_FEATURES = [
    'rsi_14', 'rsi_z', 'macd_hist', 'stoch_k', 'cci_20',
    'atr_pct', 'bb_pct_b', 'bb_width_norm',
    'ema9_ratio', 'ema21_ratio', 'ema_cross', 'golden_death',
    'adx_14', 'price_return_5d', 'price_return_20d', 'vol_ratio',
    'rs_momentum_20d'
]

# Complete set of Benchmark Indices and Large Cap Heavyweights
LARGE_CAP_SYMBOLS = {
    "^NSEI", "^NSEBANK", "^CNXIT", "^CNXAUTO", "^CNXENERGY", "^CNXREALTY",
    "^CNXMETAL", "^CNXFMCG", "^CNXPHARMA", "^NSEMDCP50", "^BSESN",
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "HINDUNILVR.NS", "LT.NS",
    "AXISBANK.NS", "KOTAKBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
    "ULTRACEMCO.NS", "ASIANPAINT.NS", "NTPC.NS", "TATAMOTORS.NS", "BAJFINANCE.NS",
    "POWERGRID.NS", "M&M.NS", "ADANIENT.NS", "TATASTEEL.NS", "COALINDIA.NS",
    "JSWSTEEL.NS", "HCLTECH.NS", "BAJAJFINSV.NS", "ONGC.NS", "GRASIM.NS",
    "TECHM.NS", "NESTLEIND.NS", "HDFCLIFE.NS", "BRITANNIA.NS", "ADANIPORTS.NS",
    "SBILIFE.NS", "DRREDDY.NS", "EICHERMOT.NS", "INDUSINDBK.NS", "WIPRO.NS",
    "CIPLA.NS", "DIVISLAB.NS", "BPCL.NS", "TATACONSUM.NS", "APOLLOHOSP.NS",
    "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "HINDALCO.NS", "LTIM.NS", "BEL.NS",
    "TRENT.NS", "VBL.NS", "PIDILITIND.NS", "CHOLAFIN.NS", "SHREECEM.NS",
    "SIEMENS.NS", "ABB.NS", "HAVELLS.NS", "DLF.NS", "GAIL.NS", "INDIGO.NS"
}


class AIEngineService:
    def __init__(self):
        self.models: dict = {}
        self.explainers: dict = {}
        self._model_features: dict = {}   # tracks which feature set each model uses
        self._load_models()

    def _load_models(self):
        """Load LightGBM models; DL models load themselves via their own singletons."""
        try:
            if os.path.exists(MODEL_LARGE_PATH):
                m = lgb.Booster(model_file=MODEL_LARGE_PATH)
                self.models["large"] = m
                n_feat = m.num_feature()
                self._model_features["large"] = FEATURE_NAMES if n_feat == N_FEATURES else LEGACY_FEATURES
                try:
                    import shap
                    self.explainers["large"] = shap.TreeExplainer(m)
                except Exception:
                    pass

            if os.path.exists(MODEL_SMALL_PATH):
                m = lgb.Booster(model_file=MODEL_SMALL_PATH)
                self.models["small"] = m
                n_feat = m.num_feature()
                self._model_features["small"] = FEATURE_NAMES if n_feat == N_FEATURES else LEGACY_FEATURES
                try:
                    import shap
                    self.explainers["small"] = shap.TreeExplainer(m)
                except Exception:
                    pass

            logger.info(
                "Loaded %d LightGBM model(s). LSTM ready=%s, Transformer ready=%s.",
                len(self.models), lstm_predictor.is_ready(), transformer_predictor.is_ready()
            )
        except Exception as e:
            logger.error("Failed to load LightGBM models: %s", e)

    def reload_models(self):
        self.models = {}
        self.explainers = {}
        self._model_features = {}
        self._load_models()
        lstm_predictor.reload()
        transformer_predictor.reload()

    # ──────────────────────────────────────────────────────────────────────────
    def score(
        self,
        indicators: dict,
        symbol: str = "",
        market_cap: float = 0,
        compute_shap: bool = True,
        candles: list[dict] | None = None,
    ) -> dict:
        """
        Compute AI ensemble score.

        Args:
            indicators: dict of latest indicator values (from IndicatorService)
            symbol: stock symbol for large/small-cap routing
            market_cap: market cap in INR for routing
            compute_shap: whether to compute SHAP explanations
            candles: optional list of OHLCV candle dicts for DL sequence inference

        Returns:
            Standardised AI score dict with probabilities, direction, confidence.
        """
        # Auto-reload if models appeared on disk after startup
        if not self.models and (
            os.path.exists(MODEL_LARGE_PATH) or os.path.exists(MODEL_SMALL_PATH)
        ):
            self._load_models()

        # ── Step 1: LightGBM tabular prediction ──────────────────────────────
        lgb_probs, explanations = self._lgb_predict(
            indicators, symbol, market_cap, compute_shap
        )

        # ── Step 2: DL sequence predictions (if candles provided) ─────────────
        lstm_probs = None
        transformer_probs = None
        if candles and len(candles) >= SEQUENCE_LENGTH + 50:
            lstm_probs, transformer_probs = self._dl_predict(candles)

        # ── Step 3: Ensemble ──────────────────────────────────────────────────
        model_keys = []
        if lgb_probs is not None:
            model_keys.append("lgb")
        if lstm_probs is not None:
            model_keys.append("lstm")
        if transformer_probs is not None:
            model_keys.append("tfm")

        if not model_keys:
            return self._neutral_response(symbol, indicators)

        ensemble_probs = ensemble_predictor.predict(lgb_probs, lstm_probs, transformer_probs)
        return ensemble_predictor.format_result(symbol, ensemble_probs, model_keys, explanations)

    # ──────────────────────────────────────────────────────────────────────────
    def _lgb_predict(
        self,
        indicators: dict,
        symbol: str,
        market_cap: float,
        compute_shap: bool,
    ) -> tuple[np.ndarray | None, list[dict]]:
        """Run LightGBM inference. Returns (probs_3class, shap_explanations)."""
        model_key = "small"
        if symbol in LARGE_CAP_SYMBOLS or market_cap > 500_000_000_000:
            model_key = "large"

        model = self.models.get(model_key) or self.models.get("large") or self.models.get("small")
        if model is None:
            return None, []

        feat_list = self._model_features.get(model_key, LEGACY_FEATURES)
        # Guard: model must have at least the minimum required indicator keys
        if not all(k in indicators for k in ['rsi_14', 'macd', 'ema_9']):
            return None, []

        try:
            fv = self._build_feature_vector(indicators, feat_list)
            X = pd.DataFrame([fv], columns=feat_list)

            raw = model.predict(X)
            # Handle both 1D (binary/regression) and 2D (multiclass) output
            if isinstance(raw, np.ndarray) and raw.ndim == 2 and raw.shape[1] == 3:
                # 3-class multiclass output [sell_prob, hold_prob, buy_prob]
                probs = raw[0].astype(np.float32)
            else:
                # Binary legacy model — convert to 3-class pseudo-probabilities
                p_up = float(calibrator.calibrate(float(raw[0])))
                p_up = np.clip(p_up, 0.0, 1.0)
                p_down = 1.0 - p_up
                # Allocate hold probability by removing from both extremes
                hold = max(0.0, 1.0 - abs(p_up - p_down))
                p_up_adj = p_up * (1.0 - hold / 2.0)
                p_down_adj = p_down * (1.0 - hold / 2.0)
                total = p_down_adj + hold + p_up_adj
                probs = np.array(
                    [p_down_adj / total, hold / total, p_up_adj / total],
                    dtype=np.float32,
                )

            # SHAP explanations
            explanations = []
            if compute_shap and model_key in self.explainers:
                try:
                    explainer = self.explainers[model_key]
                    shap_vals = explainer.shap_values(X)
                    if isinstance(shap_vals, list):
                        sv = shap_vals[-1][0]  # last class (buy) in multiclass
                    else:
                        sv = shap_vals[0]
                    for i, fname in enumerate(feat_list):
                        contrib = float(sv[i])
                        if abs(contrib) > 0.01:
                            explanations.append({
                                "feature": fname.upper(),
                                "value": round(float(X.iloc[0, i]), 4),
                                "contribution": round(abs(contrib), 4),
                                "direction": "bullish" if contrib > 0 else "bearish",
                                "reason": f"{model_key.capitalize()}Cap: {fname} is {'bullish' if contrib > 0 else 'bearish'}",
                            })
                    explanations = sorted(explanations, key=lambda x: x["contribution"], reverse=True)[:5]
                except Exception as ex:
                    logger.debug("SHAP bypassed: %s", ex)

            return probs, explanations
        except Exception as e:
            logger.error("LightGBM prediction failed for %s: %s", symbol, e)
            return None, []

    def _build_feature_vector(self, indicators: dict, feat_list: list[str]) -> list[float]:
        """Convert indicators dict to a flat feature vector matching feat_list order."""
        def _f(val, default=0.0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        price = _f(indicators.get("close", 1.0), 1.0) or 1.0
        macd_dict = indicators.get("macd") or {}
        bb = indicators.get("bb") or {}
        bb_upper = _f(bb.get("upper", price * 1.05), price * 1.05)
        bb_lower = _f(bb.get("lower", price * 0.95), price * 0.95)
        bb_mid = _f(bb.get("middle", price), price)

        ema9 = _f(indicators.get("ema_9", price), price) or price
        ema21 = _f(indicators.get("ema_21", price), price) or price
        ema50 = _f(indicators.get("ema_50", price), price) or price
        sma200 = _f(indicators.get("sma_200", price), price) or price

        rsi_14 = _f(indicators.get("rsi_14", 50.0), 50.0)
        vol = _f(indicators.get("volume", 0.0))
        vol_sma20 = _f(indicators.get("vol_sma_20", 1.0), 1.0) or 1.0

        atr = _f(indicators.get("atr_14", price * 0.02), price * 0.02)

        # Build lookup for all possible features
        feat_map = {
            "rsi_14": rsi_14,
            "rsi_z": (rsi_14 - 50.0) / 15.0,
            "macd_hist": _f(macd_dict.get("histogram", 0.0)),
            "stoch_k": _f(indicators.get("stoch_k", 50.0), 50.0),
            "cci_20": _f(indicators.get("cci_20", 0.0)),
            "atr_pct": atr / price,
            "bb_pct_b": (price - bb_lower) / (bb_upper - bb_lower + 1e-8),
            "bb_width_norm": (bb_upper - bb_lower) / (bb_mid + 1e-8),
            "williams_r": _f(indicators.get("williams_r", -50.0), -50.0),
            "mfi_14": _f(indicators.get("mfi_14", 50.0), 50.0),
            "ema9_ratio": price / ema9 - 1.0,
            "ema21_ratio": price / ema21 - 1.0,
            "ema_cross": ema9 / ema21 - 1.0,
            "golden_death_cont": (ema50 - sma200) / (sma200 + 1e-8),
            # Legacy binary golden_death for old models
            "golden_death": 1.0 if ema50 > sma200 else -1.0,
            "adx_14": _f(indicators.get("adx_14", 20.0), 20.0),
            "obv_ratio": _f(indicators.get("obv_ratio", 1.0), 1.0),
            "price_return_5d": _f(indicators.get("price_return_5d", 0.0)),
            "price_return_20d": _f(indicators.get("price_return_20d", 0.0)),
            "price_acceleration": _f(indicators.get("price_return_5d", 0.0)) - _f(indicators.get("price_return_20d", 0.0)) / 4.0,
            "vol_ratio": vol / vol_sma20,
            "rs_momentum_20d": _f(indicators.get("rs_momentum_20d", 0.0)),
            "dist_52w_high": _f(indicators.get("dist_52w_high", 0.0)),
            "dist_52w_low": _f(indicators.get("dist_52w_low", 0.0)),
            "gap_flag": _f(indicators.get("gap_flag", 0.0)),
            "vol_spike": 1.0 if vol > vol_sma20 * 2.5 else 0.0,
            "doji_flag": _f(indicators.get("doji_flag", 0.0)),
            "week_day_sin": 0.0,  # not available in live indicators dict
            "week_day_cos": 1.0,
            "month_sin": 0.0,
            "month_cos": 1.0,
            "atr_norm_return_5d": _f(indicators.get("price_return_5d", 0.0)) / max(atr / price, 0.005),
            "atr_norm_return_20d": _f(indicators.get("price_return_20d", 0.0)) / max(atr / price, 0.005),
            "log_turnover": float(np.log10(max(price * vol, 1.0)) / 10.0),
            "candle_range_atr": 1.0,
            "macro_shock_proxy": _f(indicators.get("macro_shock_proxy", 0.0)),
            "catalyst_trend_score": float(((price > ema9) + (ema9 > ema21) + (ema21 > ema50) + (ema50 > sma200)) / 2.0 - 1.0),
        }
        return [feat_map.get(f, 0.0) for f in feat_list]

    def _dl_predict(self, candles: list[dict]) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Build sequence from candles and run LSTM + Transformer inference."""
        lstm_probs = None
        transformer_probs = None

        try:
            df = pd.DataFrame(candles)
            df = df.rename(columns={
                "open": "Open", "high": "High", "low": "Low",
                "close": "Close", "volume": "Volume"
            })
            if "timestamp" in df.columns:
                df["Date"] = pd.to_datetime(df["timestamp"])
                df = df.set_index("Date")

            df_feat = engineer_features(df)
            df_feat = compute_target_3class(df_feat)
            X_seq, _, _ = build_sequences(df_feat)

            if len(X_seq) == 0:
                return None, None

            last_seq = X_seq[-1]  # (60, 30)

            if lstm_predictor.is_ready():
                lstm_probs = lstm_predictor.predict_proba(last_seq)

            if transformer_predictor.is_ready():
                transformer_probs = transformer_predictor.predict_proba(last_seq)

        except Exception as e:
            logger.debug("DL sequence prediction failed: %s", e)

        return lstm_probs, transformer_probs

    def _neutral_response(self, symbol: str, indicators: dict = None) -> dict:
        """Z-score math formula emergency fallback when no models are loaded."""
        if indicators is None:
            indicators = {}

        rsi = float(indicators.get('rsi_14', 50))
        z_rsi = (rsi - 50) / 15.0

        price = float(indicators.get("close", 1))
        ema9 = float(indicators.get('ema_9', price))
        ema21 = float(indicators.get('ema_21', price))
        z_ema = 1.5 if ema9 > ema21 else -1.5

        # Incorporate ADX for trend strength
        adx = float(indicators.get('adx_14', 20))
        adx_mult = min(adx / 25.0, 1.5)

        total_z = ((z_rsi + z_ema) / 2.0) * adx_mult

        import math
        p_buy = 1.0 / (1.0 + math.exp(-total_z))
        p_sell = 1.0 - p_buy
        p_hold = max(0.0, 1.0 - abs(p_buy - p_sell))
        # Renormalise
        total = p_sell * (1 - p_hold / 2) + p_hold + p_buy * (1 - p_hold / 2)
        sell_f = p_sell * (1 - p_hold / 2) / total
        hold_f = p_hold / total
        buy_f = p_buy * (1 - p_hold / 2) / total

        if buy_f > 0.50:
            direction = "BUY"
        elif sell_f > 0.50:
            direction = "SELL"
        else:
            direction = "HOLD"

        confidence = max(sell_f, hold_f, buy_f)

        return {
            "symbol": symbol,
            "score": direction,
            "probabilities": {
                "sell": round(sell_f, 4),
                "hold": round(hold_f, 4),
                "buy": round(buy_f, 4),
            },
            "confidence": round(confidence, 4),
            "model": "math_zscore_fallback",
            "explanation": [
                {"feature": "RSI_Z", "value": round(z_rsi, 2), "contribution": abs(z_rsi),
                 "direction": "bullish" if z_rsi > 0 else "bearish", "reason": "RSI momentum"},
                {"feature": "EMA_Z", "value": round(z_ema, 2), "contribution": abs(z_ema),
                 "direction": "bullish" if z_ema > 0 else "bearish", "reason": "Short-term trend"},
                {"feature": "ADX", "value": round(adx, 1), "contribution": adx_mult,
                 "direction": "bullish" if adx > 25 else "neutral", "reason": "Trend strength"},
            ],
        }


ai_engine_service = AIEngineService()
