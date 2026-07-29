# System Architecture Overview

## Platform Name
AI Stock Research Platform

## Architecture Style
Microservices-lite — monorepo with modular services, deployable as separate containers.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────┐
│                        USER BROWSER                       │
│              React 18 + Vite + TypeScript                 │
│   Dashboard | Chart | Alerts | Paper Trading | Backtest   │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTPS / WebSocket
┌──────────────────────────▼───────────────────────────────┐
│                     FASTAPI BACKEND                       │
│  /api/stocks  /api/alerts  /api/paper-trades  /api/ai     │
│  /api/backtest  /api/portfolio  /api/watchlist             │
│                  /api/market/regime                        │
└───┬──────────────┬──────────────┬────────────────────────┘
    │              │              │
    ▼              ▼              ▼
┌───────┐  ┌──────────────┐  ┌──────────────────┐
│ Redis │  │  PostgreSQL  │  │  Celery Workers  │
│ Cache │  │ + TimescaleDB│  │  (Background)    │
│ Queue │  │  (Primary DB)│  │                  │
└───────┘  └──────────────┘  └────────┬─────────┘
                                      │
                             ┌────────▼─────────┐
                             │  Data Sources    │
                             │  yfinance (MVP)  │
                             │  NSE scraper     │
                             │  BSE scraper     │
                             └──────────────────┘
```

## Component Responsibilities

### Frontend (React + Vite + TypeScript)
- Renders all UI screens
- Fetches data from FastAPI via REST
- Receives real-time alerts via WebSocket
- Charts via Lightweight Charts (TradingView OSS)
- State via Zustand stores (market, alerts, trades)
- Routing via React Router v6

### Backend (FastAPI)
- REST API server
- WebSocket endpoint for real-time alerts
- Orchestrates all services
- Authenticates requests (JWT)
- Background tasks delegated to Celery

### Database (PostgreSQL + TimescaleDB)
- Stores all persistent data
- `candles` table is a TimescaleDB hypertable (partitioned by time)
- `signals`, `predictions`, `paper_trades` are standard tables
- Redis caches frequent reads (live quotes, indicator values)

### Celery Workers
- Periodic data ingestion (every 1 min during market hours)
- Alert evaluation (every 30 seconds)
- Backtest task execution (on-demand)
- AI model scoring (on-demand + scheduled)

### Data Layer
- `yfinance`: OHLCV candles, company info (MVP)
- NSE scraper: index compositions, corporate actions (MVP)
- Redis: caches live quotes (TTL 60s), daily candles (TTL 3600s)

---

## Security
- JWT authentication for all API endpoints
- Environment variables for all secrets (via `.env`)
- CORS configured for frontend origin only
- Rate limiting on public endpoints
- No real money, no broker credentials stored

## Scalability Plan
- Phase 1-3: Docker Compose, single machine
- Phase 12: Docker Swarm or Kubernetes, multi-node
- TimescaleDB supports compression and continuous aggregates for large OHLCV datasets
- Redis Cluster for high-availability caching
