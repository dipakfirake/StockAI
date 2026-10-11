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
- **Live Vercel Frontend:** [https://stock-ai-iota-seven.vercel.app](https://stock-ai-iota-seven.vercel.app)
- **FastAPI Swagger Docs:** [http://92.4.71.210:8000/docs](http://92.4.71.210:8000/docs)
- **Celery Flower Dashboard:** [http://92.4.71.210:5555](http://92.4.71.210:5555)
- **Backend Health Probe:** [http://92.4.71.210:8000/health/live](http://92.4.71.210:8000/health/live)

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
