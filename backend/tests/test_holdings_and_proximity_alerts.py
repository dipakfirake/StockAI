"""
Unit tests for Swing Screener Proximity Alerts and Active Holdings Risk Monitor.
"""

import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

from backend.models.alert import Alert
from backend.models.paper_trade import PaperTrade
from backend.tasks.alert_tasks import _evaluate_alerts_async
from backend.api.alerts import (
    setup_screener_coupled_alerts,
    get_holdings_risk_monitor,
    sync_holdings_alerts,
    ScreenerAlertSetupRequest,
    VALID_CONDITIONS,
)


def test_valid_proximity_conditions():
    """Verify that all new proximity and risk conditions are registered in VALID_CONDITIONS."""
    assert "BUY_PROXIMITY" in VALID_CONDITIONS
    assert "TARGET_PROXIMITY" in VALID_CONDITIONS
    assert "TARGET_HIT" in VALID_CONDITIONS
    assert "STOP_LOSS_PROXIMITY" in VALID_CONDITIONS
    assert "STOP_LOSS_HIT" in VALID_CONDITIONS


@pytest.mark.asyncio
async def test_screener_setup_coupled_alerts():
    """Verify that setup_screener_coupled_alerts creates pre-alerts for Buy, Target, and SL."""
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    request = ScreenerAlertSetupRequest(
        symbol="TCS.NS",
        current_price=3850.0,
        best_buy_price=3800.0,
        target_price=4100.0,
        stop_loss=3650.0,
        proximity_pct=1.0,
    )

    with patch("backend.api.alerts.broadcast_alert", new_callable=AsyncMock) as mock_broadcast:
        result = await setup_screener_coupled_alerts(request, current_user=mock_user, db=mock_db)

    assert result["symbol"] == "TCS.NS"
    assert result["created_count"] == 5  # BUY_PROXIMITY, TARGET_PROXIMITY, TARGET_HIT, STOP_LOSS_PROXIMITY, STOP_LOSS_HIT

    # Verify added alerts
    added_alerts = [call.args[0] for call in mock_db.add.call_args_list]
    types = [a.condition_type for a in added_alerts]
    assert "BUY_PROXIMITY" in types
    assert "TARGET_PROXIMITY" in types
    assert "TARGET_HIT" in types
    assert "STOP_LOSS_PROXIMITY" in types
    assert "STOP_LOSS_HIT" in types

    # Check Buy Proximity Price (3800 * 1.01 = 3838)
    buy_alert = next(a for a in added_alerts if a.condition_type == "BUY_PROXIMITY")
    assert buy_alert.condition_value == 3838.0

    # Check Target Proximity Price (4100 * 0.99 = 4059)
    tgt_alert = next(a for a in added_alerts if a.condition_type == "TARGET_PROXIMITY")
    assert tgt_alert.condition_value == 4059.0

    # Check broadcast was called
    mock_broadcast.assert_called_once()


@pytest.mark.asyncio
async def test_holdings_risk_monitor_calculations():
    """Verify get_holdings_risk_monitor calculates distances, approaching flags, and risk badges."""
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    trade_1 = MagicMock(spec=PaperTrade)
    trade_1.id = uuid.uuid4()
    trade_1.symbol = "INFY.NS"
    trade_1.direction = "BUY"
    trade_1.status = "OPEN"
    trade_1.product_type = "DELIVERY"
    trade_1.quantity = 20
    trade_1.entry_price = 1800.0
    trade_1.target_price = 1950.0
    trade_1.stop_loss = 1720.0
    trade_1.commission = 0.0
    trade_1.stt_tax = 0.0
    trade_1.opened_at = datetime.now(timezone.utc)

    # CMP close to Target: 1940 (Target: 1950, so cmp >= 1950 * 0.99 = 1930.5 -> TARGET_APPROACHING)
    mock_db = AsyncMock()
    alerts_result_mock = MagicMock()
    alerts_result_mock.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = alerts_result_mock

    with patch("backend.services.paper_trading.paper_trading_service.get_all_trades", new_callable=AsyncMock) as mock_trades, \
         patch("backend.services.market_data.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_quotes:

        mock_trades.return_value = [trade_1]
        mock_quotes.return_value = {"INFY.NS": {"price": 1940.0}}

        res = await get_holdings_risk_monitor(current_user=mock_user, db=mock_db)

    assert len(res["holdings"]) == 1
    h = res["holdings"][0]
    assert h["symbol"] == "INFY.NS"
    assert h["cmp"] == 1940.0
    assert h["is_target_approaching"] is True
    assert h["risk_status"] == "TARGET_APPROACHING"
    assert res["summary"]["targets_approaching"] == 1


@pytest.mark.asyncio
async def test_proximity_alerts_evaluation_task():
    """Verify _evaluate_alerts_async evaluates TARGET_PROXIMITY and triggers alert."""
    alert = Alert(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        symbol="TATASTEEL.NS",
        condition_type="TARGET_PROXIMITY",
        condition_value=160.0,
        is_active=True,
        priority="HIGH",
        delivery_method="IN_APP",
        triggered_at=None,
    )

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [alert]

    mock_db = AsyncMock()
    mock_db.execute.return_value = result_mock
    mock_db.__aenter__.return_value = mock_db
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    with patch("backend.core.database.AsyncSessionLocal", return_value=mock_db), \
         patch("backend.services.market_data.market_data_service.fetch_quote", new_callable=AsyncMock) as mock_quote, \
         patch("backend.api.websocket.broadcast_alert", new_callable=AsyncMock) as mock_broadcast:

        # Price is at 162 (above 160 proximity target)
        mock_quote.return_value = {"price": 162.0}

        res = await _evaluate_alerts_async()

    assert alert.triggered_at is not None
    assert res["triggered"] == 1
    assert mock_broadcast.call_count >= 1
