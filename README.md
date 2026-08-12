# StockAI: Advanced Market Intelligence & Paper Trading Platform 📈🤖

![StockAI Dashboard](https://img.shields.io/badge/Status-Active-success) ![License](https://img.shields.io/badge/License-MIT-blue) ![Python](https://img.shields.io/badge/Python-3.12-blue) ![React](https://img.shields.io/badge/React-18-blue) ![Docker](https://img.shields.io/badge/Docker-Ready-blue)

StockAI is a comprehensive, full-stack AI-driven stock research and paper trading platform built for the Indian stock market (NSE/BSE). It combines real-time technical analysis, proprietary machine learning models for predictive scoring, an interactive AI Chat Assistant, and a robust walk-forward backtesting engine.

---

## ✨ Key Features

### 🧠 Artificial Intelligence & Machine Learning
- **AI Scoring Engine:** Uses LightGBM and SHAP values to evaluate 30+ technical indicators and generate a real-time `Buy`, `Hold`, or `Sell` score with confidence metrics.
- **NLP Chat Assistant:** An integrated chatbot that automatically extracts company names from conversational text (e.g., *"Should I buy Reliance?"*), looks up real-time data, and synthesizes a comprehensive technical analysis report detailing primary drivers and support/resistance levels.
- **Automated Support & Resistance:** Dynamically detects local minima and maxima to project key trading levels directly on the chart.

### 📊 Advanced Charting & Technicals
- **TradingView-style Charts:** High-performance candlestick charts powered by Lightweight Charts.
- **Dynamic Indicators:** Real-time calculation of RSI, MACD, EMAs (9, 21), VWAP, SuperTrend, and Bollinger Bands.
- **Heikin Ashi:** Seamless one-click toggle to filter out market noise using Heikin Ashi candles.

### 💼 Paper Trading & Portfolio Management
- **Zero-Risk Trading:** Practice Intraday trading with realistic execution.
- **Advanced Order Types:** Support for Market, Limit, and Stop-Loss (SL) orders.
- **Risk Management:** Dynamic margin requirements, position sizing, and automated 15:20 IST square-off (via Celery Cron jobs).
- **Tax Simulation:** Accurate accounting for simulated STT, brokerages, and exchange transaction charges.

### 🧪 Backtesting Engine
- **Walk-forward Simulation:** Test built-in strategies (RSI Mean Reversion, EMA Crossover, MACD Signal) against historical OHLCV data.
- **Realistic Execution:** Accounts for slippage and commission (dynamically configurable via the Settings panel).
- **Deep Metrics:** Calculates Total Return, Sharpe Ratio, Max Drawdown, Win Rate, and Profit Factors.

### 🔔 Real-time Alerts & Scanners
- **Custom Triggers:** Set alerts for Price levels, Indicator crossovers (e.g., RSI < 30, MACD crosses up), and Candlestick patterns (e.g., Bullish Engulfing).
- **Multi-channel Delivery:** WebSocket-powered in-app notifications and SMTP email delivery (strictly reserved for HIGH priority alerts to reduce noise).

---

## 🛠️ Technology Stack

**Backend:**
- **Framework:** FastAPI (Python 3.12)
- **Database:** PostgreSQL (with SQLAlchemy ORM & Alembic)
- **Caching & Queues:** Redis & Celery
- **Data Ingestion:** `yfinance` & Custom NSE Web Scrapers
- **Machine Learning:** `scikit-learn`, `LightGBM`, `shap`, `ta`

**Frontend:**
- **Framework:** React 18 + Vite (TypeScript)
- **Styling:** Custom CSS + Lucide Icons
- **Charting:** `lightweight-charts`
- **Routing:** React Router v6

**Infrastructure:**
- **Containerization:** Docker & Docker Compose (Multi-stage builds)

---

## 🚀 Quick Start (Docker)

The absolute easiest way to get StockAI running locally is via Docker Compose.

### Prerequisites
- Docker Engine & Docker Compose installed.

### Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/dipakfirake/StockAI.git
   cd StockAI
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env if necessary, though defaults work out of the box for local dev
   ```

3. **Start the application:**
   ```bash
   docker compose up --build -d
   ```

4. **Initialize the Database & Seed Data:**
   *(Run this once the backend container is fully up and running)*
   ```bash
   # Create tables via Alembic
   docker compose exec backend alembic upgrade head
   
   # Seed default admin user (admin@stockai.com / admin)
   docker compose exec backend python -m backend.seed_admin
   
   # Seed popular Nifty50/Midcap stocks for the search autocomplete
   docker compose exec backend python -m backend.seed_stocks
   ```

5. **Access the Application:**
   - **Frontend:** http://localhost:5173
   - **Backend API Docs (Swagger):** http://localhost:8000/docs
   
   *Login with:* `admin@stockai.com` / `admin`

## 🧪 Frontend E2E Testing

The frontend includes Playwright end-to-end tests in `frontend/e2e`. On Windows, the Playwright config uses `npm.cmd` to start the Vite dev server correctly.

1. Open a terminal in the `frontend/` folder.
2. Install dependencies if needed:
   ```bash
   npm.cmd install
   ```
3. Start the backend server in a separate terminal if it is not already running:
   ```bash
   cd ..\backend
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```
4. Run the Playwright suite:
   ```bash
   cd ..\frontend
   npm.cmd run test:e2e
   ```
5. View the report after tests complete:
   ```bash
   frontend\playwright-report\index.html
   ```

> The E2E tests require the backend API to be available at `http://127.0.0.1:8000` and the frontend dev server at `http://localhost:5173`.

---

## 📂 Project Architecture

```text
StockAI/
├── backend/                  # FastAPI Application
│   ├── api/                  # REST & WebSocket Route Handlers
│   ├── core/                 # Database config, Auth, Settings
│   ├── data/                 # Market data ingestion & scrapers
│   ├── models/               # SQLAlchemy ORM Models
│   ├── services/             # Core business logic (AI, Indicators, Backtesting)
│   ├── tasks/                # Celery background tasks (Alerts, Auto-square-off)
│   └── tests/                # Pytest suites
├── frontend/                 # React Application
│   ├── src/
│   │   ├── components/       # Reusable UI components (NavBar, SearchBox, Chat Widget)
│   │   ├── pages/            # Main views (Dashboard, Charts, Portfolio, Settings)
│   │   └── services/         # Axios API clients & WebSocket handlers
├── docker-compose.yml        # Orchestration
└── .env                      # Environment Variables
```

---

## ⚙️ Configuration & Customization

StockAI uses a **Dynamic Configuration System**. Instead of editing code to change trading fees or backtester slippage, simply log in as an Admin, navigate to the **Settings** page in the UI, and modify global parameters (like `default_slippage` and `default_commission`). These values are instantly fetched from the database by the backend engines.

---

## 📝 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

*Disclaimer: StockAI is built for educational, research, and paper trading purposes only. It is not designed to connect to real brokerages or handle real money. Always do your own research before making financial decisions.*
