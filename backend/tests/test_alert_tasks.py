import pytest
from datetime import datetime, timezone
import uuid
from unittest.mock import patch, MagicMock, AsyncMock

from backend.tasks.alert_tasks import _evaluate_alerts_async
from backend.models.alert import Alert

@pytest.mark.asyncio
async def test_pattern_alert_trigger():
    """Test that a PATTERN alert shifts to TRIGGERED when the pattern forms."""
    
    alert = Alert(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        symbol="RELIANCE.NS",
        condition_type="PATTERN",
        condition_value=4.0,  # Bullish Order Block
        is_active=True,
        priority="HIGH",
        delivery_method="IN_APP",
        triggered_at=None,
    )

    dummy_candle = {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1000, "timestamp": "2026-01-01T00:00:00Z"}
    mock_candles = [dummy_candle] * 47 + [
        {"open": 100, "high": 110, "low": 95, "close": 90, "volume": 1000, "timestamp": "2026-01-01T00:00:00Z"},  # Bearish (p1)
        {"open": 85, "high": 110, "low": 80, "close": 105, "volume": 1000, "timestamp": "2026-01-01T00:00:00Z"},  # Bullish Engulfing (p2)
        {"open": 106, "high": 115, "low": 105, "close": 110, "volume": 1000, "timestamp": "2026-01-01T00:00:00Z"} # Bullish confirming (c)
    ]
    
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [alert]
    
    mock_db = AsyncMock()
    mock_db.execute.return_value = result_mock
    
    with patch("backend.core.database.AsyncSessionLocal", return_value=mock_db):
        with patch("backend.services.market_data.market_data_service.fetch_candles", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_candles
            
            # Since AsyncSessionLocal is used as an async context manager:
            mock_db.__aenter__.return_value = mock_db
            
            # Run the alert evaluation logic
            await _evaluate_alerts_async()
            
    # Verify that the alert is triggered
    assert alert.triggered_at is not None, "Alert was not triggered"
