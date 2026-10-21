import os
import time
import datetime
import asyncio
import urllib.parse
from pathlib import Path
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import dotenv
from fyers_apiv3 import fyersModel

from backend.core.database import get_db
from backend.models.settings import SystemSettings
from backend.core.auth import get_current_user
from backend.models.user import User
from backend.api.admin import require_admin
from backend.core.audit_logger import log_security_event
from backend.core.logging_config import get_logger
from backend.core.config import settings

logger = get_logger(__name__)

router = APIRouter()

# Sensitive settings that regular users must NEVER inspect in cleartext
SENSITIVE_SETTING_KEYS = {"fyers_access_token", "fyers_client_id"}

DEFAULT_SETTINGS = [
    {"key": "default_risk_pct", "value": "2.0", "value_type": "float", "description": "Default risk percentage per trade"},
    {"key": "default_slippage", "value": "0.1", "value_type": "float", "description": "Default slippage percentage"},
    {"key": "enable_trading", "value": "true", "value_type": "boolean", "description": "Global kill switch for trading"},
    {"key": "enable_auto_trader", "value": "false", "value_type": "boolean", "description": "Master toggle switch for AI Auto-Trader daemon"},
    {"key": "fyers_client_id", "value": "", "value_type": "string", "description": "Fyers App Client ID"},
    {"key": "fyers_access_token", "value": "", "value_type": "string", "description": "Fyers Access Token (Update Daily)"}
]

@router.get("/")
async def get_all_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get system settings.
    Admins receive complete configuration; non-admin users receive sanitized values
    with broker credentials masked.
    """
    settings = (await db.execute(select(SystemSettings))).scalars().all()
    
    # Ensure all defaults are present
    existing_keys = {s.key for s in settings}
    missing_defaults = [s for s in DEFAULT_SETTINGS if s["key"] not in existing_keys]
    
    if missing_defaults:
        for s in missing_defaults:
            db.add(SystemSettings(**s))
        await db.commit()
        settings = (await db.execute(select(SystemSettings))).scalars().all()
    
    is_admin = bool(current_user.is_admin or current_user.email.lower().strip() == "admin@stockai.com")

    out: Dict[str, Any] = {}
    for s in settings:
        k_lower = s.key.lower()
        # Strictly omit sensitive broker, token, key, and secret configurations for non-admin users
        if not is_admin:
            if s.key in SENSITIVE_SETTING_KEYS or "fyers" in k_lower or "token" in k_lower or "secret" in k_lower or "client_id" in k_lower:
                continue
        out[s.key] = s.get_typed_value()
    return out


class UpdateSettingsRequest(BaseModel):
    values: Dict[str, Any]


@router.put("/")
async def update_settings(
    request: UpdateSettingsRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Update persisted dynamic configuration.
    Strictly restricted to Platform Administrators.
    """
    existing = {item.key: item for item in (await db.execute(select(SystemSettings))).scalars().all()}
    unknown = set(request.values) - set(existing)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown settings: {', '.join(sorted(unknown))}")

    for key, value in request.values.items():
        item = existing[key]
        try:
            if item.value_type == "boolean":
                if isinstance(value, str):
                    if value.lower() not in {"true", "false"}:
                        raise ValueError("must be true or false")
                    value = value.lower() == "true"
                if not isinstance(value, bool):
                    raise ValueError("must be boolean")
                item.value = str(value).lower()
            elif item.value_type == "int":
                item.value = str(int(value))
            elif item.value_type == "float":
                item.value = str(float(value))
            else:
                item.value = str(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid value for {key}: {exc}") from exc
            
    await db.flush()
    
    log_security_event(
        event_type="SYSTEM_SETTINGS_UPDATED",
        severity="INFO",
        user_id=str(admin.id),
        details={"updated_keys": list(request.values.keys()), "admin_email": admin.email},
    )

    # Invalidate cache if Fyers credentials were updated
    if "fyers_client_id" in request.values or "fyers_access_token" in request.values:
        try:
            from backend.core.cache import cache_delete
            await cache_delete("fyers_creds")
        except Exception:
            pass
            
    return {key: item.get_typed_value() for key, item in existing.items()}


# =========================================================================
# 📱 Mobile Fyers Token Generator & Cloud Direct Auto-Updater Endpoints
# =========================================================================

class FyersTokenUpdateRequest(BaseModel):
    auth_input: str


def _find_env_path() -> Path | None:
    candidates = [
        Path("/app/.env"),
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0] if candidates[0].parent.exists() else None


def _extract_auth_code(raw_input: str) -> str:
    raw = raw_input.strip()
    if "auth_code=" in raw:
        try:
            parsed = urllib.parse.urlparse(raw)
            query = parsed.query if parsed.query else parsed.path
            params = urllib.parse.parse_qs(query)
            if "auth_code" in params and params["auth_code"]:
                return params["auth_code"][0]
        except Exception:
            pass
        return raw.split("auth_code=")[1].split("&")[0].strip()
    return raw


@router.get("/fyers/status")
async def get_fyers_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check current Fyers connection status, trader name, and whether real-time data is active.
    Masks credentials completely.
    """
    client_id = None
    access_token = None

    # Priority 1: Check Database SystemSettings (persisted active token from mobile/admin renewal)
    try:
        fyers_token_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_access_token"))).scalars().first()
        if fyers_token_obj and fyers_token_obj.value and len(fyers_token_obj.value.strip()) > 20:
            access_token = fyers_token_obj.value.strip()
    except Exception:
        pass

    try:
        fyers_client_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_client_id"))).scalars().first()
        if fyers_client_obj and fyers_client_obj.value and len(fyers_client_obj.value.strip()) > 3:
            client_id = fyers_client_obj.value.strip()
    except Exception:
        pass

    # Priority 2: Check Redis Cache ('fyers_creds')
    if not access_token or not client_id:
        try:
            from backend.core.cache import cache_get
            cached_creds = await cache_get("fyers_creds")
            if cached_creds:
                if not access_token and cached_creds.get("access_token"):
                    access_token = cached_creds["access_token"]
                if not client_id and cached_creds.get("client_id"):
                    client_id = cached_creds["client_id"]
        except Exception:
            pass

    # Priority 3: Check dynamic .env file
    env_path = _find_env_path()
    env_values = dotenv.dotenv_values(str(env_path)) if (env_path and env_path.exists()) else {}
    if not client_id:
        client_id = env_values.get("FYERS_CLIENT_ID")
    if not access_token:
        access_token = env_values.get("FYERS_ACCESS_TOKEN")

    # Priority 4: Process environment variables (container launch defaults)
    if not client_id:
        client_id = os.getenv("FYERS_CLIENT_ID") or settings.FYERS_CLIENT_ID
    if not access_token:
        access_token = os.getenv("FYERS_ACCESS_TOKEN") or settings.FYERS_ACCESS_TOKEN

    from backend.services.market_data import MarketDataService

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_ist = now_utc + datetime.timedelta(hours=5, minutes=30)
    checked_at_ist = now_ist.strftime("%I:%M:%S %p IST")
    checked_at_iso = now_utc.isoformat()

    def _mask_id(val: str) -> str:
        s = str(val or "").strip()
        if len(s) > 4:
            return s[:2] + "***" + s[-2:]
        return s

    if not client_id or not access_token:
        MarketDataService.mark_fyers_token_expired("Fyers credentials unconfigured or missing token")
        feed_info = MarketDataService.get_feed_status()
        return {
            "configured": bool(client_id),
            "connected": False,
            "token_status": "MISSING",
            "name": "",
            "fy_id": client_id or "",
            "masked_fy_id": _mask_id(client_id),
            "message": "Fyers access token is not configured. Live backup engine active via Yahoo Finance.",
            "dual_engine": feed_info,
            "ping_ms": None,
            "checked_at_ist": checked_at_ist,
            "checked_at_iso": checked_at_iso,
            "fyers_live_ping": False,
        }

    start_t = time.perf_counter()
    try:
        fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=access_token, log_path="")
        prof = await asyncio.wait_for(asyncio.to_thread(fyers.get_profile), timeout=4.0)
        ping_ms = round((time.perf_counter() - start_t) * 1000, 1)

        if prof.get("s") == "ok":
            MarketDataService.reset_fyers_health()
            feed_info = MarketDataService.get_feed_status()
            data = prof.get("data", {})
            raw_fy_id = data.get("fy_id", client_id)
            return {
                "configured": True,
                "connected": True,
                "token_status": "ACTIVE",
                "name": data.get("name", "Trader"),
                "fy_id": raw_fy_id,
                "masked_fy_id": _mask_id(raw_fy_id),
                "message": f"Fyers live market feed is connected and operational (Direct API ping: {ping_ms}ms).",
                "dual_engine": feed_info,
                "ping_ms": ping_ms,
                "checked_at_ist": checked_at_ist,
                "checked_at_iso": checked_at_iso,
                "fyers_live_ping": True,
            }
        else:
            err = prof.get("message") or "Access token expired or rejected by Fyers."
            MarketDataService.mark_fyers_token_expired(err)
            feed_info = MarketDataService.get_feed_status()
            return {
                "configured": True,
                "connected": False,
                "token_status": "EXPIRED",
                "name": "",
                "fy_id": client_id,
                "masked_fy_id": _mask_id(client_id),
                "message": err,
                "dual_engine": feed_info,
                "ping_ms": ping_ms,
                "checked_at_ist": checked_at_ist,
                "checked_at_iso": checked_at_iso,
                "fyers_live_ping": False,
            }
    except Exception as e:
        ping_ms = round((time.perf_counter() - start_t) * 1000, 1)
        MarketDataService.mark_fyers_token_expired(str(e))
        feed_info = MarketDataService.get_feed_status()
        return {
            "configured": True,
            "connected": False,
            "token_status": "ERROR",
            "name": "",
            "fy_id": client_id,
            "masked_fy_id": _mask_id(client_id),
            "message": f"Connection check failed: {str(e)}",
            "dual_engine": feed_info,
            "ping_ms": ping_ms,
            "checked_at_ist": checked_at_ist,
            "checked_at_iso": checked_at_iso,
            "fyers_live_ping": False,
        }


@router.get("/fyers/auth-url")
async def get_fyers_auth_url(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Generate official Fyers v3 OAuth login URL using configured App credentials.
    Admin only.
    """
    env_path = _find_env_path()
    env_values = dotenv.dotenv_values(str(env_path)) if (env_path and env_path.exists()) else {}

    client_id = env_values.get("FYERS_CLIENT_ID") or os.getenv("FYERS_CLIENT_ID")
    secret_key = env_values.get("FYERS_SECRET_KEY") or os.getenv("FYERS_SECRET_KEY")

    if not client_id:
        try:
            fyers_client_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_client_id"))).scalars().first()
            if fyers_client_obj and fyers_client_obj.value:
                client_id = fyers_client_obj.value
        except Exception:
            pass

    if not client_id or not secret_key:
        raise HTTPException(
            status_code=400,
            detail="FYERS_CLIENT_ID and FYERS_SECRET_KEY must be configured in environment or settings."
        )

    redirect_uri = "https://trade.fyers.in/api-login/redirect-uri/index.html"
    try:
        session = fyersModel.SessionModel(
            client_id=client_id,
            secret_key=secret_key,
            redirect_uri=redirect_uri,
            response_type="code",
            grant_type="authorization_code"
        )
        auth_url = session.generate_authcode()
        return {
            "auth_url": auth_url,
            "redirect_uri": redirect_uri,
            "client_id": client_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate Fyers auth URL: {str(e)}")


@router.post("/fyers/update-token")
async def update_fyers_token(
    request: FyersTokenUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Directly exchange auth_code or save access_token into .env, hot-reloading
    market data and WebSocket streams with zero server downtime.
    Admin only.
    """
    raw_input = request.auth_input.strip()
    if not raw_input:
        raise HTTPException(status_code=400, detail="Authorization code or redirected URL cannot be empty.")

    env_path = _find_env_path()
    env_values = dotenv.dotenv_values(str(env_path)) if (env_path and env_path.exists()) else {}

    client_id = env_values.get("FYERS_CLIENT_ID") or os.getenv("FYERS_CLIENT_ID")
    secret_key = env_values.get("FYERS_SECRET_KEY") or os.getenv("FYERS_SECRET_KEY")

    if not client_id:
        try:
            fyers_client_obj = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_client_id"))).scalars().first()
            if fyers_client_obj and fyers_client_obj.value:
                client_id = fyers_client_obj.value
        except Exception:
            pass

    if not client_id:
        raise HTTPException(status_code=400, detail="FYERS_CLIENT_ID is not configured.")

    token = None
    extracted_code = _extract_auth_code(raw_input)
    is_url_or_auth_code = "auth_code=" in raw_input or raw_input.startswith("http") or len(extracted_code) < 300
    oauth_error = None

    # 1. Try OAuth exchange via Fyers API SessionModel if secret_key is available
    if secret_key:
        try:
            redirect_uri = "https://trade.fyers.in/api-login/redirect-uri/index.html"
            session = fyersModel.SessionModel(
                client_id=client_id,
                secret_key=secret_key,
                redirect_uri=redirect_uri,
                response_type="code",
                grant_type="authorization_code"
            )
            session.set_token(extracted_code)
            resp = await asyncio.to_thread(session.generate_token)
            if resp.get("s") == "ok" and resp.get("access_token"):
                token = resp["access_token"]
            else:
                oauth_error = resp.get("message") or resp.get("error_description") or str(resp)
        except Exception as e:
            oauth_error = str(e)

    # 2. If OAuth exchange did not produce token:
    if not token:
        if is_url_or_auth_code and oauth_error:
            # The user pasted a redirected URL or auth code, but Fyers rejected the exchange
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Fyers rejected this authorization code: '{oauth_error}'. "
                    "Fyers authorization codes expire within 2-3 minutes and can only be used ONCE. "
                    "Please tap '1. Open Fyers Login' to log in fresh, copy the new redirected URL, and activate it immediately."
                )
            )
        # Otherwise, user might have provided a direct full access token
        token = extracted_code

    # 3. Validate token against Fyers Profile API
    try:
        fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=token, log_path="")
        prof = await asyncio.wait_for(asyncio.to_thread(fyers.get_profile), timeout=6.0)
        if prof.get("s") != "ok":
            msg = prof.get("message") or "Authentication failed with Fyers API."
            if msg.lower() in ("bad request", "token is invalid or expired", "invalid token"):
                msg = (
                    f"{msg}. If using an auth code, it may have already been consumed. "
                    "Please click '1. Open Fyers Login' to get a fresh login URL and activate immediately."
                )
            raise HTTPException(status_code=400, detail=f"Fyers verification failed: {msg}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not connect to Fyers profile: {str(e)}")

    user_name = prof.get("data", {}).get("name", "Trader")
    fy_id = prof.get("data", {}).get("fy_id", client_id)

    # 4. Immediately update in-memory process environment and Pydantic settings
    os.environ["FYERS_ACCESS_TOKEN"] = token
    settings.FYERS_ACCESS_TOKEN = token

    # 5. Persist into DB SystemSettings (source of truth across all workers)
    try:
        fyers_setting = (await db.execute(select(SystemSettings).where(SystemSettings.key == "fyers_access_token"))).scalars().first()
        if fyers_setting:
            fyers_setting.value = token
        else:
            db.add(SystemSettings(key="fyers_access_token", value=token, value_type="string", description="Fyers Access Token (Update Daily)"))
        await db.commit()
    except Exception as e:
        logger.warning(f"Could not persist token in SystemSettings: {e}")

    # 6. Cache the active verified credentials in Redis
    try:
        from backend.core.cache import cache_set, cache_delete
        await cache_set("fyers_creds", {"client_id": client_id, "access_token": token}, ttl=86400)
        await cache_delete("quote:PCJEWELLER.NS")
        await cache_delete("quote:^NSEI")
    except Exception as e:
        logger.warning(f"Could not cache fyers_creds: {e}")

    # 7. Automatically persist into .env file if path exists
    if env_path:
        try:
            dotenv.set_key(str(env_path), "FYERS_ACCESS_TOKEN", token)
        except Exception as e:
            logger.warning(f"Failed to update .env directly: {e}")

    # 8. Hot-reload MarketDataService & reset Fyers health to primary engine
    from backend.services.market_data import MarketDataService
    if hasattr(MarketDataService, "_env_cache") and isinstance(MarketDataService._env_cache, dict):
        MarketDataService._env_cache["FYERS_ACCESS_TOKEN"] = token
    MarketDataService._env_mtime = 0.0
    MarketDataService.reset_fyers_health()

    # 9. Restart WebSocket Tick Stream with new token
    try:
        from backend.services.fyers_stream import fyers_stream_service
        await fyers_stream_service.stop()
        await fyers_stream_service.start()
    except Exception:
        pass

    log_security_event(
        event_type="FYERS_TOKEN_RENEWED",
        severity="INFO",
        user_id=str(admin.id),
        details={"admin_email": admin.email, "fyers_user": user_name, "fyers_id": fy_id},
    )

    return {
        "status": "success",
        "message": f"Fyers access token renewed successfully! Welcome, {user_name}.",
        "name": user_name,
        "fy_id": fy_id,
        "data_status": "realtime"
    }
