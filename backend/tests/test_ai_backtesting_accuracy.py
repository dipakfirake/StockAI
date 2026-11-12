"""
Focused unit tests for AI Backtesting Engine & Calibrated 3-Class Ensemble Decoding.
Verifies resolution of the 0-trades defect on LightGBM Probabilistic backtesting.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from backend.services.ml.ensemble import ensemble_predictor
from backend.services.backtesting import BacktestEngine


def test_ensemble_predictor_calibrated_decode_bullish():
    """Verify that when HOLD dominates (0.60) but BUY outweighs SELL (0.28 vs 0.12), decode returns BUY."""
    # probs: [sell=0.12, hold=0.60, buy=0.28]
    # directional_buy = 0.28 / (0.28 + 0.12) = 0.70 >= 0.58
    probs = np.array([0.12, 0.60, 0.28], dtype=np.float32)
    direction, confidence = ensemble_predictor.decode(probs, threshold=0.58)
    assert direction == "BUY"
    assert confidence >= 0.58


def test_ensemble_predictor_calibrated_decode_bearish():
    """Verify that when HOLD dominates (0.60) but SELL outweighs BUY (0.28 vs 0.12), decode returns SELL."""
    # probs: [sell=0.28, hold=0.60, buy=0.12]
    # directional_sell = 0.28 / (0.28 + 0.12) = 0.70 >= 0.58
    probs = np.array([0.28, 0.60, 0.12], dtype=np.float32)
    direction, confidence = ensemble_predictor.decode(probs, threshold=0.58)
    assert direction == "SELL"
    assert confidence >= 0.58


def test_ensemble_predictor_calibrated_decode_neutral_hold():
    """Verify that when BUY and SELL are balanced, decode returns HOLD."""
    # probs: [sell=0.20, hold=0.60, buy=0.20]
    # directional = 0.50 < 0.58
    probs = np.array([0.20, 0.60, 0.20], dtype=np.float32)
    direction, confidence = ensemble_predictor.decode(probs, threshold=0.58)
    assert direction == "HOLD"
    assert confidence == pytest.approx(0.60, abs=1e-3)


def test_ensemble_predictor_absolute_dominance():
    """Verify that when BUY or SELL explicitly exceeds HOLD, standard dominance applies."""
    probs_buy = np.array([0.10, 0.35, 0.55], dtype=np.float32)
    dir_buy, conf_buy = ensemble_predictor.decode(probs_buy)
    assert dir_buy == "BUY"
    assert conf_buy == pytest.approx(0.55, abs=1e-3)

    probs_sell = np.array([0.55, 0.35, 0.10], dtype=np.float32)
    dir_sell, conf_sell = ensemble_predictor.decode(probs_sell)
    assert dir_sell == "SELL"
    assert conf_sell == pytest.approx(0.55, abs=1e-3)


def _generate_synthetic_ohlcv(days: int = 250) -> pd.DataFrame:
    """Generate realistic trending synthetic OHLCV data for backtesting."""
    base_date = datetime(2023, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(days)]
    
    np.random.seed(42)
    # Sine wave trend + noise
    t = np.linspace(0, 4 * np.pi, days)
    trend = 1000.0 + (np.sin(t) * 150.0) + (np.linspace(0, 100, days))
    noise = np.random.normal(0, 5, days)
    closes = trend + noise
    highs = closes + np.abs(np.random.normal(5, 2, days))
    lows = closes - np.abs(np.random.normal(5, 2, days))
    opens = closes + np.random.normal(0, 2, days)
    volumes = np.random.randint(500000, 2000000, days)

    df = pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes,
        "Volume": volumes,
    }, index=pd.DatetimeIndex(dates))
    return df


def test_ai_machine_learning_backtest_execution(monkeypatch):
    """Verify that BacktestEngine._ai_machine_learning executes trades with directional calibration."""
    df = _generate_synthetic_ohlcv(250)
    
    # Mock ai_engine_service.score to return dynamic probabilities
    from backend.services.ai_engine import ai_engine_service
    
    call_count = 0
    def mock_score(indicators, symbol, compute_shap=False):
        nonlocal call_count
        call_count += 1
        # Alternate between bullish (candles 0-20), bearish (21-40), neutral (41+)
        phase = (call_count // 15) % 3
        if phase == 0:
            # Bullish skew
            return {
                "score": "BUY",
                "probabilities": {"sell": 0.10, "hold": 0.60, "buy": 0.30},
                "confidence": 0.75,
                "model": "mock",
            }
        elif phase == 1:
            # Bearish skew
            return {
                "score": "SELL",
                "probabilities": {"sell": 0.30, "hold": 0.60, "buy": 0.10},
                "confidence": 0.75,
                "model": "mock",
            }
        else:
            return {
                "score": "HOLD",
                "probabilities": {"sell": 0.20, "hold": 0.60, "buy": 0.20},
                "confidence": 0.60,
                "model": "mock",
            }

    monkeypatch.setattr(ai_engine_service, "score", mock_score)

    params = {"qty_mode": "fixed", "quantity": 10, "confidence_threshold": 0.58}
    result = BacktestEngine._ai_machine_learning(
        df=df,
        params=params,
        capital=100000.0,
        symbol="TEST.NS",
        slippage_pct=0.001,
        commission=20.0,
    )

    metrics = result["metrics"]
    assert metrics["total_trades"] > 0, "AI backtest must execute trades under calibrated signals"
    assert "final_equity" in metrics
    assert "total_return_pct" in metrics
    assert "sharpe_ratio" in metrics
    assert len(result["equity_curve"]) > 0


def test_backtest_zero_trades_graceful_handling():
    """Verify compute_metrics handles 0 trades without math division errors or NaN crashes."""
    metrics = BacktestEngine._compute_metrics([], [], 100000.0)
    assert metrics["total_trades"] == 0
    assert metrics["total_return_pct"] == 0.0
    assert metrics["win_rate"] == 0.0
    assert metrics["profit_factor"] == 0.0
    assert metrics["final_equity"] == 100000.0
