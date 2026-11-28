"""
Industrial Security Headers & DoS Request Guard Middleware.

Provides:
- OWASP Top 10 Security Headers (HSTS, Anti-Clickjacking X-Frame-Options, CSP, MIME-sniffing protection)
- Financial route caching prevention (no-store on trading/auth)
- Request Body Size Limiting (Protection against HTTP payload flooding / Memory Exhaustion DoS)
- Correlation Trace ID tracking for security forensic auditing
"""

import hmac
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

        # --- Double-Submit CSRF Guard for Cookie-Authenticated Mutations ---
        # Exempt explicit Authorization Bearer API callers, public pre-auth routes, and sendBeacon leaves.
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            auth_hdr = request.headers.get("Authorization", "")
            cookies = getattr(request, "cookies", None) or {}
            has_auth_cookie = bool(cookies.get("stockai_access_token"))
            path_l = request.url.path.lower()
            csrf_exempt = {
                "/api/auth/login",
                "/api/auth/register",
                "/api/auth/google",
                "/api/auth/send-registration-otp",
                "/api/auth/verify-registration-otp",
                "/api/auth/mfa/verify-login",
                "/api/auth/logout",
                "/api/presence/leave",
            }
            if has_auth_cookie and not auth_hdr.startswith("Bearer ") and path_l not in csrf_exempt:
                cookie_csrf = cookies.get("stockai_csrf_token") or ""
                header_csrf = request.headers.get("X-CSRF-Token") or ""
                if not cookie_csrf or not header_csrf or not hmac.compare_digest(cookie_csrf, header_csrf):
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "CSRF token validation failed", "trace_id": trace_id},
                    )

        # Execute downstream handlers
        try:
            response = await call_next(request)
        except RuntimeError as exc:
            if "No response returned" in str(exc):
                response = Response(status_code=status.HTTP_204_NO_CONTENT)
            else:
                raise

        # --- Inject Banking & OWASP Standard Security Headers ---
        headers = response.headers
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "SAMEORIGIN"
        headers["X-XSS-Protection"] = "1; mode=block"
        headers["Referrer-Policy"] = "no-referrer"
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        headers["Permissions-Policy"] = "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
        headers["X-Request-ID"] = trace_id

        # Content-Security-Policy: remove 'unsafe-eval', restrict 'unsafe-inline' scripts strictly to /docs & /redoc
        p = request.url.path.lower()
        is_docs_route = p in ("/docs", "/redoc", "/openapi.json") or p.startswith("/docs/") or p.startswith("/redoc/")
        if is_docs_route:
            headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.redoc.ly; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdn.redoc.ly; "
                "font-src 'self' https://fonts.gstatic.com https://cdn.redoc.ly data:; "
                "img-src 'self' data: https: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
                "connect-src 'self' wss: ws: https:; "
                "frame-ancestors 'self'; "
                "object-src 'none'; "
                "base-uri 'self';"
            )
        else:
            headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' https://accounts.google.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com data:; "
                "img-src 'self' data: blob: https:; "
                "connect-src 'self' wss: ws: https://accounts.google.com https://oauth2.googleapis.com; "
                "frame-src https://accounts.google.com; "
                "worker-src 'self' blob:; "
                "frame-ancestors 'self'; "
                "object-src 'none'; "
                "base-uri 'self';"
            )

        # Anti-caching for all financial and user API routes to prevent browser/disk caching of user activity
        sensitive_prefixes = (
            "/api/auth",
            "/api/stocks",
            "/api/market",
            "/api/alerts",
            "/api/watchlist",
            "/api/paper-trades",
            "/api/portfolio",
            "/api/backtest",
            "/api/ai",
            "/api/scanner",
            "/api/settings",
            "/api/admin",
            "/api/subscription",
            "/api/notifications",
            "/api/sentinel",
            "/api/validator",
            "/api/swing-audit",
            "/api/preferences",
            "/metrics",
        )
        if any(p.startswith(prefix) for prefix in sensitive_prefixes):
            headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            headers["Pragma"] = "no-cache"

        # Record telemetry metrics
        try:
            from backend.core.telemetry import metrics
            metrics.inc_request(request.method, request.url.path, response.status_code)
        except Exception:
            pass

        return response
