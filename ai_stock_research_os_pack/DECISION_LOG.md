# Decision Log

## DEC-001
**Decision:** Build a research platform, not a broker.
**Reason:** The system focuses on alerts, paper trading, and analysis — not real trade execution.
**Date:** 2026-07-29

## DEC-002
**Decision:** Make it India-first.
**Reason:** Indian market hours, events, and behaviour must shape the product from day one.
**Date:** 2026-07-29

## DEC-003
**Decision:** Use checkpoints and resume files.
**Reason:** Work must continue smoothly across sessions and AI tools.
**Date:** 2026-07-29

## DEC-004
**Decision:** Backend: FastAPI (Python 3.11)
**Reason:** Fast, async, auto-docs (Swagger), excellent for financial APIs. Python ecosystem has the best quant and ML libraries.
**Date:** 2026-07-29

## DEC-005
**Decision:** Frontend: React 18 + Vite + TypeScript
**Reason:** Fast build tool, strong typing, large ecosystem, excellent charting library support.
**Date:** 2026-07-29

## DEC-006
**Decision:** Database: PostgreSQL 15 + TimescaleDB
**Reason:** TimescaleDB is purpose-built for time-series OHLCV data. Hypertables compress and query efficiently. Standard SQL still applies.
**Date:** 2026-07-29

## DEC-007
**Decision:** Cache: Redis 7
**Reason:** Dual-purpose: Celery task broker and API response cache. Sub-millisecond for live quote caching.
**Date:** 2026-07-29

## DEC-008
**Decision:** Charting: Lightweight Charts (TradingView open-source)
**Reason:** Professional-grade candlestick rendering. Free and open-source. React-compatible.
**Date:** 2026-07-29

## DEC-009
**Decision:** State management: Zustand
**Reason:** Simpler than Redux, no boilerplate, excellent for real-time data stores.
**Date:** 2026-07-29

## DEC-010
**Decision:** Data source: yfinance for MVP
**Reason:** Free, no API key required, covers NSE/BSE symbols (e.g., RELIANCE.NS). Acceptable 15-min delay for MVP.
**Alternatives rejected:** NSE official API (complex), Upstox (requires broker account).
**Future:** NSE/BSE WebSocket feeds, Upstox, Fyers for live data.
**Date:** 2026-07-29

## DEC-011
**Decision:** AI strategy: Rule-based → LightGBM → LSTM
**Reason:** Data quality must be proven before adding model complexity. Rule-based signals are explainable by default.
**Date:** 2026-07-29

## DEC-012
**Decision:** Explainability: SHAP for all ML model outputs
**Reason:** Core product rule — no black-box outputs. Every AI score must show feature contributions.
**Date:** 2026-07-29

## DEC-013
**Decision:** Task queue: Celery + Redis
**Reason:** Periodic data ingestion, alert evaluation, and backtesting must run asynchronously without blocking the API.
**Date:** 2026-07-29

## DEC-014
**Decision:** ORM: SQLAlchemy 2.0 + Alembic migrations
**Reason:** Industry-standard Python ORM. Alembic gives version-controlled schema migrations.
**Date:** 2026-07-29

## DEC-015
**Decision:** Containerisation: Docker Compose for dev, Kubernetes for prod (later)
**Reason:** Local dev needs simple orchestration. K8s deferred to Phase 12 to avoid premature complexity.
**Date:** 2026-07-29
