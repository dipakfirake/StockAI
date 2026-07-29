# AI Stock Research System - TODO

## Completed (Phases 1-7)
- [x] Phase 1: Core Foundation & Setup (FastAPI + React)
- [x] Phase 2: User Authentication & Basic Database (TimescaleDB)
- [x] Phase 3: Watchlist Management
- [x] Phase 4: Market Data Layer (NSE Scraper, Delivery, FII/DII)
- [x] Phase 5: Charts & Indicators (Lightweight Charts, RSI, MACD, Volume, HA)
- [x] Phase 6: Alerts & Scanners (SuperTrend, BB Squeeze, Nifty 50 Scanner)
- [x] Integrate AI Scores using SHAP logic
- [x] Setup Celery tasks for alert evaluation
- [x] Phase 7: Advanced Paper Trading System
  - [x] Support Limit and Stop-Loss Orders (MARKET, LIMIT, SL order types)
  - [x] Real-time Portfolio P&L Tracking (incl. STT taxes)
  - [x] Trade History and Performance Metrics (with realized/unrealized PnL)
  - [x] Short Selling Support (INTRADAY only - DELIVERY blocked)
  - [x] Auto-Square Off at 15:20 IST (Celery CRON job)
  - [x] Background order monitoring every 60 seconds (Celery worker)

## Completed (Phases 8-12)
- [x] Phase 8: Backtesting Engine
- [x] Phase 9: Real Machine Learning Pipeline
- [x] Phase 10: NLP News Sentiment Analysis
- [x] Phase 11: Production Deployment (Docker + CI/CD)
- [x] Phase 12: Monetization/Subscriptions (Stripe/Mock)

## Next Up
- `[x]` Bug fixes & Polish (Backtester JSON errors, SMTP notification tuning)
- [ ] User Feedback loop implementation
- [ ] Expand Backtesting strategies
