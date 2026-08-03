# AI Handoff — Stock Prediction System

## Read this first

Every agent must read `AGENTS.md`, this file, and the current `git status --short` before acting. This file is deliberately tool-neutral so work can move among Codex/ChatGPT, Claude, Gemini/Antigravity, and other agents.

## Current environment

- Workspace: `D:\Stock Prediction System`
- Docker Desktop daemon was unavailable during the latest verification (`dockerDesktopLinuxEngine` named pipe missing). Start Docker Desktop, then run `docker compose up -d` before using the URLs below.
- Frontend (when Docker is running): `http://localhost:5173`
- API health (when Docker is running): `http://localhost:8000/health`
- API docs (when Docker is running): `http://localhost:8000/docs`
- Flower (when Docker is running): `http://localhost:5555`
- Demo administrator: `admin@stockai.com` / `admin` (local development only; replace before any non-local deployment).

## Latest verified checks

- Backend pytest: previously `17 passed` in the backend Docker container; latest rerun is blocked until Docker Desktop starts.
- Python compilation: passed.
- Frontend TypeScript/Vite production build: passed.
- Host frontend and API health endpoints returned HTTP 200.

## In-progress work

- All tasks from the previous session (dashboard accuracy, chart signal horizon, redundant evaluate calls) are completed.
- Deprecated `datetime.utcnow()` and `pd.Timestamp.utcnow()` calls were replaced with `datetime.now(timezone.utc)` and `pd.Timestamp.now(tz="UTC")` across `backend/data/ingestion/nse_scraper.py`, `backend/services/india_intelligence.py`, and `backend/data/validation/data_quality.py`.

## Recent product changes already present

- Consolidated chart insight endpoint, risk metrics, live data fixes, original advanced indicators, and responsive navigation.
- Secure per-user WebSocket alert delivery, cache fallbacks, dynamic settings, SMTP-only HIGH alerts, and improved paper-trading order ticket.
- Signal-engine equality bug fixed: equal EMA values are neutral rather than bearish.
- Admin seeding now creates a missing local admin account.
- The chart renders a visible "Suggested review horizon" for BUY, SELL, HOLD, and WATCH signals.
- The dashboard labels whether each index is using the NSE exchange feed or the fallback provider.
- Added regression tests for both the horizon calculation and missing index previous-close data.

## Required next verification

1. Run backend tests, Python compilation, frontend production build, API smoke tests, and cold/cached dashboard timing. (Currently blocked due to sandbox terminal access issues).
2. Verify Docker Desktop is running before interacting with the live application.

## Latest handoff update — 2026-08-03

- Added cross-tool agent rules: root `AGENTS.md`, root `GEMINI.md`, root `CLAUDE.md`, `.agents/rules/universal-agent-rules.md`, `docs/AI_START_PROMPT.md`, and global `C:\Users\dcfir\.gemini\GEMINI.md`.
- Python compilation passed after the latest changes.
- Resolved the deprecation warnings for UTC timestamps across the backend.
- Docker-backed tests passed (20 tests passed) in the previous session prior to the terminal environment disconnection. Do not represent the stack as live until its health endpoints return HTTP 200 again.
