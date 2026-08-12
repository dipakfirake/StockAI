# StockAI: Deep Technical Whitepaper & Mathematics Reference

This document serves as the absolute deep-dive reference for all formulas, machine learning parameters, APIs, and risk management systems utilized by the StockAI platform.

## 1. Mathematical Formulas & Technical Indicators
StockAI calculates over 30 technical indicators using a combination of the `ta` library and bespoke implementations tailored for accurate mathematical derivation.

### 1.1 Custom SuperTrend Algorithm
The SuperTrend is explicitly calculated in `backend/services/indicators.py` to identify trend direction and trailing stops.
*   **Multiplier:** `3.0`
*   **ATR Period:** `7`
*   **Formula:**
    *   $Basic Upper Band = (High + Low) / 2 + (Multiplier \times ATR)$
    *   $Basic Lower Band = (High + Low) / 2 - (Multiplier \times ATR)$
    *   The algorithm dynamically adjusts the final bands to ensure they never move against the trend (a trailing stop mechanism).

### 1.2 Mathematical Candlestick Pattern Recognition
Unlike basic threshold checks, StockAI uses strict mathematical bounds to detect candlestick patterns, avoiding false positives:
*   **Bullish/Bearish Engulfing:** The engulfing body must be `> 1.2x` the previous body.
*   **Hammer / Shooting Star:**
    *   The long wick must be $\ge 2.0 \times$ the body length.
    *   The opposite short wick must be $\le 15\%$ of the total candle range.
*   **Doji:** The candle body must be $\le 5\%$ of the total High-to-Low range.
*   **Institutional Order Blocks:** A massive volume footprint.
    *   Volume must be $> 150\%$ of the 20-period Simple Moving Average Volume.
    *   Candle body must be $> 1.5 \times$ the 14-period Average True Range (ATR).
    *   Candle body must be $> 3.0 \times$ the previous candle's body.

### 1.3 Standard Indicators (Computed via `ta`)
*   **RSI:** 14-period standard Relative Strength Index.
*   **MACD:** Fast = 12, Slow = 26, Signal = 9.
*   **Bollinger Bands:** 20-period SMA, 2 Standard Deviations.
*   **EMAs:** 9, 21, 50, 200 periods.
*   **ADX (Average Directional Index):** 14 periods.
*   **VWAP (Volume Weighted Average Price):** Cumulative $\frac{(High + Low + Close) / 3 \times Volume}{\text{Cumulative Volume}}$.
*   **Ichimoku Cloud:** Base Line (Kijun-Sen), Conversion Line (Tenkan-Sen), and Senkou Spans A & B calculated over 9, 26, and 52 periods.

---

## 2. Machine Learning & Predictive Engine

The AI predictive engine (`ai_engine.py` / `ml.py`) evaluates the real-time calculated technical parameters.

### 2.1 Model Architecture (LightGBM)
*   The system uses **LightGBM (Gradient Boosting)** trained on historical OHLCV and technical feature matrices.
*   It outputs a **softmax probability distribution** across three classes: `BUY`, `HOLD`, `SELL`.
*   **SHAP (SHapley Additive exPlanations):** The backend actively calculates the marginal contribution of every single indicator to the final score (e.g., "RSI being at 25 contributed +0.14 to the BUY probability").

### 2.2 NLP News Sentiment Engine (`nlp_engine.py`)
StockAI consumes news headlines and runs Natural Language Processing (NLP) to overlay fundamental sentiment onto the technical score.
*   **VADER Sentiment:** Uses the VADER lexicons, upgraded with custom financial dictionaries.
    *   *Custom Lexicon Weights:* `bullish (+2.0)`, `bearish (-2.0)`, `surge (+1.5)`, `plunge (-1.5)`, `bankruptcy (-3.0)`.
*   **Corporate Event Overlay:** 
    *   If a positive dividend event is detected, the compound score is artificially lifted by $+0.15$.
    *   If an impending earnings report is within 14 days, the score is multiplied by $0.8$ (dampened) to account for implied volatility/uncertainty.

---

## 3. Risk Management & Analysis (`risk_analysis.py`)

Financial risk is heavily quantified to prevent reckless paper trading strategies and properly classify asset safety.

### 3.1 Historical 95% Value at Risk (VaR)
*   **Mathematical Concept:** Measures the worst expected loss over a specific timeframe at a 95% confidence interval.
*   **Implementation:** Calculated as the 5th percentile of historical daily returns (`np.percentile(returns, 5)`). If the VaR is $-2.5\%$, it implies that 95% of the time, the stock will *not* lose more than $2.5\%$ in a single day.
*   **Risk Level Classification:**
    *   `LOW RISK`: $VaR_{95\%} < 1.5\%$
    *   `MEDIUM RISK`: $VaR_{95\%}$ between $1.5\%$ and $3.0\%$
    *   `HIGH RISK`: $VaR_{95\%} \ge 3.0\%$

### 3.2 Sharpe Ratio & Volatility
*   **Annualized Volatility:** The standard deviation of daily returns multiplied by $\sqrt{252}$ (trading days in a year).
*   **Downside Volatility:** Standard deviation of strictly negative returns, measuring true adverse risk.
*   **Sharpe Ratio:** $\frac{\text{Annualized Return} - \text{Risk-Free Rate (Assumed 5\%)}}{\text{Annualized Volatility}}$.
*   **Max Drawdown:** Continuous measurement of the deepest trough relative to the highest historical peak (calculating the maximum pain a holder would experience).

---

## 4. Fundamental Analysis & Intelligence (`india_intelligence.py`)

The platform relies on `yfinance` to parse fundamental data, standardizing it for the Indian market context:
*   **Valuation Ratios:** PE Ratio, Forward PE, Price-to-Book (PB).
*   **Profitability Metrics:** Return on Equity (ROE), Return on Assets (ROA).
*   **Liquidity & Debt:** Debt-to-Equity Ratio, Current Ratio.
*   **Income:** Total Revenue, Revenue Growth (YoY), Dividend Yield.

---

## 5. Complete API Reference

Below is the exhaustive list of all REST and WebSocket APIs implemented across the backend modules. All protected routes require a JWT Bearer Token.

### 5.1 Watchlist APIs (`/api/watchlist`)
*   `GET /api/watchlist` - Retrieves the user's customized watchlist with real-time quote updates.
*   `POST /api/watchlist` - Adds a new symbol. Payload: `{"symbol": "ITC.NS"}`
*   `DELETE /api/watchlist/{symbol}` - Removes a symbol from the watchlist.

### 5.2 Stock Analysis APIs (`/api/stocks`)
*   `GET /api/stocks/{symbol}/quote` - Live LTP, Volume, Day High/Low.
*   `GET /api/stocks/{symbol}/candles` - Historical OHLCV data for charts.
*   `GET /api/stocks/{symbol}/indicators` - Raw computed TA values.
*   `GET /api/stocks/{symbol}/signals` - Rule-based entry/exit signals.
*   `GET /api/stocks/{symbol}/ai-score` - LightGBM predictions & SHAP explanations.
*   `GET /api/stocks/{symbol}/info` - Fundamental balance sheet metrics.
*   `GET /api/stocks/{symbol}/patterns` - Detected mathematical candlestick patterns.
*   `GET /api/stocks/search` - Autocomplete functionality for company names.

### 5.3 Market & Macro APIs (`/api/market`)
*   `GET /api/market/indices` - Global and Indian indices overview (NIFTY50, BANKNIFTY).
*   `GET /api/market/heatmap` - Treemap data based on sector performance.
*   `GET /api/market/options/{symbol}` - Full options chain with Greeks (Delta, Theta).
*   `GET /api/market/vix` - Implied Volatility Index.
*   `GET /api/market/corporate-actions/{symbol}` - Dividends, splits, earnings calendar.
*   `GET /api/market/screener` & `/api/market/bulk-screener` - Multi-symbol filtering.

### 5.4 Paper Trading APIs (`/api/paper_trading`)
*   `GET /api/paper_trading` - Lists all open/closed paper trades.
*   `POST /api/paper_trading` - Place an order. Payload: `{"symbol": "TCS.NS", "quantity": 10, "direction": "LONG", "order_type": "MARKET"}`
*   `PUT /api/paper_trading/{trade_id}/close` - Immediately squares off an open position.

### 5.5 Portfolio & Backtesting APIs
*   `GET /api/portfolio` - Aggregate Mark-to-Market (MTM) calculations and historic P&L.
*   `GET /api/backtesting/strategies` - Lists available walk-forward algorithms.
*   `POST /api/backtesting/run` - Executes a backtest simulation. Payload includes strategy, symbol, and timeframe.
*   `GET /api/backtesting/{backtest_id}/results` - Returns Sharpe ratio, equity curve, and max drawdown.

### 5.6 Settings, Alerts & Notifications
*   `GET /api/alerts` & `POST /api/alerts` - Manage price and indicator trigger alarms.
*   `DELETE /api/alerts/{alert_id}` & `PUT /api/alerts/{alert_id}/deactivate`
*   `GET /api/settings` & `PUT /api/settings` - Global app config (slippage margins, fees).
*   `GET /api/preferences` & `PUT /api/preferences` - User-specific UI settings (Dark mode, default charts).
*   `GET /api/notifications` & `POST /api/notifications/{id}/read` - In-app notification center.

### 5.7 Authentication & WebSockets
*   `POST /api/auth/register` & `POST /api/auth/login` - JWT generation.
*   `WS /ws?token={jwt}` - Bidirectional WebSocket for real-time price streaming, live AI alerts, and trade execution confirmations.

---

## 6. Frontend Components (`/frontend/src/`)
*   **`ChartPage.tsx`**: Integrates `lightweight-charts` for Heikin Ashi, Candlestick rendering. Contains dynamic drawing engines (Trendlines).
*   **`StockSearchBox.tsx` & `WatchlistSidebar.tsx`**: Reusable component overlays for symbol tracking and immediate routing.
*   **`AIAssistantWidget.tsx`**: Extracts conversational intents to lookup prices or summarize news natively within the app.
*   **`ScannerPage.tsx` & `HeatmapPage.tsx`**: Displays macroeconomic trends and multi-symbol filtering.

---

## 7. Next-Phase Architecture (Upcoming)
1. **Asynchronous Pre-computation (Lazy Loading Support):** Migrating indicator calculation strictly to Celery workers on ingest, allowing the frontend to lazy-load massive datasets (infinite scroll) without triggering realtime CPU bottlenecks.
2. **Options Margin Engine:** Implementing a SPAN/Exposure margin calculator within `paper_trading.py` to allow for naked option selling simulations.

---

## 8. How The System Works: The Complete Lifecycle

This section details the step-by-step operational flow of the StockAI platform, from raw market data ingestion to the moment a user places a simulated trade.

### 8.1 The Ingestion Phase (Background Data Gathering)
1. **Trigger:** The system runs background Celery tasks or responds to an active user requesting a chart (e.g., opening `TCS.NS`).
2. **Data Fetching:** The backend `market_data.py` service reaches out to `yfinance` or scrapes the NSE directly. It downloads up to 10 years of raw OHLCV (Open, High, Low, Close, Volume) data.
3. **Data Caching:** To avoid being rate-limited or IP-banned by the exchanges, this massive block of data is immediately saved into Redis. For the next 15 minutes, any other user requesting `TCS.NS` gets instantaneous data from the cache.

### 8.2 The Processing Phase (Mathematics & Logic)
Once the raw data is in memory, the backend passes it through a gauntlet of engines:
1. **Technical Calculation:** `indicators.py` runs mathematically intense loops across all 1000+ data points, attaching exact values for RSI, MACD, EMAs, and calculating the Custom SuperTrend bands for every single day in history.
2. **Pattern Recognition:** `advanced_indicators.py` scans the recent candles to spot rigid mathematical configurations like Bullish Engulfing or Institutional Order Blocks.
3. **Risk Profiling:** `risk_analysis.py` analyzes the mathematical volatility of the closing prices over the last year to calculate the 95% Value at Risk (VaR), assigning a definitive `LOW`, `MEDIUM`, or `HIGH` risk label.

### 8.3 The AI & Sentiment Phase (Machine Learning)
With the mathematical foundation built, the AI steps in to interpret it:
1. **ML Scoring:** The `ml.py` engine feeds the 30+ calculated technical indicators into a pre-trained LightGBM Machine Learning model. The model looks at historical patterns and spits out a probability distribution (e.g., 65% chance the stock goes up, meaning `BUY`).
2. **SHAP Explanation:** The AI also outputs a SHAP value breakdown, which acts as the "reasoning." It tells the system *exactly which indicator* caused the AI to say `BUY` (e.g., "The MACD crossover provided +20% confidence").
3. **NLP Sentiment:** Simultaneously, `nlp_engine.py` reads the latest news headlines for the company, runs them through the VADER sentiment dictionary, and adjusts the overall mood (e.g., downgrading confidence if an earnings report is due tomorrow).

### 8.4 The Presentation Phase (User Interface)
The backend bundles the raw candles, the 30+ technical indicators, the Risk Profile, the AI Score, and the News Sentiment into a single JSON response and sends it to the Frontend.
1. **Rendering:** React and `lightweight-charts` instantly paint the candlestick chart at 60 frames per second.
2. **Overlays:** The user toggles "Indicators," and the frontend instantly draws the MACD and EMAs without any lag, because the backend already did the math.
3. **The Scorecard:** The right-hand sidebar displays the AI's `BUY/HOLD/SELL` score ring and the exact SHAP explanations.

### 8.5 The Execution Phase (Paper Trading)
The user decides they agree with the AI's `BUY` rating and clicks the 1-Click Paper Trade button.
1. **Validation:** The frontend sends a `POST /api/paper_trading` request. The backend checks if the user has enough virtual cash in their portfolio.
2. **Transaction:** The backend locks in the trade at the exact live market price (LTP). It deducts a simulated Brokerage Fee and Securities Transaction Tax (STT) to make it realistic.
3. **Tracking & Auto-Square-Off:** The trade is saved to the PostgreSQL database. If it is an Intraday trade, the system monitors it. At exactly 3:20 PM IST, a Celery worker automatically wakes up and force-closes the trade (square-off), finalizing the Profit/Loss for the day.
