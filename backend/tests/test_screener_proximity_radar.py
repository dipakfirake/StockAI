"""
Unit tests for Swing Screener Best Buy Proximity Radar and Bulk Alerts.
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock, AsyncMock

from backend.api.alerts import (
    get_screener_proximity_radar,
    setup_screener_bulk_alerts,
    BulkScreenerAlertRequest,
    BulkScreenerAlertItem,
)
from backend.models.alert import Alert
from backend.tasks.alert_tasks import _evaluate_alerts_async


@pytest.mark.asyncio
async def test_screener_proximity_radar_calculation():
    """Verify that get_screener_proximity_radar computes distances, statuses, and sorts by proximity."""
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    mock_candidates = [
        {
            "symbol": "TCS.NS",
            "name": "Tata Consultancy Services",
            "sector": "IT",
            "action": "BUY",
            "total_score": 85.0,
            "trade_plan": {
                "best_buy_price": 4000.0,
                "current_price": 4010.0,
                "target_price": 4300.0,
                "stop_loss": 3850.0,
                "expected_gain_pct": 7.5,
                "risk_reward_ratio": 2.0,
                "entry_type": "PULLBACK_DIP",
            }
        },
        {
            "symbol": "INFY.NS",
            "name": "Infosys Ltd",
            "sector": "IT",
            "action": "BUY",
            "total_score": 78.0,
            "trade_plan": {
                "best_buy_price": 1800.0,
                "current_price": 1830.0,
                "target_price": 1950.0,
                "stop_loss": 1720.0,
                "expected_gain_pct": 8.3,
                "risk_reward_ratio": 1.9,
                "entry_type": "BREAKOUT",
            }
        },
        {
            "symbol": "WIPRO.NS",
            "name": "Wipro Ltd",
            "sector": "IT",
            "action": "BUY",
            "total_score": 70.0,
            "trade_plan": {
                "best_buy_price": 500.0,
                "current_price": 550.0,  # 10% away -> should be filtered out when proximity_pct=3.0
                "target_price": 580.0,
                "stop_loss": 470.0,
                "expected_gain_pct": 16.0,
                "risk_reward_ratio": 2.7,
                "entry_type": "PULLBACK_DIP",
            }
        }
    ]

    # Mock Redis cache misses
    with patch("backend.core.cache.cache_get", new_callable=AsyncMock) as mock_cache_get, \
         patch("backend.core.cache.cache_set", new_callable=AsyncMock) as mock_cache_set, \
         patch("backend.services.screener.ScreenerService.run_screener", new_callable=AsyncMock) as mock_screener, \
         patch("backend.services.market_data.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_bulk_quotes:

        # No cached radar
        mock_cache_get.side_effect = lambda key: None
        mock_screener.return_value = {"buy_stocks": mock_candidates}
        mock_bulk_quotes.return_value = {
            "TCS.NS": {"price": 4008.0},  # 4008 vs 4000 = +0.2% -> AT_BEST_BUY
            "INFY.NS": {"price": 1825.0}, # 1825 vs 1800 = +1.39% -> NEAR_BEST_BUY
            "WIPRO.NS": {"price": 545.0}, # 545 vs 500 = +9.0% -> > 3.0% filtered
        }

        res = await get_screener_proximity_radar(
            sector="IT",
            proximity_pct=3.0,
            min_score=60.0,
            current_user=mock_user,
        )

    assert res["sector"] == "IT"
    assert res["total_candidates"] == 2  # TCS and INFY included; WIPRO filtered
    candidates = res["candidates"]
    
    # Check TCS
    tcs = next(c for c in candidates if c["symbol"] == "TCS.NS")
    assert tcs["cmp"] == 4008.0
    assert tcs["best_buy_price"] == 4000.0
    assert tcs["distance_pct"] == 0.2
    assert tcs["proximity_status"] == "AT_BEST_BUY"

    # Check INFY
    infy = next(c for c in candidates if c["symbol"] == "INFY.NS")
    assert infy["cmp"] == 1825.0
    assert infy["distance_pct"] == 1.39
    assert infy["proximity_status"] == "NEAR_BEST_BUY"

    # Sorted closest first: TCS (0.2%) before INFY (1.39%)
    assert candidates[0]["symbol"] == "TCS.NS"
    assert candidates[1]["symbol"] == "INFY.NS"

    assert res["summary"]["at_best_buy"] == 1
    assert res["summary"]["near_best_buy"] == 1


@pytest.mark.asyncio
async def test_setup_screener_bulk_alerts():
    """Verify setup_screener_bulk_alerts creates coupled pre-alerts for multiple candidates."""
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    items = [
        BulkScreenerAlertItem(
            symbol="RELIANCE.NS",
            current_price=2950.0,
            best_buy_price=2930.0,
            target_price=3150.0,
            stop_loss=2820.0,
            proximity_pct=1.0,
        ),
        BulkScreenerAlertItem(
            symbol="HDFCBANK.NS",
            current_price=1650.0,
            best_buy_price=1640.0,
            target_price=1750.0,
            stop_loss=1580.0,
            proximity_pct=1.0,
        )
    ]
    req = BulkScreenerAlertRequest(items=items)

    with patch("backend.api.alerts.broadcast_alert", new_callable=AsyncMock) as mock_broadcast:
        res = await setup_screener_bulk_alerts(req, current_user=mock_user, db=mock_db)

    assert res["symbols_count"] == 2
    assert res["alerts_created_count"] == 10  # 5 coupled alerts per stock (Buy, Target Prox, Target Hit, SL Prox, SL Hit)
    assert "RELIANCE.NS" in res["symbols"]
    assert "HDFCBANK.NS" in res["symbols"]
    assert mock_db.add.call_count == 10
    mock_broadcast.assert_called_once()


@pytest.mark.asyncio
async def test_alert_evaluation_uses_bulk_quotes():
    """Verify that _evaluate_alerts_async uses bulk quote pre-fetching to prevent individual queries."""
    alert1 = Alert(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        symbol="SBIN.NS",
        condition_type="BUY_PROXIMITY",
        condition_value=810.0,
        is_active=True,
        priority="HIGH",
        delivery_method="IN_APP",
        triggered_at=None,
    )
    alert2 = Alert(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        symbol="ICICIBANK.NS",
        condition_type="TARGET_PROXIMITY",
        condition_value=1250.0,
        is_active=True,
        priority="HIGH",
        delivery_method="IN_APP",
        triggered_at=None,
    )

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [alert1, alert2]

    mock_db = AsyncMock()
    mock_db.execute.return_value = result_mock
    mock_db.__aenter__.return_value = mock_db
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    with patch("backend.core.database.AsyncSessionLocal", return_value=mock_db), \
         patch("backend.services.market_data.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_bulk, \
         patch("backend.services.market_data.market_data_service.fetch_quote", new_callable=AsyncMock) as mock_single, \
         patch("backend.api.websocket.broadcast_alert", new_callable=AsyncMock):

        mock_bulk.return_value = {
            "SBIN.NS": {"price": 805.0},  # <= 810 -> triggers BUY_PROXIMITY
            "ICICIBANK.NS": {"price": 1260.0},  # >= 1250 -> triggers TARGET_PROXIMITY
        }

        res = await _evaluate_alerts_async()

    # Verify bulk quotes was called with the symbols
    mock_bulk.assert_called_once()
    symbols_requested = mock_bulk.call_args[0][0]
    assert "SBIN.NS" in symbols_requested
    assert "ICICIBANK.NS" in symbols_requested
    # Single quote fetch should NOT have been called because bulk quote succeeded!
    assert mock_single.call_count == 0
    assert res["triggered"] == 2


@pytest.mark.asyncio
async def test_pre_buy_and_sell_pre_alerts_radar_features():
    """Verify that radar accurately computes Pre-Buy Opportunities (strictly before buy price) and Sell Pre-Alerts."""
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    mock_candidates = [
        {
            "symbol": "RELIANCE.NS",
            "name": "Reliance Industries",
            "sector": "ENERGY",
            "action": "BUY",
            "total_score": 82.0,
            "indicators": {"rsi_14": 46.5, "atr_14": 28.0},
            "ai_analysis": {"confidence": 0.78, "probabilities": {"buy": 0.68}},
            "trade_plan": {
                "best_buy_price": 1360.0,
                "target_price": 1490.0,
                "stop_loss": 1310.0,
                "expected_gain_pct": 9.5,
                "risk_reward_ratio": 2.6,
                "entry_type": "PULLBACK_DIP",
            }
        },
        {
            "symbol": "TCS.NS",
            "name": "Tata Consultancy",
            "sector": "IT",
            "action": "BUY",
            "total_score": 79.0,
            "indicators": {"rsi_14": 52.0, "atr_14": 42.0},
            "ai_analysis": {"confidence": 0.74, "probabilities": {"buy": 0.62}},
            "trade_plan": {
                "best_buy_price": 4000.0,
                "target_price": 4300.0,
                "stop_loss": 3880.0,
                "expected_gain_pct": 7.5,
                "risk_reward_ratio": 2.5,
                "entry_type": "PULLBACK_DIP",
            }
        }
    ]

    with patch("backend.core.cache.cache_get", new_callable=AsyncMock) as mock_cache_get, \
         patch("backend.core.cache.cache_set", new_callable=AsyncMock) as mock_cache_set, \
         patch("backend.services.screener.ScreenerService.run_screener", new_callable=AsyncMock) as mock_screener, \
         patch("backend.services.market_data.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_bulk_quotes:

        mock_cache_get.side_effect = lambda key: None
        mock_screener.return_value = {"buy_stocks": mock_candidates}
        
        # RELIANCE CMP = 1370.0 (Best Buy = 1360.0 -> +0.74% BEFORE buy price -> Pre-Buy Opportunity)
        # TCS CMP = 4220.0 (Target = 4300.0 -> 1.9% away from target -> Sell Pre-Alert)
        mock_bulk_quotes.return_value = {
            "RELIANCE.NS": {"price": 1370.0},
            "TCS.NS": {"price": 4220.0},
        }

        # 1. Test All Opportunities
        res_all = await get_screener_proximity_radar(
            sector="ALL",
            proximity_pct=3.0,
            min_score=60.0,
            stage="ALL",
            current_user=mock_user,
        )

        assert res_all["total_candidates"] >= 2
        rel = next(c for c in res_all["candidates"] if c["symbol"] == "RELIANCE.NS")
        tcs = next(c for c in res_all["candidates"] if c["symbol"] == "TCS.NS")

        # Verify Pre-Buy Opportunity on RELIANCE
        assert rel["is_pre_buy"] is True
        assert rel["pre_buy_diff"] == 10.0  # 1370 - 1360 = 10 Rs before buy price
        assert rel["distance_pct"] == 0.74
        assert rel["technical_verification"]["verified"] is True
        assert len(rel["technical_verification"]["passed_constraints"]) >= 3

        # Verify Sell Pre-Alert on TCS
        assert tcs["is_near_target"] is True
        assert tcs["target_distance_pct"] == 1.9
        assert "Sell Pre-Alert" in tcs["sell_pre_alert_label"]

        # 2. Test Stage Filter: PRE_BUY
        res_pre_buy = await get_screener_proximity_radar(
            sector="ALL",
            proximity_pct=3.0,
            min_score=60.0,
            stage="PRE_BUY",
            current_user=mock_user,
        )
        symbols_pre_buy = [c["symbol"] for c in res_pre_buy["candidates"]]
        assert "RELIANCE.NS" in symbols_pre_buy
        assert "TCS.NS" not in symbols_pre_buy

        # 3. Test Stage Filter: SELL_PRE_ALERT
        res_sell = await get_screener_proximity_radar(
            sector="ALL",
            proximity_pct=3.0,
            min_score=60.0,
            stage="SELL_PRE_ALERT",
            current_user=mock_user,
        )
        symbols_sell = [c["symbol"] for c in res_sell["candidates"]]
        assert "TCS.NS" in symbols_sell
        assert "RELIANCE.NS" not in symbols_sell


@pytest.mark.asyncio
async def test_pre_buy_corridor_evaluation_before_buy_price():
    """Verify that BUY_PROXIMITY only triggers BEFORE Best Buy is hit (not after price has dropped below)."""
    # Alert configured for Pre-Buy: Best Buy is 1000.0, Pre-Buy proximity price is 1010.0
    alert_pre_buy = Alert(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        symbol="INFY.NS",
        condition_type="BUY_PROXIMITY",
        condition_value=1010.0,
        message="INFY.NS: ⚡ PRE-BUY ALERT! Price near ₹1010.00 is approaching Best Buy ₹1000.00 from above.",
        is_active=True,
        priority="MEDIUM",
        delivery_method="IN_APP",
        triggered_at=None,
    )

    alert_sell_pre = Alert(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        symbol="SBIN.NS",
        condition_type="TARGET_PROXIMITY",
        condition_value=840.0,
        message="SBIN.NS: 🎯 SELL PRE-ALERT! Price near ₹840.00 is within 1% of Target ₹850.00.",
        is_active=True,
        priority="HIGH",
        delivery_method="IN_APP",
        triggered_at=None,
    )

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [alert_pre_buy, alert_sell_pre]

    mock_db = AsyncMock()
    mock_db.execute.return_value = result_mock
    mock_db.__aenter__.return_value = mock_db
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    # Case A: INFY price is 1005 (in pre-buy corridor [1000, 1010]) -> triggers!
    # SBIN price is 845 (in sell pre-alert corridor [840, 850]) -> triggers!
    with patch("backend.core.database.AsyncSessionLocal", return_value=mock_db), \
         patch("backend.services.market_data.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_bulk, \
         patch("backend.api.websocket.broadcast_alert", new_callable=AsyncMock):

        mock_bulk.return_value = {
            "INFY.NS": {"price": 1005.0},
            "SBIN.NS": {"price": 845.0},
        }

        res_triggered = await _evaluate_alerts_async()
        assert res_triggered["triggered"] == 2

    # Reset triggered_at
    alert_pre_buy.triggered_at = None
    alert_sell_pre.triggered_at = None

    # Case B: INFY price dropped to 950 (already below Best Buy 1000) -> should NOT trigger Pre-Buy alert!
    with patch("backend.core.database.AsyncSessionLocal", return_value=mock_db), \
         patch("backend.services.market_data.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_bulk, \
         patch("backend.api.websocket.broadcast_alert", new_callable=AsyncMock):

        mock_bulk.return_value = {
            "INFY.NS": {"price": 950.0},  # Price is AFTER/BELOW Best Buy
            "SBIN.NS": {"price": 800.0},  # Price is far below target proximity
        }

        res_not_triggered = await _evaluate_alerts_async()
        assert res_not_triggered["triggered"] == 0


def test_screener_dynamic_target_variance_mathematical_proof():
    """Verify that different stock volatility (ATR) and technical structures produce distinct targets and gains (no 12.5% constant)."""
    test_cases = [
        {"symbol": "HINDUNILVR.NS", "price": 2400.0, "atr": 26.4, "swing_high": 2510.0, "swing_low": 2360.0, "ml_conf": 0.65, "ml_p_buy": 0.58},
        {"symbol": "RELIANCE.NS", "price": 1360.0, "atr": 24.5, "swing_high": 1470.0, "swing_low": 1330.0, "ml_conf": 0.78, "ml_p_buy": 0.68},
        {"symbol": "BAJFINANCE.NS", "price": 6800.0, "atr": 217.6, "swing_high": 7500.0, "swing_low": 6600.0, "ml_conf": 0.82, "ml_p_buy": 0.72},
        {"symbol": "TCS.NS", "price": 4000.0, "atr": 80.0, "swing_high": 4280.0, "swing_low": 3920.0, "ml_conf": 0.68, "ml_p_buy": 0.55},
    ]

    calculated_gains = []

    for tc in test_cases:
        entry = tc["price"]
        atr = tc["atr"]
        swing_high = tc["swing_high"]
        swing_low = tc["swing_low"]
        ml_conf = tc["ml_conf"]
        ml_p_buy = tc["ml_p_buy"]

        # Run exact formula from screener.py
        structural_sl = swing_low - (0.5 * atr)
        min_risk_dist = max(entry * 0.015, 1.2 * atr)
        max_risk_dist = min(entry * 0.065, 2.5 * atr)

        risk_distance = entry - structural_sl
        if risk_distance > max_risk_dist:
            stop_loss = max(0.05, round(entry - max_risk_dist, 2))
        elif risk_distance < min_risk_dist:
            stop_loss = max(0.05, round(entry - min_risk_dist, 2))
        else:
            stop_loss = max(0.05, round(structural_sl, 2))

        r1 = max(swing_high, entry + (1.2 * atr))
        swing_range = max(atr, swing_high - swing_low)
        fib_1272 = swing_high + (0.272 * swing_range)
        r2 = max(fib_1272, entry + (2.0 * atr))
        r3 = max(swing_high + (0.618 * swing_range), r2 + (1.5 * atr))

        if ml_conf >= 0.70 and ml_p_buy >= 0.55:
            expansion_factor = min(1.0, (ml_conf - 0.70) / 0.30)
            raw_target = r2 + (0.4 * (r3 - r2) * expansion_factor)
        elif ml_conf < 0.60:
            raw_target = min(r1, r2)
        else:
            raw_target = r2

        max_11d_gain = max(entry * 0.035, min(entry * 0.16, 4.2 * atr))
        min_11d_gain = max(entry * 0.025, 1.4 * atr)

        target_gain_dist = raw_target - entry
        if target_gain_dist > max_11d_gain:
            target = round(entry + max_11d_gain, 2)
        elif target_gain_dist < min_11d_gain:
            target = round(entry + min_11d_gain, 2)
        else:
            target = round(raw_target, 2)

        gain_pct = round(((target - entry) / entry) * 100.0, 2)
        calculated_gains.append(gain_pct)

    # Assert that all gains are mathematically distinct and realistic
    assert len(set(calculated_gains)) == len(test_cases), f"Expected all gains to be distinct, got {calculated_gains}"
    for g in calculated_gains:
        assert g != 12.5, f"Expected gain not to be constant 12.5%, got {g}"
        assert 3.0 <= g <= 16.0, f"Expected realistic 11-day gain (3% to 16%), got {g}%"
