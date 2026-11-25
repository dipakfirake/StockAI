"""
Unit tests for Swing Audit Cycle #2 Rollover, Anti-Churn Deduplication, Archive Routing & Sector Tagging.
"""

import pytest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.models.swing_audit import SwingTradeAuditCycle, SwingTradeAudit, SwingTradeAuditPrice
from backend.services.swing_audit_service import SwingAuditService, get_audit_dir
from backend.services.screener import resolve_stock_sector, SECTOR_UNIVERSES


@pytest.fixture
def mock_db():
    """Mock async SQLAlchemy session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_resolve_stock_sector_mapping():
    """Verify that symbols from all 10 universes map accurately to canonical display sector names."""
    assert resolve_stock_sector("HDFCBANK.NS") == "Banking & Financials"
    assert resolve_stock_sector("TCS.NS") == "IT & Technology"
    assert resolve_stock_sector("MARUTI.NS") == "Automotive & Ancillaries"
    assert resolve_stock_sector("SUNPHARMA.NS") == "Pharma & Healthcare"
    assert resolve_stock_sector("POWERGRID.NS") == "Energy & Utilities"
    assert resolve_stock_sector("ITC.NS") == "FMCG & Consumer"
    assert resolve_stock_sector("TATASTEEL.NS") == "Metals & Mining"
    assert resolve_stock_sector("POLYCAB.NS") == "Midcap Growth"
    assert resolve_stock_sector("SUZLON.NS") == "Smallcap Momentum"


@pytest.mark.asyncio
async def test_cycle_anti_churn_deduplication(mock_db):
    """
    Verify Cycle-Level Anti-Churn Invariant:
    A stock can be tracked AT MOST ONCE per 11-day cycle, even if it was previously exited.
    """
    cycle_id = uuid.uuid4()
    cycle = SwingTradeAuditCycle(
        id=cycle_id,
        cycle_number=1,
        from_date=date(2026, 11, 11),
        to_date=date(2026, 11, 26),
        status="ACTIVE"
    )

    existing_stopped_trade = SwingTradeAudit(
        id=uuid.uuid4(),
        cycle_id=cycle_id,
        symbol="RELIANCE.NS",
        company_name="Reliance Industries",
        sector="Energy & Utilities",
        recommendation_date=date(2026, 11, 11),
        buy_price=Decimal("2500.00"),
        target_price=Decimal("2700.00"),
        stop_loss=Decimal("2400.00"),
        status="STOPLOSS_HIT",
        exit_date=date(2026, 11, 14),
        exit_price=Decimal("2400.00"),
        exit_day_number=3,
        profit_loss_pct=Decimal("-4.00"),
        realized_pnl_rupees=Decimal("-4000.00")
    )

    trade_plan = {
        "best_buy_price": 2500.0,
        "target_price": 2700.0,
        "stop_loss": 2400.0,
        "target_1": 2600.0,
        "target_2": 2700.0,
        "reward_to_risk": 2.0
    }

    # Case 1: When stock already exists in cycle (even though exited), it must skip re-adding
    mock_cycle_res = MagicMock()
    mock_cycle_res.scalars.return_value.first.return_value = cycle

    mock_existing_res = MagicMock()
    mock_existing_res.scalars.return_value.first.return_value = existing_stopped_trade

    mock_db.execute.side_effect = [mock_cycle_res, mock_existing_res]

    with patch.object(SwingAuditService, "update_daily_prices", new=AsyncMock(return_value={})):
        result = await SwingAuditService.track_swing_trade(
            db=mock_db,
            symbol="RELIANCE",  # Without .NS suffix
            trade_plan=trade_plan,
            company_name="Reliance Industries",
            recommendation_date=date(2026, 11, 16),
            total_score=80.0,
            sector="Energy & Utilities"
        )

        assert result.id == existing_stopped_trade.id
        assert result.status == "STOPLOSS_HIT"
        # mock_db.add must NOT be called since trade already exists in cycle
        mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_batch_track_anti_churn_and_multi_sector(mock_db):
    """Verify track_batch_swing_trades tags sector and skips already audited symbols."""
    cycle_id = uuid.uuid4()
    cycle = SwingTradeAuditCycle(
        id=cycle_id,
        cycle_number=1,
        from_date=date(2026, 11, 11),
        to_date=date(2026, 11, 26),
        status="ACTIVE"
    )

    # Pre-existing in cycle: TCS.NS already audited
    mock_cycle_res = MagicMock()
    mock_cycle_res.scalars.return_value.first.return_value = cycle

    mock_symbols_res = MagicMock()
    mock_symbols_res.scalars.return_value.all.return_value = ["TCS.NS"]

    mock_db.execute.side_effect = [mock_cycle_res, mock_symbols_res]

    stocks = [
        {
            "symbol": "TCS.NS",  # Already in cycle -> MUST be skipped
            "name": "Tata Consultancy Services",
            "sector": "IT & Technology",
            "total_score": 82.0,
            "trade_plan": {"entry_price": 4100.0, "target_price": 4400.0, "stop_loss": 3950.0}
        },
        {
            "symbol": "HDFCBANK",  # Fresh stock -> MUST be added
            "name": "HDFC Bank",
            "sector": "Banking & Financials",
            "total_score": 79.5,
            "trade_plan": {"entry_price": 1750.0, "target_price": 1880.0, "stop_loss": 1690.0}
        },
        {
            "symbol": "HDFCBANK.NS",  # Duplicate in same batch -> MUST be skipped
            "name": "HDFC Bank Duplicate",
            "sector": "Banking & Financials",
            "total_score": 85.0,
            "trade_plan": {"entry_price": 1750.0, "target_price": 1880.0, "stop_loss": 1690.0}
        }
    ]

    with patch.object(SwingAuditService, "update_daily_prices", new=AsyncMock(return_value={})):
        added = await SwingAuditService.track_batch_swing_trades(
            db=mock_db,
            stocks=stocks,
            recommendation_date=date(2026, 11, 12)
        )
        assert added == 1  # Only HDFCBANK added; TCS and duplicate HDFCBANK skipped!
        assert mock_db.add.call_count == 1
        added_audit = mock_db.add.call_args[0][0]
        assert added_audit.symbol == "HDFCBANK.NS"
        assert added_audit.sector == "Banking & Financials"


@pytest.mark.asyncio
async def test_rollover_to_next_cycle(mock_db):
    """
    Verify rollover_to_next_cycle:
    - Finalizes active Cycle #1 (freezes scorecard, sets COMPLETED)
    - Generates archive workbook
    - Initializes Cycle #2 with ACTIVE status
    """
    cycle1 = SwingTradeAuditCycle(
        id=uuid.uuid4(),
        cycle_number=1,
        from_date=date(2026, 11, 11),
        to_date=date(2026, 11, 26),
        status="ACTIVE",
        total_trades=2,
        win_trades=1,
        loss_trades=1,
        win_rate=Decimal("50.00"),
        total_pnl_rupees=Decimal("5000.00")
    )

    open_audit = SwingTradeAudit(
        id=uuid.uuid4(),
        cycle_id=cycle1.id,
        symbol="INFY.NS",
        buy_price=Decimal("1800.00"),
        status="IN_PROGRESS",
        allocated_capital=Decimal("100000.00"),
        profit_loss_pct=Decimal("0.00"),
        realized_pnl_rupees=Decimal("0.00")
    )
    # Eagerly attach daily prices
    open_audit.daily_prices = []

    mock_cycle_res = MagicMock()
    mock_cycle_res.scalars.return_value.first.return_value = cycle1

    mock_audits_res = MagicMock()
    mock_audits_res.scalars.return_value.all.return_value = [open_audit]

    mock_db.execute.side_effect = [mock_cycle_res, mock_audits_res]

    with patch.object(SwingAuditService, "update_daily_prices", new=AsyncMock(return_value={})), \
         patch.object(SwingAuditService, "generate_excel_workbook", new=AsyncMock(return_value=None)):
        res = await SwingAuditService.rollover_to_next_cycle(mock_db, square_off_remaining=True)

        assert res["status"] == "success"
        assert res["completed_cycle"]["cycle_number"] == 1
        assert res["completed_cycle"]["status"] == "COMPLETED"
        assert res["active_cycle"]["cycle_number"] == 2
        assert res["active_cycle"]["status"] == "ACTIVE"

        # Verify open trade was squared off
        assert open_audit.status == "DAY_11_EXIT"


@pytest.mark.asyncio
async def test_download_archive_vs_active_collision():
    """
    Verify that downloading a specific archive filename serves that file directly
    and is NOT overwritten or intercepted by the active cycle.
    """
    audit_dir = get_audit_dir()
    archive_file = audit_dir / "Swing_Trade_Audit_Archive_Test.xlsx"
    archive_file.write_bytes(b"TEST_ARCHIVE_EXCEL_BYTES_12345")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request the archive file
        resp = await client.get("/api/swing-audit/download/Swing_Trade_Audit_Archive_Test.xlsx")
        assert resp.status_code == 200
        assert resp.content == b"TEST_ARCHIVE_EXCEL_BYTES_12345"
        assert "Swing_Trade_Audit_Archive_Test.xlsx" in resp.headers.get("content-disposition", "")

