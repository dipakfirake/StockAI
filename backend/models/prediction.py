"""Prediction model — AI scoring with SHAP explainability."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from backend.core.database import Base


class Prediction(Base):
    """
    AI model prediction for a stock's future direction.
    Every prediction MUST include shap_values — no black-box outputs.
    """
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(30), ForeignKey("stocks.symbol", ondelete="CASCADE"), nullable=False, index=True)
    horizon: Mapped[str] = mapped_column(String(10), nullable=False)            # 1d, 5d, 1w
    predicted_direction: Mapped[str] = mapped_column(String(10), nullable=False) # BUY, HOLD, SELL
    probabilities: Mapped[dict] = mapped_column(JSONB, nullable=False)           # {"buy": 0.72, "hold": 0.20, "sell": 0.08}
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), default="rule_based_v1")
    shap_values: Mapped[dict | None] = mapped_column(JSONB, nullable=True)       # Feature contributions
    features_used: Mapped[dict | None] = mapped_column(JSONB, nullable=True)     # Feature snapshot at prediction time
    actual_outcome: Mapped[str | None] = mapped_column(String(10), nullable=True) # Filled after horizon passes
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    stock: Mapped["Stock"] = relationship("Stock", back_populates="predictions")

    def __repr__(self) -> str:
        return f"<Prediction {self.symbol} {self.predicted_direction} conf={self.confidence} [{self.model_version}]>"
