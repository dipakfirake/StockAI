# AI Memory

## Persistent project memory
- India-first stock research platform (NSE/BSE)
- Research only — no trade execution, no financial guarantees
- Explainable alerts and AI scores (SHAP-backed)
- Paper trading and backtesting required (no real money)
- Checkpoint-based continuation required across sessions and AI tools

## Stack decisions (permanent)
- Backend: FastAPI (Python 3.11)
- Frontend: React 18 + Vite + TypeScript
- Database: PostgreSQL 15 + TimescaleDB
- Cache: Redis 7
- Task queue: Celery + Redis
- Charting: Lightweight Charts (TradingView OSS)
- State: Zustand
- ORM: SQLAlchemy 2.0 + Alembic
- AI: pandas-ta → LightGBM + SHAP → LSTM
- Data: yfinance (MVP), NSE/BSE feeds (later)
- Containers: Docker Compose (dev)

## Data model (permanent)
- User → Watchlist, Alert, PaperTrade, Portfolio
- Stock → Candle (hypertable), Signal, Prediction
- Alert has: symbol, condition_type, condition_value, is_active, triggered_at
- PaperTrade has: symbol, direction, quantity, entry_price, exit_price, status, pnl
- Signal has: symbol, signal_type, strength, reason (explainable text)
- Prediction has: symbol, horizon, predicted_direction, confidence, shap_values

## AI rules (permanent)
- Never give unexplained scores
- Always include feature importance for ML outputs
- Rule-based signals must have readable reason strings
- Walk-forward validation required for all backtests
- Out-of-sample period must be at least 20% of total data

## Decision history (summary)
- Phased development (12 phases defined)
- Progress stored in checkpoint files
- Modular architecture — each engine is independent
- Data quality before model complexity
- India market hours: 9:15 AM – 3:30 PM IST, Mon–Fri
- Market calendar: NSE holidays must be respected

## Resume rule
Always read PROJECT_CHECKPOINT.md and PROJECT_STATE.json first.
Continue from the latest `in_progress` items.
Never restart completed phases.
Never redesign completed architecture unless explicitly instructed.
