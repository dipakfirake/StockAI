# Data Flow

## Overview

Data flows through four distinct pipelines:
1. **Ingestion pipeline** — raw market data → validated → stored in DB
2. **Query pipeline** — API request → cache → DB → response
3. **Alert pipeline** — Celery beat → evaluate rules → WebSocket push
4. **AI pipeline** — features → model → score + SHAP explanation

---

## 1. Ingestion Pipeline

```
yfinance / NSE scraper
        │
        ▼
DataValidation layer
  ├── Check OHLCV completeness
  ├── Check volume > 0
  ├── Check no future timestamps
  └── Check price continuity
        │
        ▼
PostgreSQL + TimescaleDB
  └── candles hypertable (symbol, timeframe, timestamp, open, high, low, close, volume)
        │
        ▼
Redis cache invalidation
  └── delete stale cached candles for symbol
```

**Trigger:** Celery beat task every 1 minute (during NSE market hours: 09:15–15:30 IST).
**Backfill:** On first startup, fetch last 2 years of daily candles for all watchlisted stocks.

---

## 2. Query Pipeline (API Request)

```
Frontend HTTP request
  GET /api/stocks/RELIANCE.NS/candles?timeframe=1d&limit=200
        │
        ▼
FastAPI router → service layer
        │
        ▼
Redis cache lookup (key: candles:RELIANCE.NS:1d)
  ├── HIT → return immediately (< 5ms)
  └── MISS ▼
        │
        ▼
TimescaleDB query
  SELECT * FROM candles WHERE symbol='RELIANCE.NS' AND timeframe='1d'
  ORDER BY timestamp DESC LIMIT 200
        │
        ▼
Indicator calculation (pandas-ta)
  ├── RSI, MACD, Bollinger Bands, EMA
  └── Attached to each candle row
        │
        ▼
Redis cache store (TTL: 60s for intraday, 3600s for daily)
        │
        ▼
JSON response to frontend
```

---

## 3. Alert Evaluation Pipeline

```
Celery beat (every 30 seconds)
        │
        ▼
Load all active alerts from DB
        │
        ▼
For each alert:
  ├── Fetch latest quote from Redis / yfinance
  ├── Evaluate condition (price > X, RSI < 30, etc.)
  ├── If triggered:
  │     ├── Mark alert as triggered in DB
  │     ├── Create Signal record
  │     └── Push via WebSocket to connected user
  └── If not triggered: skip
```

---

## 4. AI Scoring Pipeline

```
API request: GET /api/stocks/{symbol}/ai-score
        │
        ▼
FeatureBuilder
  ├── Load last N candles from DB
  ├── Compute indicators (RSI, MACD, EMA, ATR, ADX, Volume)
  ├── Compute derived features (trend strength, momentum score)
  └── Build feature vector
        │
        ▼
LightGBM model (or rule-based in MVP)
  ├── Predict: BUY / HOLD / SELL probability
  └── Output: {buy: 0.72, hold: 0.20, sell: 0.08}
        │
        ▼
SHAP explainer
  └── Top 5 feature contributions
        │
        ▼
Response:
  {
    "symbol": "RELIANCE.NS",
    "score": "BUY",
    "confidence": 0.72,
    "explanation": [
      {"feature": "RSI", "value": 28.4, "contribution": "+0.18", "reason": "RSI is oversold"},
      {"feature": "MACD", "value": "bullish_cross", "contribution": "+0.14", "reason": "MACD line crossed signal line upward"},
      ...
    ]
  }
```

---

## 5. Paper Trading Pipeline

```
User places paper trade (POST /api/paper-trades)
  │
  ▼
OrderSimulator
  ├── Validate symbol exists
  ├── Fetch current price from Redis / yfinance
  ├── Apply simulated slippage (0.1% default)
  ├── Apply brokerage commission (₹20 flat or 0.03%)
  ├── Create PaperTrade record (status: OPEN)
  └── Return order confirmation
        │
        ▼ (on exit)
User closes trade (PUT /api/paper-trades/{id}/close)
  ├── Fetch exit price
  ├── Calculate PnL: (exit - entry) × qty - commission
  ├── Update PaperTrade record (status: CLOSED)
  └── Update Portfolio metrics
```

---

## 6. Backtesting Pipeline

```
User submits backtest (POST /api/backtest/run)
  ├── Strategy definition (buy/sell rules)
  ├── Symbol
  ├── Date range
  └── Capital
        │
        ▼
Celery task (async)
  ├── Load historical candles from DB
  ├── Compute indicators for each bar
  ├── Simulate strategy signal-by-signal
  ├── Apply slippage + brokerage
  ├── Calculate metrics:
  │     ├── Total return
  │     ├── Sharpe ratio
  │     ├── Max drawdown
  │     ├── Win rate
  │     └── Number of trades
  └── Store results in DB
        │
        ▼
Frontend polls for results (GET /api/backtest/{id}/results)
```
