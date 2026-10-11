# Product Requirements Document (PRD) — StockAI

**Product Name:** StockAI — Advanced Indian Equity Research & Algorithmic Trading Platform  
**Repository:** `dipakfirake/StockAI`  
**Workspace:** `D:\Stock Prediction System`  
**Target Environment:** Python 3.11.5 (FastAPI), React 18 + TypeScript + Vite, Neon Serverless PostgreSQL, Render.com (Backend), Vercel (Frontend).  

---

## 1. System Overview & Architecture

StockAI is a high-performance full-stack market intelligence and paper-trading platform engineered for Indian equities (NSE & BSE). It combines real-time broker market feeds (Fyers v3), deep historical analytics, Smart Money Concepts (SMC/FVG), institutional order block tracking, multi-cap LightGBM machine learning models, and automated trading daemons.

### Verification Commands
Before marking any task complete in this PRD, the autonomous agent must execute and pass:
- **Backend Tests:**  
  `pytest backend/tests/test_indicators.py backend/tests/test_signals.py backend/tests/test_risk_analysis.py backend/tests/test_options_engine.py backend/tests/test_market_data.py`
- **Frontend Linter:**  
  `cd frontend && npm run lint`
- **Frontend Production Build:**  
  `cd frontend && npm run build`

---

## 2. Completed Milestones (Archive / Verified)

The following core modules are implemented, tested, and verified green in CI:

- [x] **EPIC-01: Real-time Market Data & Ingestion Engine**
  - [x] Official `fyers-apiv3` SDK integration with automatic token refreshing (`generate_fyers_token.bat`).
  - [x] Zero-downtime dual-listed symbol normalization (`.NS` / `.BO` / `NSE:SYMBOL-EQ`).
  - [x] High-speed batch quote engine (`fetch_quotes_bulk`) with under 300ms parallel batching.
  - [x] In-memory HTTP 429 cooldown circuit breaker preventing API rate-limit starvation.
  - [x] Real-time tick streaming over WebSockets (`backend/api/websocket.py`) updating UI wicks and indicators every second.

- [x] **EPIC-02: Quantitative Analytics & Technical Indicators**
  - [x] Over 30 technical indicators: Custom SuperTrend (ATR 7, Multiplier 3.0), RSI, MACD, Bollinger Bands, Ichimoku Cloud, ATR, VWAP, EMA (9/21/50/200).
  - [x] Mathematical candlestick pattern recognition (Bullish/Bearish Engulfing, Hammer, Shooting Star, Doji, Institutional Order Blocks).
  - [x] Historical 95% Value at Risk (VaR), Sharpe Ratio, Maximum Drawdown, and Annualized Volatility analysis in `risk_analysis.py`.
  - [x] Multi-strategy backtesting engine (`rsi_mean_reversion`, `ema_crossover`, `macd_signal`, `ai_machine_learning`) with ATR trailing stop loss.

- [x] **EPIC-03: Machine Learning & NLP Sentiment**
  - [x] Walk-forward validated LightGBM multi-cap classification models (`lgb_model_largecap.txt`, `lgb_model_smallcap.txt`) predicting BUY / HOLD / SELL with confidence scores.
  - [x] SHAP explanation engine calculating indicator marginal contributions.
  - [x] Financial VADER NLP sentiment engine parsing live news headlines and corporate event overlays.

- [x] **EPIC-04: Institutional Smart Money Concepts (SMC) & Auto-Trader**
  - [x] Institutional Liquidity Hunter (`backend/services/institutional_hunter.py`) scanning 60-day daily candles for Fair Value Gaps (FVG > 0.3%).
  - [x] Confluence grading (A+ to C) combining RSI, Volume spikes, and EMA21 proximity.
  - [x] Full trade plan generator (Entry, Stop Loss, Target, R:R ratio, Potential Profit %).
  - [x] Background Auto-Trader daemon (`backend/tasks/auto_trader.py`) with master kill switch in `backend/api/settings.py` and dual-mode (live order execution vs. broadcast WebSocket toasts).
  - [x] Pre-Market SMC UI (`frontend/src/pages/SMCWatchlist.tsx`) and Settings toggle UI (`SettingsPage.tsx`).

- [x] **EPIC-05: Database & Cloud Infrastructure Setup**
  - [x] Neon Serverless PostgreSQL connection with `postgresql+asyncpg://` compatibility and 13 production tables provisioned.
  - [x] GitHub Actions CI workflow pinned to Python 3.11 with `libgomp1` and strict lint/test validations.
  - [x] Render.com blueprint (`render.yaml`) configured for free 24/7 web service deployment.

---

## 3. Active Tasks & Backlog (To Be Executed)

Autonomous coding loops (Ralph Loop) should select tasks sequentially from this section:

### User Story 1: Production Cloud Deployment & API Proxy Verification
**Goal:** Finalize the cloud connectivity between the Vercel frontend, Render backend, and Neon PostgreSQL database.

- [x] **TASK-101: Validate Render Blueprint Configuration**
  - **File:** `render.yaml`
  - **Description:** Verify `render.yaml` has correct environment declarations (`DATABASE_URL`, `SECRET_KEY`, `PYTHON_VERSION: 3.11.5`), proper health check path `/api/market/indices`, and build command `pip install -r backend/requirements.txt`.
  - **Verification:** Ensure `render.yaml` passes syntax validation and contains no hardcoded secrets.

- [x] **TASK-102: Configure Frontend API Routing for Cloud Backend**
  - **Files:** `frontend/vercel.json`, `vercel.json`
  - **Description:** Ensure API rewrite rules in `frontend/vercel.json` and root `vercel.json` allow dynamic backend routing via `VITE_API_URL` or standard proxy rewrite when deployed to Vercel.
  - **Verification:** Run `cd frontend && npm run build` without error.

---

### User Story 2: Volume Profile Horizontal Histogram
**Goal:** Display institutional volume distribution by price level on the main chart to identify high-volume nodes (POC - Point of Control) and low-volume rejection areas.

- [x] **TASK-201: Backend Volume Profile Calculation Service**
  - **File:** `backend/services/indicators.py` or new `backend/services/volume_profile.py`
  - **Description:** Create an endpoint or service function that groups historical volume into $N$ price bins between the chart High and Low for the selected period. Compute Point of Control (POC), Value Area High (VAH), and Value Area Low (VAL) containing 70% of total traded volume.
  - **Verification:** Unit test with mock OHLCV candles confirming correct bin allocation and POC calculation.

- [x] **TASK-202: Frontend Volume Profile Visual Overlay**
  - **File:** `frontend/src/pages/ChartPage.tsx`
  - **Description:** Add a toggleable Volume Profile sidebar/histogram on the right side of the Lightweight Chart showing horizontal bars for buy/sell volume at each price level, highlighting POC with a prominent line.
  - **Verification:** `cd frontend && npm run build` passes; verify chart renders with toggle active.

---

### User Story 3: Export Chart & Technical Insight to PDF
**Goal:** Enable traders and analysts to download a complete 1-page institutional report summarizing technical indicators, AI predictions, and chart snapshots.

- [x] **TASK-301: Frontend Report Generation Component**
  - **File:** `frontend/src/pages/ChartPage.tsx` (or new modal component `ExportReportModal.tsx`)
  - **Description:** Add an "Export PDF Report" button in the chart toolbar. When clicked, generate a formatted document containing:
    - Symbol details, current LTP, and Day Range.
    - AI Model prediction score & confidence ring.
    - Key Indicator summary table (RSI, MACD, SuperTrend, Support/Resistance).
    - Risk Analysis metrics (VaR 95%, Sharpe Ratio, Volatility).
    - Lightweight Charts screenshot or SVG chart snapshot.
  - **Verification:** `npm run build` succeeds; PDF generation triggers without browser console errors.

---

### User Story 4: Pattern-Based Alert Notifications
**Goal:** Allow users to set automated alerts triggered when specific candlestick patterns or SMC Order Blocks form on their watched stocks.

- [x] **TASK-401: Backend Candlestick Pattern Alert Trigger**
  - **Files:** `backend/api/alerts.py`, `backend/services/signals.py`, `backend/tasks/auto_trader.py`
  - **Description:** Extend the alert evaluation service to support `alert_type="PATTERN"` (e.g., `HAMMER`, `BULLISH_ENGULFING`, `ORDER_BLOCK`). When detected during background polling, trigger the user notification and broadcast WebSocket toast.
  - **Verification:** Pytest test case simulating candle data forming a Bullish Engulfing pattern and verifying alert firing.

- [x] **TASK-402: Frontend Pattern Alert Form**
  - **File:** `frontend/src/pages/AlertsPage.tsx`
  - **Description:** Add pattern selection dropdown to the Create Alert modal so users can select specific patterns to monitor in addition to price/RSI thresholds.
  - **Verification:** `cd frontend && npm run build` and `npm run lint` pass.

---

### User Story 5: Anchored VWAP Overlay
**Goal:** Allow traders to anchor the Volume Weighted Average Price (AVWAP) to a significant market event (such as earnings release date, 52-week high, or swing low).

- [x] **TASK-501: Backend Anchored VWAP Indicator**
  - **File:** `backend/services/indicators.py`
  - **Description:** Implement `calculate_anchored_vwap(df, anchor_date)` which computes cumulative $(Price \times Volume) / Cumulative\ Volume$ starting exclusively from `anchor_date` onward.
  - **Verification:** Unit test asserting AVWAP equals normal VWAP when anchored at index 0, and calculates correctly from midpoint.

- [x] **TASK-502: Frontend Chart Click-to-Anchor Interaction**
  - **File:** `frontend/src/pages/ChartPage.tsx`
  - **Description:** Add an "Anchor VWAP" tool to the drawing toolbar. Clicking a candle on the chart sets `anchorDate` and dynamically adds the AVWAP line series.
  - **Verification:** `cd frontend && npm run build` passes cleanly.

---

## 4. Ralph Loop Execution Protocol

When executing with the Ralph Loop:
1. **Pick the first unchecked task (`- [ ]`)** in Section 3.
2. **Review existing codebase** for conventions, types, and reusable utilities before editing.
3. **Never touch or inspect `.env`**.
4. **Implement the code changes** with minimal blast radius.
5. **Run the required verification commands**:
   - Backend: `pytest backend/tests/...`
   - Frontend: `npm run lint` and `npm run build`
6. **Mark task complete (`- [x]`)** in this `PRD.md`.
7. **Append an entry in `progress.txt`** detailing the completed work, verified test results, and timestamp.
8. **End session cleanly** for next iteration.
