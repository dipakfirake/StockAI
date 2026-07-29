"""Stock master model."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from backend.core.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # NSE, BSE
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    signals: Mapped[list["Signal"]] = relationship("Signal", back_populates="stock", cascade="all, delete-orphan")
    predictions: Mapped[list["Prediction"]] = relationship("Prediction", back_populates="stock", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Stock symbol={self.symbol} exchange={self.exchange}>"
