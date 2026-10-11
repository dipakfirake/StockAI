"""
Unit & Integration tests for the Automated Swing Screener Engine.
Verifies market-wide stock scanning, multi-tier ranking, and categorized
Buy / Sell / Hold partitioning with mathematical precision and risk metrics.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.screener import screener_service, ScreenerService, SECTOR_UNIVERSES


@pytest.mark.asyncio
class TestSwingScreenerCategorization:
    """Validate swing screener engine behavior, sector universe parsing, and categorized output."""

    async def test_run_screener_categorization_and_metrics(self):
        """Test screener correctly partitions setups into BUY, SELL, and HOLD lists."""
        
        async def fake_analyze(symbol: str, force_refresh: bool = False):
            if "BUY" in symbol:
                return {
                    "symbol": symbol,
                    "name": f"{symbol} Ltd",
                    "action": "BUY",
                    "total_score": 78.5,
                    "scores": {"technical": 80.0, "fundamental": 75.0, "sentiment": 80.0},
                    "trade_plan": {
                        "entry_price": 2500.0,
                        "stop_loss": 2420.0,
                        "target_price": 2680.0,
                        "target_1": 2580.0,
                        "target_2": 2680.0,
                        "target_3": 2780.0,
                        "expected_gain_pct": 7.2,
                        "risk_pct": 3.2,
                        "reward_to_risk": 2.25,
                        "estimated_hold_time": "4 to 7 Days",
                        "targets": [
                            {"level": "T1 (Conservative)", "price": 2580.0, "gain_pct": 3.2, "reward_to_risk": 1.0},
                            {"level": "T2 (Primary / Optimal)", "price": 2680.0, "gain_pct": 7.2, "reward_to_risk": 2.25},
                            {"level": "T3 (Extended Breakout)", "price": 2780.0, "gain_pct": 11.2, "reward_to_risk": 3.5}
                        ]
                    },
                    "news_sentiment": "POSITIVE"
                }
            elif "SELL" in symbol:
                return {
                    "symbol": symbol,
                    "name": f"{symbol} Ltd",
                    "action": "SELL",
                    "total_score": 32.0,
                    "scores": {"technical": 30.0, "fundamental": 35.0, "sentiment": 30.0},
                    "trade_plan": {
                        "entry_price": 1800.0,
                        "stop_loss": 1860.0,
                        "target_price": 1660.0,
                        "target_1": 1730.0,
                        "target_2": 1660.0,
                        "target_3": 1580.0,
                        "expected_gain_pct": 7.78,
                        "risk_pct": 3.33,
                        "reward_to_risk": 2.33,
                        "estimated_hold_time": "3 to 6 Days",
                        "targets": [
                            {"level": "T1 (Conservative)", "price": 1730.0, "gain_pct": 3.89, "reward_to_risk": 1.17},
                            {"level": "T2 (Primary / Optimal)", "price": 1660.0, "gain_pct": 7.78, "reward_to_risk": 2.33},
                            {"level": "T3 (Extended Breakout)", "price": 1580.0, "gain_pct": 12.22, "reward_to_risk": 3.67}
                        ]
                    },
                    "news_sentiment": "NEGATIVE"
                }
            else:
                return {
                    "symbol": symbol,
                    "name": f"{symbol} Ltd",
                    "action": "HOLD",
                    "total_score": 52.0,
                    "scores": {"technical": 51.0, "fundamental": 53.0, "sentiment": 52.0},
                    "trade_plan": {
                        "entry_price": 1000.0,
                        "stop_loss": 950.0,
                        "target_price": 1050.0,
                        "target_1": 1030.0,
                        "target_2": 1050.0,
                        "target_3": 1070.0,
                        "expected_gain_pct": 5.0,
                        "risk_pct": 5.0,
                        "reward_to_risk": 1.0,
                        "estimated_hold_time": "3 to 5 Days",
                        "targets": [
                            {"level": "T1 (Conservative)", "price": 1030.0, "gain_pct": 3.0, "reward_to_risk": 0.6},
                            {"level": "T2 (Primary / Optimal)", "price": 1050.0, "gain_pct": 5.0, "reward_to_risk": 1.0},
                            {"level": "T3 (Extended Breakout)", "price": 1070.0, "gain_pct": 7.0, "reward_to_risk": 1.4}
                        ]
                    },
                    "news_sentiment": "NEUTRAL"
                }

        test_universe = ["BUY_STOCK_1", "SELL_STOCK_1", "HOLD_STOCK_1", "BUY_STOCK_2"]

        with patch.object(ScreenerService, "_analyze_symbol", side_effect=fake_analyze):
            result = await screener_service.run_screener(symbols=test_universe, sector="TEST", force_refresh=True)

        assert "buy_stocks" in result
        assert "sell_stocks" in result
        assert "hold_stocks" in result
        assert "summary" in result
        assert result["sector"] == "TEST"
        assert result["total_scanned"] == 4

        # BUY stocks assertions
        assert len(result["buy_stocks"]) == 2
        for item in result["buy_stocks"]:
            assert item["action"] == "BUY"
            assert item["total_score"] >= 60.0
            assert "trade_plan" in item
            tp = item["trade_plan"]
            assert tp["entry_price"] > 0
            assert tp["target_price"] > tp["entry_price"]
            assert tp["stop_loss"] < tp["entry_price"]
            assert tp["expected_gain_pct"] > 0
            assert len(tp["targets"]) == 3

        # SELL stocks assertions
        assert len(result["sell_stocks"]) == 1
        item = result["sell_stocks"][0]
        assert item["action"] == "SELL"
        assert item["total_score"] <= 40.0
        tp = item["trade_plan"]
        assert tp["entry_price"] > 0
        assert tp["target_price"] < tp["entry_price"]
        assert tp["stop_loss"] > tp["entry_price"]

        # HOLD stocks assertions
        assert len(result["hold_stocks"]) == 1
        item = result["hold_stocks"][0]
        assert item["action"] == "HOLD"
        assert 40.0 < item["total_score"] < 60.0

        # Summary quantitative stats
        summary = result["summary"]
        assert summary["total_scanned"] == 4
        assert summary["valid_results"] == 4
        assert summary["buy_count"] == 2
        assert summary["sell_count"] == 1
        assert summary["hold_count"] == 1
        assert summary["market_breadth"] == "BULLISH"
        assert summary["top_buy_pick"] == "BUY_STOCK_1"
        assert summary["top_sell_pick"] == "SELL_STOCK_1"


class TestSectorUniverses:
    """Validate sector universes."""

    def test_sector_universes_presence(self):
        """Verify standard sector universes are configured with liquid equities."""
        sectors = ["NIFTY_50", "BANKING", "IT", "AUTO", "PHARMA", "ENERGY", "FMCG", "METAL", "MID_CAP", "SMALL_CAP"]
        for s in sectors:
            assert s in SECTOR_UNIVERSES
            assert len(SECTOR_UNIVERSES[s]) >= 5
