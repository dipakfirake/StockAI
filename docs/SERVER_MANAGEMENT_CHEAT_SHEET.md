# Oracle Cloud Server Management & Operations Cheat Sheet — StockAI

**Server Details:**
- **Instance Name:** `stockai-server`
- **Region:** `ap-mumbai-1` (Availability Domain `AD-1`)
- **Shape:** `VM.Standard.A1.Flex` (Ampere ARM64, 1 OCPU, 6 GB RAM — **100% Always Free**)
- **Public IP:** `92.4.71.210`
- **SSH User:** `opc`
- **Private Key Location (Local):** `C:\Users\dcfir\Downloads\ssh-key-2026-10-11.key`
- **Project Directory on Server:** `/home/opc/StockAI`

**Public URLs:**
- **Live DuckDNS HTTPS Website:** [https://stockai-live.duckdns.org](https://stockai-live.duckdns.org)
- **Live Vercel Frontend:** [https://stock-ai-iota-seven.vercel.app](https://stock-ai-iota-seven.vercel.app)
- **DuckDNS Swagger Docs:** [https://stockai-live.duckdns.org/docs](https://stockai-live.duckdns.org/docs) (or `/swagger`)
- **DuckDNS Celery Flower:** [https://stockai-live.duckdns.org/flower/](https://stockai-live.duckdns.org/flower/)
- **DuckDNS Health Probe:** [https://stockai-live.duckdns.org/health/live](https://stockai-live.duckdns.org/health/live) (or `/health/liv`)
- **Direct IP Swagger Docs:** [http://92.4.71.210:8000/docs](http://92.4.71.210:8000/docs)
- **Direct IP Celery Flower:** [http://92.4.71.210:5555/flower/](http://92.4.71.210:5555/flower/)
- **Direct IP Health Probe:** [http://92.4.71.210:8000/health/live](http://92.4.71.210:8000/health/live)

---

## 1. How to Access the Server Console via Windows PowerShell

### Step-by-Step to Log In:
1. On your Windows laptop, open **PowerShell** or **Terminal** (press `Win + X` and click **Terminal** / **PowerShell**, or press `Win + R`, type `powershell`, and hit Enter).
2. Copy and paste this single command and press **Enter**:
```powershell
ssh -o ServerAliveInterval=30 -i "C:\Users\dcfir\Downloads\ssh-key-2026-10-11.key" opc@92.4.71.210
```
3. Your terminal prompt will change from `PS C:\...>` to:
```text
[opc@stockai-server ~]$
```
🎉 **You are now inside the Linux cloud server console!**

---

### How to Navigate to the Project Folder:
Once inside the server console, go to your project folder by running:
```bash
cd /home/opc/StockAI
```
Your prompt will now show:
```text
[opc@stockai-server StockAI]$
```
*(All `docker compose` commands should be run here).*

---

### How to Exit / Close the Server Console:
When you are done working on the server and want to return to your normal Windows PowerShell:
* Type `exit` and hit **Enter** (or press `Ctrl + D`).
* Your prompt will return back to `PS C:\...>` on your Windows laptop.

---

### If PowerShell Ever Shows "UNPROTECTED PRIVATE KEY FILE" / Bad Permissions:
If you ever move or re-download your `.key` file and Windows complains about permissions, run these 2 quick commands in Windows PowerShell before connecting:
```powershell
icacls "C:\Users\dcfir\Downloads\ssh-key-2026-10-11.key" /inheritance:r
icacls "C:\Users\dcfir\Downloads\ssh-key-2026-10-11.key" /grant:r "$($env:USERNAME):R"
```


## 2. Starting, Pausing & Stopping the Application

All commands below are run inside `/home/opc/StockAI` on the server:

### 🛑 To Pause / Stop the Entire Application
```bash
sudo docker compose down
```
> **Data Safety Note:** Your PostgreSQL/TimescaleDB data and Redis cache are stored in persistent Docker volumes (`pgdata` and `redisdata`). Stopping the containers **never** deletes your paper trades, users, or records.

### ▶️ To Start / Resume the Application
```bash
sudo docker compose up -d
```
*(Starts all 6 services: `backend`, `db`, `redis`, `celery_worker`, `celery_beat`, and `flower` in the background).*

### 📊 To Check Status of All Services
```bash
sudo docker compose ps
```

### ⚡ To Check Memory & CPU Usage
```bash
docker stats --no-stream
```

---

## 3. Daily Fyers API Token Update

Because Fyers access tokens expire daily, use either of these methods:

### Option A: 1-Click Update from your Laptop (Fastest)
Whenever you update `.env` on your PC, paste this into your local **Windows PowerShell**:
```powershell
scp -i "C:\Users\dcfir\Downloads\ssh-key-2026-10-11.key" "D:\Stock Prediction System\.env" opc@92.4.71.210:/home/opc/StockAI/.env; ssh -i "C:\Users\dcfir\Downloads\ssh-key-2026-10-11.key" opc@92.4.71.210 "cd /home/opc/StockAI && sudo docker compose restart backend celery_worker"
```

### Option B: Update Directly on the Server
Inside your server terminal:
```bash
cd /home/opc/StockAI
nano .env
```
1. Scroll down to `FYERS_ACCESS_TOKEN=...` and paste your new token.
2. Press `Ctrl + O`, then `Enter` (to save).
3. Press `Ctrl + X` (to exit).
4. Restart the backend to apply changes:
```bash
sudo docker compose restart backend celery_worker
```

---

## 4. Deploying New Code Updates

Whenever you make code changes locally on your PC:

### Step 1: Push from your Laptop
In local Windows PowerShell:
```powershell
git add .
git commit -m "feat: description of changes"
git push origin main
```
*(Vercel will automatically redeploy the frontend in ~30 seconds).*

### Step 2: Pull & Restart on the Server
In your cloud server SSH terminal:
```bash
cd /home/opc/StockAI
git pull origin main
sudo docker compose restart backend
```
*(If you added new packages to `requirements.txt`, run `sudo docker compose up -d --build backend` instead).*

---

## 5. Live Logs & Debugging

To stream live logs in real time from the server:

```bash
# Backend API (FastAPI) logs:
sudo docker compose logs -f backend

# Celery Worker logs (market scanner & alerts):
sudo docker compose logs -f celery_worker

# Celery Beat logs (scheduled tasks):
sudo docker compose logs -f celery_beat

# TimescaleDB / PostgreSQL logs:
sudo docker compose logs -f db

# Redis logs:
sudo docker compose logs -f redis
```
*(Press `Ctrl + C` anytime to exit the log view).*

---

## 6. Turning Off / Starting the Entire Cloud Machine (VM)

### To Turn Off the Server:
```bash
sudo shutdown -h now
```
*(Or in Oracle Console: Compute $\to$ Instances $\to$ `stockai-server` $\to$ click **Stop**).*

### To Turn the Server Back On:
1. Open [Oracle Cloud Console](https://cloud.oracle.com).
2. Go to **Compute** $\to$ **Instances** $\to$ click **stockai-server**.
3. Click **Start**.
4. The server boots up in ~45 seconds. Docker automatically launches all 6 containers on startup because `docker.service` is enabled.

---

## 7. Cost & Always Free Tier Reference

| Resource | Configuration | Free Tier Limit | Status |
| :--- | :--- | :--- | :--- |
| **Compute VM** | Ampere A1 (1 OCPU, 6 GB RAM) | 4 OCPUs, 24 GB RAM | **100% Free** |
| **Boot Storage** | 46.6 GB Volume | 200 GB Storage | **100% Free** |
| **Public IPv4** | 1 Ephemeral IPv4 | 1 Free Public IPv4 | **100% Free** |
| **Data Egress** | ~10-50 GB / month | 10,000 GB (10 TB) / month | **100% Free** |
| **Total Monthly Cost** | — | — | **₹0.00 / $0.00** |

---

## 8. Billing, Card Verification (₹102 Pre-Auth) & Zero-Cost Guardrails

### ❓ What was the "₹102.xx at ORACLE SINGAPORE" transaction?
- **It is NOT a bill or charge for using this project or uploading code.**
- Oracle Cloud's regional billing hub for Asia-Pacific is located in **Singapore** (`Oracle Corporation Singapore Pte Ltd`).
- To prevent bot spam and disposable card fraud, Oracle periodically issues a **temporary authorization hold** of **$1.00 USD (or SGD 1.38)** to test that the card on file is active and genuine.
- When converted to Indian Rupees (INR) at daily forex exchange rates + standard bank currency conversion markup, it amounts to **exactly ₹102.xx**.
- **Crucial Rule:** In normal operations, this is a **hold** that is **automatically reversed / refunded within 3 to 7 business days**.
- If you disabled online or international transactions on your card, your bank **declined** this authorization test, causing Oracle's automated system to send a warning: *"Transaction declined: please update your payment method"*.

---

### 🛡️ How to Check Your Actual Bill (Confirming ₹0.00) in Oracle Console:
1. Log in to [Oracle Cloud Console](https://cloud.oracle.com).
2. Open the main navigation menu (top-left ☰ hamburger icon).
3. Scroll down and click **Billing & Cost Management** $\to$ **Cost Analysis**.
4. Set the date filter to **Current Month**.
5. You will see your total billed amount is **₹0.00** ($0.00).
6. Click **Billing & Cost Management** $\to$ **Invoices** to confirm there are **0 unpaid invoices**.

---

### 🔔 How to Set Up a ₹1.00 Budget Alert (Never Get Charged Surprises):
1. In Oracle Cloud Console, open the navigation menu (☰).
2. Go to **Billing & Cost Management** $\to$ **Budgets**.
3. Click **Create Budget**.
4. Configure:
   - **Name:** `Zero-Cost-Safety-Alert`
   - **Target Type:** Cost Tracking Tag or Compartment (select your root compartment)
   - **Monthly Budget Amount:** `1` (₹1 or $1)
   - **Threshold Metric:** Actual Spend
   - **Threshold (%):** `100`%
   - **Recipient Email:** Your personal email address
5. Click **Create**.
6. **Result:** If your cloud account ever consumes even ₹1 of paid services, Oracle will instantly email you an emergency warning.

---

### ✅ How to Verify Every Resource is "Always Free Eligible":
1. **Compute Instance:**
   - Go to **Compute** $\to$ **Instances** $\to$ click `stockai-server`.
   - Next to the shape `VM.Standard.A1.Flex`, confirm the grey tag: **"Always Free Eligible"**.
2. **Boot Volume:**
   - Go to **Storage** $\to$ **Block Storage** $\to$ **Boot Volumes**.
   - Confirm size is `46.6 GB` or `50 GB` (Free limit is up to **200 GB**).
3. **Public IP:**
   - Go to **Networking** $\to$ **Virtual Cloud Networks** $\to$ **Reserved Public IPs**.
   - Ensure there are **no unattached reserved IPs** (unattached reserved IPs incur a small hourly fee). An ephemeral IP attached to a running instance is 100% free.
4. **Always Free Filter / Toggle:**
   - Whenever viewing or provisioning in Oracle Cloud, look for the toggle switch labeled:
     **"Show only Always Free eligible options"**. Ensure this toggle is always kept ON.

