"""
Comprehensive automated stress-test suite verifying zero-crash resilience
and mathematical precision across all StockAI API endpoints and quantitative models.
"""

import pytest
import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.backtesting import BacktestEngine
from backend.services.risk_analysis import analyse_risk
from backend.services.options_engine import BlackScholesEngine, OptionsChainGenerator, options_engine
from backend.services.volume_profile import calculate_volume_profile
from backend.services.institutional_hunter import SMC_Engine


# ==============================================================================
# SECTION 1: QUANTITATIVE & MATHEMATICAL FORMULA PRECISION TESTS
# ==============================================================================

class TestMathematicalPrecision:
    """Validate mathematical precision, edge case bounds, and financial metrics."""

    def test_backtesting_profit_factor_precision(self):
        """Test profit factor removes magic 9999.0 and computes exact ratios."""
        # Case A: Mixed wins and losses
        trades_mixed = [
            {"pnl": 500.0}, {"pnl": -200.0}, {"pnl": 300.0}, {"pnl": -100.0}
        ]
        metrics_mixed = BacktestEngine._compute_metrics(trades_mixed, [{"equity": 100500.0}], 100000.0)
        assert metrics_mixed["profit_factor"] == round(800.0 / 300.0, 3)
        assert metrics_mixed["win_rate"] == 0.5
        assert metrics_mixed["total_trades"] == 4

        # Case B: All wins, 0 losses (must NOT be 9999.0)
        trades_all_wins = [{"pnl": 1200.0}, {"pnl": 800.0}]
        metrics_wins = BacktestEngine._compute_metrics(trades_all_wins, [{"equity": 102000.0}], 100000.0)
        assert metrics_wins["profit_factor"] == 2000.0  # Exact sum of wins
        assert metrics_wins["profit_factor"] != 9999.0
        assert metrics_wins["win_rate"] == 1.0

        # Case C: 0 trades
        metrics_empty = BacktestEngine._compute_metrics([], [], 100000.0)
        assert metrics_empty["profit_factor"] == 0.0
        assert metrics_empty["win_rate"] == 0.0

    def test_backtesting_equity_curve_and_calmar_precision(self):
        """Test Calmar ratio under positive, flat, and severe negative returns."""
        # Positive returns
        eq_curve_pos = [{"date": "2026-01-01", "equity": 100000.0}] + [
            {"date": f"2026-01-{i:02d}", "equity": 100000.0 + i * 500} for i in range(2, 50)
        ]
        # Introduce a 5% drawdown
        eq_curve_pos.append({"date": "2026-03-01", "equity": 118000.0})
        metrics_pos = BacktestEngine._compute_metrics([{"pnl": 18000.0}], eq_curve_pos, 100000.0)
        assert math.isfinite(metrics_pos["calmar_ratio"])
        assert metrics_pos["calmar_ratio"] >= 0.0

        # Severe negative returns (must not yield NaN or complex numbers)
        eq_curve_neg = [
            {"date": "2026-01-01", "equity": 100000.0},
            {"date": "2026-01-02", "equity": 40000.0},
            {"date": "2026-01-03", "equity": 30000.0},
        ]
        metrics_neg = BacktestEngine._compute_metrics([{"pnl": -70000.0}], eq_curve_neg, 100000.0)
        assert math.isfinite(metrics_neg["calmar_ratio"])
        assert not math.isnan(metrics_neg["calmar_ratio"])

    def test_risk_analysis_var_cvar_and_sortino_precision(self):
        """Test VaR 95%, VaR 99%, CVaR (Expected Shortfall), and Sortino ratio."""
        # Generate synthetic realistic OHLCV
        np.random.seed(42)
        base_price = 1000.0
        daily_returns = np.random.normal(0.0005, 0.015, 100)
        prices = [base_price]
        for r in daily_returns:
            prices.append(prices[-1] * (1 + r))

        candles = [{"close": p, "timestamp": f"2026-01-{i}"} for i, p in enumerate(prices)]
        res = analyse_risk(candles)

        assert res["level"] in {"LOW", "MEDIUM", "HIGH"}
        assert "value_at_risk_95_pct" in res
        assert "value_at_risk_99_pct" in res
        assert "expected_shortfall_cvar_95_pct" in res
        assert "expected_shortfall_cvar_99_pct" in res
        assert "sortino_ratio" in res
        assert "sharpe_ratio" in res

        # Mathematical Invariants:
        # VaR 99% must be >= VaR 95%
        assert res["value_at_risk_99_pct"] >= res["value_at_risk_95_pct"]
        # Expected Shortfall (CVaR 95%) must be >= VaR 95%
        assert res["expected_shortfall_cvar_95_pct"] >= res["value_at_risk_95_pct"]

    def test_risk_analysis_edge_case_flat_prices(self):
        """Test risk analysis with completely flat candles (0 volatility)."""
        flat_candles = [{"close": 500.0, "timestamp": f"2026-01-{i}"} for i in range(30)]
        res = analyse_risk(flat_candles)
        assert res["annualized_volatility_pct"] == 0.0
        assert res["max_drawdown_pct"] == 0.0
        assert res["value_at_risk_95_pct"] == 0.0
        assert res["level"] == "LOW"
        assert not math.isnan(res["sharpe_ratio"])

    def test_risk_analysis_insufficient_data(self):
        """Test risk analysis with fewer than 3 candles returns gracefully."""
        res = analyse_risk([{"close": 100.0}])
        assert res["level"] == "UNKNOWN"

    def test_black_scholes_boundary_guards(self):
        """Test Black-Scholes formulas under extreme and zero values without crashing."""
        # Zero spot price
        assert BlackScholesEngine.call_price(0.0, 100.0, 0.1, 0.07, 0.2) == 0.0
        assert BlackScholesEngine.put_price(0.0, 100.0, 0.1, 0.07, 0.2) == 0.0

        # Zero or negative strike
        assert BlackScholesEngine.call_price(100.0, 0.0, 0.1, 0.07, 0.2) == 0.0
        assert BlackScholesEngine.d1(100.0, 0.0, 0.1, 0.07, 0.2) == 0.0

        # Zero time to expiry T=0
        assert BlackScholesEngine.call_price(110.0, 100.0, 0.0, 0.07, 0.2) == 10.0
        assert BlackScholesEngine.put_price(90.0, 100.0, 0.0, 0.07, 0.2) == 10.0

        # Zero volatility sigma=0
        assert math.isfinite(BlackScholesEngine.gamma(100.0, 100.0, 0.1, 0.07, 0.0))
        assert math.isfinite(BlackScholesEngine.vega(100.0, 100.0, 0.1, 0.07, 0.0))
        assert math.isfinite(BlackScholesEngine.call_theta(100.0, 100.0, 0.1, 0.07, 0.0))

    def test_options_chain_and_dynamic_lot_sizes(self):
        """Test dynamic lot sizes and strategy recommendation."""
        # Verify lot sizes
        assert OptionsChainGenerator.get_lot_size("^NSEI") == 50
        assert OptionsChainGenerator.get_lot_size("^NSEBANK") == 15
        assert OptionsChainGenerator.get_lot_size("RELIANCE.NS") == 250
        assert OptionsChainGenerator.get_lot_size("TCS.NS") == 175

        # Test chain generation with zero price (must return clean dict, not [])
        chain_zero = OptionsChainGenerator.generate_chain("^NSEI", 0.0)
        assert isinstance(chain_zero, dict)
        assert chain_zero["chain"] == []
        assert chain_zero["spot_price"] == 0.0

        # Test valid chain generation
        chain_valid = OptionsChainGenerator.generate_chain("^NSEI", 24500.0, 14.5)
        assert isinstance(chain_valid, dict)
        assert len(chain_valid["chain"]) > 0
        assert chain_valid["lot_size"] == 50

        # Test strategy recommendation
        strategy_buy = OptionsChainGenerator.recommend_strategy(chain_valid, "BUY", 75.0, 14.5)
        assert strategy_buy is not None
        assert strategy_buy["lot_size"] == 50
        assert strategy_buy["max_profit_per_lot"] >= 0.0
        assert strategy_buy["max_loss_per_lot"] >= 0.0
        assert len(strategy_buy["legs"]) == 2

    def test_volume_profile_accounting_invariant(self):
        """Test volume profile guarantees exact total volume accounting with 0 loss."""
        df = pd.DataFrame({
            "Open": [100.0, 102.0, 101.0, 105.0, 104.0],
            "High": [103.0, 105.0, 104.0, 108.0, 106.0],
            "Low": [99.0, 101.0, 100.0, 103.0, 102.0],
            "Close": [102.0, 104.0, 103.0, 107.0, 105.0],
            "Volume": [10000, 15000, 12000, 20000, 18000],
        })
        profile = calculate_volume_profile(df, num_bins=20)
        assert "bins" in profile
        assert "poc" in profile
        assert "vah" in profile
        assert "val" in profile
        assert profile["val"] <= profile["poc"] <= profile["vah"]

        # Invariant: Sum of individual bin volumes strictly equals total_volume
        bins_sum = sum(b["total_volume"] for b in profile["bins"])
        assert profile["total_volume"] == bins_sum

    def test_institutional_fvg_trade_plan_precision(self):
        """Test SMC Engine FVG trade plan calculations."""
        smc = SMC_Engine()
        fvg = {
            "type": "bullish_fvg",
            "top": 2500.0,
            "bottom": 2450.0,
            "gap_size": 50.0,
            "gap_pct": 2.0,
        }
        plan = smc._build_trade_plan(fvg, 2520.0)
        assert plan["recommended_entry"] == 2475.0  # Midpoint
        assert plan["stop_loss"] < plan["recommended_entry"]
        assert plan["target_1"] > plan["recommended_entry"]
        assert plan["target_2"] > plan["target_1"]
        assert plan["target_3"] > plan["target_2"]
        assert plan["reward_to_risk"] > 0.0


# ==============================================================================
# SECTION 2: ENDPOINT CRASH RESILIENCE & INPUT BOUNDARY TESTS
# ==============================================================================

class TestEndpointCrashResilience:
    """Stress test endpoints against malformed payloads, NoneType casts, and edge inputs."""

    @pytest.mark.asyncio
    async def test_portfolio_calculation_with_none_fields(self):
        """Verify portfolio calculations survive unexecuted orders with None entry_price or commission."""
        from backend.api.portfolio import get_portfolio

        mock_user = MagicMock()
        mock_user.id = "00000000-0000-0000-0000-000000000001"

        # Trade with None entry_price and None commission
        mock_trade = MagicMock()
        mock_trade.user_id = mock_user.id
        mock_trade.symbol = "RELIANCE.NS"
        mock_trade.direction = "BUY"
        mock_trade.product_type = "INTRADAY"
        mock_trade.quantity = 10
        mock_trade.entry_price = None  # CRASH VECTOR: float(None)
        mock_trade.commission = None   # CRASH VECTOR: float(None)
        mock_trade.stt_tax = None
        mock_trade.realized_pnl = None
        mock_trade.status = "OPEN"

        mock_db = AsyncMock()
        mock_db_result = MagicMock()
        mock_db_result.scalars.return_value.all.return_value = [mock_trade]
        mock_db.execute.return_value = mock_db_result

        with patch("backend.services.market_data.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_bulk:
            mock_bulk.return_value = {
                "RELIANCE.NS": {"price": 2500.0, "change": 10.0, "change_pct": 0.4}
            }
            # Must complete with 200 OK without raising TypeError
            res = await get_portfolio(current_user=mock_user, db=mock_db)
            assert res["initial_capital"] == 100000.0
            assert "total_pnl" in res
            assert len(res["allocation"]) == 1

    @pytest.mark.asyncio
    async def test_paper_trading_invalid_uuid_safe_rejection(self):
        """Verify close_paper_trade rejects non-UUID strings with 400 instead of 500 crash."""
        from backend.api.paper_trading import close_paper_trade
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.id = "00000000-0000-0000-0000-000000000001"
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await close_paper_trade("invalid-non-uuid-string", current_user=mock_user, db=mock_db)
        assert exc_info.value.status_code == 400
        assert "Invalid trade_id format" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_alerts_invalid_uuid_safe_rejection(self):
        """Verify alert delete & deactivate reject malformed UUIDs with 400."""
        from backend.api.alerts import delete_alert, deactivate_alert
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.id = "00000000-0000-0000-0000-000000000001"
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_delete:
            await delete_alert("bad-alert-id", current_user=mock_user, db=mock_db)
        assert exc_delete.value.status_code == 400

        with pytest.raises(HTTPException) as exc_deact:
            await deactivate_alert("bad-alert-id", current_user=mock_user, db=mock_db)
        assert exc_deact.value.status_code == 400

    @pytest.mark.asyncio
    async def test_websocket_broadcast_alert_parameter_resilience(self):
        """Verify broadcast_alert handles both user_id targeted and broadcast calls without TypeError."""
        from backend.api.websocket import broadcast_alert

        # 1. Targeted call with user_id (as called in alert_tasks.py)
        await broadcast_alert({"message": "Targeted test"}, user_id="user-123")

        # 2. General broadcast without user_id (as called in auto_trader.py)
        await broadcast_alert({"message": "General broadcast"})

    @pytest.mark.asyncio
    async def test_backtest_run_negative_capital_rejected(self):
        """Verify run_backtest rejects negative initial capital with 400."""
        from backend.api.backtesting import run_backtest, BacktestRequest
        from fastapi import HTTPException, BackgroundTasks

        mock_user = MagicMock()
        mock_bg = MagicMock(spec=BackgroundTasks)
        mock_db = AsyncMock()

        req = BacktestRequest(
            symbol="RELIANCE.NS",
            strategy="rsi_mean_reversion",
            start_date="2025-01-01",
            end_date="2026-01-01",
            initial_capital=-5000.0
        )

        with pytest.raises(HTTPException) as exc_info:
            await run_backtest(req, mock_bg, current_user=mock_user, db=mock_db)
        assert exc_info.value.status_code == 400
        assert "initial_capital must be greater than 0" in exc_info.value.detail
