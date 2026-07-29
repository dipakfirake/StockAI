"""
AI Stock Research Platform — FastAPI Application Entry Point

Platform: India-first stock research (NSE/BSE)
Purpose: Research, analytics, alerts, paper trading, backtesting
NOT a broker — never executes real trades.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.core.database import create_db_tables
from backend.core.logging_config import setup_logging
from backend.api import stocks, alerts, paper_trading, backtesting, ai_engine, portfolio, watchlist, auth, market, scanner, ml, settings as api_settings, notifications
from backend.api.websocket import ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    setup_logging()
    await create_db_tables()
    
    # Start WebSocket market data poller
    from backend.api.websocket import poll_market_data
    import asyncio
    task = asyncio.create_task(poll_market_data())
    
    yield
    
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    # Cleanup on shutdown


app = FastAPI(
    title="AI Stock Research Platform",
    description=(
        "Open-source, India-first, AI-powered investment research platform. "
        "Provides research, analytics, alerts, paper trading, and backtesting. "
        "NOT a broker. No real trade execution."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Routers ---
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["Stocks"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["Watchlist"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(paper_trading.router, prefix="/api/paper-trades", tags=["Paper Trading"])
app.include_router(backtesting.router, prefix="/api/backtest", tags=["Backtesting"])
app.include_router(ai_engine.router, prefix="/api/ai", tags=["AI Engine"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(market.router, prefix="/api/market", tags=["Market"])
app.include_router(scanner.router, prefix="/api/scanner", tags=["Scanner"])
app.include_router(ml.router, prefix="/api/ml", tags=["Machine Learning"])
app.include_router(api_settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(ws_router)


@app.get("/", tags=["Health"])
async def root():
    return {"message": "AI Stock Research Platform API", "version": "0.1.0", "status": "running"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}
