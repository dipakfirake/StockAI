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

engine = create_async_engine(
    settings.DATABASE_URL,
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
    async with engine.begin() as conn:
        # Create all tables first
        await conn.run_sync(Base.metadata.create_all)
        
        # Now create TimescaleDB hypertable for candles if it doesn't exist
        # We catch exceptions gracefully in case it's already a hypertable or TimescaleDB isn't installed
        from sqlalchemy import text
        try:
            await conn.execute(text(
                "SELECT create_hypertable('candles', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"
            ))
        except Exception as e:
            # Depending on the DB, this might fail if Timescale isn't installed.
            # In MVP we can log it and continue.
            pass
