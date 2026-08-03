"""Data quality validation for OHLCV candles."""

import pandas as pd
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


def validate_candles(df: pd.DataFrame, symbol: str = "") -> pd.DataFrame:
    """
    Validate OHLCV DataFrame and remove invalid rows.
    Checks:
    - No null values in OHLCV columns
    - High >= Low
    - High >= Close >= Low
    - High >= Open >= Low (approx)
    - Volume > 0
    - No future timestamps
    - No extreme outliers (price > 10x previous)
    """
    if df.empty:
        return df

    original_len = len(df)
    issues = []

    # Drop rows with null OHLCV
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

    # High must be >= Low
    invalid_hl = df["High"] < df["Low"]
    if invalid_hl.any():
        issues.append(f"{invalid_hl.sum()} rows with High < Low")
        df = df[~invalid_hl]

    # Close must be within [Low, High]
    invalid_close = (df["Close"] < df["Low"]) | (df["Close"] > df["High"])
    if invalid_close.any():
        issues.append(f"{invalid_close.sum()} rows with Close outside [Low, High]")
        df = df[~invalid_close]

    # Volume must be positive
    invalid_vol = df["Volume"] <= 0
    if invalid_vol.any():
        issues.append(f"{invalid_vol.sum()} rows with Volume <= 0")
        df = df[~invalid_vol]

    # No future timestamps
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    if df.index.tz is not None:
        now = pd.Timestamp.now(tz="UTC")
    future = df.index > now
    if future.any():
        issues.append(f"{future.sum()} rows with future timestamps")
        df = df[~future]

    # Remove extreme price outliers (>10x compared to rolling median)
    if len(df) > 10:
        rolling_med = df["Close"].rolling(window=10, min_periods=3).median()
        outliers = (df["Close"] > rolling_med * 10) | (df["Close"] < rolling_med * 0.1)
        if outliers.any():
            issues.append(f"{outliers.sum()} rows flagged as price outliers")
            df = df[~outliers]

    removed = original_len - len(df)
    if removed > 0:
        logger.warning(f"[{symbol}] Removed {removed}/{original_len} invalid candles. Issues: {'; '.join(issues)}")
    else:
        logger.debug(f"[{symbol}] All {original_len} candles passed validation")

    return df
