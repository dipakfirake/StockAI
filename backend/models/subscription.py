"""Subscription and payment orders model."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from backend.core.database import Base


class SubscriptionOrder(Base):
    """Tracks payment transactions and Pro upgrade requests."""
    __tablename__ = "subscription_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_tier: Mapped[str] = mapped_column(String(50), default="PRO")
    amount: Mapped[float] = mapped_column(Float, default=29.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    payment_method: Mapped[str] = mapped_column(String(50), default="UPI_CARD")  # UPI, CARD, ADMIN_OVERRIDE
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING")  # PENDING, SUCCESS, FAILED, ADMIN_APPROVED, REJECTED
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<SubscriptionOrder id={self.id} user={self.user_id} status={self.status}>"
