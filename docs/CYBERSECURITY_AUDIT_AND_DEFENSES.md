# Cybersecurity & Financial Risk Architecture Audit — StockAI

**Document Status:** Production Ready  
**Scope:** Vulnerability Audit, Financial Theft Defense, Maximum Request Handling, Denial of Service (DoS) Mitigation, and Industrial FinTech Hardening.  
**Platform Classification:** High-Financial-Risk Algorithmic Trading & Stock Research System (NSE/BSE Indian Equities).

---

## 1. Executive Summary & Threat Model

When an algorithmic stock trading and research system is hosted on the public internet, it immediately becomes a target for high-severity threat vectors:

| Threat Vector | Real-World Attack Scenario | Impact on Financial System | Implemented Safeguard |
| :--- | :--- | :--- | :--- |
| **API Flooding / DoS / DDoS** | Attackers spam resource-heavy ML endpoints (`/api/ai/predict`) or market insight routes to crash services. | System downtime, missed stop-loss triggers, server crash. | **Token Bucket Multi-Tier Rate Limiting** with standard IETF `Retry-After` headers. |
| **Credential Stuffing & Brute Force** | Automated bots iterate common passwords on `/api/auth/login` to seize accounts with connected broker API keys. | Account takeover, unauthorized live trading, capital theft. | **IP/Account Lockout Protection** (5 attempts triggers 15-min lockout) + Password Complexity enforcement. |
| **Order Replay / Double-Spending** | Rapid double-clicking or network retries re-submitting `POST /api/paper-trades` concurrently. | Double position size, unintentional margin exhaustion, duplicate trades. | **Financial Idempotency Key Manager** (`Idempotency-Key` tracking and replay deduplication). |
| **Fat-Finger & Out-of-Bounds Orders** | Malicious or buggy clients sending order quantities of 100M shares or limit prices ±500% from market. | Margin overflow, accounting distortion, simulated market manipulation. | **Fat-Finger Circuit Breakers & Risk Bounds** (Max quantity 50k, max notional ₹1 Crore, ±30% price deviation limit). |
| **Memory Exhaustion (Payload Flooding)** | Sending multi-megabyte JSON payloads to standard API endpoints. | Python process out-of-memory (OOM) kill by kernel. | **Request Body Size Guard** (Max 1 MB payload limit with HTTP 413). |
| **Clickjacking / UI Redressing** | Embedding the trading interface in an invisible iframe on a malicious website to trick users into executing trades. | Unauthorized trade executions without user knowledge. | **`X-Frame-Options: DENY`** + Strict Content-Security-Policy. |
| **MIME Sniffing & XSS** | Injecting scripts via symbol or query params and MIME confusion. | Session token theft, malicious API calls on behalf of user. | **`X-Content-Type-Options: nosniff`** + Symbol sanitization regex. |
| **Forensic Blindspots** | Financial disputes or breaches without immutable audit records. | Inability to prove state or pinpoint origin of compromise. | **Structured Security & Financial Audit Logger** (`security_audit.log`). |

---

## 2. Implemented Defense Architecture

### 2.1 Industrial Token Bucket Rate Limiter (`backend/core/rate_limiter.py`)
- **Algorithm:** Classical Token Bucket replenishment with burst capacity ($B$) and refill rate ($R$).
- **Multi-Tier Classification:**
  - **`AUTH` Tier:** 10 requests / min (Burst 10). Enforced on `/api/auth/*` to eliminate automated credential stuffing.
  - **`TRADING` Tier:** 30 requests / min (Burst 20). Enforced on `/api/paper-trades` and `/api/portfolio` to eliminate order spamming.
  - **`AI` Tier:** 30 requests / min (Burst 15). Enforced on compute-heavy LightGBM, SHAP, and sentiment endpoints.
  - **`GENERAL` Tier:** 120 requests / min (Burst 100). Enforced on standard browsing and market data feeds.
- **Dual Identification:**
  - Authenticated requests are tracked by user token hash (`AUTH:user:<hash>`).
  - Unauthenticated requests are tracked by client IP address (`AUTH:<ip>`).
- **Standard HTTP Headers Injected:**
  - `X-RateLimit-Limit`: Maximum bucket capacity.
  - `X-RateLimit-Remaining`: Tokens currently remaining in bucket.
  - `X-RateLimit-Reset`: Seconds until complete refill.
  - `X-RateLimit-Tier`: Name of the active tier.
  - `Retry-After`: Seconds client must wait when HTTP 429 is returned.
- **Memory Safety:** Automatic background garbage collection sweeps idle token buckets older than 15 minutes.

### 2.2 Financial Idempotency Key Manager (`backend/core/idempotency.py`)
- Supported on `POST /api/paper-trades` via `Idempotency-Key` header or payload field.
- **Concurrent Race Protection:** If two identical order requests hit the server simultaneously, the second receives `HTTP 409 Conflict` ("Order request is currently being processed").
- **Deduplication Replay:** If an order has already succeeded and the client re-submits the same key (e.g. after a Wi-Fi drop), the server returns the cached response with `X-Idempotent-Replay: true` without duplicating trades or commissions.

### 2.3 Financial Risk Guardrails & Fat-Finger Circuit Breakers (`backend/services/paper_trading.py`)
- **Maximum Quantity Cap:** Single order cannot exceed `50,000` shares.
- **Notional Order Cap:** Single order notional value (`price * quantity`) cannot exceed **₹1,00,00,000 (₹1 Crore)**.
- **Fat-Finger Price Deviation Bounds:** Limit and Stop orders cannot deviate by more than **±30%** from the active market price.
- **Input Sanitization:** Strict regex enforcement on symbols (`^[A-Za-z0-9\.\-\:]{1,30}$`) prevents script or SQL injection attempts.

### 2.4 Security Headers & DoS Guard Middleware (`backend/core/security_middleware.py`)
- **OWASP Headers Attached to All Responses:**
  - `X-Frame-Options: DENY` (Anti-Clickjacking)
  - `X-Content-Type-Options: nosniff` (Anti-MIME sniffing)
  - `X-XSS-Protection: 1; mode=block`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` (HSTS)
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: accelerometer=(), camera=(), geolocation=(), ...`
- **Request Entity Size Limit:** Rejects request payloads greater than **1 MB** with `HTTP 413 Payload Too Large`.
- **Cache-Control Lock:** Attaches `no-store, no-cache, must-revalidate` to all `/api/auth` and `/api/paper-trades` responses to prevent browser disk caching of sensitive financial balances.
- **Trace ID Tracking:** Generates and threads `X-Request-ID` across all requests for end-to-end auditability.

### 2.5 Auth Hardening & Brute-Force Lockout (`backend/core/auth_security.py`)
- **Password Complexity Enforcement:** Requires minimum 8 characters, at least 1 alphabet, and at least 1 digit or special character.
- **Automatic Account/IP Lockout:** Tracks failed authentication attempts. 5 consecutive failures triggers an automatic 15-minute lockout with HTTP 429 and `Retry-After`.

### 2.6 Structured Security Audit Logger (`backend/core/audit_logger.py`)
- Writes immutable, structured JSON records to `logs/security_audit.log`.
- Sensitive tokens, passwords, and secrets are automatically redacted before logging (`[REDACTED]`).
- Logs all critical security and financial events:
  - `AUTH_LOGIN_SUCCESS`, `AUTH_LOGIN_FAILED`, `AUTH_ACCOUNT_LOCKED`
  - `ORDER_PLACED`, `ORDER_CLOSED`, `ORDER_CANCELLED`, `ORDER_RISK_LIMIT_EXCEEDED`
  - `IDEMPOTENCY_RACE_DETECTED`, `RATE_LIMIT_BLOCKED`

### 2.7 Anti-Information Leakage Exception Handling (`backend/main.py`)
- Intercepts all unhandled 500 exceptions.
- Logs the full stack trace securely into internal server logs with the correlation `trace_id`.
- Returns a sanitized external payload:
  ```json
  {
    "error": "Internal Server Error",
    "detail": "An unexpected error occurred. The incident has been logged for security review.",
    "trace_id": "c1f7b9e2-..."
  }
  ```
  Guarantees internal database connection strings, paths, and library versions are never disclosed to clients.

---

## 3. Verification & Test Evidence

All cybersecurity protections were verified with dedicated automated tests:

```bash
# Executed Test Command
pytest backend/tests/test_cybersecurity.py
```

### Results:
- `test_token_bucket_consume_and_exhaust`: **PASSED** (Bucket depletes and enforces HTTP 429 when empty)
- `test_token_bucket_refill`: **PASSED** (Tokens replenish at configured rate over time)
- `test_rate_limiter_tier_mapping`: **PASSED** (Correct tier mapping for AUTH, TRADING, AI, GENERAL)
- `test_idempotency_lifecycle`: **PASSED** (Detects concurrent races and replays cached results)
- `test_order_risk_quantity_limit`: **PASSED** (Blocks order quantity > 50,000)
- `test_order_risk_notional_value_limit`: **PASSED** (Blocks order notional value > ₹1 Crore)
- `test_fat_finger_limit_price_circuit_breaker`: **PASSED** (Blocks price deviating > 30%)
- `test_symbol_injection_sanitization`: **PASSED** (Rejects XSS/malformed symbols)
- `test_password_strength_validation`: **PASSED** (Enforces 8-char + complexity)
- `test_brute_force_lockout`: **PASSED** (5 failed attempts locks IP/account for 15 min)
- `test_security_audit_logger_redaction`: **PASSED** (Logs structured JSON and redacts passwords)

### Full Regression Test Suite:
```text
======================= 43 passed, 1 warning in 17.56s ========================
```
- Frontend Lint: `npm run lint` -> **PASSED (0 errors)**
- Frontend Production Build: `npm run build` -> **PASSED (49.07s)**

---

## 4. Production Hosting & Cloud Hardening Checklist

When deploying this project online (e.g. Render, AWS, Vercel, Neon), ensure the following infrastructure-level controls are applied:

1. **Cloudflare / CDN Reverse Proxy (Layer 7 WAF & DDoS Shield):**
   - Place Cloudflare in front of the API.
   - Enable Cloudflare "Under Attack Mode" and Managed WAF Rules (OWASP Core Ruleset).
   - Set Rate Limiting rules at the Cloudflare edge for `/api/auth/*` as the first line of defense.
2. **Strict TLS 1.3 Encryption:**
   - Terminate TLS with TLS 1.3 only; disable TLS 1.0 and 1.1.
3. **Database Security (Neon PostgreSQL):**
   - Enable IP Allowlisting on Neon to permit connections only from the Render backend IP/VPC.
   - Use pooled connections (`-pooler` endpoint) with SSL mode `require`.
   - Never grant `SUPERUSER` privileges to the application database user.
4. **Broker Credential Security (Fyers API):**
   - Store `FYERS_ACCESS_TOKEN`, `FYERS_SECRET_KEY`, and `SECRET_KEY` in cloud secret managers (Render Secrets / AWS Secrets Manager).
   - Rotate `SECRET_KEY` and broker tokens periodically.
   - Maintain the strict zero-read rule on `.env` files in source repositories.
5. **Periodic SIEM Log Ingestion:**
   - Ingest `logs/security_audit.log` into Grafana Loki / Datadog to set alerts on `AUTH_ACCOUNT_LOCKED` and `ORDER_RISK_LIMIT_EXCEEDED`.
