"""Tests for 11-Day Swing Trade Audit & Excel Generation System."""

import os
import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path
import openpyxl

from backend.models.swing_audit import SwingTradeAuditCycle, SwingTradeAudit, SwingTradeAuditPrice
from backend.services.swing_audit_service import SwingAuditService, add_trading_days, get_audit_dir


@pytest.fixture
def mock_db():
    """Mock async SQLAlchemy session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


def test_add_trading_days():
    # Friday 2026-11-06 + 3 trading days -> Mon 9, Tue 10, Wed 11 (2026-11-11)
    friday = date(2026, 11, 6)
    res = add_trading_days(friday, 3)
    assert res == date(2026, 11, 11)


@pytest.mark.asyncio
async def test_get_or_create_active_cycle(mock_db):
    # Mock no active cycle found
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_result.scalar.return_value = 0
    mock_db.execute.return_value = mock_result

    today = date(2026, 11, 10)
    cycle = await SwingAuditService.get_or_create_active_cycle(mock_db, today)

    assert cycle is not None
    assert cycle.cycle_number == 1
    assert cycle.from_date == today
    assert cycle.status == "ACTIVE"
    assert "Swing_Trade_Audit_" in cycle.excel_file_path


@pytest.mark.asyncio
async def test_track_swing_trade_and_idempotency(mock_db):
    today = date(2026, 11, 10)
    cycle = SwingTradeAuditCycle(
        id="c1111111-1111-1111-1111-111111111111",
        cycle_number=1,
        from_date=today,
        to_date=add_trading_days(today, 11),
        status="ACTIVE"
    )

    # Mock cycle query returning active cycle, existing audit query returning None
    mock_cycle_res = MagicMock()
    mock_cycle_res.scalars.return_value.first.return_value = cycle
    
    mock_existing_res = MagicMock()
    mock_existing_res.scalars.return_value.first.return_value = None
    
    mock_db.execute.side_effect = [mock_cycle_res, mock_existing_res]

    trade_plan = {
        "entry_price": 260.25,
        "target_price": 277.56,
        "stop_loss": 252.70,
        "target_1": 269.90,
        "target_2": 277.56,
        "reward_to_risk": 2.29
    }

    with patch.object(SwingAuditService, "update_daily_prices", new=AsyncMock(return_value={})):
        audit = await SwingAuditService.track_swing_trade(
            db=mock_db,
            symbol="POWERGRID",
            trade_plan=trade_plan,
            company_name="Power Grid Corp",
            recommendation_date=today,
            total_score=73.8,
            user_bought=True,
            user_buy_price=260.25
        )

        assert audit.symbol == "POWERGRID.NS"
        assert audit.buy_price == Decimal("260.25")
        assert audit.user_bought is True
        assert audit.user_buy_price == Decimal("260.25")
        assert audit.target_price == Decimal("277.56")
        assert audit.stop_loss == Decimal("252.70")
        assert audit.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_update_daily_prices_stop_loss_trigger(mock_db, tmp_path):
    today = date(2026, 11, 2)
    cycle = SwingTradeAuditCycle(
        id="c2222222-2222-2222-2222-222222222222",
        cycle_number=1,
        from_date=today,
        to_date=add_trading_days(today, 11),
        status="ACTIVE",
        excel_file_path=str(tmp_path / "test_audit.xlsx")
    )
    
    audit = SwingTradeAudit(
        id="a1111111-1111-1111-1111-111111111111",
        cycle_id=cycle.id,
        symbol="POWERGRID.NS",
        company_name="Power Grid Corp",
        recommendation_date=today,
        buy_price=Decimal("260.00"),
        target_price=Decimal("280.00"),
        stop_loss=Decimal("250.00"),
        status="IN_PROGRESS",
        allocated_capital=Decimal("100000.00")
    )
    audit.daily_prices = []

    # Mock candles: Day 1 flat, Day 2 drops below SL (248.00)
    fake_candles = [
        {"timestamp": "2026-11-02T10:00:00Z", "open": 260.0, "high": 262.0, "low": 258.0, "close": 261.0},
        {"timestamp": "2026-11-03T10:00:00Z", "open": 255.0, "high": 256.0, "low": 248.0, "close": 249.0}, # SL Breached!
        {"timestamp": "2026-11-04T10:00:00Z", "open": 250.0, "high": 260.0, "low": 249.0, "close": 258.0}, # Day 3 should not be processed
    ]

    mock_cycle_res = MagicMock()
    mock_cycle_res.scalars.return_value.first.return_value = cycle

    mock_audits_res = MagicMock()
    mock_audits_res.scalars.return_value.all.return_value = [audit]

    mock_db.execute.side_effect = [mock_cycle_res, mock_audits_res]

    with patch("backend.services.market_data.market_data_service.fetch_candles", new=AsyncMock(return_value=fake_candles)), \
         patch.object(SwingAuditService, "generate_excel_workbook", new=AsyncMock(return_value=None)):

        res = await SwingAuditService.update_daily_prices(mock_db, cycle_id=cycle.id)

        assert res["status"] == "success"
        # Verify Stop Loss trigger: marked SOLD immediately on Day 2
        assert audit.status == "STOPLOSS_HIT"
        assert audit.exit_day_number == 2
        assert audit.exit_price == Decimal("250.00")
        assert audit.profit_loss_pct < 0
        assert audit.realized_pnl_rupees < 0


@pytest.mark.asyncio
async def test_update_daily_prices_target_achieved(mock_db, tmp_path):
    today = date(2026, 11, 2)
    cycle = SwingTradeAuditCycle(
        id="c3333333-3333-3333-3333-333333333333",
        cycle_number=1,
        from_date=today,
        to_date=add_trading_days(today, 11),
        status="ACTIVE",
        excel_file_path=str(tmp_path / "test_audit_tgt.xlsx")
    )
    
    audit = SwingTradeAudit(
        id="a2222222-2222-2222-2222-222222222222",
        cycle_id=cycle.id,
        symbol="RELIANCE.NS",
        company_name="Reliance Industries",
        recommendation_date=today,
        buy_price=Decimal("1300.00"),
        target_price=Decimal("1380.00"),
        stop_loss=Decimal("1260.00"),
        status="IN_PROGRESS",
        allocated_capital=Decimal("100000.00")
    )
    audit.daily_prices = []

    # Mock candles: Day 1 flat, Day 2 reaches 1390 (>= 1380 Target!)
    fake_candles = [
        {"timestamp": "2026-11-02T10:00:00Z", "open": 1300.0, "high": 1310.0, "low": 1290.0, "close": 1305.0},
        {"timestamp": "2026-11-03T10:00:00Z", "open": 1310.0, "high": 1390.0, "low": 1305.0, "close": 1385.0}, # Target Hit!
    ]

    mock_cycle_res = MagicMock()
    mock_cycle_res.scalars.return_value.first.return_value = cycle

    mock_audits_res = MagicMock()
    mock_audits_res.scalars.return_value.all.return_value = [audit]

    mock_db.execute.side_effect = [mock_cycle_res, mock_audits_res]

    with patch("backend.services.market_data.market_data_service.fetch_candles", new=AsyncMock(return_value=fake_candles)), \
         patch.object(SwingAuditService, "generate_excel_workbook", new=AsyncMock(return_value=None)):

        res = await SwingAuditService.update_daily_prices(mock_db, cycle_id=cycle.id)

        assert res["status"] == "success"
        # Verify Target trigger: profit booked immediately on Day 2
        assert audit.status == "TARGET_ACHIEVED"
        assert audit.exit_day_number == 2
        assert audit.exit_price == Decimal("1380.00")
        assert audit.profit_loss_pct > 0
        assert audit.realized_pnl_rupees > 0


@pytest.mark.asyncio
async def test_generate_excel_workbook_creates_valid_file(mock_db, tmp_path):
    today = date(2026, 11, 2)
    test_file = tmp_path / "Swing_Trade_Audit_2026-11-02_to_2026-11-17.xlsx"

    cycle = SwingTradeAuditCycle(
        id="c4444444-4444-4444-4444-444444444444",
        cycle_number=1,
        from_date=today,
        to_date=date(2026, 11, 17),
        status="ACTIVE",
        excel_file_path=str(test_file),
        total_trades=2,
        win_trades=1,
        loss_trades=1,
        win_rate=Decimal("50.00"),
        total_gain_loss_pct=Decimal("3.50"),
        total_pnl_rupees=Decimal("3500.00")
    )

    trade1 = SwingTradeAudit(
        id="t1111111-1111-1111-1111-111111111111",
        cycle_id=cycle.id,
        symbol="POWERGRID.NS",
        company_name="Power Grid Corp",
        recommendation_date=today,
        buy_price=Decimal("260.00"),
        user_bought=True,
        user_buy_price=Decimal("260.00"),
        target_price=Decimal("280.00"),
        stop_loss=Decimal("250.00"),
        status="TARGET_ACHIEVED",
        exit_date=date(2026, 11, 5),
        exit_price=Decimal("280.00"),
        exit_day_number=3,
        profit_loss_pct=Decimal("7.69"),
        realized_pnl_rupees=Decimal("7690.00"),
        allocated_capital=Decimal("100000.00")
    )
    trade1.daily_prices = [
        SwingTradeAuditPrice(day_number=1, trade_date=today, close_price=Decimal("265.00"), change_pct_from_buy=Decimal("1.92")),
        SwingTradeAuditPrice(day_number=2, trade_date=date(2026, 11, 3), close_price=Decimal("272.00"), change_pct_from_buy=Decimal("4.62")),
        SwingTradeAuditPrice(day_number=3, trade_date=date(2026, 11, 5), close_price=Decimal("280.00"), change_pct_from_buy=Decimal("7.69"), target_hit=True)
    ]

    trade2 = SwingTradeAudit(
        id="t2222222-2222-2222-2222-222222222222",
        cycle_id=cycle.id,
        symbol="TCS.NS",
        company_name="Tata Consultancy Services",
        recommendation_date=today,
        buy_price=Decimal("4000.00"),
        target_price=Decimal("4300.00"),
        stop_loss=Decimal("3850.00"),
        status="STOPLOSS_HIT",
        exit_date=date(2026, 11, 4),
        exit_price=Decimal("3850.00"),
        exit_day_number=2,
        profit_loss_pct=Decimal("-3.75"),
        realized_pnl_rupees=Decimal("-3750.00"),
        allocated_capital=Decimal("100000.00")
    )
    trade2.daily_prices = [
        SwingTradeAuditPrice(day_number=1, trade_date=today, close_price=Decimal("3950.00"), change_pct_from_buy=Decimal("-1.25")),
        SwingTradeAuditPrice(day_number=2, trade_date=date(2026, 11, 4), close_price=Decimal("3840.00"), change_pct_from_buy=Decimal("-4.00"), stoploss_hit=True)
    ]

    cycle.audits = [trade1, trade2]

    mock_cycle_res = MagicMock()
    mock_cycle_res.scalars.return_value.first.return_value = cycle
    mock_db.execute.return_value = mock_cycle_res

    res_path = await SwingAuditService.generate_excel_workbook(mock_db, cycle.id)
    assert res_path is not None
    assert os.path.exists(res_path)

    # Inspect openpyxl workbook
    wb = openpyxl.load_workbook(res_path)
    sheet_names = wb.sheetnames
    assert "Audit Scorecard" in sheet_names
    assert "11-Day Price Tracking" in sheet_names
    assert "Booked Trades" in sheet_names

    ws_ledger = wb["11-Day Price Tracking"]
    # Check headers
    assert ws_ledger.cell(row=1, column=1).value == "Rec #"
    assert ws_ledger.cell(row=1, column=2).value == "Symbol"
    assert ws_ledger.cell(row=1, column=5).value == "Buy Price (₹)"
    assert ws_ledger.cell(row=1, column=6).value == "User Bought"
    assert ws_ledger.cell(row=1, column=7).value == "User Buy Price (₹)"
    assert ws_ledger.cell(row=1, column=16).value == "Day 6 Price (Check)"
    assert ws_ledger.cell(row=1, column=21).value == "Day 11 Price (Check)"

    # Check rows for POWERGRID and TCS
    assert ws_ledger.cell(row=2, column=2).value == "POWERGRID"
    assert ws_ledger.cell(row=2, column=6).value == "YES"
    assert ws_ledger.cell(row=2, column=7).value == 260.0
    assert ws_ledger.cell(row=3, column=2).value == "TCS"
    assert ws_ledger.cell(row=3, column=6).value == "NO"


@pytest.mark.asyncio
async def test_swing_audit_api_routes():
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.core.auth import get_current_user_optional
    from backend.core.database import get_db

    mock_cycle_data = {
        "cycle": {
            "cycle_number": 1,
            "from_date": "2026-11-02",
            "to_date": "2026-11-17",
            "status": "ACTIVE",
            "total_trades": 1,
            "win_trades": 1,
            "loss_trades": 0,
            "win_rate": 100.0,
            "total_gain_loss_pct": 6.7,
            "total_pnl_rupees": 6700.0
        },
        "trades": []
    }

    mock_db = AsyncMock()

    app.dependency_overrides[get_current_user_optional] = lambda: {"id": "test_user"}
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /api/swing-audit/current-cycle
        with patch.object(SwingAuditService, "get_cycle_summary", new=AsyncMock(return_value=mock_cycle_data)):
            resp = await client.get("/api/swing-audit/current-cycle")
            assert resp.status_code == 200
            data = resp.json()
            assert data["cycle"]["cycle_number"] == 1
            assert data["cycle"]["win_rate"] == 100.0

        # 2. POST /api/swing-audit/track
        fake_audit = SwingTradeAudit(
            id="a3333333-3333-3333-3333-333333333333",
            symbol="POWERGRID.NS",
            buy_price=Decimal("260.25"),
            user_bought=True,
            user_buy_price=Decimal("260.25"),
            target_price=Decimal("277.56"),
            stop_loss=Decimal("252.70"),
            status="IN_PROGRESS"
        )
        with patch.object(SwingAuditService, "track_swing_trade", new=AsyncMock(return_value=fake_audit)):
            payload = {
                "symbol": "POWERGRID",
                "buy_price": 260.25,
                "target_price": 277.56,
                "stop_loss": 252.70,
                "reward_to_risk": 2.29,
                "total_score": 73.8,
                "user_bought": True,
                "user_buy_price": 260.25
            }
            resp = await client.post("/api/swing-audit/track", json=payload)
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"
            assert resp.json()["symbol"] == "POWERGRID.NS"
            assert resp.json()["user_bought"] is True
            assert resp.json()["user_buy_price"] == 260.25

        # 3. POST /api/swing-audit/sync
        with patch.object(SwingAuditService, "update_daily_prices", new=AsyncMock(return_value={"status": "success", "updated_count": 1})):
            resp = await client.post("/api/swing-audit/sync")
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"

    app.dependency_overrides.clear()
