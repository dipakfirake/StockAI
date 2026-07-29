# Changelog

## 2026-07-29 — Session 1: Bootstrap + Full Scaffold

### Added
- Created project operating system pack (ai_stock_research_os_pack)
- Defined project constitution
- Defined resume and checkpoint rules
- Drafted master prompt
- Drafted Phase 1 roadmap

### Phase 1 — Product Definition (COMPLETED)
- Wrote full problem statement
- Defined user personas (beginner investor, swing trader, quant researcher, analyst)
- Documented core use cases
- Documented non-goals (no broker, no real trades)
- Defined MVP scope
- Defined success metrics

### Phase 2 — MVP Design (COMPLETED)
- Approved MVP feature set (7 screens, 12 API endpoints)
- Decided technology stack (FastAPI, React+Vite+TS, PostgreSQL+TimescaleDB, Redis, Celery)
- Designed full database schema (8 entities)
- Defined initial build order
- Created extended ER diagram

### Phase 3 — System Architecture (COMPLETED)
- Written system_overview.md
- Written tech_stack.md
- Written data_flow.md
- Written api_design.md (all MVP endpoints with request/response schemas)
- Created extended ER diagram (mermaid)
- Updated all diagram files

### Phase 3 — Project Scaffold (COMPLETED)
- Created full backend scaffold (FastAPI, SQLAlchemy, Alembic, Celery)
  - core/ (config, database, auth, logging)
  - models/ (8 models)
  - api/ (7 routers)
  - services/ (6 services)
  - data/ingestion/ + data/validation/
  - tests/ (3 test files)
  - requirements.txt
  - Dockerfile
- Created full frontend scaffold (React 18 + Vite + TypeScript)
  - 6 pages (Dashboard, Chart, Alerts, PaperTrading, Backtest, Portfolio)
  - 6 components (NavBar, StockChart, Watchlist, AlertCard, SignalCard, AIScoreCard)
  - 2 services (api.ts, websocket.ts)
  - 3 stores (marketStore, alertStore, tradeStore)
  - App.tsx, main.tsx, index.css
  - Dockerfile
- Created infrastructure
  - docker-compose.yml (FastAPI, React, PostgreSQL, TimescaleDB, Redis, Celery, Flower)
  - docker-compose.prod.yml
  - .env.example
  - Makefile
  - README.md

### Documentation Updated
- PROJECT_STATE.json — full update with architecture decisions
- PROJECT_CHECKPOINT.md — full update with resume instructions
- DECISION_LOG.md — 15 decisions recorded (DEC-001 to DEC-015)
- AI_MEMORY.md — full permanent memory written
- DONE.md — all completed items recorded
- NEXT_TASK.md — Phase 4 tasks defined
- TODO.md — remaining work listed
- ROADMAP.md — phases and status updated

## 2026-07-29 — Session 2: Implementation (Phases 4-12)

### Phase 4-6 — Market Data, Charts, Alerts (COMPLETED)
- Implemented core backend models and TS interfaces.
- Implemented robust `yfinance` integration with Redis caching and Celery periodic background tasks.
- Advanced Technical Analysis indicators via `pandas-ta` (MACD, RSI, BB, etc.).
- Alerts engine implemented and scheduled.

### Phase 7-9 — Paper Trading, Backtesting, ML Pipeline (COMPLETED)
- Established Paper Trading accounts with Stop-Loss, Limit Orders, and realistic simulated gaps and STT taxes.
- Implemented robust Walk-Forward Strategy Backtesting (Sharpe Ratio, Drawdown, Benchmark).
- Real LightGBM ML implementation running inside `/api/ai/score` providing real SHAP feature contribution explanations.

### Phase 10-12 — Sentiment, Deployment, Monetization (COMPLETED)
- NLP Pipeline with FinBERT for real-time news sentiment via scraping.
- Full Docker Compose environment stabilized and building successfully.
- Built complete FREE vs PRO Tier access mechanism (RBAC), UI Paywalls, `/pricing` flow, and mock checkout endpoint.
