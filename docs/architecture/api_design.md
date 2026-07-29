# API Design

## Base URL
- Development: `http://localhost:8000/api`
- Production: `https://api.aistock.local/api`

## Authentication
All endpoints require `Authorization: Bearer <jwt_token>` header except `/api/auth/login` and `/api/auth/register`.

## Common Response Envelope
```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": {
    "timestamp": "2026-07-29T09:15:00+05:30",
    "request_id": "uuid"
  }
}
```

---

## Auth Endpoints

### POST /api/auth/register
```json
// Request
{ "email": "user@example.com", "password": "secure123", "name": "Ravi" }

// Response
{ "user_id": "uuid", "email": "user@example.com", "token": "jwt..." }
```

### POST /api/auth/login
```json
// Request
{ "email": "user@example.com", "password": "secure123" }

// Response
{ "token": "jwt...", "expires_in": 86400 }
```

---

## Stock Endpoints

### GET /api/stocks/search?q={query}
```json
// Response
{
  "results": [
    { "symbol": "RELIANCE.NS", "name": "Reliance Industries", "exchange": "NSE", "sector": "Energy" },
    { "symbol": "RELIANCE.BO", "name": "Reliance Industries", "exchange": "BSE", "sector": "Energy" }
  ]
}
```

### GET /api/stocks/{symbol}/quote
```json
// Response
{
  "symbol": "RELIANCE.NS",
  "name": "Reliance Industries",
  "price": 2847.50,
  "change": 32.15,
  "change_pct": 1.14,
  "volume": 4820341,
  "market_cap": 19250000000000,
  "52w_high": 3024.90,
  "52w_low": 2220.05,
  "timestamp": "2026-07-29T15:29:00+05:30"
}
```

### GET /api/stocks/{symbol}/candles?timeframe=1d&limit=200
```json
// timeframe: 1m, 5m, 15m, 30m, 1h, 1d, 1w
// Response
{
  "symbol": "RELIANCE.NS",
  "timeframe": "1d",
  "candles": [
    { "timestamp": "2026-07-29T00:00:00Z", "open": 2820.0, "high": 2855.0, "low": 2815.0, "close": 2847.5, "volume": 4820341 }
  ]
}
```

### GET /api/stocks/{symbol}/indicators?timeframe=1d
```json
// Response
{
  "symbol": "RELIANCE.NS",
  "timeframe": "1d",
  "indicators": {
    "rsi_14": 62.4,
    "macd": { "macd": 12.3, "signal": 8.7, "histogram": 3.6 },
    "bb": { "upper": 2890.0, "middle": 2820.0, "lower": 2750.0 },
    "ema_9": 2835.0, "ema_21": 2800.0, "ema_50": 2750.0, "ema_200": 2600.0,
    "sma_50": 2740.0, "sma_200": 2590.0,
    "atr_14": 45.2,
    "adx_14": 28.7
  }
}
```

### GET /api/stocks/{symbol}/signals
```json
// Response
{
  "symbol": "RELIANCE.NS",
  "signals": [
    {
      "type": "BUY",
      "strength": "STRONG",
      "reason": "RSI recovered from oversold zone. EMA9 crossed above EMA21. Volume surge detected.",
      "triggered_at": "2026-07-29T09:20:00+05:30",
      "indicators_used": ["RSI", "EMA9", "EMA21", "Volume"]
    }
  ]
}
```

### GET /api/stocks/{symbol}/ai-score
```json
// Response
{
  "symbol": "RELIANCE.NS",
  "score": "BUY",
  "probabilities": { "buy": 0.72, "hold": 0.20, "sell": 0.08 },
  "confidence": 0.72,
  "model": "rule_based_v1",
  "explanation": [
    { "feature": "rsi_14", "value": 28.4, "contribution": 0.18, "direction": "bullish", "reason": "RSI is in oversold territory — historically precedes a bounce" },
    { "feature": "macd_histogram", "value": 3.6, "contribution": 0.14, "direction": "bullish", "reason": "MACD histogram turned positive — momentum shifting bullish" },
    { "feature": "ema_crossover", "value": "golden_cross", "contribution": 0.12, "direction": "bullish", "reason": "EMA9 crossed above EMA21 — short-term trend is up" }
  ],
  "generated_at": "2026-07-29T15:30:00+05:30"
}
```

---

## Watchlist Endpoints

### GET /api/watchlist
```json
// Response
{ "stocks": [{ "symbol": "RELIANCE.NS", "name": "Reliance Industries", "price": 2847.5, "change_pct": 1.14 }] }
```

### POST /api/watchlist
```json
// Request
{ "symbol": "RELIANCE.NS" }
// Response
{ "added": true, "symbol": "RELIANCE.NS" }
```

### DELETE /api/watchlist/{symbol}
```json
{ "removed": true, "symbol": "RELIANCE.NS" }
```

---

## Alert Endpoints

### POST /api/alerts
```json
// Request
{
  "symbol": "RELIANCE.NS",
  "condition_type": "PRICE_ABOVE",  // PRICE_ABOVE, PRICE_BELOW, RSI_BELOW, RSI_ABOVE, MACD_CROSS_UP, MACD_CROSS_DOWN
  "condition_value": 2900.0,
  "message": "Reliance hit 2900!"
}
// Response
{ "alert_id": "uuid", "created": true }
```

### GET /api/alerts
```json
{ "alerts": [{ "alert_id": "uuid", "symbol": "RELIANCE.NS", "condition_type": "PRICE_ABOVE", "condition_value": 2900.0, "is_active": true, "triggered_at": null }] }
```

### DELETE /api/alerts/{alert_id}
```json
{ "deleted": true }
```

---

## Paper Trading Endpoints

### POST /api/paper-trades
```json
// Request
{ "symbol": "RELIANCE.NS", "direction": "BUY", "quantity": 10, "order_type": "MARKET" }
// Response
{ "trade_id": "uuid", "entry_price": 2848.35, "commission": 20.0, "status": "OPEN" }
```

### GET /api/paper-trades
```json
{ "trades": [{ "trade_id": "uuid", "symbol": "RELIANCE.NS", "direction": "BUY", "quantity": 10, "entry_price": 2848.35, "current_price": 2855.0, "unrealized_pnl": 65.5, "status": "OPEN" }] }
```

### PUT /api/paper-trades/{trade_id}/close
```json
{ "exit_price": 2855.0, "realized_pnl": 45.5, "commission": 20.0, "status": "CLOSED" }
```

---

## Backtesting Endpoints

### POST /api/backtest/run
```json
// Request
{
  "symbol": "RELIANCE.NS",
  "strategy": "rsi_mean_reversion",
  "params": { "rsi_buy": 30, "rsi_sell": 70, "quantity": 10 },
  "start_date": "2024-01-01",
  "end_date": "2026-07-01",
  "initial_capital": 100000
}
// Response (async job)
{ "backtest_id": "uuid", "status": "QUEUED" }
```

### GET /api/backtest/{backtest_id}/results
```json
{
  "backtest_id": "uuid",
  "status": "COMPLETED",
  "metrics": {
    "total_return_pct": 28.4,
    "sharpe_ratio": 1.42,
    "max_drawdown_pct": -12.3,
    "win_rate": 0.63,
    "total_trades": 47,
    "profit_factor": 1.85
  },
  "equity_curve": [{ "date": "2024-01-01", "equity": 100000 }]
}
```

---

## Portfolio Endpoint

### GET /api/portfolio
```json
{
  "initial_capital": 100000,
  "current_value": 112450,
  "total_pnl": 12450,
  "total_pnl_pct": 12.45,
  "open_trades": 3,
  "closed_trades": 24,
  "win_rate": 0.67,
  "allocation": [{ "symbol": "RELIANCE.NS", "value": 28485, "weight_pct": 25.3 }]
}
```

---

## Market Regime Endpoint

### GET /api/market/regime
```json
{
  "regime": "BULLISH",  // BULLISH, BEARISH, SIDEWAYS, VOLATILE
  "confidence": 0.74,
  "signals": [
    { "indicator": "Nifty 50 trend", "value": "Above 200 EMA", "direction": "bullish" },
    { "indicator": "Market breadth", "value": "68% stocks advancing", "direction": "bullish" },
    { "indicator": "VIX", "value": 14.2, "direction": "bullish" }
  ],
  "updated_at": "2026-07-29T15:30:00+05:30"
}
```

---

## WebSocket

### WS /ws/alerts
- Connect with JWT token in query param: `wss://api.aistock.local/ws/alerts?token=<jwt>`
- Server pushes alert payloads when conditions trigger:
```json
{ "type": "ALERT_TRIGGERED", "alert_id": "uuid", "symbol": "RELIANCE.NS", "message": "Reliance hit 2900!", "price": 2901.5, "timestamp": "2026-07-29T11:45:00+05:30" }
```
