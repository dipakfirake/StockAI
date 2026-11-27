"""Database connection — SQLAlchemy async engine + session factory."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from backend.core.config import settings

import sys
from sqlalchemy.pool import NullPool

is_celery = "celery" in sys.argv[0] or "celery" in sys.modules

engine_kwargs = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,
    "pool_recycle": 300,
}
if is_celery:
    engine_kwargs["poolclass"] = NullPool
else:
    engine_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW
    engine_kwargs["pool_timeout"] = 8.0

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
if "sqlite" not in db_url.lower():
    engine_kwargs["connect_args"] = {
        "timeout": 5.0,
        "command_timeout": 8.0,
    }
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

                    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'swing_trade_audits') THEN
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS target_1 NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS target_2 NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS target_3 NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS reward_to_risk NUMERIC(8, 2);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS total_score NUMERIC(6, 2);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS allocated_capital NUMERIC(14, 2) DEFAULT 100000.00;
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS dynamic_stop_loss NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS tranche_2_active BOOLEAN DEFAULT FALSE;
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS tranche_2_buy_price NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS tranche_2_stop_loss NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS ratchet_stage VARCHAR(40) DEFAULT 'INITIAL';
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS highest_price_recorded NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS user_bought BOOLEAN DEFAULT FALSE;
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS user_buy_price NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS user_buy_time TIMESTAMPTZ;
                        ALTER TABLE swing_trade_audits ADD COLUMN IF NOT EXISTS fill_confirmed BOOLEAN DEFAULT TRUE;

                        DELETE FROM swing_trade_audits a
                        USING swing_trade_audits b
                        WHERE a.cycle_id IS NOT NULL
                          AND a.cycle_id = b.cycle_id
                          AND a.symbol = b.symbol
                          AND (
                              (a.user_bought::int < b.user_bought::int)
                              OR (a.user_bought = b.user_bought AND a.ctid > b.ctid)
                          );
                        CREATE UNIQUE INDEX IF NOT EXISTS uq_swing_audit_cycle_symbol
                            ON swing_trade_audits (cycle_id, symbol)
                            WHERE cycle_id IS NOT NULL;
                    END IF;

                    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'swing_trade_audit_prices') THEN
                        ALTER TABLE swing_trade_audit_prices ADD COLUMN IF NOT EXISTS dynamic_sl_day NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audit_prices ADD COLUMN IF NOT EXISTS atr_value NUMERIC(12, 4);
                        ALTER TABLE swing_trade_audit_prices ADD COLUMN IF NOT EXISTS ratchet_event VARCHAR(40);
                    END IF;

                    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'swing_trade_audit_cycles') THEN
                        ALTER TABLE swing_trade_audit_cycles ADD COLUMN IF NOT EXISTS excel_file_path VARCHAR(500);
                        ALTER TABLE swing_trade_audit_cycles ADD COLUMN IF NOT EXISTS total_gain_loss_pct NUMERIC(8, 2) DEFAULT 0.00;
                        ALTER TABLE swing_trade_audit_cycles ADD COLUMN IF NOT EXISTS total_pnl_rupees NUMERIC(14, 2) DEFAULT 0.00;
                    END IF;

                    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'paper_trades') THEN
                        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS target_1 NUMERIC(12, 4);
                        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS target_2 NUMERIC(12, 4);
                        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS target_3 NUMERIC(12, 4);
                        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS initial_stop_loss NUMERIC(12, 4);
                        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS highest_price_recorded NUMERIC(12, 4);
                        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS lowest_price_recorded NUMERIC(12, 4);
                        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS ratchet_stage VARCHAR(40) DEFAULT 'INITIAL';
                        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS trailing_enabled BOOLEAN DEFAULT TRUE;
                        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS closed_by VARCHAR(30);
                        ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS exit_reason VARCHAR(60);
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
