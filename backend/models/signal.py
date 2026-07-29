"""Signal model — rule-based buy/sell/hold signals."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from backend.core.database import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(30), ForeignKey("stocks.symbol", ondelete="CASCADE"), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(10), nullable=False)   # BUY, SELL, HOLD, WATCH
    strength: Mapped[str] = mapped_column(String(10), nullable=False)       # STRONG, MODERATE, WEAK
    reason: Mapped[str] = mapped_column(Text, nullable=False)               # Human-readable explanation
    indicators_used: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timeframe: Mapped[str] = mapped_column(String(5), default="1d")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    stock: Mapped["Stock"] = relationship("Stock", back_populates="signals")

    def __repr__(self) -> str:
        return f"<Signal {self.signal_type} {self.symbol} [{self.strength}]>"
