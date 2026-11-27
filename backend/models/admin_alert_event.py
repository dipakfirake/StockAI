"""Admin-only security threats, system failures, Celery crashes, and application error-log ledger."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from backend.core.database import Base


class AdminAlertEvent(Base):
    """
    Strictly admin-only operational, security, and error-log notification ledger.
    Separated from user-facing Notification rows so traces, client IPs, and system internals
    never leak to standard user endpoints.
    """
    __tablename__ = "admin_alert_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="SYSTEM_FAILURE", index=True)  # SECURITY_THREAT, SYSTEM_FAILURE, ERROR_LOG, CELERY_FAILURE, BROKER_FEED
    subsystem: Mapped[str] = mapped_column(String(50), default="SYSTEM", index=True)
    severity: Mapped[str] = mapped_column(String(20), default="WARNING", index=True)  # CRITICAL, WARNING, INFO
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    is_seen: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)  # OPEN, ACKNOWLEDGED, RESOLVED
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
