"""User Preference model — stores per-user UI/app preferences as key-value pairs."""

import uuid
import json
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from backend.core.database import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        # Each user can have only one value per preference key
        UniqueConstraint("user_id", "pref_key", name="uq_user_pref_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pref_key: Mapped[str] = mapped_column(String(100), nullable=False)
    # Value is stored as a JSON string so any type (bool, str, int, list) is supported
    pref_value: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship back to user (optional, for joins)
    user: Mapped["User"] = relationship("User", back_populates="preferences")

    def get_value(self):
        """Deserialize the stored JSON value."""
        try:
            return json.loads(self.pref_value)
        except (json.JSONDecodeError, TypeError):
            return self.pref_value

    def set_value(self, value):
        """Serialize a Python value to JSON for storage."""
        self.pref_value = json.dumps(value, default=str)

    def __repr__(self) -> str:
        return f"<UserPreference user={self.user_id} key={self.pref_key}>"
