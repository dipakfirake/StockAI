# 100% Free Live Deployment Guide

This guide will walk you through hosting your complete Stock Prediction System (Frontend, Backend, Database, and Redis) online for **100% free** using the best free tiers available today.

## Stack Overview
- **Database (PostgreSQL)**: [Neon Serverless Postgres](https://neon.tech/) (Generous free tier)
- **Redis Cache**: [Upstash Redis](https://upstash.com/) (Generous free tier)
- **Backend (FastAPI)**: [Render](https://render.com/) (Free Web Service)
- **Frontend (React/Vite)**: [Vercel](https://vercel.com/) (Free Tier)

---

## 1. Setup Neon Serverless Postgres (Database)
1. Go to [Neon.tech](https://neon.tech/) and sign up.
2. Create a new project (e.g., `StockPredictionDB`).
3. Once created, go to the **Dashboard** and copy the **Connection String** (it starts with `postgresql://...`).
4. **Important**: Save this connection string; you will need it for the backend `.env`.

---

## 2. Setup Upstash Redis (Cache)
1. Go to [Upstash.com](https://upstash.com/) and sign up.
2. Create a new Redis database (Global, choose the region closest to your users).
3. Scroll down to the **Connect** section, choose **Redis Connect** (or URI), and copy the URI (it starts with `rediss://...`).
4. **Important**: Save this connection string for the backend `.env`.

---

## 3. Host Backend on Render
1. Push your entire repository to a free GitHub account.
2. Go to [Render.com](https://render.com/) and sign up with GitHub.
3. Click **New +** and select **Web Service**.
4. Connect your GitHub repository.
5. **Configuration**:
   - **Name**: `stock-backend`
   - **Root Directory**: `backend` (if your backend is inside the `backend` folder)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port 10000`
   - **Instance Type**: Select **Free**.
6. **Environment Variables**:
   Add the following variables:
   - `DATABASE_URL` = (Paste your Neon Postgres connection string here)
   - `REDIS_URL` = (Paste your Upstash Redis URI here)
   - `JWT_SECRET_KEY` = (A random long string)
   - `FYERS_CLIENT_ID` = (Your default Client ID)
   - `FYERS_ACCESS_TOKEN` = (Leave blank or paste initial token)
7. Click **Create Web Service**. Wait for the deployment to finish.
8. Copy the **Render URL** (e.g., `https://stock-backend-xyz.onrender.com`).

---

## 4. Host Frontend on Vercel
1. Go to [Vercel.com](https://vercel.com/) and sign up with GitHub.
2. Click **Add New Project**.
3. Import your GitHub repository.
4. **Configuration**:
   - **Root Directory**: Select the `frontend` folder.
   - **Framework Preset**: Vite
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
5. **Environment Variables**:
   Add the following variables to point to your live backend:
   - `VITE_API_URL` = `https://stock-backend-xyz.onrender.com/api` (Replace with your actual Render URL).
6. Click **Deploy**.
7. Once finished, Vercel will give you a live domain (e.g., `https://stock-frontend.vercel.app`).

---

## 5. How to Handle Fyers Daily API Key Constraint
Since Fyers requires you to generate a new API token every day, updating the Render `.env` file every day is tedious because it forces the server to restart and spin up again (which takes several minutes on the free tier).

**The Solution:**
We have modified the system so that your Fyers API Keys are now stored dynamically in the Database and Cached in Redis.

**Daily Workflow:**
1. Run your `generate_fyers_token.bat` on your local PC as you always do, log in, and copy the newly generated Access Token.
2. Log into your live Vercel Frontend (e.g., `https://stock-frontend.vercel.app`).
3. Navigate to the **Settings** page in the left sidebar.
4. You will see fields for **Fyers Client Id** and **Fyers Access Token**.
5. Paste your new daily Access Token into the input field and click **Save Configuration**.
6. **Done!** The system will instantly invalidate the old cache and start using the new token for all live market data and chart requests without needing a server restart.

---

### Important Free Tier Notes:
- **Render Inactivity:** Render's free tier spins down your backend if there is no web traffic for 15 minutes. When you open your app after 15 minutes, the first API request will take about ~30-50 seconds to respond while the backend wakes up.
- **Neon Scaling:** Neon is serverless and scales to zero, meaning it also pauses when inactive, but it wakes up in milliseconds, so it is barely noticeable.
