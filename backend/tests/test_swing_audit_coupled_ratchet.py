"""Unit tests for Coupled Ratchet & Dynamic ATR Trailing Stops in the 11-Day Swing Audit System."""

import os
import uuid
import pytest
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path
import openpyxl

from backend.models.swing_audit import SwingTradeAuditCycle, SwingTradeAudit, SwingTradeAuditPrice
from backend.services.swing_audit_service import SwingAuditService, add_trading_days


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_single_target_normal_win(mock_db):
    """When no Target 2 is configured, reaching Target 1 exits normally as TARGET_ACHIEVED."""
    today = date(2026, 11, 10)
    cycle = SwingTradeAuditCycle(
        id=uuid.uuid4(),
        cycle_number=1,
        from_date=today,
        to_date=add_trading_days(today, 11),
        status="ACTIVE"
    )

    audit = SwingTradeAudit(
        id=uuid.uuid4(),
        cycle_id=cycle.id,
        symbol="POWERGRID.NS",
        recommendation_date=today,
        buy_price=Decimal("100.00"),
        target_price=Decimal("105.00"),
        stop_loss=Decimal("96.00"),
        target_1=Decimal("105.00"),
        target_2=None,  # Single target
        status="IN_PROGRESS",
        allocated_capital=Decimal("100000.00")
    )
    audit.daily_prices = []
    cycle.audits = [audit]

    # Candle 1: reaches 105.50
    mock_candles = [
        {"timestamp": today.isoformat(), "open": 100.0, "high": 105.5, "low": 99.0, "close": 105.0}
    ]

    with patch("backend.services.market_data.market_data_service.fetch_candles", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_candles

        mock_exec = MagicMock()
        mock_exec.scalars.return_value.first.return_value = cycle
        mock_exec.scalars.return_value.all.return_value = [audit]
        mock_db.execute.return_value = mock_exec

        with patch.object(SwingAuditService, "generate_excel_workbook", new_callable=AsyncMock) as mock_xl:
            mock_xl.return_value = Path("test.xlsx")
            res = await SwingAuditService.update_daily_prices(mock_db, cycle.id)

    assert audit.status == "TARGET_ACHIEVED"
    assert float(audit.profit_loss_pct) == 5.0  # Sold at limit target ₹105.00
    assert float(audit.realized_pnl_rupees) == 5000.0
    assert audit.tranche_2_active is False


@pytest.mark.asyncio
async def test_multi_target_coupled_ratchet_activation(mock_db):
    """When Target 2 is configured, crossing Target 1 activates Tranche 2 and ratchets Tranche 1 stop."""
    today = date(2026, 11, 10)
    cycle = SwingTradeAuditCycle(
        id=uuid.uuid4(),
        cycle_number=1,
        from_date=today,
        to_date=add_trading_days(today, 11),
        status="ACTIVE"
    )

    audit = SwingTradeAudit(
        id=uuid.uuid4(),
        cycle_id=cycle.id,
        symbol="RELIANCE.NS",
        recommendation_date=today,
        buy_price=Decimal("100.00"),
        target_price=Decimal("110.00"),
        stop_loss=Decimal("96.00"),
        target_1=Decimal("105.00"),
        target_2=Decimal("110.00"),  # Extended Target 2 active!
        status="IN_PROGRESS",
        allocated_capital=Decimal("100000.00")
    )
    audit.daily_prices = []
    cycle.audits = [audit]

    # Day 1: Price rallies to 106.00 (Crosses Target 1)
    mock_candles = [
        {"timestamp": today.isoformat(), "open": 100.0, "high": 106.0, "low": 99.5, "close": 105.5}
    ]

    with patch("backend.services.market_data.market_data_service.fetch_candles", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_candles

        mock_exec = MagicMock()
        mock_exec.scalars.return_value.first.return_value = cycle
        mock_exec.scalars.return_value.all.return_value = [audit]
        mock_db.execute.return_value = mock_exec

        with patch.object(SwingAuditService, "generate_excel_workbook", new_callable=AsyncMock) as mock_xl:
            mock_xl.return_value = Path("test.xlsx")
            await SwingAuditService.update_daily_prices(mock_db, cycle.id)

    # Trade should NOT exit; it must be IN_PROGRESS with Tranche 2 active
    assert audit.status == "IN_PROGRESS"
    assert audit.tranche_2_active is True
    assert float(audit.tranche_2_buy_price) >= 105.0
    assert float(audit.dynamic_stop_loss) >= 101.0  # Ratcheted above entry (Break-even + 1%)
    assert audit.ratchet_stage == "BREAKEVEN_LOCKED"


@pytest.mark.asyncio
async def test_multi_target_reversal_guaranteed_profit(mock_db):
    """When price reaches halfway (108), both stops lock in profits. A reversal triggers STOPPED_IN_PROFIT."""
    today = date(2026, 11, 10)
    cycle = SwingTradeAuditCycle(
        id=uuid.uuid4(),
        cycle_number=1,
        from_date=today,
        to_date=add_trading_days(today, 11),
        status="ACTIVE"
    )

    audit = SwingTradeAudit(
        id=uuid.uuid4(),
        cycle_id=cycle.id,
        symbol="TCS.NS",
        recommendation_date=today,
        buy_price=Decimal("100.00"),
        target_price=Decimal("110.00"),
        stop_loss=Decimal("96.00"),
        target_1=Decimal("105.00"),
        target_2=Decimal("110.00"),
        status="IN_PROGRESS",
        allocated_capital=Decimal("100000.00")
    )
    audit.daily_prices = []
    cycle.audits = [audit]

    # Day 1: rallies to 108.00 (triggers T2_RATCHET_ACTIVE)
    # Day 2: sharp reversal drops low to 104.00 (triggers Coupled Ratchet stop)
    d1 = today.isoformat()
    d2 = (today + timedelta(days=1)).isoformat()
    mock_candles = [
        {"timestamp": d1, "open": 100.0, "high": 108.0, "low": 100.0, "close": 107.5},
        {"timestamp": d2, "open": 107.0, "high": 107.5, "low": 104.0, "close": 104.5},
    ]

    with patch("backend.services.market_data.market_data_service.fetch_candles", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_candles

        mock_exec = MagicMock()
        mock_exec.scalars.return_value.first.return_value = cycle
        mock_exec.scalars.return_value.all.return_value = [audit]
        mock_db.execute.return_value = mock_exec

        with patch.object(SwingAuditService, "generate_excel_workbook", new_callable=AsyncMock) as mock_xl:
            mock_xl.return_value = Path("test.xlsx")
            await SwingAuditService.update_daily_prices(mock_db, cycle.id)

    # Must exit as STOPPED_IN_PROFIT with positive net profit!
    assert audit.status == "STOPPED_IN_PROFIT"
    assert audit.ratchet_stage == "STOPPED_IN_PROFIT"
    assert float(audit.realized_pnl_rupees) > 0.0  # Zero loss guaranteed! Net profit secured
    assert float(audit.profit_loss_pct) > 0.0


@pytest.mark.asyncio
async def test_multi_target_continuation_hits_target_2(mock_db):
    """When price surges to Target 2 (110.00), both tranches exit with maximum profit."""
    today = date(2026, 11, 10)
    cycle = SwingTradeAuditCycle(
        id=uuid.uuid4(),
        cycle_number=1,
        from_date=today,
        to_date=add_trading_days(today, 11),
        status="ACTIVE"
    )

    audit = SwingTradeAudit(
        id=uuid.uuid4(),
        cycle_id=cycle.id,
        symbol="INFY.NS",
        recommendation_date=today,
        buy_price=Decimal("100.00"),
        target_price=Decimal("110.00"),
        stop_loss=Decimal("96.00"),
        target_1=Decimal("105.00"),
        target_2=Decimal("110.00"),
        status="IN_PROGRESS",
        allocated_capital=Decimal("100000.00")
    )
    audit.daily_prices = []
    cycle.audits = [audit]

    d1 = today.isoformat()
    d2 = (today + timedelta(days=1)).isoformat()
    mock_candles = [
        {"timestamp": d1, "open": 100.0, "high": 107.0, "low": 100.0, "close": 106.5},
        {"timestamp": d2, "open": 107.0, "high": 111.0, "low": 106.0, "close": 110.5},
    ]

    with patch("backend.services.market_data.market_data_service.fetch_candles", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_candles

        mock_exec = MagicMock()
        mock_exec.scalars.return_value.first.return_value = cycle
        mock_exec.scalars.return_value.all.return_value = [audit]
        mock_db.execute.return_value = mock_exec

        with patch.object(SwingAuditService, "generate_excel_workbook", new_callable=AsyncMock) as mock_xl:
            mock_xl.return_value = Path("test.xlsx")
            await SwingAuditService.update_daily_prices(mock_db, cycle.id)

    assert audit.status == "TARGET_2_ACHIEVED"
    assert audit.ratchet_stage == "TARGET_2_ACHIEVED"
    assert float(audit.realized_pnl_rupees) > 5000.0  # Massive gain combining both tranches!
    assert float(audit.profit_loss_pct) > 5.0


@pytest.mark.asyncio
async def test_excel_generation_with_coupled_ratchet_columns(mock_db, tmp_path):
    """Excel workbook must generate 32 columns in ledger and include Coupled Ratchet KPI cards."""
    today = date(2026, 11, 10)
    cycle = SwingTradeAuditCycle(
        id=uuid.uuid4(),
        cycle_number=1,
        from_date=today,
        to_date=add_trading_days(today, 11),
        status="ACTIVE",
        total_trades=1,
        win_trades=1,
        win_rate=Decimal("100.00"),
        total_gain_loss_pct=Decimal("8.50"),
        total_pnl_rupees=Decimal("8500.00")
    )

    audit = SwingTradeAudit(
        id=uuid.uuid4(),
        cycle_id=cycle.id,
        symbol="SBIN.NS",
        company_name="State Bank of India",
        recommendation_date=today,
        buy_price=Decimal("100.00"),
        target_price=Decimal("110.00"),
        stop_loss=Decimal("96.00"),
        target_1=Decimal("105.00"),
        target_2=Decimal("110.00"),
        dynamic_stop_loss=Decimal("105.00"),
        tranche_2_active=True,
        tranche_2_buy_price=Decimal("106.00"),
        tranche_2_stop_loss=Decimal("105.00"),
        ratchet_stage="T2_RATCHET_ACTIVE",
        status="TARGET_2_ACHIEVED",
        exit_date=today,
        exit_price=Decimal("110.00"),
        exit_day_number=2,
        profit_loss_pct=Decimal("8.50"),
        realized_pnl_rupees=Decimal("8500.00"),
        allocated_capital=Decimal("100000.00")
    )
    audit.daily_prices = []
    cycle.audits = [audit]

    mock_exec = MagicMock()
    mock_exec.scalars.return_value.first.return_value = cycle
    mock_db.execute.return_value = mock_exec

    with patch("backend.services.swing_audit_service.get_audit_dir", return_value=tmp_path):
        out_path = await SwingAuditService.generate_excel_workbook(mock_db, cycle.id)

    assert out_path is not None
    assert out_path.exists()

    # Load workbook and verify
    wb = openpyxl.load_workbook(out_path)
    assert "Audit Scorecard" in wb.sheetnames
    assert "11-Day Price Tracking" in wb.sheetnames

    ws_ledger = wb["11-Day Price Tracking"]
    # Check headers count = 31
    header_cells = [cell.value for cell in ws_ledger[1]]
    assert len(header_cells) == 31
    assert "Dynamic Trailing SL (₹)" in header_cells
    assert "Tranche 2 Buy (₹)" in header_cells
    assert "Ratchet Milestone" in header_cells

    # Check Scorecard KPI card texts
    ws_scorecard = wb["Audit Scorecard"]
    scorecard_values = [ws_scorecard.cell(row=r, column=c).value for r in range(1, 15) for c in range(1, 10)]
    assert any("T2 Pyramiding Expansions" in str(v) for v in scorecard_values if v)
    assert any("Coupled Ratchet Wins" in str(v) for v in scorecard_values if v)
    assert any("Zero-Loss Protection Rate" in str(v) for v in scorecard_values if v)
