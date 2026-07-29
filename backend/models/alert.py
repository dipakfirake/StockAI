"""Alert model."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Numeric, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from backend.core.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    condition_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Supported: PRICE_ABOVE, PRICE_BELOW, RSI_BELOW, RSI_ABOVE, MACD_CROSS_UP, MACD_CROSS_DOWN
    condition_value: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="MEDIUM")  # HIGH, MEDIUM, LOW
    delivery_method: Mapped[str] = mapped_column(String(20), default="IN_APP")  # IN_APP, EMAIL, BOTH
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="alerts")

    def __repr__(self) -> str:
        return f"<Alert {self.symbol} {self.condition_type} {self.condition_value}>"
