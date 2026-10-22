"""
Unit tests for Portfolio Holdings Analytics:
- Buy profit/loss percentage (pnl_pct)
- Days held since bought (days_held & buy_date_formatted)
- Today's Profit and Loss for current stock (day_pnl, day_change, day_change_pct)
  * When bought TODAY: Day's P&L is calculated from purchase entry price, NOT today's starting price.
  * When bought PREVIOUSLY: Day's P&L is today's session movement from previous close.
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
    Verify holding days, purchase return %, and Day's P&L across individual holdings:
    - Stocks bought TODAY calculate Day's P&L from buy price at purchase time.
    - Stocks bought PREVIOUSLY calculate Day's P&L from previous day close.
    """
    user_id = uuid.uuid4()
    user = MagicMock()
    user.id = user_id

    now = datetime.now(timezone.utc)
    ten_days_ago = now - timedelta(days=10, hours=1)
    five_days_ago = now - timedelta(days=5, hours=3)
    today_two_hours_ago = now - timedelta(hours=2)

    # Trade 1: RELIANCE (Bought 10 days ago at 2500, now 2800, prev_close 2750, Qty 10)
    # Bought previously -> baseline = prev_close (2750)
    # Day Change: +50 (+1.82%), Day P&L: +50 * 10 = +500
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
    # Bought previously -> baseline = prev_close (1550)
    # Day Change: -50 (-3.23%), Day P&L: -50 * 20 = -1000
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

    # Trade 3: TCS (Bought TODAY at 3800, now 3850, prev_close 3700, Qty 5)
    # BOUGHT TODAY -> baseline MUST be buy price 3800, NOT today's starting price 3700!
    # Day Change: +50 (+1.32%), Day P&L: +50 * 5 = +250 (NOT 150 * 5 = +750)
    t3 = PaperTrade(
        id=uuid.uuid4(),
        user_id=user_id,
        symbol="TCS.NS",
        direction="BUY",
        order_type="MARKET",
        product_type="DELIVERY",
        quantity=5,
        entry_price=Decimal("3800.00"),
        commission=Decimal("0.00"),
        status="OPEN",
        opened_at=today_two_hours_ago,
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [t1, t2, t3]
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
        "TCS.NS": {
            "symbol": "TCS.NS",
            "price": 3850.0,
            "previous_close": 3700.0,
            "change": 150.0,
            "change_pct": 4.05,
        },
    }

    with patch("backend.api.portfolio.market_data_service.fetch_quotes_bulk", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = quotes_map

        res = await get_portfolio(current_user=user, db=mock_db)

        # 1. Verify Allocation Holdings Details
        alloc = res["allocation"]
        assert len(alloc) == 3

        r_item = next(a for a in alloc if a["symbol"] == "RELIANCE.NS")
        i_item = next(a for a in alloc if a["symbol"] == "INFY.NS")
        t_item = next(a for a in alloc if a["symbol"] == "TCS.NS")

        # RELIANCE assertions (bought 10 days ago)
        assert r_item["days_held"] == 10
        assert r_item["is_bought_today"] is False
        assert r_item["day_baseline"] == 2750.0
        assert r_item["entry_price"] == 2500.0
        assert r_item["current_price"] == 2800.0
        assert r_item["invested"] == 25000.0
        assert r_item["value"] == 28000.0
        assert r_item["pnl_pct"] == 12.0  # +12% buy gain
        assert r_item["day_change"] == 50.0
        assert r_item["day_pnl"] == 500.0  # +50 * 10 = +500

        # INFY assertions (bought 5 days ago)
        assert i_item["days_held"] == 5
        assert i_item["is_bought_today"] is False
        assert i_item["day_baseline"] == 1550.0
        assert i_item["entry_price"] == 1600.0
        assert i_item["current_price"] == 1500.0
        assert i_item["invested"] == 32000.0
        assert i_item["value"] == 30000.0
        assert i_item["pnl_pct"] == -6.25  # -6.25% buy loss
        assert i_item["day_change"] == -50.0
        assert i_item["day_pnl"] == -1000.0  # -50 * 20 = -1000

        # TCS assertions (BOUGHT TODAY)
        # Baseline MUST be buy price (3800.0), NOT starting price (3700.0)!
        assert t_item["days_held"] == 0
        assert t_item["is_bought_today"] is True
        assert t_item["day_baseline"] == 3800.0
        assert t_item["entry_price"] == 3800.0
        assert t_item["current_price"] == 3850.0
        assert t_item["invested"] == 19000.0  # 3800 * 5
        assert t_item["value"] == 19250.0     # 3850 * 5
        assert t_item["pnl_pct"] == 1.32      # (3850 - 3800) / 3800 = +1.32%
        assert t_item["day_change"] == 50.0   # 3850 - 3800 = +50 (from buy price!)
        assert t_item["day_change_pct"] == 1.32
        assert t_item["day_pnl"] == 250.0     # +50 * 5 = +250 (from buy price, not +750 from prev close)

        # 2. Verify Portfolio Aggregate Totals
        # Total Invested: 25,000 + 32,000 + 19,000 = 76,000
        assert res["total_invested"] == 76000.0

        # Total Day's P&L for all stocks: +500 (Reliance) + (-1000) (Infy) + 250 (TCS) = -250.0
        assert res["total_day_pnl"] == -250.0

        # Total Baseline Value: (2750 * 10) + (1550 * 20) + (3800 * 5) = 27,500 + 31,000 + 19,000 = 77,500
        # Total Day P&L %: (-250 / 77,500) * 100 = -0.32%
        assert res["total_day_pnl_pct"] == -0.32
