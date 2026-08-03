"""Transparent, data-derived risk measurements for stock research."""

from __future__ import annotations

import math
import statistics
import numpy as np


def analyse_risk(candles: list[dict]) -> dict:
    """Calculate Value at Risk (VaR), Sharpe Ratio, and downside risk from supplied OHLCV data.
    
    Uses institutional-grade metrics like 95% Historical VaR to determine the risk level,
    separating risk (volatility/downside) from price direction (signals).
    """
    closes = [float(c["close"]) for c in candles if c.get("close") not in (None, 0)]
    if len(closes) < 3:
        return {"level": "UNKNOWN", "reason": "At least three candles are required"}

    returns = [(current / previous) - 1 for previous, current in zip(closes, closes[1:]) if previous]
    
    # Standard Volatility (Annualized)
    daily_vol = statistics.stdev(returns) if len(returns) > 1 else 0.0
    volatility = daily_vol * math.sqrt(252) * 100
    
    # Downside Volatility
    downside = [r for r in returns if r < 0]
    downside_volatility = statistics.stdev(downside) * math.sqrt(252) * 100 if len(downside) > 1 else 0.0
    
    # Maximum Drawdown
    peak = closes[0]
    max_drawdown = 0.0
    for close in closes:
        peak = max(peak, close)
        max_drawdown = min(max_drawdown, (close / peak - 1) * 100)
        
    # Historical 95% Value at Risk (VaR)
    # The 5th percentile of returns. If it's -0.02, it means 95% of the time, the stock doesn't drop more than 2% in a day.
    var_95 = abs(np.percentile(returns, 5)) * 100 if returns else 0.0
    
    # Simplified Sharpe Ratio (assuming 5% risk-free rate)
    total_return = (closes[-1] / closes[0]) - 1
    annualized_return = (total_return / len(closes)) * 252
    risk_free_rate = 0.05
    sharpe_ratio = (annualized_return - risk_free_rate) / (daily_vol * math.sqrt(252)) if daily_vol > 0 else 0.0

    # Risk Classification based on VaR (95%)
    if var_95 < 1.5:
        level = "LOW"
    elif var_95 < 3.0:
        level = "MEDIUM"
    else:
        level = "HIGH"

    return {
        "level": level,
        "annualized_volatility_pct": round(volatility, 2),
        "downside_volatility_pct": round(downside_volatility, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "period_return_pct": round(total_return * 100, 2),
        "value_at_risk_95_pct": round(var_95, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "observations": len(closes),
        "methodology": "95% Historical Value at Risk (VaR) used for level classification. Sharpe ratio assumes 5% risk-free rate.",
    }
