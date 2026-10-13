"""System incident model for 24/7 Sentinel Watchdog bug and threat tracking."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from backend.core.database import Base


class SentinelIncident(Base):
    """Tracks bugs, anomalies, system failures, and cybersecurity threats detected by Sentinel."""
    __tablename__ = "sentinel_incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # Deduplication key
    subsystem: Mapped[str] = mapped_column(String(50), index=True)  # DATABASE, REDIS, CELERY, BROKER_API, API_ENDPOINT, SECURITY
    severity: Mapped[str] = mapped_column(String(20), default="WARNING")  # CRITICAL, WARNING, INFO
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN, RESOLVED, MUTED
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<SentinelIncident id={self.id} subsystem={self.subsystem} severity={self.severity} title={self.title}>"
