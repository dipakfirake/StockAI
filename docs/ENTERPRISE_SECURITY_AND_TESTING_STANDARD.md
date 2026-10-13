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

---

## 5. The Three Testing Paradigms: White Box, Black Box & Grey Box Matrix

The platform is fortified across all three industry-standard software testing methodologies:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        StockAI Three-Tier Testing Matrix                               │
├──────────────────────────┬─────────────────────────────┬───────────────────────────────┤
│ ⬜ White Box Testing      │ ⬛ Black Box Testing         │ 🔳 Grey Box Testing           │
│ (Internal Structure/Math)│ (External HTTP Contracts)   │ (Security & Hybrid Boundaries)│
├──────────────────────────┼─────────────────────────────┼───────────────────────────────┤
│ • Algorithmic Math & RSI │ • Public Endpoints (GET /)  │ • SQL Injection Fuzzing       │
│ • ATR True Range Limits  │ • Prometheus /metrics       │ • XSS Script Tag Injection    │
│ • Zero-Division Guards   │ • Pydantic Schema (422)     │ • Token Bucket Throttling(429)│
│ • PyTorch 36-Tensor Dim  │ • Data Type Mismatch (422)  │ • RBAC Admin Elevation (403)  │
│ • ORM Model Attributes   │ • Non-Existent Routes (404) │ • Financial Idempotency Replay│
│ • NaN & Inf Sanitizers   │ • Unsupported Verbs (405)   │ • Unauthenticated Guard (401) │
│ • State Machine Logic    │ • CORS Preflight (OPTIONS)  │ • Transaction Rollback Safety │
└──────────────────────────┴─────────────────────────────┴───────────────────────────────┘
```

### A. ⬜ White Box Testing (Internal Structural & Algorithmic Verification)
- **Definition**: Tests internal algorithms, mathematical boundary conditions, and code branches with full access to source code.
- **Automated Modules**: `backend/tests/test_three_tier_paradigms.py::test_white_box_paradigm_probes`, `backend/tests/test_indicators.py`, `backend/tests/test_signals.py`, `backend/tests/test_risk_analysis.py`.
- **Target Verification**:
  - `WB-01`: Indicator Engine Numerical Sanity (RSI strictly $0 \le RSI \le 100$, ATR $> 0$, zero `NaN` or `inf`).
  - `WB-02`: Machine Learning Universal Scale-Invariant Feature Engine calibrated at exactly 36 normalized feature dimensions.

### B. ⬛ Black Box Testing (External Contract & Schema Verification)
- **Definition**: Tests the system from the outside without knowledge of internal code, treating each endpoint as an opaque interface and evaluating HTTP status codes, headers, and payload contracts.
- **Automated Modules**: `backend/tests/test_three_tier_paradigms.py::test_black_box_paradigm_probes`, `backend/services/request_validator.py`.
- **Target Verification**:
  - `BB-01`: `GET /` responds with HTTP 200 OK and system metadata.
  - `BB-02`: `GET /metrics` delivers RFC-compliant Prometheus telemetry format.
  - `BB-03`: `POST /api/auth/login` with missing body returns `HTTP 422 Unprocessable Entity`.
  - `BB-04`: `POST /api/auth/login` with invalid data types returns `HTTP 422` schema error before hitting DB.
  - `BB-05`: `GET /api/non_existent_route` returns standard `HTTP 404 Not Found`.
  - `BB-06`: `DELETE /api/auth/login` on POST-only endpoint returns standard `HTTP 405 Method Not Allowed`.
  - `BB-07`: `OPTIONS /api/stocks/quote/RELIANCE` returns `200/204` with CORS Access-Control headers.

### C. 🔳 Grey Box Testing (Hybrid Architecture & Security Boundary Testing)
- **Definition**: Combines black box external inputs with internal structural awareness of database states, Redis token buckets, and cryptographic role boundaries.
- **Automated Modules**: `backend/tests/test_three_tier_paradigms.py::test_grey_box_paradigm_probes`, `backend/tests/test_cybersecurity.py`.
- **Target Verification**:
  - `GB-01`: SQL injection attack payload (`' OR '1'='1' --`) safely escaped by parameterized binders.
  - `GB-02`: XSS script tags (`<script>alert(1)</script>`) strictly sanitized without code execution.
  - `GB-03`: Unauthenticated access to `/api/admin/users` blocked with `HTTP 401/403`.
  - `GB-04`: Negative order shares (`quantity: -99`) rejected by Pydantic boundary validation.
  - `GB-05`: Token bucket burst exhaustion triggers anti-bruteforce throttling.

---

## 6. All-Request Validation & Fuzz Testing Console (Admin UI)

Accessible directly within the Admin Console at `/admin/sentinel`:
1. **HTTP Verb Selector**: Test `GET`, `POST`, `PUT`, `DELETE`, and `OPTIONS`.
2. **Endpoint Address Bar**: Input any target path (e.g. `/api/auth/login`, `/api/paper-trades`).
3. **One-Click Presets**:
   - `🟢 200 OK Health`: Probes live application health contract.
   - `🟡 422 Schema Violation`: Sends bad data types to verify Pydantic rejection.
   - `🔴 SQL Injection Fuzz`: Tests query parameter escaping.
   - `🟠 XSS Script Fuzz`: Tests HTML/script sanitization.
   - `🟣 Boundary Negative Order`: Verifies numeric range constraints.
   - `🔵 OPTIONS CORS Preflight`: Verifies cross-origin header compliance.
4. **Live Response Inspector**: Displays status code badge, roundtrip latency in milliseconds, headers, and formatted JSON response body.

---

## 7. Repository Security Hygiene Audit Evidence Report

An automated audit of the repository was conducted against the Security Hygiene Manifesto:

| Check Category | Item Audited | Status | Evidence & Verification |
|---|---|---|---|
| **A. Git / Public Repo** | `.env` file | ✅ SECURE | Verified ignored by `.gitignore`. Zero `.env` files tracked in `git ls-files`. |
| **A. Git / Public Repo** | SSH Private Keys (`.key`, `.pem`, `id_rsa`) | ✅ SECURE | Zero `.key`, `.pem`, or `id_rsa` files in git repository. Blocked in `.gitignore`. |
| **A. Git / Public Repo** | Database dumps (`*.sql`, `*.dump`) | ✅ SECURE | Only `backend/init_db.sql` (9-line extension enabler) is tracked. Zero data dumps. |
| **A. Git / Public Repo** | Hardcoded secrets in code | ✅ SECURE | Regex scan across `backend/` and `frontend/` found 0 hardcoded passwords or keys. |
| **A. Git / Public Repo** | Shell history (`.bash_history`) | ✅ SECURE | Blocked in `.gitignore`. Zero history files tracked in repository. |
| **B. Frontend** | Backend secrets in React code | ✅ SECURE | Zero database URLs or private keys in `frontend/src/`. |
| **B. Frontend** | `localStorage` inspection | ✅ SECURE | Only caches `auth_token` (short-lived JWT) and `app-theme`. Zero plaintext credentials. |
| **B. Frontend** | Server-side authorization | ✅ SECURE | All admin actions protected by `@router.post(..., dependencies=[Depends(require_admin)])`. |
| **B. Frontend** | Stack trace disclosure | ✅ SECURE | Global exception handler sanitizes all backend tracebacks into safe HTTP errors. |
| **C. Backend** | Password hashing algorithm | ✅ SECURE | Passwords hashed using bcrypt via Passlib `CryptContext(schemes=["bcrypt"])`. |
| **C. Backend** | `DEBUG` mode in production | ✅ SECURE | `Settings.DEBUG` defaults strictly to `False`. |
| **C. Backend** | CORS policy | ✅ SECURE | CORS strictly restricted to trusted origins (`https://stock-ai-iota-seven.vercel.app`). |
| **C. Backend** | Parameterized queries | ✅ SECURE | Queries use SQLAlchemy ORM or `text("... :param")` parameter binding. |
| **D. Logs** | Redaction of secrets & tokens | ✅ SECURE | `security_audit.log` sanitizes Authorization headers and sensitive parameters. |

