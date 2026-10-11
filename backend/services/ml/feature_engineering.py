"""
Centralized Feature Engineering for ML and Deep Learning Models.

Universal Scale-Invariant Foundation Feature Architecture:
Provides:
- 36 scale-independent, normalized technical and macro features
- Dynamic ATR-relative target labeling (Triple Barrier) calibrated per stock
- Sequence builder for LSTM/Transformer (N, window, features) tensors
- Feature names registry (single source of truth)

Feature groups:
  Oscillators (5): rsi_14, rsi_z, macd_hist, stoch_k, cci_20
  Volatility (5): atr_pct, bb_pct_b, bb_width_norm, williams_r, mfi_14
  Trend/MA (6): ema9_ratio, ema21_ratio, ema_cross, golden_death_cont, adx_14, obv_ratio
  Momentum (5): price_return_5d, price_return_20d, price_acceleration, vol_ratio, rs_momentum_20d
  Market Structure (5): dist_52w_high, dist_52w_low, gap_flag, vol_spike, doji_flag
  Cyclical (4): week_day_sin, week_day_cos, month_sin, month_cos
  Universal Scale-Invariant & Macro Shock Features (6):
    atr_norm_return_5d, atr_norm_return_20d, log_turnover,
    candle_range_atr, macro_shock_proxy, catalyst_trend_score
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
from ta.trend import MACD, EMAIndicator, ADXIndicator, CCIIndicator, SMAIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator, MFIIndicator

from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────
# Feature Registry (36 features, single source of truth)
# ─────────────────────────────────────────────────────
FEATURE_NAMES = [
    # Oscillators (5)
    "rsi_14", "rsi_z", "macd_hist", "stoch_k", "cci_20",
    # Volatility (5)
    "atr_pct", "bb_pct_b", "bb_width_norm", "williams_r", "mfi_14",
    # Trend & Moving Averages (6)
    "ema9_ratio", "ema21_ratio", "ema_cross", "golden_death_cont", "adx_14", "obv_ratio",
    # Momentum (5)
    "price_return_5d", "price_return_20d", "price_acceleration", "vol_ratio", "rs_momentum_20d",
    # Market Structure (5)
    "dist_52w_high", "dist_52w_low", "gap_flag", "vol_spike", "doji_flag",
    # Cyclical time features (4)
    "week_day_sin", "week_day_cos", "month_sin", "month_cos",
    # Universal Scale-Invariant & Macro Constraints (6)
    "atr_norm_return_5d", "atr_norm_return_20d", "log_turnover",
    "candle_range_atr", "macro_shock_proxy", "catalyst_trend_score",
]

N_FEATURES = len(FEATURE_NAMES)  # 36
SEQUENCE_LENGTH = 60              # bars of history fed to LSTM/Transformer


def engineer_features(df: pd.DataFrame, nifty_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Generate 36 scale-independent, normalized technical features from OHLCV data.

    Args:
        df: DataFrame with columns Open, High, Low, Close, Volume.
            Index should be DatetimeIndex, or a 'Date' column should exist.
        nifty_df: Optional Nifty 50 DataFrame with 'nifty_return_20d' column for RS momentum.

    Returns:
        DataFrame with all 36 features added (original OHLCV preserved).
    """
    df = df.copy()

    # Ensure DatetimeIndex
    if "Date" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
        df = df.set_index("Date")

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"].replace(0, 1).astype(float)

    # ── 1. Oscillators ────────────────────────────────────────────────────────
    rsi = RSIIndicator(close=close, window=14).rsi()
    df["rsi_14"] = rsi
    df["rsi_z"] = (rsi - 50.0) / 15.0

    macd_ind = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
    df["macd_hist"] = macd_ind.macd_diff()

    stoch = StochasticOscillator(high=high, low=low, close=close, window=14, smooth_window=3)
    df["stoch_k"] = stoch.stoch()

    df["cci_20"] = CCIIndicator(high=high, low=low, close=close, window=20).cci()

    # ── 2. Volatility ─────────────────────────────────────────────────────────
    atr = AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()
    df["atr_pct"] = atr / (close + 1e-8)

    bb = BollingerBands(close=close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()
    bb_mid = bb.bollinger_mavg()
    df["bb_pct_b"] = (close - bb_lower) / (bb_upper - bb_lower + 1e-8)
    df["bb_width_norm"] = (bb_upper - bb_lower) / (bb_mid + 1e-8)

    df["williams_r"] = WilliamsRIndicator(high=high, low=low, close=close, lbp=14).williams_r()
    df["mfi_14"] = MFIIndicator(high=high, low=low, close=close, volume=volume, window=14).money_flow_index()

    # ── 3. Trend & Moving Averages ────────────────────────────────────────────
    ema9 = EMAIndicator(close=close, window=9).ema_indicator()
    ema21 = EMAIndicator(close=close, window=21).ema_indicator()
    ema50 = EMAIndicator(close=close, window=50).ema_indicator()
    sma200 = close.rolling(window=200, min_periods=20).mean()

    df["ema9_ratio"] = close / (ema9 + 1e-8) - 1.0
    df["ema21_ratio"] = close / (ema21 + 1e-8) - 1.0
    df["ema_cross"] = ema9 / (ema21 + 1e-8) - 1.0

    df["golden_death_cont"] = (ema50 - sma200) / (sma200 + 1e-8)
    df["adx_14"] = ADXIndicator(high=high, low=low, close=close, window=14).adx()

    obv = OnBalanceVolumeIndicator(close=close, volume=volume).on_balance_volume()
    obv_sma = SMAIndicator(close=obv, window=20).sma_indicator()
    df["obv_ratio"] = obv / (obv_sma.abs() + 1e-8)

    # ── 4. Momentum ──────────────────────────────────────────────────────────
    df["price_return_5d"] = close / close.shift(5) - 1.0
    df["price_return_20d"] = close / close.shift(20) - 1.0
    df["price_acceleration"] = df["price_return_5d"] - (df["price_return_20d"] / 4.0)

    vol_sma20 = SMAIndicator(close=volume, window=20).sma_indicator()
    df["vol_ratio"] = volume / (vol_sma20 + 1e-8)

    # Market Relative Strength vs Nifty 50
    if nifty_df is not None and not nifty_df.empty and "nifty_return_20d" in nifty_df.columns:
        nifty_aligned = nifty_df["nifty_return_20d"].reindex(df.index, method="nearest")
        df["rs_momentum_20d"] = df["price_return_20d"] - nifty_aligned
    else:
        df["rs_momentum_20d"] = df["price_acceleration"]

    # ── 5. Market Structure ──────────────────────────────────────────────────
    rolling_52w_high = high.rolling(window=252, min_periods=20).max()
    rolling_52w_low = low.rolling(window=252, min_periods=20).min()
    df["dist_52w_high"] = (rolling_52w_high - close) / (close + 1e-8)
    df["dist_52w_low"] = (close - rolling_52w_low) / (close + 1e-8)

    prev_close = close.shift(1)
    open_price = df["Open"]
    df["gap_flag"] = np.where(open_price > prev_close * 1.005, 1.0,
                     np.where(open_price < prev_close * 0.995, -1.0, 0.0))

    df["vol_spike"] = np.where(volume > vol_sma20 * 2.5, 1.0, 0.0)

    body = (close - df["Open"]).abs()
    candle_range = (high - low).replace(0, 1e-8)
    df["doji_flag"] = np.where(body / candle_range < 0.05, 1.0, 0.0)

    # ── 6. Cyclical Time Features ─────────────────────────────────────────────
    idx = df.index
    try:
        dow = idx.dayofweek.astype(float)
        month = idx.month.astype(float)
    except AttributeError:
        dt_idx = pd.to_datetime(idx)
        dow = dt_idx.dayofweek.astype(float)
        month = dt_idx.month.astype(float)

    df["week_day_sin"] = np.sin(2 * np.pi * dow / 5.0)
    df["week_day_cos"] = np.cos(2 * np.pi * dow / 5.0)
    df["month_sin"] = np.sin(2 * np.pi * (month - 1) / 12.0)
    df["month_cos"] = np.cos(2 * np.pi * (month - 1) / 12.0)

    # ── 7. Universal Scale-Invariant & Macro Constraint Features ──────────────
    # A) Volatility-Normalized Returns: Removes small vs large-cap magnitude bias
    atr_safe = df["atr_pct"].clip(lower=0.005)
    df["atr_norm_return_5d"] = (df["price_return_5d"] / atr_safe).clip(-10.0, 10.0)
    df["atr_norm_return_20d"] = (df["price_return_20d"] / atr_safe).clip(-10.0, 10.0)

    # B) Log Turnover: Dimensionless liquidity and market cap embedding
    turnover = close * volume
    df["log_turnover"] = (np.log10(turnover.clip(lower=1.0)) / 10.0).clip(0.0, 2.0)

    # C) Relative Candle Range: Measures expansion relative to normal volatility
    # Detects circuit limit lockups (range ~ 0) vs wide-range panic or breakout bars (> 3.0)
    df["candle_range_atr"] = (candle_range / (atr + 1e-8)).clip(0.0, 10.0)

    # D) Macro Volatility Shock Proxy: Measures regime shifts (wars, inflation surges, oil hikes)
    # Detects sudden regime cluster jumps: 14d ATR expanding relative to 60d ATR
    atr_60_raw = AverageTrueRange(high=high, low=low, close=close, window=60).average_true_range()
    atr_60 = atr_60_raw.bfill().fillna(atr)
    df["macro_shock_proxy"] = ((atr / (atr_60 + 1e-8)) - 1.0).clip(-3.0, 5.0)

    # E) Structural Positive Catalyst Trend Alignment Score
    # Evaluates multi-timeframe bull stacking: [EMA9 > EMA21, EMA21 > EMA50, EMA50 > SMA200]
    c1 = (close > ema9).astype(float)
    c2 = (ema9 > ema21).astype(float)
    c3 = (ema21 > ema50).astype(float)
    c4 = (ema50 > sma200).astype(float)
    df["catalyst_trend_score"] = ((c1 + c2 + c3 + c4) / 2.0 - 1.0).clip(-1.0, 1.0)

    # Defensive fill on computed features to ensure no NaNs in leading warm-up bars
    for col in FEATURE_NAMES:
        if col in df.columns:
            df[col] = df[col].bfill().ffill().fillna(0.0)

    return df


def compute_target_volatility_adaptive(
    df: pd.DataFrame,
    horizon: int = 10,
    k_atr: float = 1.75,
    min_thresh: float = 0.02,
    max_thresh: float = 0.12,
) -> pd.DataFrame:
    """
    Compute 3-class target using a Volatility-Calibrated Dynamic Barrier.
    Threshold_t = clip(k_atr * ATR_pct_t, min_thresh, max_thresh).

    0 = SELL (fwd_return < -threshold)
    1 = HOLD (-threshold <= fwd_return <= threshold)
    2 = BUY (fwd_return > threshold)
    """
    df = df.copy()
    fwd_return = df["Close"].shift(-horizon) / df["Close"] - 1.0
    df["fwd_return"] = fwd_return

    if "atr_pct" not in df.columns:
        atr = AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14).average_true_range()
        atr_pct = atr / (df["Close"] + 1e-8)
    else:
        atr_pct = df["atr_pct"]

    dyn_threshold = (k_atr * atr_pct).clip(lower=min_thresh, upper=max_thresh)
    df["dyn_threshold"] = dyn_threshold

    df["target"] = np.where(
        fwd_return > dyn_threshold, 2,
        np.where(fwd_return < -dyn_threshold, 0, 1)
    ).astype(int)
    return df


def compute_target_3class(
    df: pd.DataFrame,
    horizon: int = 5,
    threshold: float = 0.015,
) -> pd.DataFrame:
    """
    Backward-compatible wrapper.
    If dynamic threshold is possible, use volatility adaptive target.
    """
    return compute_target_volatility_adaptive(df, horizon=horizon)


def build_sequences(
    df: pd.DataFrame,
    features: list[str] | None = None,
    window: int = SEQUENCE_LENGTH,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Build 3D sequence tensors for LSTM/Transformer from feature DataFrame.
    Supports both training mode (with 'target') and inference mode (without 'target').

    Returns:
        X_seq: (N, window, n_features) float32 array
        y: (N,) int64 array of targets (or zeros if in inference mode)
        indices: (N,) row indices in the cleaned DataFrame
    """
    if features is None:
        features = FEATURE_NAMES

    valid_cols = [f for f in features if f in df.columns]
    has_target = "target" in df.columns

    needed = valid_cols + (["target"] if has_target else [])
    df_clean = df[needed].dropna(subset=valid_cols)

    n = len(df_clean)
    if n < window:
        return (
            np.empty((0, window, len(valid_cols)), dtype=np.float32),
            np.empty(0, dtype=np.int64),
            np.empty(0),
        )

    feat_arr = df_clean[valid_cols].values.astype(np.float32)
    target_arr = df_clean["target"].values.astype(np.int64) if has_target else np.zeros(n, dtype=np.int64)

    # Defensive clipping prevents exploding gradients
    feat_arr = np.clip(feat_arr, -10.0, 10.0)
    feat_arr = np.nan_to_num(feat_arr, nan=0.0, posinf=10.0, neginf=-10.0)

    X_seq, y_seq, idx_seq = [], [], []
    for i in range(window, n + 1 if not has_target else n):
        X_seq.append(feat_arr[i - window:i])
        y_seq.append(target_arr[i - 1] if not has_target else target_arr[i])
        idx_seq.append(i - 1 if not has_target else i)

    return (
        np.array(X_seq, dtype=np.float32),
        np.array(y_seq, dtype=np.int64),
        np.array(idx_seq),
    )


def build_tabular_features(
    df: pd.DataFrame,
    features: list[str] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build flat feature matrix for LightGBM from feature DataFrame.

    Returns:
        X: (N, n_features) float32 array
        y: (N,) int64 array of targets
    """
    if features is None:
        features = FEATURE_NAMES

    valid_cols = [f for f in features if f in df.columns]
    needed = valid_cols + ["target"]
    df_clean = df[needed].dropna()

    X = df_clean[valid_cols].values.astype(np.float32)
    y = df_clean["target"].values.astype(np.int64)

    X = np.clip(X, -10.0, 10.0)
    X = np.nan_to_num(X, nan=0.0, posinf=10.0, neginf=-10.0)

    return X, y
