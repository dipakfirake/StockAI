"""Swing Trade Audit Models — Multi-tier tracking and ledger for swing recommendations over 11-day cycles."""

import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import String, Integer, Text, Date, DateTime, Numeric, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from backend.core.database import Base


class SwingTradeAuditCycle(Base):
    """Represents an 11-trading-day audit evaluation cycle."""
    __tablename__ = "swing_trade_audit_cycles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE, COMPLETED
    excel_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_trades: Mapped[int] = mapped_column(Integer, default=0)
    loss_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"))
    total_gain_loss_pct: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0.00"))
    total_pnl_rupees: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    audits: Mapped[List["SwingTradeAudit"]] = relationship("SwingTradeAudit", back_populates="cycle", cascade="all, delete-orphan")


class SwingTradeAudit(Base):
    """Individual stock recommendation tracked across next 11 trading days."""
    __tablename__ = "swing_trade_audits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("swing_trade_audit_cycles.id", ondelete="SET NULL"), nullable=True, index=True)
    
    symbol: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(120), default="")
    recommendation_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    
    buy_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    target_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    
    target_1: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    target_2: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    target_3: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    reward_to_risk: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    total_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    
    # Audit outcome status: IN_PROGRESS, TARGET_ACHIEVED, STOPLOSS_HIT, DAY_11_EXIT
    status: Mapped[str] = mapped_column(String(30), default="IN_PROGRESS", index=True)
    exit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    exit_day_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Day 1..11
    
    profit_loss_pct: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0.00"))
    realized_pnl_rupees: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    allocated_capital: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("100000.00"))
    
    # User execution tracking (when user explicitly buys this recommendation)
    user_bought: Mapped[bool] = mapped_column(Boolean, default=False)
    user_buy_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    user_buy_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    cycle: Mapped[Optional["SwingTradeAuditCycle"]] = relationship("SwingTradeAuditCycle", back_populates="audits")
    daily_prices: Mapped[List["SwingTradeAuditPrice"]] = relationship("SwingTradeAuditPrice", back_populates="audit", cascade="all, delete-orphan", order_by="SwingTradeAuditPrice.day_number")


class SwingTradeAuditPrice(Base):
    """Daily price milestone snapshot (Day 1 through Day 11) for an audited swing stock."""
    __tablename__ = "swing_trade_audit_prices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("swing_trade_audits.id", ondelete="CASCADE"), nullable=False, index=True)
    
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 to 11
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    high_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    low_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    close_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    
    change_pct_from_buy: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0.00"))
    target_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    stoploss_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    audit: Mapped["SwingTradeAudit"] = relationship("SwingTradeAudit", back_populates="daily_prices")
