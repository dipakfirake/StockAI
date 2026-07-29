# Database Schema

## Database: PostgreSQL 15 + TimescaleDB

---

## Tables

### users
```sql
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       VARCHAR(255) UNIQUE NOT NULL,
    name        VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### stocks
```sql
CREATE TABLE stocks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol      VARCHAR(30) UNIQUE NOT NULL,   -- e.g. RELIANCE.NS
    name        VARCHAR(255) NOT NULL,
    exchange    VARCHAR(10) NOT NULL,           -- NSE, BSE
    sector      VARCHAR(100),
    industry    VARCHAR(100),
    market_cap  BIGINT,
    isin        VARCHAR(12),
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_stocks_symbol ON stocks(symbol);
CREATE INDEX idx_stocks_exchange ON stocks(exchange);
```

### candles  *(TimescaleDB Hypertable)*
```sql
CREATE TABLE candles (
    symbol      VARCHAR(30) NOT NULL,
    timeframe   VARCHAR(5) NOT NULL,   -- 1m, 5m, 15m, 30m, 1h, 1d, 1w
    timestamp   TIMESTAMPTZ NOT NULL,
    open        NUMERIC(12, 4) NOT NULL,
    high        NUMERIC(12, 4) NOT NULL,
    low         NUMERIC(12, 4) NOT NULL,
    close       NUMERIC(12, 4) NOT NULL,
    volume      BIGINT NOT NULL,
    PRIMARY KEY (symbol, timeframe, timestamp)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('candles', 'timestamp', chunk_time_interval => INTERVAL '7 days');

-- Enable compression
ALTER TABLE candles SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, timeframe'
);
SELECT add_compression_policy('candles', INTERVAL '30 days');

CREATE INDEX idx_candles_symbol_tf ON candles(symbol, timeframe, timestamp DESC);
```

### watchlists
```sql
CREATE TABLE watchlists (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol      VARCHAR(30) NOT NULL,
    added_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, symbol)
);
CREATE INDEX idx_watchlists_user ON watchlists(user_id);
```

### alerts
```sql
CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol          VARCHAR(30) NOT NULL,
    condition_type  VARCHAR(50) NOT NULL,  -- PRICE_ABOVE, PRICE_BELOW, RSI_BELOW, RSI_ABOVE, MACD_CROSS_UP, MACD_CROSS_DOWN
    condition_value NUMERIC(12, 4) NOT NULL,
    message         TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    triggered_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_alerts_user ON alerts(user_id);
CREATE INDEX idx_alerts_symbol_active ON alerts(symbol, is_active);
```

### paper_trades
```sql
CREATE TABLE paper_trades (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol          VARCHAR(30) NOT NULL,
    direction       VARCHAR(5) NOT NULL,       -- BUY, SELL
    quantity        INTEGER NOT NULL,
    entry_price     NUMERIC(12, 4) NOT NULL,
    exit_price      NUMERIC(12, 4),
    slippage        NUMERIC(8, 4) DEFAULT 0,
    commission      NUMERIC(8, 2) DEFAULT 20,
    status          VARCHAR(10) DEFAULT 'OPEN', -- OPEN, CLOSED, CANCELLED
    realized_pnl    NUMERIC(12, 4),
    opened_at       TIMESTAMPTZ DEFAULT NOW(),
    closed_at       TIMESTAMPTZ
);
CREATE INDEX idx_paper_trades_user ON paper_trades(user_id);
CREATE INDEX idx_paper_trades_status ON paper_trades(user_id, status);
```

### signals
```sql
CREATE TABLE signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          VARCHAR(30) NOT NULL,
    signal_type     VARCHAR(10) NOT NULL,   -- BUY, SELL, HOLD, WATCH
    strength        VARCHAR(10) NOT NULL,   -- STRONG, MODERATE, WEAK
    reason          TEXT NOT NULL,
    indicators_used JSONB,
    timeframe       VARCHAR(5) DEFAULT '1d',
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_signals_symbol ON signals(symbol, generated_at DESC);
```

### predictions
```sql
CREATE TABLE predictions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol              VARCHAR(30) NOT NULL,
    horizon             VARCHAR(10) NOT NULL,   -- 1d, 5d, 1w
    predicted_direction VARCHAR(10) NOT NULL,   -- BUY, HOLD, SELL
    probabilities       JSONB NOT NULL,         -- {"buy": 0.72, "hold": 0.20, "sell": 0.08}
    confidence          NUMERIC(5, 4) NOT NULL,
    model_version       VARCHAR(50) DEFAULT 'rule_based_v1',
    shap_values         JSONB,                  -- Feature contributions
    features_used       JSONB,                  -- Feature snapshot at prediction time
    actual_outcome      VARCHAR(10),            -- Filled in after horizon has passed
    generated_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_predictions_symbol ON predictions(symbol, generated_at DESC);
```

---

## Entity Relationship Summary

```
users
  ├──< watchlists (symbol)
  ├──< alerts (symbol, condition)
  └──< paper_trades (symbol, direction, qty)

stocks
  ├──< candles (OHLCV time-series — hypertable)
  ├──< signals (rule-based buy/sell signals)
  └──< predictions (AI scores with SHAP)
```

---

## TimescaleDB Notes

- `candles` is the only hypertable. All other tables are standard PostgreSQL tables.
- Chunk interval: 7 days (balanced for NSE market data density).
- Compression kicks in after 30 days (older OHLCV data is rarely queried at full resolution).
- Continuous aggregates can be added later for faster dashboard queries (e.g., pre-aggregated weekly/monthly candles).
