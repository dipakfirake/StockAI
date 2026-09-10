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
    try:
        closes = []
        for c in candles:
            val = c.get("close")
            if val is not None:
                try:
                    fval = float(val)
                    if math.isfinite(fval) and fval > 0:
                        closes.append(fval)
                except (ValueError, TypeError):
                    continue

        if len(closes) < 3:
            return {"level": "UNKNOWN", "reason": "At least three valid candles are required"}

        returns = [(current / previous) - 1 for previous, current in zip(closes, closes[1:]) if previous > 0]
        returns = [r for r in returns if math.isfinite(r)]

        if len(returns) < 2:
            return {"level": "UNKNOWN", "reason": "Insufficient return data for risk analysis"}

        # Standard Volatility (Annualized) using NumPy sample std (ddof=1)
        daily_vol = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
        if not math.isfinite(daily_vol):
            daily_vol = 0.0
        volatility = daily_vol * math.sqrt(252) * 100

        # Downside Volatility
        downside = [r for r in returns if r < 0]
        downside_vol = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
        if not math.isfinite(downside_vol):
            downside_vol = 0.0
        downside_volatility = downside_vol * math.sqrt(252) * 100

        # Maximum Drawdown
        peak = closes[0]
        max_drawdown = 0.0
        for close in closes:
            peak = max(peak, close)
            if peak > 0:
                max_drawdown = min(max_drawdown, (close / peak - 1) * 100)

        # Historical 95% Value at Risk (VaR)
        var_95 = abs(float(np.percentile(returns, 5))) * 100 if returns else 0.0
        if not math.isfinite(var_95):
            var_95 = 0.0

        # Simplified Sharpe Ratio (assuming 5% risk-free rate)
        total_return = (closes[-1] / closes[0]) - 1 if closes[0] > 0 else 0.0
        annualized_return = (total_return / len(closes)) * 252
        risk_free_rate = 0.05
        sharpe_ratio = (annualized_return - risk_free_rate) / (daily_vol * math.sqrt(252)) if daily_vol > 0 else 0.0
        if not math.isfinite(sharpe_ratio):
            sharpe_ratio = 0.0

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
    except Exception as e:
        return {
            "level": "UNKNOWN",
            "reason": f"Risk analysis error: {str(e)}",
            "annualized_volatility_pct": 0.0,
            "downside_volatility_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "period_return_pct": 0.0,
            "value_at_risk_95_pct": 0.0,
            "sharpe_ratio": 0.0,
            "observations": len(candles),
            "methodology": "Error fallback",
        }
