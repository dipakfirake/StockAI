"""
Unit tests for the Universal Scale-Invariant Deep Learning Architecture.
Verifies:
1. 36 features engineered correctly with correct column registry.
2. Dynamic ATR-relative target generation adapts across both large and small caps.
3. AsymmetricCrashFocalLoss penalizes false buys during drawdowns.
4. BidirectionalLSTMModel & StockTransformer instantiate and execute forward passes.
5. Ensemble Predictor computes calibrated probabilities.
"""

import numpy as np
import pandas as pd
import pytest
import torch

from backend.services.ml.feature_engineering import (
    FEATURE_NAMES,
    N_FEATURES,
    SEQUENCE_LENGTH,
    engineer_features,
    compute_target_volatility_adaptive,
    build_sequences,
)
from backend.services.ml.losses import AsymmetricCrashFocalLoss
from backend.services.ml.lstm_model import BidirectionalLSTMModel
from backend.services.ml.transformer_model import StockTransformer
from backend.services.ml.ensemble import ensemble_predictor


def _generate_synthetic_ohlcv(n_bars: int = 150, volatility: float = 0.015, base_price: float = 1000.0) -> pd.DataFrame:
    """Generate realistic synthetic OHLCV data."""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=n_bars, freq="B")
    
    returns = np.random.normal(loc=0.0005, scale=volatility, size=n_bars)
    price_series = base_price * np.exp(np.cumsum(returns))
    
    high = price_series * (1.0 + np.abs(np.random.normal(0, volatility * 0.8, n_bars)))
    low = price_series * (1.0 - np.abs(np.random.normal(0, volatility * 0.8, n_bars)))
    open_p = (high + low) / 2.0 + np.random.normal(0, volatility * 0.2, n_bars)
    close = price_series
    volume = np.random.uniform(50000, 500000, n_bars)

    df = pd.DataFrame({
        "Open": open_p,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)
    return df


def test_feature_registry_consistency():
    assert len(FEATURE_NAMES) == 36
    assert N_FEATURES == 36
    assert "atr_norm_return_5d" in FEATURE_NAMES
    assert "log_turnover" in FEATURE_NAMES
    assert "macro_shock_proxy" in FEATURE_NAMES
    assert "catalyst_trend_score" in FEATURE_NAMES


def test_feature_engineering_pipeline():
    df = _generate_synthetic_ohlcv(n_bars=220)
    df_feat = engineer_features(df)
    
    for feat in FEATURE_NAMES:
        assert feat in df_feat.columns, f"Missing feature {feat}"
    
    # Verify no NaN or Inf in valid feature region
    valid_slice = df_feat[FEATURE_NAMES].dropna()
    assert len(valid_slice) > 100
    assert not np.isinf(valid_slice.values).any()


def test_dynamic_atr_target_balancing():
    # Low volatility large cap simulation (ATR ~ 1%)
    df_large = _generate_synthetic_ohlcv(n_bars=150, volatility=0.01, base_price=2500.0)
    df_large_feat = engineer_features(df_large)
    df_large_target = compute_target_volatility_adaptive(df_large_feat, horizon=10)
    
    # High volatility small cap simulation (ATR ~ 5%)
    df_small = _generate_synthetic_ohlcv(n_bars=150, volatility=0.05, base_price=50.0)
    df_small_feat = engineer_features(df_small)
    df_small_target = compute_target_volatility_adaptive(df_small_feat, horizon=10)
    
    # Dynamic threshold should be lower for large cap than for small cap
    assert df_large_target["dyn_threshold"].mean() < df_small_target["dyn_threshold"].mean()
    
    # Both should maintain valid 3-class distribution {0, 1, 2}
    assert set(df_large_target["target"].unique()).issubset({0, 1, 2})
    assert set(df_small_target["target"].unique()).issubset({0, 1, 2})


def test_sequence_builder():
    df = _generate_synthetic_ohlcv(n_bars=120)
    df_feat = engineer_features(df)
    
    # Inference mode without target
    X_seq, _, _ = build_sequences(df_feat, window=SEQUENCE_LENGTH)
    assert len(X_seq) > 0
    assert X_seq.shape[1] == SEQUENCE_LENGTH
    assert X_seq.shape[2] == N_FEATURES


def test_asymmetric_crash_focal_loss():
    loss_fn = AsymmetricCrashFocalLoss(crash_penalty_weight=3.0)
    
    # Scenario: True label is SELL (class 0, market crash)
    targets = torch.tensor([0], dtype=torch.long)
    
    # Case A: Model predicts BUY (high class 2 logit) - catastrophic false bull
    logits_false_buy = torch.tensor([[-2.0, -1.0, 4.0]], dtype=torch.float32)
    loss_false_buy = loss_fn(logits_false_buy, targets)
    
    # Case B: Model predicts HOLD (class 1) - cautious error
    logits_hold = torch.tensor([[-1.0, 3.0, -1.0]], dtype=torch.float32)
    loss_hold = loss_fn(logits_hold, targets)
    
    # Case C: Model predicts correctly SELL (class 0)
    logits_correct = torch.tensor([[4.0, -1.0, -2.0]], dtype=torch.float32)
    loss_correct = loss_fn(logits_correct, targets)
    
    # The false BUY during crash must be penalized far more heavily than HOLD
    assert loss_false_buy.item() > loss_hold.item() * 1.5
    assert loss_correct.item() < loss_hold.item()


def test_deep_learning_models_forward_pass():
    batch_size = 4
    x = torch.randn(batch_size, SEQUENCE_LENGTH, N_FEATURES)
    
    # BiLSTM Model
    lstm = BidirectionalLSTMModel(input_size=N_FEATURES)
    lstm_out = lstm(x)
    assert lstm_out.shape == (batch_size, 3)
    
    # Transformer Model
    tf = StockTransformer(input_size=N_FEATURES)
    tf_out = tf(x)
    assert tf_out.shape == (batch_size, 3)


def test_ensemble_predictor():
    lgb_probs = np.array([0.1, 0.2, 0.7])
    lstm_probs = np.array([0.15, 0.25, 0.60])
    tf_probs = np.array([0.2, 0.3, 0.5])
    
    res = ensemble_predictor.predict(lgb_probs, lstm_probs, tf_probs)
    assert len(res) == 3
    assert np.isclose(res.sum(), 1.0)
    
    direction, conf = ensemble_predictor.decode(res)
    assert direction == "BUY"
    assert conf > 0.5
