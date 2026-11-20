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
