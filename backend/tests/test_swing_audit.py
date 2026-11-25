"""Tests for 11-Day Swing Trade Audit & Excel Generation System."""

import os
import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path
import openpyxl

from backend.models.swing_audit import SwingTradeAuditCycle, SwingTradeAudit, SwingTradeAuditPrice
from backend.services.swing_audit_service import SwingAuditService, add_trading_days, get_audit_dir, swing_audit_service


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

    # Mock cycle query returning active cycle, existing active query returning None, existing same-day query returning None
    mock_cycle_res = MagicMock()
    mock_cycle_res.scalars.return_value.first.return_value = cycle
    
    mock_existing_res = MagicMock()
    mock_existing_res.scalars.return_value.first.return_value = None
    
    mock_db.execute.side_effect = [mock_cycle_res, mock_existing_res, mock_existing_res]

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
    assert ws_ledger.cell(row=1, column=4).value == "Sector"
    assert ws_ledger.cell(row=1, column=6).value == "Buy Price (₹)"
    assert ws_ledger.cell(row=1, column=7).value == "User Bought"
    assert ws_ledger.cell(row=1, column=8).value == "User Buy Price (₹)"
    assert ws_ledger.cell(row=1, column=17).value == "Day 6 Price (Check)"
    assert ws_ledger.cell(row=1, column=22).value == "Day 11 Price (Check)"

    # Check rows for POWERGRID and TCS
    assert ws_ledger.cell(row=2, column=2).value == "POWERGRID"
    assert ws_ledger.cell(row=2, column=7).value == "YES"
    assert ws_ledger.cell(row=2, column=8).value == 260.0
    assert ws_ledger.cell(row=3, column=2).value == "TCS"
    assert ws_ledger.cell(row=3, column=7).value == "NO"


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


def test_swing_audit_service_get_audit_dir():
    """Verify get_audit_dir is exposed on both class and instance and returns a valid directory."""
    assert hasattr(swing_audit_service, "get_audit_dir") is True
    assert hasattr(SwingAuditService, "get_audit_dir") is True

    dir_from_instance = swing_audit_service.get_audit_dir()
    dir_from_class = SwingAuditService.get_audit_dir()

    assert isinstance(dir_from_instance, Path)
    assert isinstance(dir_from_class, Path)
    assert dir_from_instance == dir_from_class
    assert dir_from_instance.exists()


@pytest.mark.asyncio
async def test_generate_excel_workbook_empty_cycle_and_none_dates(mock_db, tmp_path):
    """
    Test generate_excel_workbook handles empty cycles and audits with recommendation_date=None
    without raising TypeError, and includes TARGET_2_ACHIEVED and STOPPED_IN_PROFIT in Booked Trades.
    """
    # 1. Empty cycle test
    empty_cycle = SwingTradeAuditCycle(
        id="c1111111-1111-1111-1111-111111111111",
        cycle_number=99,
        from_date=date(2026, 11, 1),
        to_date=date(2026, 11, 16),
        status="ACTIVE",
        audits=[]
    )

    mock_result_empty = MagicMock()
    mock_result_empty.scalars.return_value.first.return_value = empty_cycle
    mock_db.execute.return_value = mock_result_empty

    with patch("backend.services.swing_audit_service.get_audit_dir", return_value=tmp_path):
        wb_path = await SwingAuditService.generate_excel_workbook(mock_db, empty_cycle.id)
        assert wb_path is not None
        assert wb_path.exists()

        # Verify empty cycle workbook has sheets
        wb = openpyxl.load_workbook(wb_path)
        assert "Audit Scorecard" in wb.sheetnames
        assert "11-Day Price Tracking" in wb.sheetnames
        assert "Booked Trades" in wb.sheetnames

    # 2. Cycle with recommendation_date=None and coupled ratchet closed statuses
    audit_none_date = SwingTradeAudit(
        id="a1111111-1111-1111-1111-111111111111",
        cycle_id="c2222222-2222-2222-2222-222222222222",
        symbol="HDFCBANK.NS",
        company_name="HDFC Bank Ltd",
        recommendation_date=None,  # Tests the sort key=lambda a: a.recommendation_date or date.min
        buy_price=Decimal("1500.00"),
        status="TARGET_2_ACHIEVED",  # Expanded closed status
        exit_date=date(2026, 11, 10),
        exit_price=Decimal("1650.00"),
        profit_loss_pct=Decimal("10.0"),
        realized_pnl_rupees=Decimal("10000.0"),
        exit_day_number=5,
        daily_prices=[]
    )
    audit_valid_date = SwingTradeAudit(
        id="a2222222-2222-2222-2222-222222222222",
        cycle_id="c2222222-2222-2222-2222-222222222222",
        symbol="INFY.NS",
        company_name="Infosys Ltd",
        recommendation_date=date(2026, 11, 5),
        buy_price=Decimal("1800.00"),
        status="STOPPED_IN_PROFIT",  # Expanded closed status
        exit_date=date(2026, 11, 8),
        exit_price=Decimal("1850.00"),
        profit_loss_pct=Decimal("2.78"),
        realized_pnl_rupees=Decimal("2780.0"),
        exit_day_number=3,
        daily_prices=[]
    )

    cycle_with_data = SwingTradeAuditCycle(
        id="c2222222-2222-2222-2222-222222222222",
        cycle_number=100,
        from_date=date(2026, 11, 1),
        to_date=date(2026, 11, 16),
        status="ACTIVE",
        audits=[audit_none_date, audit_valid_date]
    )

    mock_result_data = MagicMock()
    mock_result_data.scalars.return_value.first.return_value = cycle_with_data
    mock_db.execute.return_value = mock_result_data

    with patch("backend.services.swing_audit_service.get_audit_dir", return_value=tmp_path):
        wb_path_data = await SwingAuditService.generate_excel_workbook(mock_db, cycle_with_data.id)
        assert wb_path_data is not None
        assert wb_path_data.exists()

        wb_data = openpyxl.load_workbook(wb_path_data)
        ws_closed = wb_data["Booked Trades"]

        # Verify both TARGET_2_ACHIEVED and STOPPED_IN_PROFIT are rendered in Booked Trades
        booked_symbols = [ws_closed.cell(row=r, column=2).value for r in range(2, ws_closed.max_row + 1)]
        assert "HDFCBANK" in booked_symbols
        assert "INFY" in booked_symbols


@pytest.mark.asyncio
async def test_swing_audit_api_download_latest_route(tmp_path):
    """
    Test GET /api/swing-audit/download-latest returns HTTP 200, valid openxml MIME type,
    and Content-Disposition attachment header.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.core.database import get_db

    mock_cycle = SwingTradeAuditCycle(
        id="c3333333-3333-3333-3333-333333333333",
        cycle_number=5,
        from_date=date(2026, 11, 2),
        to_date=date(2026, 11, 17),
        status="ACTIVE",
        excel_file_path=None
    )

    test_excel_file = tmp_path / "Swing_Trade_Audit_2026-11-02_to_2026-11-17.xlsx"
    # Create valid openpyxl file
    wb = openpyxl.Workbook()
    wb.active.title = "Test"
    wb.save(test_excel_file)

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(swing_audit_service, "get_or_create_active_cycle", new=AsyncMock(return_value=mock_cycle)), \
             patch.object(swing_audit_service, "generate_excel_workbook", new=AsyncMock(return_value=test_excel_file)), \
             patch("backend.api.swing_audit.get_audit_dir", return_value=tmp_path):

            resp = await client.get("/api/swing-audit/download-latest")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            assert "attachment" in resp.headers["content-disposition"]
            assert "Swing_Trade_Audit_" in resp.headers["content-disposition"]
            assert "no-store" in resp.headers.get("cache-control", "")
            assert len(resp.content) > 0

            # Test HEAD request (used by curl -I, health monitors)
            head_resp = await client.head("/api/swing-audit/download-latest")
            assert head_resp.status_code == 200
            assert head_resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            assert "no-store" in head_resp.headers.get("cache-control", "")
            assert int(head_resp.headers.get("content-length", 0)) > 0
            assert len(head_resp.content) == 0  # HEAD body must be empty per HTTP RFC

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_swing_audit_api_files_and_specific_download(tmp_path):
    """
    Test GET /api/swing-audit/files and GET /api/swing-audit/download/{filename}
    confirming HTTP 200 without AttributeError and proper file streaming.
    """
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.core.database import get_db

    # Create dummy workbook in tmp_path
    test_filename = "Swing_Trade_Audit_Archive_Test.xlsx"
    test_file_path = tmp_path / test_filename
    wb = openpyxl.Workbook()
    wb.active.title = "Archive"
    wb.save(test_file_path)

    mock_cycle = SwingTradeAuditCycle(
        id="c4444444-4444-4444-4444-444444444444",
        cycle_number=1,
        from_date=date(2026, 10, 1),
        to_date=date(2026, 10, 15),
        status="COMPLETED",
        excel_file_path=str(test_file_path),
        total_trades=5,
        win_trades=4,
        loss_trades=1,
        win_rate=Decimal("80.0")
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_cycle]
    mock_result.scalars.return_value.first.return_value = mock_cycle
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("backend.api.swing_audit.get_audit_dir", return_value=tmp_path):
            # 1. GET /api/swing-audit/files
            files_resp = await client.get("/api/swing-audit/files")
            assert files_resp.status_code == 200
            files_data = files_resp.json()
            assert "files" in files_data
            assert "count" in files_data
            assert files_data["count"] >= 1

            # 2. GET /api/swing-audit/download/{filename}
            dl_resp = await client.get(f"/api/swing-audit/download/{test_filename}")
            assert dl_resp.status_code == 200
            assert dl_resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            assert f'attachment; filename="{test_filename}"' in dl_resp.headers["content-disposition"]
            assert len(dl_resp.content) > 0

            # 3. Invalid extension test
            invalid_resp = await client.get("/api/swing-audit/download/bad_file.txt")
            assert invalid_resp.status_code == 400

            # 4. Non-existent file test
            mock_result.scalars.return_value.first.return_value = None
            not_found_resp = await client.get("/api/swing-audit/download/non_existent.xlsx")
            assert not_found_resp.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_run_eod_screener_and_audit_sync_task():
    """Verify Celery task run_eod_screener_and_audit_sync coordinates screener + auto-catalog + price sync."""
    from backend.tasks.swing_audit_tasks import run_eod_screener_and_audit_sync

    fake_screener_data = {
        "buy_stocks": [
            {
                "symbol": "RELIANCE.NS",
                "name": "Reliance Industries Ltd",
                "action": "BUY",
                "total_score": 85.0,
                "trade_plan": {
                    "entry_price": 1335.0,
                    "target_price": 1400.0,
                    "stop_loss": 1300.0,
                    "target_1": 1380.0,
                    "target_2": 1410.0,
                    "reward_to_risk": 2.1
                }
            },
            {
                "symbol": "TCS.NS",
                "name": "Tata Consultancy Services",
                "action": "BUY",
                "total_score": 62.0,  # Below 70 threshold; should NOT catalog
                "trade_plan": {"entry_price": 2400.0, "target_price": 2500.0, "stop_loss": 2350.0}
            }
        ]
    }

    mock_sync_result = {
        "status": "success",
        "total_trades": 10,
        "updated_count": 10,
        "win_rate": 50.0,
        "total_pnl_rupees": 5000.0
    }

    with patch("backend.services.screener.ScreenerService.run_all_sectors_screener", new=AsyncMock(return_value=fake_screener_data)), \
         patch("backend.services.swing_audit_service.swing_audit_service.track_swing_trade", new=AsyncMock()) as mock_track, \
         patch("backend.services.swing_audit_service.swing_audit_service.update_daily_prices", new=AsyncMock(return_value=mock_sync_result)), \
         patch("backend.core.database.AsyncSessionLocal"):

        result = run_eod_screener_and_audit_sync()
        assert result["status"] == "success"
        assert result["screener_candidates"] == 2
        assert result["cataloged_count"] == 1
        assert mock_track.call_count == 1
        assert result["sync_result"]["status"] == "success"


@pytest.mark.asyncio
async def test_sync_audit_prices_endpoint_with_run_scan():
    """Verify POST /api/swing-audit/sync?run_scan=true executes multi-sector scan step."""
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.core.database import get_db

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    fake_screener = {
        "buy_stocks": [
            {
                "symbol": "INFY.NS",
                "name": "Infosys",
                "total_score": 75.0,
                "trade_plan": {"entry_price": 1150.0, "target_price": 1220.0, "stop_loss": 1110.0}
            }
        ]
    }

    fake_sync = {"status": "success", "updated_count": 5, "win_rate": 60.0, "total_pnl_rupees": 3500.0}

    with patch("backend.services.screener.ScreenerService.run_all_sectors_screener", new=AsyncMock(return_value=fake_screener)), \
         patch("backend.services.swing_audit_service.swing_audit_service.track_swing_trade", new=AsyncMock()), \
         patch("backend.services.swing_audit_service.swing_audit_service.update_daily_prices", new=AsyncMock(return_value=fake_sync)):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/swing-audit/sync?run_scan=true")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["cataloged_count"] == 1
            assert data["updated_count"] == 5

    app.dependency_overrides.clear()


def test_screener_service_get_all_sector_symbols():
    """Verify get_all_sector_symbols includes Energy/Oil & Resources, Smallcap Momentum, and all 10 universes."""
    from backend.services.screener import ScreenerService, SECTOR_UNIVERSES

    symbols = ScreenerService.get_all_sector_symbols()
    assert len(symbols) >= 80
    assert len(symbols) == len(set(symbols))  # Deduplicated

    # Verify key symbols across requested user categories
    # Oil & Resources
    assert "ONGC.NS" in symbols
    assert "BPCL.NS" in symbols
    assert "RELIANCE.NS" in symbols

    # Smallcap Momentum
    assert "SUZLON.NS" in symbols
    assert "CDSL.NS" in symbols
    assert "BSE.NS" in symbols

    # Midcap Growth
    assert "POLYCAB.NS" in symbols
    assert "DIXON.NS" in symbols


@pytest.mark.asyncio
async def test_stopped_in_profit_accounting_invariant(mock_db, tmp_path):
    """
    Verifies the mathematical invariant: if an exit price >= entry price,
    it is strictly classified as STOPPED_IN_PROFIT with non-negative realized PnL.
    Prevents phantom loss anomalies (e.g., M&M exited at +1.0% labeled as STOPLOSS_HIT).
    """
    today = date(2026, 11, 11)
    cycle = SwingTradeAuditCycle(
        id="c3333333-3333-3333-3333-333333333333",
        cycle_number=1,
        from_date=today,
        to_date=add_trading_days(today, 11),
        status="ACTIVE",
        excel_file_path=str(tmp_path / "test_invariant.xlsx")
    )

    audit = SwingTradeAudit(
        id="a2222222-2222-2222-2222-222222222222",
        cycle_id=cycle.id,
        symbol="M&M.NS",
        company_name="Mahindra & Mahindra",
        recommendation_date=today,
        buy_price=Decimal("3333.00"),
        target_price=Decimal("3750.00"),
        stop_loss=Decimal("3200.00"),
        target_1=Decimal("3450.00"),
        target_2=Decimal("3750.00"),
        status="IN_PROGRESS",
        allocated_capital=Decimal("100000.00"),
        dynamic_stop_loss=Decimal("3366.33"),  # Trailing stop elevated above entry
        highest_price_recorded=Decimal("3460.00"),
        tranche_2_active=True,
        tranche_2_buy_price=Decimal("3450.00"),
        tranche_2_stop_loss=Decimal("3366.33"),
        ratchet_stage="TARGET_1_HIT"
    )
    audit.daily_prices = []

    # Candles: Day 1 touches T1 (3460), Day 2 pulls back to 3366.33 (which is > entry 3333.00)
    fake_candles = [
        {"timestamp": "2026-11-11T10:00:00Z", "open": 3333.0, "high": 3460.0, "low": 3330.0, "close": 3455.0},
        {"timestamp": "2026-11-12T10:00:00Z", "open": 3450.0, "high": 3455.0, "low": 3360.0, "close": 3366.33},
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
        # Must be STOPPED_IN_PROFIT, NEVER STOPLOSS_HIT!
        assert audit.status == "STOPPED_IN_PROFIT"
        assert audit.ratchet_stage == "STOPPED_IN_PROFIT"
        assert float(audit.exit_price) >= 3333.00
        assert float(audit.realized_pnl_rupees) >= 0.0
        assert float(audit.profit_loss_pct) >= 0.0


@pytest.mark.asyncio
async def test_chronological_state_isolation_prevents_day1_leakage(mock_db, tmp_path):
    """
    Verifies that re-evaluating an active trade always starts Day 1 with initial conditions,
    preventing lookahead bias from killing valid trades on Day 1 using later days' elevated stops.
    """
    today = date(2026, 11, 11)
    cycle = SwingTradeAuditCycle(
        id="c4444444-4444-4444-4444-444444444444",
        cycle_number=1,
        from_date=today,
        to_date=add_trading_days(today, 11),
        status="ACTIVE",
        excel_file_path=str(tmp_path / "test_isolation.xlsx")
    )

    # In previous run, dynamic_stop_loss was set to 500.0 on Day 3
    audit = SwingTradeAudit(
        id="a3333333-3333-3333-3333-333333333333",
        cycle_id=cycle.id,
        symbol="KOTAKBANK.NS",
        company_name="Kotak Bank",
        recommendation_date=today,
        buy_price=Decimal("488.00"),
        target_price=Decimal("540.00"),
        stop_loss=Decimal("460.00"),  # Initial SL
        target_1=Decimal("505.00"),
        target_2=Decimal("540.00"),
        status="IN_PROGRESS",
        allocated_capital=Decimal("100000.00"),
        dynamic_stop_loss=Decimal("500.00"),  # Previously elevated
        tranche_2_active=True
    )
    audit.daily_prices = []

    # Candles: Day 1 low is 480 (below previous dynamic SL 500, but well above initial SL 460)
    # Day 2 reaches 508 (hits T1)
    fake_candles = [
        {"timestamp": "2026-11-11T10:00:00Z", "open": 488.0, "high": 495.0, "low": 480.0, "close": 492.0},
        {"timestamp": "2026-11-12T10:00:00Z", "open": 493.0, "high": 508.0, "low": 490.0, "close": 506.0},
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
        # Must NOT be stopped out on Day 1! Should have advanced to Target 1 hit / breakeven locked or Day 11 exit
        assert audit.status != "STOPLOSS_HIT"
        assert audit.ratchet_stage in ("TARGET_1_HIT", "INITIAL", "BREAKEVEN_LOCKED", "DAY_11_EXIT")


@pytest.mark.asyncio
async def test_anti_duplication_active_trade(mock_db):
    """Verifies that an active IN_PROGRESS trade cannot be duplicated in the same cycle."""
    today = date(2026, 11, 15)
    cycle = SwingTradeAuditCycle(
        id="c5555555-5555-5555-5555-555555555555",
        cycle_number=1,
        from_date=today,
        to_date=add_trading_days(today, 11),
        status="ACTIVE"
    )

    existing_active = SwingTradeAudit(
        id="a4444444-4444-4444-4444-444444444444",
        cycle_id=cycle.id,
        symbol="TITAN.NS",
        status="IN_PROGRESS",
        recommendation_date=today,
        buy_price=Decimal("3400.00")
    )

    mock_cycle_res = MagicMock()
    mock_cycle_res.scalars.return_value.first.return_value = cycle

    mock_active_res = MagicMock()
    mock_active_res.scalars.return_value.first.return_value = existing_active

    mock_db.execute.side_effect = [mock_cycle_res, mock_active_res]

    result = await SwingAuditService.track_swing_trade(
        db=mock_db,
        symbol="TITAN.NS",
        trade_plan={"entry_price": 3410.0, "target_price": 3600.0, "stop_loss": 3300.0},
        total_score=80.0
    )

    # Must return the existing active record without inserting a new one
    assert result.id == existing_active.id
    mock_db.add.assert_not_called()
