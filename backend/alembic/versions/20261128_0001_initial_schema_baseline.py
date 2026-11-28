"""Initial baseline schema anchored to all registered SQLAlchemy models.

Revision ID: 20261128_0001
Revises:
Create Date: 2026-11-28 22:18:00+05:30
"""

from __future__ import annotations

import os
from alembic import op

# revision identifiers, used by Alembic.
revision = "20261128_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all baseline tables idempotently if any are missing."""
    from backend.core.database import Base
    import backend.models  # noqa: F401 — ensure every model is registered on Base.metadata

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Safety-guarded baseline downgrade (never drops production data unless explicitly allowed)."""
    if os.getenv("ALLOW_BASELINE_DROP", "").lower() != "true":
        return
    from backend.core.database import Base
    import backend.models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
