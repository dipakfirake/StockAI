# Enterprise Security, Automated Testing & DevOps Standard

This document establishes the canonical cybersecurity defenses, automated system validation architecture, hygiene rules ("what NEVER to allow anywhere"), and DevOps CI/CD strategy for the AI Stock Research Platform.

---

## 1. Dual-Pathway Testing Architecture (Automated + Manual)

To prevent catastrophic system outages, data leakage, and financial transaction replay, the platform implements a **Dual-Pathway Testing System**:

```
                       ┌────────────────────────────────────────────────────────┐
                       │          StockAI Dual-Pathway Testing System           │
                       └───────────────────────────────────┬────────────────────┘
                                                           │
                        ┌──────────────────────────────────┴──────────────────────────────────┐
                        ▼                                                                     ▼
    ┌───────────────────────────────────────┐                             ┌───────────────────────────────────────┐
    │     1. Automated Scheduled Sweeps     │                             │   2. Interactive QA & Security Lab    │
    │  (Runs 24/7 in Background / CI/CD)    │                             │      (Admins / Security Engineers)    │
    ├───────────────────────────────────────┤                             ├───────────────────────────────────────┤
    │ • Hourly: Sentinel loop executes      │                             │ • Located at `/admin/sentinel`        │
    │   10-point health & security probe    │                             │ • 1-Click "Run Full 10-Point Suite"   │
    │ • Daily: GitHub Actions cron at 00:00 │                             │ • Category filters: Cyber, DB, Quant  │
    │   runs vulnerability scan & full test │                             │ • Individual "▶ Re-test" per module   │
    │ • Autonomous: Catches bugs, hashes    │                             │ • Live telemetry: Latency, status     │
    │   fingerprints & raises alert tickets │                             │ • One-click Markdown audit export     │
    └───────────────────────────────────────┘                             └───────────────────────────────────────┘
```

### The 10-Point Validation Suite Specification

| Test Code | Module Name | Category | Scope & Attack Defense |
|---|---|---|---|
| **SEC-001** | Data Leakage & Secret Sanitization | Cybersecurity | Scans serialized configs and responses to ensure zero raw database URLs, private keys, or secret tokens leak. |
| **SEC-002** | Token Bucket Rate Limiting & DoS Shield | Cybersecurity | Tests burst consumption and refill rates across AUTH, TRADING, AI, and GENERAL tiers; enforces IETF Retry-After headers. |
| **SEC-003** | SQL Injection & Parameter Binding | Cybersecurity | Injects SQL injection payloads (`' OR '1'='1' --`) into async sessions, verifying parameters are strictly escaped. |
| **SEC-004** | RBAC & Administrative Privilege Boundary | Cybersecurity | Probes admin-only routes with mock unprivileged tokens, verifying strict HTTP 403 Forbidden enforcement. |
| **SEC-005** | Financial Idempotency & Replay Defense | Cybersecurity | Sends duplicate trade submissions with identical `X-Idempotency-Key` headers, verifying zero duplicate order execution. |
| **SYS-001** | PostgreSQL Database & Connection Pool | System | Executes async roundtrip query (`SELECT 1`), measures latency in milliseconds, and validates pool health. |
| **SYS-002** | Redis Cache & Celery Task Queue Status | System | Performs async SET/GET/DEL cycle, measures roundtrip latency, and inspects active broker queue health. |
| **SYS-003** | Market Data Feeds & Fallback Resilience | System | Validates index quote resolution (`^NSEI`), price positivity, and automated failover when primary broker feed is offline. |
| **SYS-004** | Indicator Engine Numerical Sanity | Quant | Calculates RSI (14) and ATR (14) over edge-case data, asserting strictly bounded numbers with zero `NaN` or `inf`. |
| **SYS-005** | ML Model Inference & Pipeline Bounds | Quant | Verifies 36-feature scale-invariant tensor normalization and bounded loss functions across BiLSTM/Transformer pipelines. |

---

## 2. What Must NEVER Be Anywhere (Cybersecurity Hygiene Manifesto)

To completely eliminate data breaches, credential theft, and unauthorized server takeovers, adhere strictly to these rules across all platform layers:

### A. What Must NEVER Be on GitHub / Git Repositories
1. **Never commit the `.env` file**: Contains live database passwords, JWT secrets, and broker keys. Must remain exclusively on the production host server.
2. **Never commit SSH Private Keys (`.key`, `.pem`, `id_rsa`)**: Never store server login keys in git commits or repository folders.
3. **Never commit database dumps or SQL backups (`*.sql`, `*.dump`)**: Contains real user records, hashed passwords, or order histories.
4. **Never hardcode API keys or secret tokens in source code**: All keys must be retrieved via `os.getenv()` or `pydantic-settings`.
5. **Never commit `.bash_history` or shell history files**: May record commands containing typed passwords or access tokens.
6. **Automated Enforcement**: Pre-commit hooks and `.github/workflows/scheduled_security_audit.yml` scan git file trees and block unauthorized files.

### B. What Must NEVER Be in the Frontend (Vite / React Client)
1. **Never include Server Private Keys or Secrets in Frontend code**: Variables that do not start with `VITE_` are ignored by Vite, but developers must never prefix backend database credentials or secret keys with `VITE_`!
2. **Never store sensitive tokens in `localStorage` indefinitely**: Only short-lived access JWT tokens should be cached; never store master admin credentials or raw passwords in browser storage.
3. **Never implement authorization checks solely on the frontend**: Hiding a button (`{user.isAdmin && <AdminButton />}`) is purely visual; the backend API MUST enforce `@router.post(..., dependencies=[Depends(require_admin)])` on every request.
4. **Never expose raw stack traces in user UI**: If a backend API returns an error, display friendly notifications (e.g. *"Service temporarily unavailable"*), never database query dumps or internal paths.

### C. What Must NEVER Be in the Backend / Host Server
1. **Never store plaintext passwords in PostgreSQL**: All passwords must be salted and hashed using `bcrypt` (12+ rounds) or Argon2.
2. **Never run with `DEBUG=True` in production**: Debug mode exposes interactive debuggers (Werkzeug/Uvicorn) and full traceback internals.
3. **Never allow Wildcard CORS (`*`) with credentials**: CORS must be restricted strictly to trusted origins (e.g. `https://stock-ai-iota-seven.vercel.app`).
4. **Never execute unparameterized SQL strings**: Never do `f"SELECT * FROM users WHERE email = '{email}'"`. Always use SQLAlchemy text binding `text("SELECT * FROM users WHERE email = :email")`.
5. **Never use world-readable file permissions (`chmod 777`)**: SSH keys must be `chmod 600`, directory permissions `chmod 755` or `700`.

### D. What Must NEVER Be in Server Logs (`logs/*.log`)
1. **Never log raw passwords or authorization tokens**: Redact `Authorization: Bearer <TOKEN>` to `Authorization: Bearer ***REDACTED***`.
2. **Never log payment references or personal contact numbers**.
3. **Never log raw database connection URLs** containing the password component (`postgresql://user:password@host...`).

---

## 3. DevOps & CI/CD: Is Jenkins Required?

### Direct Answer: NO, Jenkins is NOT required and is strongly discouraged for your architecture.

### Why Jenkins is the Wrong Choice for this Stack:
1. **Severe Memory & Resource Overhead**: Jenkins requires a full Java Runtime Environment (JVM) that permanently consumes 1.5GB – 2GB of RAM on your server. On a 1GB–4GB cloud VM, running Jenkins alongside PostgreSQL, Redis, Celery, and FastAPI would cause immediate out-of-memory (OOM) kernel crashes.
2. **Maintenance Burden**: Jenkins requires manual plugin updates, security patch management, firewall port openings (port 8080), and reverse proxy setup.
3. **Cost**: You have to pay for the compute and storage to host Jenkins 24/7.

### The Recommended Modern Standard: GitHub Actions
Instead of Jenkins, your repository is configured with **GitHub Actions**:
1. **Zero Server Memory Footprint**: Workflows run entirely in GitHub's cloud virtual machines (Ubuntu latest), consuming 0 RAM on your Oracle Cloud VM.
2. **Free**: GitHub provides 2,000 free runner minutes per month for public and private repositories.
3. **Automated & Maintenance-Free**:
   - **Continuous Integration (`.github/workflows/ci.yml`)**: Automatically triggers on every `git push origin main`. Runs unit tests, linter, and frontend build before deployment.
   - **Daily Security Sweep (`.github/workflows/scheduled_security_audit.yml`)**: Runs automatically every night at 00:00 UTC (cron), checking for secret leaks, running cybersecurity tests, and verifying system integrity.
4. **Automatic Production Deployment**:
   - Frontend is automatically built and deployed by **Vercel** within 60 seconds of pushing to `main`.
   - Backend on Oracle VM pulls and restarts via Docker Compose (`sudo docker compose restart backend celery_worker`).

---

## 4. Operational Checklist for Daily & Hourly Verification

| Verification Cadence | Tool / Mechanism | Action / Observation |
|---|---|---|
| **Continuous (Every 2s)** | Sentinel 24/7 Watchdog | Probes PostgreSQL latency, Redis ping, Celery queues, and security audit log. |
| **Hourly (Every 1800 cycles)** | Sentinel Autonomous Sweep | Automatically executes full 10-point System Validator suite in background. |
| **On-Demand (Manual QA)** | Admin Lab at `/admin/sentinel` | Click **"🚀 Run Full 10-Point Suite"** to verify all 10 tests live and export markdown report. |
| **Daily (Every Midnight UTC)** | GitHub Actions Cron | Executes secret scanning, security pytest suites, and production build checks. |
