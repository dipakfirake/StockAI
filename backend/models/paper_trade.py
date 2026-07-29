"""Paper Trade model — virtual order simulation. No real money, no broker."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from backend.core.database import Base

if TYPE_CHECKING:
    from backend.models.user import User


class PaperTrade(Base):
    """
    Simulated trade. Never connected to a real broker.
    Slippage and commission are applied to reflect realistic PnL.
    """
    __tablename__ = "paper_trades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(5), nullable=False)       # BUY, SELL
    order_type: Mapped[str] = mapped_column(String(10), default="MARKET")   # MARKET, LIMIT, SL, SL_LIMIT
    product_type: Mapped[str] = mapped_column(String(10), default="INTRADAY") # INTRADAY, DELIVERY
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Order prices
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    
    # Execution details
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    slippage: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    commission: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("20"))
    stt_tax: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"))
    
    status: Mapped[str] = mapped_column(String(10), default="PENDING", index=True)  # PENDING, OPEN, CLOSED, CANCELLED
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="paper_trades")

    @property
    def unrealized_pnl(self, current_price: float = 0.0) -> float:
        """Calculate unrealized PnL at a given current price."""
        if self.status != "OPEN" or not self.entry_price:
            return 0.0
        multiplier = 1 if self.direction == "BUY" else -1
        # PnL = (Exit - Entry) * Qty - Commission - STT
        return multiplier * (current_price - float(self.entry_price)) * self.quantity - float(self.commission) - float(self.stt_tax)

    def __repr__(self) -> str:
        return f"<PaperTrade {self.direction} {self.quantity}x{self.symbol} @ {self.entry_price} [{self.status}]>"
