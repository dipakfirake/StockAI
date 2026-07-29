# Project Constitution

## Project Identity
**Name:** AI Stock Research Platform
**Type:** Open-source, India-first, AI-powered investment research platform
**Version:** 0.1.0 (MVP Phase)
**License:** MIT

---

## Mission Statement
Build the world's most transparent, explainable, open-source, AI-powered investment research platform starting with the Indian stock market — helping every type of investor study stocks deeply, detect setups, simulate trades, and understand markets through data and explainable AI.

---

## Core Principles (Non-Negotiable)

### 1. Research Only — Never a Broker
- The platform MUST NOT execute real trades
- The platform MUST NOT connect to any broker's execution engine
- The platform MUST NOT handle real money in any form
- Paper trading is simulation ONLY — no real orders, no real fills

### 2. Explainability Over Black Boxes
- Every AI score MUST have a human-readable explanation
- Every signal MUST have a reason string
- Every prediction MUST include feature contributions (SHAP or equivalent)
- "Black box" outputs are strictly prohibited

### 3. Data Quality Before Model Complexity
- Data ingestion and validation must be stable before adding ML models
- Rule-based signals must be proven before adding ML signals
- ML signals must be proven before adding deep learning
- Walk-forward validation is mandatory for all backtests

### 4. India-First Design
- Market hours: 09:15–15:30 IST, Mon–Fri (NSE/BSE)
- Pre-open: 09:00–09:15 IST
- Closing session: 15:40–16:00 IST
- Market calendar: NSE holidays must be respected
- India VIX must be monitored as a regime signal
- RBI policy and budget announcements are first-class events
- Sector rotation follows Indian market behaviour
- Corporate actions (bonus, split, dividend, rights) must adjust historical data

### 5. Modular Architecture
- Each engine is independent: market data, indicators, signals, alerts, paper trading, backtesting, AI, portfolio
- Engines communicate through well-defined interfaces (service classes)
- Adding a new indicator or strategy must not require changes to unrelated modules
- Every module must be individually testable

### 6. Open-Source Readiness
- Code must be readable and documented
- No proprietary data sources in the core (yfinance, NSE website are acceptable)
- Contributors must be able to add indicators, strategies, scanners without deep knowledge of other modules
- All architectural decisions must be recorded in DECISION_LOG.md

### 7. Checkpoint Continuity
- Every session must end with updated checkpoint files
- Any AI tool (ChatGPT, Claude, Antigravity, etc.) must be able to resume from the checkpoint
- No completed work should ever be repeated or redesigned unless explicitly requested
- The DECISION_LOG.md is the final authority for all design conflicts

---

## Development Phases (Constitution-Level Commitments)

| Phase | Name | Status |
|-------|------|--------|
| 1 | Product Definition | ✅ Complete |
| 2 | MVP Design | ✅ Complete |
| 3 | System Architecture + Scaffold | ✅ Complete |
| 4 | Market Data Layer | 🔄 In Progress |
| 5 | Charts and Indicators | ⏳ Pending |
| 6 | Alerts and Scanners | ⏳ Pending |
| 7 | Paper Trading (advanced) | ⏳ Pending |
| 8 | Backtesting (advanced) | ⏳ Pending |
| 9 | AI/ML Engine | ⏳ Pending |
| 10 | India Intelligence | ⏳ Pending |
| 11 | Advanced Platform Features | ⏳ Pending |
| 12 | Scaling and Production | ⏳ Pending |

---

## Technology Choices (Constitution-Level — Do Not Change Without DECISION_LOG Entry)

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | FastAPI (Python 3.11) | 0.111+ |
| Frontend | React 18 + Vite + TypeScript | Latest |
| Database | PostgreSQL 15 + TimescaleDB | 15 / 2.x |
| Cache | Redis 7 | 7.x |
| Task Queue | Celery + Redis | 5.3+ |
| Charting | Lightweight Charts (TradingView OSS) | 4.x |
| State | Zustand | 4.x |
| ORM | SQLAlchemy 2.0 + Alembic | 2.0 |
| AI Phase 1 | Rule-based (Python) | — |
| AI Phase 2 | LightGBM + SHAP | Latest |
| AI Phase 3 | PyTorch LSTM (optional) | Latest |
| Containers | Docker Compose | 2.x |

---

## Quality Gates

Before any phase is marked complete:
1. All features in the phase are implemented
2. All relevant unit tests pass
3. All documentation is updated
4. PROJECT_CHECKPOINT.md is updated
5. DECISION_LOG.md has entries for any new decisions
6. No previously working feature is broken

---

## Conflict Resolution

If any two project documents conflict:
1. Latest entry in **DECISION_LOG.md** takes precedence
2. Then **PROJECT_CHECKPOINT.md**
3. Then **PROJECT_CONSTITUTION.md** (this file)
4. Then **MASTER_PROMPT_Stock_Research_Platform.md**
5. Then other docs

---

## What This Platform Aspires To Become

A combination of:
- **TradingView-style** charting and drawing tools
- **Chartink-style** stock screening and scanners
- **Screener.in-style** fundamental data access
- **AI research assistant** with explainable outputs
- **Paper trading simulator** with realistic fills
- **Strategy backtester** with walk-forward validation
- **Indian market intelligence engine** (RBI, FII/DII, sectors, breadth, India VIX)
- **Open-source contribution platform** for quant researchers
