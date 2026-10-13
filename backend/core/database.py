"""Database connection — SQLAlchemy async engine + session factory."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from backend.core.config import settings

import sys
from sqlalchemy.pool import NullPool

is_celery = "celery" in sys.argv[0] or "celery" in sys.modules

engine_kwargs = {"echo": settings.DEBUG}
if is_celery:
    engine_kwargs["poolclass"] = NullPool
else:
    engine_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW

import urllib.parse


def get_async_db_url(url: str) -> str:
    """Ensure database URL uses postgresql+asyncpg driver and adapts query params for asyncpg."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    parsed = urllib.parse.urlsplit(url)
    if parsed.query:
        query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        # asyncpg takes 'ssl', not 'sslmode', and does not support 'channel_binding'
        filtered_params = [
            ("ssl" if k == "sslmode" else k, v)
            for k, v in query_params
            if k != "channel_binding"
        ]
        new_query = urllib.parse.urlencode(filtered_params)
        url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))

    return url

db_url = get_async_db_url(settings.DATABASE_URL)
engine = create_async_engine(
    db_url,
    **engine_kwargs
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_db_tables():
    """Create all tables on startup (use Alembic for production migrations)."""
    try:
        import backend.models  # noqa: F401
        async with engine.begin() as conn:
            # Create all tables first
            await conn.run_sync(Base.metadata.create_all)
            
            # Ensure columns exist on users table for existing databases
            from sqlalchemy import text
            await conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users') THEN
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS pro_status VARCHAR(50) DEFAULT 'NONE';
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS pro_requested_at TIMESTAMPTZ;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS pro_approved_by VARCHAR(255);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_reference VARCHAR(255);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_method VARCHAR(50);
                    END IF;
                END $$;
            """))

            # Now create TimescaleDB hypertable for candles if it doesn't exist
            # We catch exceptions gracefully in case it's already a hypertable or TimescaleDB isn't installed
            try:
                await conn.execute(text(
                    "SELECT create_hypertable('candles', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"
                ))
            except Exception:
                # Depending on the DB, this might fail if Timescale isn't installed.
                pass
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"⚠️ [Database] Connection check deferred: {e}")
