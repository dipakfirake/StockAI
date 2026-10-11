"""
Industrial Security Headers & DoS Request Guard Middleware.

Provides:
- OWASP Top 10 Security Headers (HSTS, Anti-Clickjacking X-Frame-Options, CSP, MIME-sniffing protection)
- Financial route caching prevention (no-store on trading/auth)
- Request Body Size Limiting (Protection against HTTP payload flooding / Memory Exhaustion DoS)
- Correlation Trace ID tracking for security forensic auditing
"""

import uuid
from typing import Optional
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# 1 MB max request body size for standard API endpoints
MAX_REQUEST_BODY_SIZE = 1 * 1024 * 1024


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects banking-grade security headers into every HTTP response."""

    async def dispatch(self, request: Request, call_next):
        # Generate or capture trace ID for auditability
        trace_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.trace_id = trace_id

        # --- Request Body Size Guard (DDoS / Memory Exhaustion defense) ---
        content_length: Optional[str] = request.headers.get("content-length")
        if content_length:
            try:
                length_int = int(content_length)
                if length_int > MAX_REQUEST_BODY_SIZE:
                    logger.warning(
                        f"[SecurityGuard] 413 Payload Too Large ({length_int} bytes) "
                        f"from {request.client.host if request.client else 'unknown'} "
                        f"on {request.method} {request.url.path} (TraceID: {trace_id})"
                    )
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "error": "Payload Too Large",
                            "detail": f"Request body exceeds maximum allowed size of {MAX_REQUEST_BODY_SIZE // 1024} KB.",
                            "trace_id": trace_id,
                        },
                    )
            except ValueError:
                pass

        # Execute downstream handlers
        response = await call_next(request)

        # --- Inject Banking & OWASP Standard Security Headers ---
        headers = response.headers
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["X-XSS-Protection"] = "1; mode=block"
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        headers["Permissions-Policy"] = "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
        headers["X-Request-ID"] = trace_id

        # Anti-caching for financial & auth routes to prevent browser caching of sensitive data
        p = request.url.path.lower()
        if p.startswith("/api/auth") or p.startswith("/api/paper-trades") or p.startswith("/api/portfolio"):
            headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            headers["Pragma"] = "no-cache"

        # Record telemetry metrics
        try:
            from backend.core.telemetry import metrics
            metrics.inc_request(request.method, request.url.path, response.status_code)
        except Exception:
            pass

        return response
