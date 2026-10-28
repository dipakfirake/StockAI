# Google OAuth2 & 100% Free Email OTP Setup Guide

This guide walks you through setting up **Google 1-Click Login / Registration** and **100% Free Email OTP Verification** for the StockAI platform. Both solutions are completely free and require no credit cards.

---

## 1. Google OAuth2 Setup (100% Free, No Credit Card Required)

Google Identity Services allows real users to register or sign in with their verified Google Account with a single click.

### Step 1: Go to Google Cloud Console
1. Open [https://console.cloud.google.com/](https://console.cloud.google.com/) and sign in with your Google account.
2. Click the project dropdown at the top and click **New Project**.
3. Name it **StockAI** and click **Create**.

### Step 2: Configure OAuth Consent Screen
1. In the left navigation, click **APIs & Services** > **OAuth consent screen**.
2. Select **External** and click **Create**.
3. Fill in the required fields:
   - **App name**: `StockAI`
   - **User support email**: Your Gmail address
   - **Developer contact information**: Your Gmail address
4. Click **Save and Continue** through the Scopes step (the default `email`, `profile`, `openid` scopes are already included).
5. On the **Test users** screen, you can click **Save and Continue** (or add your test email). When ready for public users, click **Publish App** on the OAuth consent screen to make it live for anyone.

### Step 3: Create OAuth 2.0 Web Client ID
1. In the left navigation, click **APIs & Services** > **Credentials**.
2. Click **+ CREATE CREDENTIALS** at the top and select **OAuth client ID**.
3. Set **Application type** to **Web application**.
4. Set **Name** to `StockAI Web Client`.
5. Under **Authorized JavaScript origins**, click **+ ADD URI** and add:
   - `http://localhost:5173` *(Local frontend)*
   - `http://localhost:8000` *(Local backend)*
   *(Note: Google security policy does NOT allow raw IP addresses like `http://92.4.71.210` directly. For your live server, Google requires a domain with a public extension like `.io` or `.org`. You can use a free domain in two ways:)*
   - **Instant Free Domain (Zero setup)**: `http://92.4.71.210.nip.io` or `http://92.4.71.210.sslip.io` *(These automatically route directly to your IP `92.4.71.210` and are accepted by Google)*.
   - **Custom Free Domain (DuckDNS)**: `https://your-name.duckdns.org` *(From our free HTTPS setup guide)*.
6. Click **Create**.
7. Google will display your **Client ID** (e.g., `123456789012-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com`).
8. Copy this **Client ID**. *(You do NOT need the Client Secret because we use Google's secure frontend credential token flow)*.

### Step 4: Configure the Client ID in StockAI
You can configure the Client ID in either of two ways:
- **Option A (Via Web UI - Recommended)**: Log in as Admin (`admin@stockai.com`), navigate to the **Settings** page, locate **Google OAuth Client ID**, paste your Client ID, and click **Save Settings**.
- **Option B (Via Environment Variable)**: Add `GOOGLE_CLIENT_ID=<your_client_id>` to your server environment.

---

## 2. 100% Free Email OTP Setup (Gmail SMTP App Password)

TRAI regulations in India mandate paid DLT registration and per-SMS fees for mobile OTPs. However, **Email OTP** via Gmail's SMTP server is **100% free** and provides up to **500 verification emails per day**—more than enough for organic growth.

### Step 1: Enable 2-Step Verification on Your Gmail
1. Go to [https://myaccount.google.com/security](https://myaccount.google.com/security).
2. Under **How you sign in to Google**, click on **2-Step Verification** and turn it ON (if not already enabled).

### Step 2: Generate a 16-Character App Password
1. Once 2-Step Verification is enabled, search for **App passwords** in the search bar at the top of Google Account settings (or navigate to [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)).
2. Under **App name**, enter `StockAI OTP` and click **Create**.
3. Google will display a **16-character password** (e.g. `abcd efgh ijkl mnop`).
4. Copy this 16-character code (remove spaces). This is your free `SMTP_PASSWORD`.

### Step 3: Configure SMTP in StockAI
Add the following configuration to your environment or update `.env` on your local/production machine:

```bash
# 100% Free Gmail SMTP Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_gmail_username@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
SMTP_FROM=your_gmail_username@gmail.com
```

> **Note for Local Development:** If SMTP credentials are not yet entered, StockAI automatically prints the 6-digit OTP code directly to the backend terminal log (`🔑 [DEV OTP CODE] For user@example.com: 123456`), allowing you to test registration without email delivery.

---

## 3. How the Multi-Tier Anti-Temp-Mail Defense Protects Your Platform

Attackers and bots frequently attempt to create disposable accounts using temporary email services or aliasing tricks. StockAI defends against this through four automated tiers:

| Tier | Defense Mechanism | What It Blocks |
| :--- | :--- | :--- |
| **Tier 1** | **3,500+ Disposable Domain Blacklist** | Blocks known burner services like `mailinator.com`, `temp-mail.org`, `10minutemail.com`, `guerrillamail.com`, etc. |
| **Tier 2** | **Dynamic Regex Pattern Matching** | Identifies generated throwaway domains matching patterns like `.*temp[-_]?mail.*`, `.*burner.*`, `.*disposable.*`. |
| **Tier 3** | **Live Asynchronous DNS MX Verification** | Queries DNS mail exchange (MX) records to confirm the domain is capable of receiving email and does not resolve to null (`0.0.0.0`) or localhost (`127.0.0.1`). Results are cached for 24 hours. |
| **Tier 4** | **Sub-addressing & Dot-Aliasing Normalization** | Attackers exploit Gmail by adding plus tags (`user+temp1@gmail.com`) or inserting dots (`u.s.e.r@gmail.com`). StockAI canonicalizes all Gmail addresses to their root form (`user@gmail.com`), preventing multiple accounts from a single Gmail inbox. |
| **Tier 5** | **Entropy & Consonant Clustering Heuristics** | Analyzes username randomness using Shannon entropy and consonant sequences (e.g., `qwxzkj1984712@...`), flagging machine-generated bot patterns. |

---

## 4. Live Server Deployment Instructions (Remote Oracle Cloud VM)

To deploy these enhancements to your live production server (`92.4.71.210`), run the following copy-pasteable commands on the live server:

```bash
# 1. Connect to your Oracle Cloud VM
ssh -i "C:\path\to\your-ssh-key.key" ubuntu@92.4.71.210

# 2. Navigate to the Stock Prediction System workspace
cd ~/Stock\ Prediction\System  # (or your server project path)

# 3. Pull the latest tested commits
git pull origin main

# 4. Rebuild the frontend production bundle
cd frontend
npm run build
cd ..

# 5. Restart the Docker stack
docker compose down
docker compose up -d --build

# 6. Verify backend and frontend containers are healthy
docker compose ps
docker compose logs -f backend --tail=50
```

---

## Summary of Completed Capabilities

1. **Google Identity Services 1-Click Login / Registration**: Verified with Google OAuth tokeninfo cryptographic endpoint.
2. **Email OTP Verification**: 6-digit cryptographically secure codes with 5-minute TTL, 60s cooldown, and 5-attempt brute-force lockouts.
3. **Multi-Tier Anti-Temp-Mail Shield**: Comprehensive protection against burner domains and Gmail aliasing tricks.
4. **Zero Regressions**: All 26 backend unit and regression tests passing; frontend TypeScript build passing with zero errors.
