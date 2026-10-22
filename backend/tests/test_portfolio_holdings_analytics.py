"""
Unit tests for Portfolio Holdings Analytics:
- Buy profit/loss percentage (pnl_pct)
- Days held since bought (days_held & buy_date_formatted)
- Today's Profit and Loss for current stock (day_pnl, day_change, day_change_pct)
- Today's Total Day's P&L across all stocks combined (total_day_pnl & total_day_pnl_pct)
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal

from backend.api.portfolio import get_portfolio
from backend.models.paper_trade import PaperTrade


@pytest.mark.asyncio
async def test_portfolio_empty_trades():
    """Verify empty portfolio returns structured zero-value day and total metrics."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    user = MagicMock()
    user.id = uuid.uuid4()

    res = await get_portfolio(current_user=user, db=mock_db)
    assert res["current_value"] == 100000.0
    assert res["total_pnl"] == 0.0
    assert res["total_pnl_pct"] == 0.0
    assert res["total_day_pnl"] == 0.0
    assert res["total_day_pnl_pct"] == 0.0
    assert res["total_invested"] == 0.0
    assert res["allocation"] == []


@pytest.mark.asyncio
async def test_portfolio_holdings_analytics_calculation():
    """
    Verify holding days, purchase return %, and Day's P&L across individual and portfolio totals.
    """
    user_id = uuid.uuid4()
    user = MagicMock()
    user.id = user_id

    now = datetime.now(timezone.utc)
    five_days_ago = now - timedelta(days=5, hours=3)
    ten_days_ago = now - timedelta(days=10, hours=1)

    # Trade 1: RELIANCE (Bought 10 days ago at 2500, now 2800, prev_close 2750, Qty 10)
    # Total Invested: 25,000
    # Current Value: 28,000
    # Total Gain: +3,000 (+12.0%)
    # Day Change: +50 (+1.82%)
    # Day P&L: +50 * 10 = +500
    t1 = PaperTrade(
        id=uuid.uuid4(),
        user_id=user_id,
        symbol="RELIANCE.NS",
        direction="BUY",
        order_type="MARKET",
        product_type="DELIVERY",
        quantity=10,
        entry_price=Decimal("2500.00"),
        commission=Decimal("0.00"),
        status="OPEN",
        opened_at=ten_days_ago,
    )

    # Trade 2: INFY (Bought 5 days ago at 1600, now 1500, prev_close 1550, Qty 20)
    # Total Invested: 32,000
    # Current Value: 30,000
    # Total Gain: -2,000 (-6.25%)
    # Day Change: -50 (-3.23%)
    # Day P&L: -50 * 20 = -1000
    t2 = PaperTrade(
        id=uuid.uuid4(),
        user_id=user_id,
        symbol="INFY.NS",
        direction="BUY",
        order_type="MARKET",
        product_type="DELIVERY",
        quantity=20,
        entry_price=Decimal("1600.00"),
        commission=Decimal("0.00"),
        status="OPEN",
        opened_at=five_days_ago,
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [t1, t2]
    mock_db.execute.return_value = mock_result

    quotes_map = {
        "RELIANCE.NS": {
            "symbol": "RELIANCE.NS",
            "price": 2800.0,
            "previous_close": 2750.0,
            "change": 50.0,
            "change_pct": 1.82,
        },
        "INFY.NS": {
            "symbol": "INFY.NS",
            "price": 1500.0,
            "previous_close": 1550.0,
            "change": -50.0,
            "change_pct": -3.23,
        },
    }

    with patch("backend.api.portfolio.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = quotes_map

        res = await get_portfolio(current_user=user, db=mock_db)

        # 1. Verify Allocation Holdings Details
        alloc = res["allocation"]
        assert len(alloc) == 2

        r_item = next(a for a in alloc if a["symbol"] == "RELIANCE.NS")
        i_item = next(a for a in alloc if a["symbol"] == "INFY.NS")

        # RELIANCE assertions
        assert r_item["days_held"] == 10
        assert r_item["entry_price"] == 2500.0
        assert r_item["current_price"] == 2800.0
        assert r_item["invested"] == 25000.0
        assert r_item["value"] == 28000.0
        assert r_item["pnl_pct"] == 12.0  # +12% buy gain
        assert r_item["day_change"] == 50.0
        assert r_item["day_pnl"] == 500.0  # +50 * 10 = +500
        assert "buy_date_formatted" in r_item

        # INFY assertions
        assert i_item["days_held"] == 5
        assert i_item["entry_price"] == 1600.0
        assert i_item["current_price"] == 1500.0
        assert i_item["invested"] == 32000.0
        assert i_item["value"] == 30000.0
        assert i_item["pnl_pct"] == -6.25  # -6.25% buy loss
        assert i_item["day_change"] == -50.0
        assert i_item["day_pnl"] == -1000.0  # -50 * 20 = -1000
        assert "buy_date_formatted" in i_item

        # 2. Verify Portfolio Aggregate Totals
        # Total Invested: 25,000 + 32,000 = 57,000
        assert res["total_invested"] == 57000.0

        # Total Day's P&L for all stocks: +500 + (-1000) = -500.0
        assert res["total_day_pnl"] == -500.0

        # Total Prev Value: (2750 * 10) + (1550 * 20) = 27,500 + 31,000 = 58,500
        # Total Day P&L %: (-500 / 58,500) * 100 = -0.85%
        assert res["total_day_pnl_pct"] == -0.85
