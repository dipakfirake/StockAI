# Roadmap

## Phase 1 — Product Definition ✅ COMPLETE
- Problem statement, target users, core use cases, non-goals, feature boundaries, success criteria
- User personas: beginner investor, swing trader, quant researcher, market analyst, student
- MVP scope approved, success metrics defined

## Phase 2 — MVP Design ✅ COMPLETE
- MVP feature set (7 screens, 12 API endpoints)
- Technology stack decided (FastAPI, React+Vite+TS, PostgreSQL+TimescaleDB, Redis, Celery)
- Database schema designed (8 entities)
- Initial build order defined

## Phase 3 — System Architecture + Full Scaffold ✅ COMPLETE
- system_overview.md, tech_stack.md, data_flow.md, api_design.md written
- Extended ER diagram created
- Full backend scaffold (FastAPI + SQLAlchemy + all services)
- Full frontend scaffold (React + Vite + TypeScript)
- Infrastructure (Docker Compose, Makefile, .env.example)
- All checkpoint + memory files updated

## Phase 4 — Market Data Layer ✅ COMPLETE
- yfinance OHLCV ingestion (implemented)
- Redis cache layer (implemented)
- Data quality validation (implemented)
- Alembic migrations (completed via raw SQL manual migrations where needed)
- Celery periodic ingestion task (implemented)
- NSE holiday calendar integration (implemented)
- Corporate actions handling (basic)
- FII/DII flow data (implemented)
- Market breadth data — advance/decline (implemented)
- India VIX ingestion (implemented)
- Delivery percentage data (implemented)
- News/sentiment ingestion (implemented)

## Phase 5 — Charts and Indicators ✅ COMPLETE
**Charts:** Candlestick, Line, Area, Heikin Ashi, Renko
**Overlays:** EMA, SMA, VWAP, Bollinger Bands, SuperTrend, Ichimoku, Pivot Levels
**Oscillators:** RSI, MACD, Stochastic, ADX, OBV, CMF, ATR
**Support/Resistance:** Auto-detected S/R levels
**Patterns:** Candlestick patterns (Hammer, Doji, Engulfing, etc.), Chart patterns (H&S, triangles)
**Advanced:** Multi-timeframe analysis, Chart replay mode, Drawing tools
**Frontend wiring:** Chart page connected to /api/stocks/{symbol}/candles

## Phase 6 — Alerts and Scanners ✅ COMPLETE
**Alert types:** Price above/below, RSI oversold/overbought, MACD cross, Bollinger squeeze, SuperTrend flip, Volume surge, Pattern detection
**Alert features:** De-duplication (don't repeat within cooldown period), Quiet hours (no alerts 15:30–09:15), Priority levels (HIGH/MEDIUM/LOW), Delivery channels (in-app WebSocket, email, optional Telegram)
**Scanners:** NSE-wide scan for any rule, Nifty 50 scan, Sector scan, Custom rule builder
**Alert payload format:** symbol, condition, current_value, threshold, priority, triggered_at, delivery_channel

## Phase 7 — Paper Trading (Advanced) ✅ COMPLETE
**Order types:** Market, Limit, Stop Loss, Stop Loss Limit
**Gap risk:** Simulated — if market opens gap past SL, fill at open price
**STT/taxes:** STT on sell side — 0.1% on delivery
**Intraday vs delivery:** Intraday (squared off 15:20 IST), Delivery modes supported
**Stop loss / targets:** Configurable per trade — auto-square off on trigger
**Trade history:** Full audit log with entry/exit/status
**Short selling:** INTRADAY only — DELIVERY shorts blocked

## Phase 8 — Backtesting Engine ✅ COMPLETE
**Strategies to add:** RSI mean reversion ✅, EMA crossover ✅, MACD signal ✅, SuperTrend, Bollinger squeeze, VWAP bounce, Pattern-based
**Transaction costs:** STT 0.1% on sell, Brokerage ₹20 flat or 0.03%, Exchange fees, Stamp duty
**Realistic fills:** Slippage model, volume-based fill limit (can't fill 100% of daily volume)
**Walk-forward validation:** Minimum 20% out-of-sample data
**Benchmark comparison:** Compare strategy returns vs Nifty 50 buy-and-hold
**Overfitting protection:** Max 5 free parameters per strategy, forward test required
**Risk metrics:** Sharpe, Sortino, Calmar ratio, max drawdown, VaR, CAGR

## Phase 9 — Real Machine Learning Pipeline ✅ COMPLETE
**Stage 1 (done):** Rule-based scoring with SHAP-style explanations ✅
**Stage 2:** Classical ML — LightGBM classifier with SHAP explainability ✅
  - Feature store: RSI, MACD, EMA crossovers, ADX, ATR, volume ratios, pattern labels, sector strength
  - Target: next-N-day direction (binary or 3-class)
  - Walk-forward training: retrain monthly, out-of-sample evaluation
**Stage 3:** Ensemble — LightGBM + rule signal + sentiment
**Stage 4 (optional):** LSTM sequence model for regime detection
**Calibration:** Platt scaling or isotonic regression to calibrate probabilities
**Prediction archive:** Every prediction stored with features snapshot, outcome tracked after horizon
**False signal analysis:** Periodic analysis of wrong predictions with root cause

## Phase 10 — NLP News Sentiment Analysis ✅ COMPLETE
**NLP Implementation:** Real-time news scraping and NLP scoring (FinBERT/VADER) ✅
**Integration:** Sentiment badges on UI, gated by PRO tier ✅

## Phase 11 — Production Deployment (Docker + CI/CD) ✅ COMPLETE
**Containerization:** Full Docker Compose setup for frontend, backend, celery, db, redis ✅
**Builds:** Vite production build, FastAPI multi-worker runner ✅

## Phase 12 — Monetization/Subscriptions ✅ COMPLETE
**Tier System:** FREE vs PRO roles implemented in database and RBAC ✅
**Gating:** AI Score, NLP Sentiment, and Strategy Backtesting locked for FREE users ✅
**Checkout:** Mock upgrade flow on `/pricing` page, permanent PRO for admin ✅

---

## Out of Scope (Constitution Rule — Never Build These)
- Real brokerage order execution
- Real money handling
- Financial guarantees or investment advice
- Unexplained black-box AI outputs
- Global markets in Phase 1–9 (may be added in Phase 12+)
