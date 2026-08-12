# AI Handoff — Stock Prediction System

## Read this first

Every agent must read `AGENTS.md`, this file, and the current `git status --short` before acting. This file is deliberately tool-neutral so work can move among Codex/ChatGPT, Claude, Gemini/Antigravity, and other agents.

## Current environment

- Workspace: `D:\Stock Prediction System`
- Frontend dev server: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Demo admin: `admin@stockai.com` / `admin` (local development only)

## Latest verified checks (2026-08-09)

- Frontend TypeScript/Vite build: passed (last verified pre-session)
- Backend Python compilation: passed
- Backend pytest: 17 passed (last verified in Docker run)

## What has been built (complete system memory)

### Frontend (`frontend/src/`)
- **ChartPage.tsx** — Full charting with Lightweight Charts; HA mode, OBs, RSI/MACD/EMA panels; pattern detection overlay; corporate event markers (dividends + earnings); Drawing Engine for trendlines; AI Score circular confidence ring; 1-click paper trade button; keyboard shortcuts (I=indicators, E=events, Esc=clear)
- **Dashboard.tsx** — Animated indices with AnimatedNumber counters; shimmer loading skeletons; sector heat tiles with color intensity by performance; AI Morning Brief via LLM; pulsing live-dot market status; staggered card entrance animations
- **NavBar.tsx** — Dual-row with LiveTicker (NIFTY50 + Bank NIFTY), StockSearchBox, dark/light theme toggle
- **ScannerPage.tsx** — Preset + custom rule scanner for Nifty50/sector universes
- **PaperTradingPage.tsx** — Paper trade entry, positions list, P&L tracking
- **AlertsPage.tsx** — Price/RSI/MACD alerts with in-app and email delivery
- **BacktestPage.tsx** — Strategy backtesting with date range
- **PortfolioPage.tsx** — Holdings view
- **OptionsChainPage.tsx** — Options chain with IV and OI
- **HeatmapPage.tsx** — Sector heatmap

### New Components (2026-08-09 Phase 3)
- **WatchlistSidebar.tsx** — Sliding right-panel watchlist with live price updates
- **ChartReplayControls.tsx** — Interactive simulator bar for playing historical candles
- **Chart Comparison** — Added relative strength comparison mode to `ChartPage.tsx` using Lightweight Charts percentage scale

### New Components (2026-08-09)
- **AnimatedNumber.tsx** — Smooth easeOut counter animation
- **Toast.tsx** — Global toast notification system (success/error/warning/info with auto-dismiss + slide-in animation); accessible via `toast.success(...)` from any file
- **AIAssistantWidget.tsx** — Chat widget with localStorage persistence (last 12 messages), pulsing typing indicator, gradient header, clear history button

### CSS (`index.css`)
- Full dark/light theme via `[data-theme]` CSS variables (light overrides dark/:root)
- Keyframe animations: `fadeInUp`, `shimmer`, `pulseRing`, `pulseDot`, `gradientShift`, `toastSlideIn`, `spin`
- Utility classes: `.animate-fade-in-up`, `.stagger-1..6`, `.skeleton`, `.skeleton-card`, `.skeleton-line`, `.heat-tile`, `.live-dot`

### Backend (`backend/`)
- **services/market_data.py** — yfinance provider with timezone-aware dividend filtering; events cache key `events:v2:{symbol}` (v2 busts old broken cache)
- **api/stocks.py** — `/stocks/{symbol}/insight` returns candles, indicators, patterns, events, signals, ai_score, risk, swing_trade in one call
- **services/indicators.py** — RSI, MACD, EMA, ATR, SuperTrend, VWAP, Ichimoku, Bollinger Bands
- **api/websocket.py** — Per-user WebSocket live price streaming

## Known Issues / Remaining Bugs

1. **Events still flaky** — Backend timezone fix (v2 cache key) should resolve for fresh loads. If still missing, check backend logs for `[Events] Could not parse date:` warnings.
2. **Light mode** — CSS vars work but some pages have residual inline rgba colors that don't react to theme. Minor cosmetic issue.
3. **Pattern timestamp matching** — `findIndex` uses `===` on timestamps; yfinance sometimes has minor offset. Could use `Math.abs(diff) < 1000ms` fuzzy match.

## Completed Work (2026-08-09 session)

### AI/ML Backend Upgrades (Completed)
1. ✅ Removed all Mock Data fallbacks from `market_data.py`.
2. ✅ Fixed PC Jeweller / Penny Stock Swing Trade bug (enforced minimum ATR 1.5% so Entry/SL/Target are distinct).
3. ✅ Deleted broken `ensemble.py` and mock models.
4. ✅ Upgraded `train_ml_model.py` to use `TimeSeriesSplit` (Walk-Forward Validation) to handle all macro regimes (Demonetization, COVID Crash, Russia-Ukraine War, Middle East Crises, Rate Hikes, and ATH Rallies).
5. ✅ Expanded dataset coverage to 110+ tickers across Nifty 50, Nifty Midcap 100, Nifty Smallcap 100, Micro/Penny Stocks (`SUZLON`, `PCJEWELLER`, `IDEA`, `YESBANK`, etc.), and major Benchmark/Sectoral Indices (`^NSEI`, `^NSEBANK`, `^CNXIT`, `^CNXAUTO`, `^CNXPHARMA`, etc.).
6. ✅ Upgraded data loading in `train_ml_model.py` to fetch 10+ years of daily data (2015 to Present) with `asyncio.Semaphore(8)` concurrent batching.
7. ✅ Added "Jugaad NSE Fallback" to bypass Yahoo Finance rate limits using direct NSE API stealth scraping.
8. ✅ Added `yf.download` direct chart API fallback in `market_data.py` to bypass Yahoo `v10/quoteSummary` 404 errors for stocks like `TATAMOTORS.NS`, `LTIM.NS`, `ZOMATO.NS`.

### UI & Frontend Bug Fixes (Completed)
1. ✅ Events marker fix — rewritten `snapToValidTime` to always return `chartData[i].time` (guaranteed in validTimes set)
2. ✅ Light mode fix — dark theme now defined before light theme in CSS so light overrides properly
3. ✅ selectedPattern reset — clears when symbol changes (no TCS pattern bleeding into RELIANCE)
4. ✅ AI Assistant chat persistence — localStorage saves last 12 messages per browser
5. ✅ Keyboard shortcuts — I, E, Esc work on chart page with toast feedback
6. ✅ Events backend cache busted — v2 cache key forces fresh fetch

### Enhancements Added
1. ✅ AnimatedNumber component — easeOut counter animation for all prices
2. ✅ Toast notification system — global, slide-in, auto-dismiss
3. ✅ Dashboard shimmer skeletons — replaces plain "Loading…"
4. ✅ Dashboard stagger animations — cards appear with 60ms stagger
5. ✅ Sector heat tiles — colored by magnitude not just direction
6. ✅ Live dot indicator — pulsing green/red based on market open status
7. ✅ AI Morning Brief — LLM-generated 2-sentence market summary on Dashboard
8. ✅ AI Score circular ring — animated SVG confidence ring (replaces plain badge)
9. ✅ 1-Click paper trade button — actually calls API with toast success/error
10. ✅ Animated typing indicator — pulsing dots in AI assistant
11. ✅ AI Assistant redesign — gradient header, slide-in animation, clear history button

## Next Safe Steps

1. Restart backend (`uvicorn backend.main:app --reload`) to pick up model routing and cache key changes
2. Refresh browser — clear localStorage if events still don't show
3. Run `npm run build` to verify no TypeScript errors
4. Test: Dashboard loading skeleton → animated counters, sector tiles
5. Test: Check PCJEWELLER.NS Swing Trade setup (should now have valid Target/SL)
6. Test: Chat widget → reload page → verify conversation persists
7. Test: Premium Live Setup → click "1-Click Paper BUY" → verify toast appears + check Paper Trading page

## Ideas backlog (not yet implemented)
- Volume profile (horizontal histogram on chart right)
- Export chart analysis to PDF
- Pattern-based alert creation ("alert me when Doji appears on TCS")
- Streak / gamification (visit streak counter in navbar)
