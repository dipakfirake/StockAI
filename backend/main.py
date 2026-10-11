"""
AI Stock Research Platform — FastAPI Application Entry Point

Platform: India-first stock research (NSE/BSE)
Purpose: Research, analytics, alerts, paper trading, backtesting
NOT a broker — never executes real trades.
"""

import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.core.database import create_db_tables
from backend.core.logging_config import setup_logging, get_logger
from backend.core.rate_limiter import RateLimitMiddleware
from backend.core.security_middleware import SecurityHeadersMiddleware
from backend.core.audit_logger import log_security_event
from backend.api import stocks, alerts, paper_trading, backtesting, ai_engine, portfolio, watchlist, auth, market, scanner, ml, settings as api_settings, notifications, preferences
from backend.api.websocket import ws_router

logger = get_logger(__name__)


from backend.core.lifecycle import lifecycle
from backend.core.telemetry import router as telemetry_router, metrics

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle managed by enterprise LifecycleManager."""
    await lifecycle.startup()
    
    # Start WebSocket market data poller and daemons, registered for graceful shutdown
    from backend.api.websocket import poll_market_data
    from backend.tasks.screener_poller import poll_screener_cache
    from backend.tasks.auto_trader import auto_trader_loop
    import asyncio
    
    task1 = asyncio.create_task(poll_market_data())
    task2 = asyncio.create_task(poll_screener_cache())
    task3 = asyncio.create_task(auto_trader_loop())
    
    lifecycle.register_task(task1)
    lifecycle.register_task(task2)
    lifecycle.register_task(task3)
    
    yield
    
    await lifecycle.shutdown()


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

# --- 1. Security Headers & Request Body Size Guard Middleware ---
app.add_middleware(SecurityHeadersMiddleware)

# --- 2. Industrial Token Bucket Rate Limiting Middleware ---
app.add_middleware(RateLimitMiddleware)

# --- 3. CORS Configuration ---
# Allow explicit trusted frontend origins in production, or localhost during development
allowed_origins = list(settings.CORS_ORIGINS)
if "http://localhost:5173" not in allowed_origins:
    allowed_origins.append("http://localhost:5173")
if "http://127.0.0.1:5173" not in allowed_origins:
    allowed_origins.append("http://127.0.0.1:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if not settings.DEBUG else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=[
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "X-RateLimit-Tier",
        "X-Idempotent-Replay",
        "Retry-After",
        "X-Request-ID",
    ],
)


# --- 4. Sanitized Global Exception Handler (Anti-Information Leakage) ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from fastapi import HTTPException as FastAPIHTTPException

    # Preserve explicit HTTP error codes (400, 401, 403, 404, 409, 422, 429)
    if isinstance(exc, (FastAPIHTTPException, StarletteHTTPException)):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )
    if isinstance(exc, RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    trace_id = getattr(request.state, "trace_id", "N/A")
    client_ip = request.client.host if request.client else "unknown"
    
    # Secure internal logging with full stacktrace
    logger.error(
        f"[UnhandledException] TraceID: {trace_id} Path: {request.url.path} from {client_ip}: {exc}",
        exc_info=True,
    )
    log_security_event(
        event_type="UNHANDLED_EXCEPTION",
        severity="CRITICAL",
        ip_address=client_ip,
        trace_id=trace_id,
        details={"path": request.url.path, "error": str(exc)},
    )
    
    # Sanitized response for external clients (never leaks DB connections, file paths, or credentials)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred. The incident has been logged for security review.",
            "trace_id": trace_id,
        },
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
app.include_router(preferences.router, prefix="/api/preferences", tags=["Preferences"])
app.include_router(ws_router)
app.include_router(telemetry_router)


@app.get("/metrics", tags=["Observability & Telemetry"])
async def prometheus_metrics_root():
    """Prometheus-compatible scraping endpoint."""
    from fastapi import Response
    return Response(content=metrics.generate_prometheus_text(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/", tags=["Health"])
async def root():
    return {"message": "AI Stock Research Platform API", "version": "0.1.0", "status": "running"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}


@app.get("/health/live", tags=["Health"])
@app.get("/health/liv", include_in_schema=False)
async def health_live_root():
    import time
    from datetime import datetime, timezone
    from backend.core.telemetry import START_TIME
    return {
        "status": "alive",
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

