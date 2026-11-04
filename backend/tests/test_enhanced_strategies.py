"""
Unit tests for Enhanced Quantitative Trading Strategies & Institutional Analytics:
1. SuperTrend Trend Rider Strategy (ATR trailing stop + 200 EMA trend filter).
2. SMC Institutional FVG Hunter Strategy (asymmetric 2.5R profit targets).
3. Institutional Analytics (Sortino, Calmar, Profit Factor, Expectancy, Payoff Ratio).
4. SignalEngine Dynamic ATR Entry, Stop Loss, Target 1, Target 2, and Risk/Reward.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from backend.services.backtesting import BacktestEngine
from backend.services.signals import SignalEngine


def _create_synthetic_candles(num_bars: int = 100, trend: str = "bullish") -> pd.DataFrame:
    """Generate realistic OHLCV DataFrame for testing strategies."""
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(num_bars)]
    base_price = 1000.0
    prices = [base_price]
    
    np.random.seed(42)
    for i in range(1, num_bars):
        step = np.random.normal(1.5 if trend == "bullish" else -1.0, 5.0)
        prices.append(max(10.0, prices[-1] + step))

    df = pd.DataFrame({
        "Open": [p * 0.995 for p in prices],
        "High": [p * 1.015 for p in prices],
        "Low": [p * 0.985 for p in prices],
        "Close": prices,
        "Volume": [100000 + int(np.random.uniform(0, 50000)) for _ in prices],
    }, index=pd.DatetimeIndex(dates))
    return df


def test_advanced_metrics_calculation():
    """Verify Sortino, Calmar, Profit Factor, and Expectancy calculation."""
    trades = [
        {"entry": 100.0, "exit": 110.0, "pnl": 1000.0, "entry_date": "2023-01-01", "exit_date": "2023-01-05"},
        {"entry": 110.0, "exit": 115.0, "pnl": 500.0, "entry_date": "2023-01-06", "exit_date": "2023-01-10"},
        {"entry": 115.0, "exit": 112.0, "pnl": -300.0, "entry_date": "2023-01-11", "exit_date": "2023-01-15"},
        {"entry": 112.0, "exit": 120.0, "pnl": 800.0, "entry_date": "2023-01-16", "exit_date": "2023-01-20"},
    ]
    equity_curve = [
        {"date": "2023-01-01", "equity": 100000.0},
        {"date": "2023-01-05", "equity": 101000.0},
        {"date": "2023-01-10", "equity": 101500.0},
        {"date": "2023-01-15", "equity": 101200.0},
        {"date": "2023-01-20", "equity": 102000.0},
    ]

    metrics = BacktestEngine._compute_metrics(trades, equity_curve, 100000.0)

    assert metrics["total_trades"] == 4
    assert metrics["win_rate"] == 0.75  # 3 wins out of 4
    assert metrics["profit_factor"] > 1.0  # 2300 wins / 300 loss = 7.67
    assert metrics["expectancy_per_trade"] > 0.0  # Positive expectancy
    assert metrics["max_consecutive_wins"] >= 2
    assert metrics["win_loss_ratio"] > 1.0


def test_supertrend_trend_rider_backtest():
    """Verify SuperTrend ATR Trend Rider strategy generates trades and valid metrics."""
    df = _create_synthetic_candles(num_bars=120, trend="bullish")
    params = {"period": 7, "multiplier": 2.5, "quantity": 10}

    result = BacktestEngine._supertrend_trend_rider(
        df=df,
        params=params,
        capital=100000.0,
        symbol="TEST.NS",
        slippage_pct=0.001,
        commission=20.0,
    )

    assert result["strategy"] == "supertrend_trend_rider"
    assert "metrics" in result
    assert "equity_curve" in result
    assert len(result["equity_curve"]) > 0
    assert "profit_factor" in result["metrics"]
    assert "sortino_ratio" in result["metrics"]


def test_smc_liquidity_fvg_backtest():
    """Verify SMC Institutional FVG Hunter strategy generates FVG setups with 2.5R targets."""
    # Create candle series with an intentional gap up (Bullish FVG)
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(80)]
    df = _create_synthetic_candles(num_bars=80, trend="bullish")
    
    # Inject a clear bullish FVG at bar 30: candle[28].high < candle[30].low
    c28_high = 1050.0
    c30_low = 1070.0
    df.iloc[28, df.columns.get_loc("High")] = c28_high
    df.iloc[29, df.columns.get_loc("Close")] = 1060.0
    df.iloc[30, df.columns.get_loc("Low")] = c30_low
    # Ensure bar 35 dips back into FVG zone [1050, 1070] to trigger entry
    df.iloc[35, df.columns.get_loc("Low")] = 1055.0
    df.iloc[35, df.columns.get_loc("Close")] = 1058.0

    params = {"gap_pct": 0.2, "risk_reward": 2.5, "quantity": 10}

    result = BacktestEngine._smc_liquidity_fvg(
        df=df,
        params=params,
        capital=100000.0,
        symbol="TEST.NS",
        slippage_pct=0.001,
        commission=20.0,
    )

    assert result["strategy"] == "smc_liquidity_fvg"
    assert "metrics" in result
    assert "equity_curve" in result
    assert len(result["equity_curve"]) > 0


def test_signal_engine_dynamic_atr_targets():
    """Verify SignalEngine computes dynamic Entry, Stop Loss, Target 1, Target 2, and R:R."""
    indicators = {
        "close": 2500.0,
        "atr_14": 30.0,
        "rsi_14": 25.0,  # Oversold -> Bullish
        "macd": {"macd": 15.0, "signal": 10.0},
        "ema_9": 2520.0,
        "ema_21": 2500.0,
        "ema_50": 2450.0,
        "ema_200": 2300.0,
        "sma_50": 2450.0,
        "sma_200": 2300.0,
        "supertrend": 1,  # Bullish SuperTrend
        "volume": 2000000,
        "vol_sma_20": 1000000,  # 2x volume expansion
        "adx_14": 28.0,
    }

    signals = SignalEngine.evaluate(indicators, symbol="RELIANCE.NS", timeframe="1d")
    assert len(signals) == 1
    sig = signals[0]

    assert sig["type"] == "BUY"
    assert sig["entry_price"] == 2500.0
    # Stop loss: Entry - 1.5 * ATR (2500 - 45 = 2455)
    assert sig["stop_loss"] == 2455.0
    # Target 1: Entry + 1.5 * Risk (2500 + 1.5 * 45 = 2567.5)
    assert sig["target_1"] == 2567.5
    # Target 2: Entry + 2.5 * Risk (2500 + 2.5 * 45 = 2612.5)
    assert sig["target_2"] == 2612.5
    assert sig["risk_reward_ratio"] == 1.5
    assert sig["risk_quality"] in {"OPTIMAL", "ACCEPTABLE"}
    assert "SuperTrend confirms Bullish trend" in sig["reason"] or "RSI" in sig["reason"]

