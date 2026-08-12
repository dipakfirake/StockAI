@echo off
echo Starting Stock Prediction System...

echo Starting Backend...
start "Backend Server" cmd /k "cd /d "D:\Stock Prediction System\backend" && .\venv\Scripts\Activate.bat && python -m uvicorn main:app --reload --port 8000"

echo Starting Frontend...
start "Frontend Server" cmd /k "cd /d "D:\Stock Prediction System\frontend" && npm run dev"

echo Both servers are starting up!
echo - Backend API: http://127.0.0.1:8000
echo - Frontend UI: http://localhost:5173
