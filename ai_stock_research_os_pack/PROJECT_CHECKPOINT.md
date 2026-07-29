# Project Checkpoint

## Current state
- **Current phase:** Phase 3 — System Architecture + Full Project Scaffold
- **Current goal:** Build working backend + frontend scaffolds; wire to database and data layer
- **Last updated:** 2026-07-29
- **Status:** In Progress

## Completed

### Phase 1 — Product Definition ✅
- Project constitution created
- Master prompt drafted
- Resume + checkpoint system defined
- Core folder structure created
- Problem statement defined
- User personas defined (beginner investor, swing trader, quant researcher, market analyst)
- Core use cases documented
- Non-goals documented (no broker execution, no financial guarantees)
- MVP scope approved
- Success metrics defined

### Phase 2 — MVP Design ✅
- MVP feature set approved
- MVP screens identified (Dashboard, Chart, Alerts, Paper Trading, Backtest, Portfolio)
- MVP API endpoints defined
- Technology stack decided
- Database schema designed (User, Stock, Candle, Watchlist, Alert, PaperTrade, Signal, Prediction)
- Initial build order defined

### Phase 3 — System Architecture (Docs) ✅
- System overview documented
- Tech stack documented
- Data flow documented
- API design documented
- Extended ER diagram created
- All diagram stubs upgraded

### Phase 3 — Project Scaffold ✅
- Backend scaffold created (FastAPI)
- Frontend scaffold created (React + Vite + TypeScript)
- Data ingestion layer created (yfinance)
- Infrastructure created (Docker Compose, Makefile, .env)

## In Progress
- Backend service implementations (market_data, indicators, signals)
- Frontend page implementations
- Database migrations (Alembic)
- Docker integration testing

## Next tasks
1. Implement `market_data.py` service — yfinance fetcher with validation
2. Implement `indicators.py` service — pandas-ta RSI, MACD, Bollinger Bands, EMA
3. Implement `signals.py` service — rule-based buy/sell/hold signals
4. Implement `ai_engine.py` service — scoring + SHAP explainability
5. Wire frontend Chart page to backend candle API
6. Set up Alembic database migrations
7. Build Celery task for periodic data ingestion
8. Implement alert evaluation loop (Celery beat)
9. Implement paper trading order simulation
10. Implement basic backtesting engine

## Key decisions
- Backend: FastAPI (Python 3.11)
- Frontend: React 18 + Vite + TypeScript
- Database: PostgreSQL 15 + TimescaleDB
- Cache: Redis 7
- Task queue: Celery + Redis
- Charting: Lightweight Charts (TradingView OSS)
- State management: Zustand
- Data: yfinance (MVP), NSE/BSE official (later)
- AI: Rule-based → LightGBM → LSTM
- ORM: SQLAlchemy 2.0 + Alembic
- Containerisation: Docker Compose

## Open questions
- None — all Phase 1/2 questions resolved

## Assumptions
- yfinance provides sufficient data for MVP (15-min delay acceptable)
- TimescaleDB handles OHLCV time-series efficiently
- Paper trading requires no real brokerage integration
- Explainability via SHAP for all AI scores

## Blockers
- None

## Files updated this session
- PROJECT_STATE.json
- PROJECT_CHECKPOINT.md
- DONE.md
- NEXT_TASK.md
- CHANGELOG.md
- AI_MEMORY.md
- DECISION_LOG.md
- phases/phase_01_product_definition_complete.md
- phases/phase_02_mvp_design_complete.md
- phases/phase_03_system_architecture.md
- docs/architecture/* (4 files)
- docs/database/* (2 files)
- backend/** (all scaffold files)
- frontend/** (all scaffold files)
- docker-compose.yml
- .env.example
- Makefile
- README.md

## Architecture notes
- **Frontend:** React 18 + Vite + TypeScript. Pages: Dashboard, Chart, Alerts, PaperTrading, Backtest, Portfolio. State via Zustand. Charts via Lightweight Charts.
- **Backend:** FastAPI. Routers: stocks, alerts, paper_trading, backtesting, ai_engine, portfolio, watchlist. Celery for background tasks.
- **Data:** yfinance for OHLCV ingestion. NSE scraper stub for corporate actions.
- **AI/ML:** pandas-ta for indicators, LightGBM for scoring, SHAP for explainability.
- **Alerts:** Rule-based conditions evaluated by Celery beat. WebSocket push to frontend.
- **Paper trading:** Virtual order simulation — no real money, no broker.
- **Backtesting:** Walk-forward on historical OHLCV data.
- **Storage:** PostgreSQL 15 + TimescaleDB (hypertables for candles). Redis for caching and task queue.
- **DevOps:** Docker Compose for local dev. GitHub Actions CI/CD planned for Phase 12.

## Resume prompt
Continue from Phase 3 implementation. The scaffold exists. The next priority is implementing the `market_data` service, `indicators` service, and `signals` service in the backend. After that, wire the frontend Chart page to the backend candle API. Do not redesign anything already decided.
