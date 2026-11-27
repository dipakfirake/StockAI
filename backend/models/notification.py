from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from backend.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    category = Column(String(40), default="GENERAL", index=True)  # AUTO_SELL, ORDER_FILL, SYSTEM_NOTICE, ALERT_TRIGGERED, GENERAL
    symbol = Column(String(30), nullable=True)
    trade_id = Column(String(64), nullable=True)
    metadata_json = Column(Text, nullable=True)
    is_seen = Column(Boolean, default=False, index=True)
    is_read = Column(Boolean, default=False)
    priority = Column(String, default="INFO")  # INFO, WARNING, CRITICAL, HIGH
    seen_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
