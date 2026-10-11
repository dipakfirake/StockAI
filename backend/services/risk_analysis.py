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

        # Historical 95% & 99% Value at Risk (VaR)
        var_95_val = float(np.percentile(returns, 5)) if returns else 0.0
        var_95 = abs(var_95_val) * 100 if math.isfinite(var_95_val) else 0.0

        var_99_val = float(np.percentile(returns, 1)) if returns else 0.0
        var_99 = abs(var_99_val) * 100 if math.isfinite(var_99_val) else 0.0

        # Expected Shortfall (CVaR / Conditional VaR) - average of tail losses beyond VaR
        tail_95 = [r for r in returns if r <= var_95_val]
        cvar_95 = abs(float(np.mean(tail_95))) * 100 if tail_95 else var_95

        tail_99 = [r for r in returns if r <= var_99_val]
        cvar_99 = abs(float(np.mean(tail_99))) * 100 if tail_99 else var_99

        # Annualized return (Compound Annual Growth Rate if >= 20 bars, else sample annualized)
        total_return = (closes[-1] / closes[0]) - 1 if closes[0] > 0 else 0.0
        years = max(1.0 / 252.0, len(closes) / 252.0)
        if total_return > -1.0:
            annualized_return = ((1.0 + total_return) ** (1.0 / years)) - 1.0
        else:
            annualized_return = -1.0

        risk_free_rate = 0.05
        annualized_vol = daily_vol * math.sqrt(252)
        sharpe_ratio = (annualized_return - risk_free_rate) / annualized_vol if annualized_vol > 0 else 0.0
        if not math.isfinite(sharpe_ratio):
            sharpe_ratio = 0.0

        # Sortino Ratio (Excess return / Downside Volatility)
        annualized_downside_vol = downside_vol * math.sqrt(252)
        sortino_ratio = (annualized_return - risk_free_rate) / annualized_downside_vol if annualized_downside_vol > 0 else 0.0
        if not math.isfinite(sortino_ratio):
            sortino_ratio = 0.0

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
            "annualized_return_pct": round(annualized_return * 100, 2),
            "value_at_risk_95_pct": round(var_95, 2),
            "value_at_risk_99_pct": round(var_99, 2),
            "expected_shortfall_cvar_95_pct": round(cvar_95, 2),
            "expected_shortfall_cvar_99_pct": round(cvar_99, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "observations": len(closes),
            "methodology": "Historical Value at Risk (VaR 95%/99%) and Expected Shortfall (CVaR). Sharpe & Sortino ratios assume 5% risk-free rate.",
        }
    except Exception as e:
        return {
            "level": "UNKNOWN",
            "reason": f"Risk analysis error: {str(e)}",
            "annualized_volatility_pct": 0.0,
            "downside_volatility_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "period_return_pct": 0.0,
            "annualized_return_pct": 0.0,
            "value_at_risk_95_pct": 0.0,
            "value_at_risk_99_pct": 0.0,
            "expected_shortfall_cvar_95_pct": 0.0,
            "expected_shortfall_cvar_99_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "observations": len(candles),
            "methodology": "Error fallback",
        }
