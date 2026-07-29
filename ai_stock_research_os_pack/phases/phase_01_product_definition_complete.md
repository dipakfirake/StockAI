# Phase 1 — Product Definition (Complete)

## Goal
Define exactly what the platform is, who it is for, and what it will not do.

## Status: ✅ COMPLETE

---

## Problem Statement

Most retail investors in India have access to either basic charting tools or full brokerage platforms that mix execution with research. There is no open-source, India-first platform that combines:
- Deep technical analysis with explainable AI
- Paper trading for safe skill-building
- Backtesting to validate strategies
- Market regime detection
- Smart alerts without broker dependency

This platform fills that gap.

---

## User Personas

### 1. Beginner Retail Investor
- Wants to learn technical analysis safely
- Needs explainable signals (not just BUY/SELL)
- Uses paper trading to practice
- Risk: overwhelmed by too many indicators

### 2. Swing Trader
- Holds positions for 2–10 days
- Needs daily alerts for breakouts/breakdowns
- Needs sector rotation signals
- Uses backtesting to validate swing strategies

### 3. Long-term Investor
- Focuses on quality stocks over months/years
- Needs fundamental + macro context
- Uses portfolio analytics to track allocation

### 4. Quantitative Researcher
- Builds and tests strategies systematically
- Needs raw data access, feature engineering
- Uses backtesting with realistic assumptions
- Needs AI scoring with confidence intervals

### 5. Market Analyst
- Covers multiple stocks/sectors
- Needs scanners for pattern detection
- Needs exportable reports

### 6. Student / Learner
- Uses paper trading as a simulator
- Needs educational tooltips
- Needs a non-intimidating UI

---

## Core Use Cases

1. Search for a stock and see live quote + chart
2. Apply technical indicators to a chart
3. Set a price/indicator alert and receive notification
4. Run a stock scanner (e.g., RSI < 30 for all Nifty 50 stocks)
5. Place a simulated paper trade and track PnL
6. Backtest a strategy on historical data
7. View AI buy/hold/sell score with explanation
8. View portfolio allocation and performance
9. Detect current market regime (bull, bear, sideways)
10. View sector heatmap and rotation signals

---

## Non-Goals

- No real brokerage execution
- No financial advice guarantees
- No unexplained black-box predictions
- No user funds management
- No broker API integration (Phase 1/2)
- No global markets (US, EU) in MVP
- No social trading / copy trading in MVP

---

## MVP Scope (Day One)

| Feature | Priority | Notes |
|---------|----------|-------|
| Stock search + quote | P0 | NSE/BSE symbols |
| OHLCV chart | P0 | Candlestick + volume |
| Technical indicators | P0 | RSI, MACD, EMA, Bollinger |
| Watchlist | P0 | Add/remove stocks |
| Price alert | P0 | Email or in-app notification |
| Paper trade | P0 | BUY/SELL simulation |
| Backtest (simple) | P1 | Single strategy, single symbol |
| AI score (rule-based) | P1 | BUY/HOLD/SELL with reason |
| Portfolio view | P1 | Summarize paper trades |
| Market regime | P2 | Bull/Bear/Sideways label |
| Scanner | P2 | Rule-based screen |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Data freshness | ≤ 15 min delay (MVP), real-time later |
| API response time | < 200ms for quotes |
| Chart load time | < 1 second for daily candles |
| Alert delivery | < 30 seconds after trigger |
| Backtest accuracy | Slippage and brokerage included |
| AI score accuracy | > 60% directional accuracy (walk-forward) |
| Explainability | Every score has ≥ 3 feature reasons |

---

## Exit Criteria ✅
- Product scope is clear ✅
- MVP is defined ✅
- User personas documented ✅
- Success metrics defined ✅
- Phase 2 can begin ✅
