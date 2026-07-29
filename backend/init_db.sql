-- init_db.sql
-- This script runs automatically when the TimescaleDB container starts
-- It is used to ensure the timescaledb extension is enabled

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- We'll create the hypertable via Alembic migrations after SQLAlchemy creates the table.
-- But just in case, we can ensure the extension is available here.
