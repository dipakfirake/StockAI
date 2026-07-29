# Phase 2 — MVP Design (Complete)

## Goal
Choose the smallest useful feature set that can be built quickly and validated.

## Status: ✅ COMPLETE

---

## Approved MVP Feature Set

### Screens (7)
1. **Dashboard** — Nifty 50 index, top gainers/losers, market breadth, sector heatmap
2. **Chart** — Candlestick OHLCV, indicators overlay, AI score panel, signal markers
3. **Alerts** — Create/manage price and indicator alerts, alert history
4. **Paper Trading** — Place virtual orders, view open positions, PnL tracker
5. **Backtesting** — Run strategy on historical data, view metrics
6. **Portfolio** — Summarize all paper trades, allocation pie chart, equity curve
7. **Watchlist** — Add/remove stocks, sort by change/volume/signals

### API Endpoints (12)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /api/stocks/search | Search stocks by name or symbol |
| GET | /api/stocks/{symbol}/quote | Live quote |
| GET | /api/stocks/{symbol}/candles | OHLCV candles (with timeframe) |
| GET | /api/stocks/{symbol}/indicators | Computed indicators |
| GET | /api/stocks/{symbol}/signals | Rule-based signals |
| GET | /api/stocks/{symbol}/ai-score | AI score + explanation |
| GET/POST | /api/watchlist | Manage watchlist |
| GET/POST/DELETE | /api/alerts | Manage alerts |
| GET/POST | /api/paper-trades | Manage paper trades |
| GET | /api/portfolio | View portfolio summary |
| POST | /api/backtest/run | Run a backtest |
| GET | /api/market/regime | Current market regime |

---

## Technology Stack (Approved)

| Layer | Technology | Reason |
|-------|-----------|--------|
| Backend | FastAPI (Python 3.11) | Fast, async, auto-docs |
| Frontend | React 18 + Vite + TypeScript | Fast build, strong typing |
| Database | PostgreSQL 15 + TimescaleDB | Time-series optimised |
| Cache | Redis 7 | Low-latency quote cache |
| Task queue | Celery + Redis | Background ingestion + alerts |
| Charting | Lightweight Charts (TradingView OSS) | Professional candlestick rendering |
| State | Zustand | Simple, no boilerplate |
| ORM | SQLAlchemy 2.0 + Alembic | Standard Python ORM |
| Containers | Docker Compose | Simple local dev |

---

## Database Schema (8 Entities)

| Entity | Purpose |
|--------|---------|
| User | Platform user (auth) |
| Stock | Stock master (symbol, exchange, sector) |
| Candle | OHLCV time-series (TimescaleDB hypertable) |
| Watchlist | User's tracked stocks |
| Alert | Price/indicator alert rules |
| PaperTrade | Virtual order simulation |
| Signal | Rule-based buy/sell signals |
| Prediction | AI model predictions with SHAP values |

---

## Build Order

1. Core infrastructure (Docker, DB, Redis)
2. Market data ingestion (yfinance → DB)
3. Indicator calculations (pandas-ta)
4. REST API endpoints (FastAPI)
5. Frontend scaffold + chart page
6. Alert evaluation loop (Celery)
7. Paper trading engine
8. Backtesting engine
9. AI scoring engine
10. Portfolio analytics

---

## Exit Criteria ✅
- MVP scope approved ✅
- First build order defined ✅
- Technology stack decided ✅
- Database schema designed ✅
- Phase 3 can begin ✅
