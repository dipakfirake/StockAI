import uuid
import asyncio
import os
import secrets
import httpx
from typing import Optional, Tuple, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.config import settings
from backend.core.auth import verify_password, hash_password, create_access_token, get_current_user, oauth2_scheme
from backend.core.auth_security import validate_password_strength, brute_force_protector, validate_email_syntax, sanitize_display_name
from backend.core.audit_logger import log_security_event
from backend.core.email_intelligence import validate_email_for_registration, canonicalize_email
from backend.core.fraud_detection import fraud_detection_engine
from backend.services.email_service import email_otp_service
from backend.models.user import User

router = APIRouter()


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class RegisterResponse(BaseModel):
    user_id: str
    email: str
    name: str
    token: str


class SendOtpRequest(BaseModel):
    email: str
    password: str
    name: str


class VerifyOtpRequest(BaseModel):
    email: str
    otp: str


class GoogleAuthRequest(BaseModel):
    credential: str


class ClientTelemetryRequest(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    screen_resolution: Optional[str] = None
    consent_version: Optional[str] = None


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def _extract_geo_from_request(req: Request) -> Tuple[Optional[float], Optional[float]]:
    """Extract opt-in client geo coordinates from headers or query parameters."""
    try:
        lat_val = req.headers.get("X-Client-Geo-Lat") or req.query_params.get("lat")
        lon_val = req.headers.get("X-Client-Geo-Lon") or req.query_params.get("lon")
        if lat_val and lon_val:
            return float(lat_val), float(lon_val)
    except Exception:
        pass
    return None, None


@router.get("/config")
async def get_auth_config(db: AsyncSession = Depends(get_db)):
    """Public auth configuration containing client ID for Google Sign-In."""
    google_id = getattr(settings, "GOOGLE_CLIENT_ID", None) or os.getenv("GOOGLE_CLIENT_ID", "")
    if not google_id:
        try:
            from backend.models.settings import SystemSettings
            res = await db.execute(select(SystemSettings).where(SystemSettings.key == "google_client_id"))
            row = res.scalar_one_or_none()
            if row and row.value:
                google_id = row.value.strip()
        except Exception:
            pass

    return {
        "google_client_id": google_id or "",
        "email_otp_enabled": True,
    }


@router.post("/send-registration-otp")
async def send_registration_otp(request: SendOtpRequest, req: Request, db: AsyncSession = Depends(get_db)):
    """
    Validates user credentials against Anti-Temp-Mail heuristics and dispatches
    a 6-digit cryptographic verification OTP to the user's email.
    """
    client_ip = _get_client_ip(req)
    
    # 1. Enforce display name sanitization
    try:
        sanitized_name = sanitize_display_name(request.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Enforce email syntax and length
    try:
        clean_email = validate_email_syntax(request.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3. Enforce password complexity & length bounds
    try:
        validate_password_strength(request.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 4. Anti-Temp-Mail & Disposable Domain Validation
    email_check = await validate_email_for_registration(clean_email)
    if not email_check["valid"]:
        log_security_event(
            event_type="AUTH_OTP_DISPOSABLE_BLOCKED",
            severity="WARNING",
            ip_address=client_ip,
            details={"email": clean_email, "reason": email_check["reason"]},
        )
        raise HTTPException(status_code=422, detail=email_check["reason"])

    canonical = email_check["canonical_email"]
    raw = clean_email

    # 5. Check duplicate user in DB (check both raw and canonical)
    existing = await db.execute(select(User).where((User.email == raw) | (User.email == canonical)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="An account with this email address already exists. Please login.")

    # 6. Hash password before storing in Redis OTP payload
    hashed_pwd = hash_password(request.password)

    # 7. Dispatch OTP via EmailOtpService
    success, message, cooldown = await email_otp_service.request_registration_otp(
        canonical_email=canonical,
        user_name=sanitized_name,
        hashed_password=hashed_pwd,
        raw_email=raw
    )

    if not success:
        raise HTTPException(status_code=429, detail=message)

    return {
        "status": "success",
        "message": message,
        "canonical_email": canonical,
        "cooldown_seconds": cooldown,
        "expires_in": 300
    }


@router.post("/verify-registration-otp")
async def verify_registration_otp(request: VerifyOtpRequest, req: Request, db: AsyncSession = Depends(get_db)):
    """
    Verifies 6-digit OTP code. Upon successful verification, creates the user account
    in PostgreSQL and returns the authentication token and user profile.
    """
    client_ip = _get_client_ip(req)

    # 1. Enforce email syntax
    try:
        clean_email = validate_email_syntax(request.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Enforce strictly 6 numeric digits
    cleaned_otp = request.otp.strip()
    if not cleaned_otp.isdigit() or len(cleaned_otp) != 6:
        raise HTTPException(status_code=400, detail="Verification code must be exactly 6 numeric digits.")

    canonical = canonicalize_email(clean_email)[0]

    valid, reason, user_data = await email_otp_service.verify_registration_otp(
        canonical_email=canonical,
        entered_otp=cleaned_otp
    )
    if not valid or not user_data:
        raise HTTPException(status_code=400, detail=reason)

    email = user_data["email"].lower().strip()

    # Re-check race condition
    existing = await db.execute(select(User).where((User.email == email) | (User.email == canonical)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Account already registered. Please login.")

    is_admin = (email == "admin@stockai.com")
    new_user = User(
        id=uuid.uuid4(),
        email=email,
        name=user_data["name"],
        hashed_password=user_data["hashed_password"],
        is_active=True,
        is_admin=is_admin,
        subscription_tier="PRO" if is_admin else "FREE",
        pro_status="APPROVED" if is_admin else "NONE",
    )
    db.add(new_user)
    await db.flush()

    token = create_access_token({"sub": str(new_user.id)})
    log_security_event(
        event_type="AUTH_REGISTER_OTP_SUCCESS",
        severity="INFO",
        ip_address=client_ip,
        user_id=str(new_user.id),
        details={"email": new_user.email, "canonical": canonical},
    )

    user_payload = {
        "id": str(new_user.id),
        "email": new_user.email,
        "name": new_user.name,
        "subscription_tier": new_user.subscription_tier,
        "is_admin": is_admin,
        "pro_status": new_user.pro_status,
        "pro_requested_at": None,
    }
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_payload
    }


async def verify_google_id_token(cred: str) -> dict:
    """Verifies Google ID token against Google's official public tokeninfo endpoint."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={cred}")
            if resp.status_code != 200:
                raise HTTPException(status_code=401, detail="Google authentication failed or token has expired.")
            return resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to communicate with Google authentication server: {str(e)}")


@router.post("/google")
async def google_auth(request: GoogleAuthRequest, req: Request, db: AsyncSession = Depends(get_db)):
    """
    Verifies Google OAuth2 ID token, automatically registering or logging in real users.
    100% Free: uses Google tokeninfo cryptographic endpoint directly.
    """
    client_ip = _get_client_ip(req)
    cred = request.credential.strip()
    if not cred:
        raise HTTPException(status_code=400, detail="Missing Google credential token.")

    payload = await verify_google_id_token(cred)

    email = (payload.get("email") or "").lower().strip()
    email_verified = payload.get("email_verified")
    name = payload.get("name") or payload.get("given_name") or "Google User"

    if not email:
        raise HTTPException(status_code=400, detail="Google token does not contain a valid email address.")

    if str(email_verified).lower() not in ("true", "1"):
        raise HTTPException(status_code=403, detail="Unverified Google email accounts are not permitted.")

    # Optional: verify aud matches configured GOOGLE_CLIENT_ID if configured
    configured_client_id = getattr(settings, "GOOGLE_CLIENT_ID", None) or os.getenv("GOOGLE_CLIENT_ID")
    if configured_client_id and payload.get("aud") != configured_client_id:
        logger.warning(f"[GoogleAuth] Token audience mismatch: {payload.get('aud')} != {configured_client_id}")

    # Check if user already exists
    canonical = canonicalize_email(email)[0]
    result = await db.execute(select(User).where((User.email == email) | (User.email == canonical)))
    user = result.scalar_one_or_none()

    is_admin = (email == "admin@stockai.com")

    if not user:
        # Auto-provision new user with secure unguessable internal password hash
        new_user = User(
            id=uuid.uuid4(),
            email=email,
            name=name,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            is_active=True,
            is_admin=is_admin,
            subscription_tier="PRO" if is_admin else "FREE",
            pro_status="APPROVED" if is_admin else "NONE",
        )
        db.add(new_user)
        await db.flush()
        user = new_user
        log_security_event(
            event_type="AUTH_GOOGLE_REGISTER_SUCCESS",
            severity="INFO",
            ip_address=client_ip,
            user_id=str(user.id),
            details={"email": user.email, "name": user.name},
        )
    else:
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Account is deactivated")
        log_security_event(
            event_type="AUTH_GOOGLE_LOGIN_SUCCESS",
            severity="INFO",
            ip_address=client_ip,
            user_id=str(user.id),
            details={"email": user.email},
        )

    token = create_access_token({"sub": str(user.id)})
    user_is_admin = bool(user.is_admin or user.email.lower().strip() == "admin@stockai.com")

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "subscription_tier": "PRO" if user_is_admin else user.subscription_tier,
            "is_admin": user_is_admin,
            "pro_status": "APPROVED" if user_is_admin else (user.pro_status or "NONE"),
            "pro_requested_at": user.pro_requested_at.isoformat() if user.pro_requested_at else None,
        }
    }


@router.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest, req: Request, db: AsyncSession = Depends(get_db)):
    """Register a new user with password strength validation and Anti-Temp-Mail defense."""
    client_ip = _get_client_ip(req)

    # 1. Enforce display name sanitization
    try:
        sanitized_name = sanitize_display_name(request.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Enforce email syntax and RFC bounds
    try:
        clean_email = validate_email_syntax(request.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3. Enforce password complexity
    try:
        validate_password_strength(request.password)
    except ValueError as e:
        log_security_event(
            event_type="AUTH_REGISTER_REJECTED",
            severity="WARNING",
            ip_address=client_ip,
            details={"email": clean_email, "reason": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e))

    # 4. Anti-Temp-Mail & Disposable Domain Validation
    email_check = await validate_email_for_registration(clean_email)
    if not email_check["valid"]:
        log_security_event(
            event_type="AUTH_REGISTER_DISPOSABLE_BLOCKED",
            severity="WARNING",
            ip_address=client_ip,
            details={"email": clean_email, "reason": email_check["reason"]},
        )
        raise HTTPException(status_code=422, detail=email_check["reason"])

    canonical = email_check["canonical_email"]
    raw = clean_email

    existing = await db.execute(select(User).where((User.email == raw) | (User.email == canonical)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="An account with this email address already exists. Please login.")

    is_admin = raw == "admin@stockai.com"
    user = User(
        id=uuid.uuid4(),
        email=raw,
        name=sanitized_name,
        hashed_password=hash_password(request.password),
        is_active=True,
        is_admin=is_admin,
        subscription_tier="PRO" if is_admin else "FREE",
        pro_status="APPROVED" if is_admin else "NONE",
    )
    db.add(user)
    await db.flush()

    token = create_access_token({"sub": str(user.id)})
    log_security_event(
        event_type="AUTH_REGISTER_SUCCESS",
        severity="INFO",
        ip_address=client_ip,
        user_id=str(user.id),
        details={"email": user.email, "subscription_tier": user.subscription_tier},
    )
    return RegisterResponse(user_id=str(user.id), email=user.email, name=user.name, token=token)


@router.post("/login")
async def login(
    req: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login with brute-force lockout protection and security auditing."""
    client_ip = _get_client_ip(req)
    username = form_data.username.lower().strip()

    if not username or len(username) > 254:
        raise HTTPException(status_code=400, detail="Invalid email address length.")
    if len(form_data.password) > 128:
        raise HTTPException(status_code=400, detail="Password length exceeds maximum allowable limit.")

    # Check brute-force lockout
    brute_force_protector.check_lockout(client_ip, username)

    result = await db.execute(select(User).where(User.email == username))
    user = result.scalar_one_or_none()

    if not user:
        brute_force_protector.record_failure(client_ip, username)
        is_stuffing, stuffing_reason = fraud_detection_engine.record_failed_attempt(client_ip, username)
        log_security_event(
            event_type="AUTH_CREDENTIAL_STUFFING_ALERT" if is_stuffing else "AUTH_LOGIN_FAILED",
            severity="CRITICAL" if is_stuffing else "WARNING",
            ip_address=client_ip,
            details={"email": username, "reason": stuffing_reason or "User not found"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Offload CPU-intensive bcrypt to thread pool so async event loop never blocks
    is_valid = await asyncio.to_thread(verify_password, form_data.password, user.hashed_password)
    if not is_valid:
        brute_force_protector.record_failure(client_ip, username)
        is_stuffing, stuffing_reason = fraud_detection_engine.record_failed_attempt(client_ip, username)
        log_security_event(
            event_type="AUTH_CREDENTIAL_STUFFING_ALERT" if is_stuffing else "AUTH_LOGIN_FAILED",
            severity="CRITICAL" if is_stuffing else "WARNING",
            ip_address=client_ip,
            details={"email": username, "reason": stuffing_reason or "Invalid credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        log_security_event(
            event_type="AUTH_LOGIN_DEACTIVATED",
            severity="WARNING",
            ip_address=client_ip,
            user_id=str(user.id),
            details={"email": username},
        )
        raise HTTPException(status_code=400, detail="Account deactivated")

    # Evaluate industrial fraud signals (Impossible Travel, Device Shift)
    user_agent = req.headers.get("user-agent")
    client_lat, client_lon = _extract_geo_from_request(req)
    fraud_eval = fraud_detection_engine.evaluate_login_risk(
        email=user.email,
        user_id=str(user.id),
        ip_address=client_ip,
        user_agent=user_agent,
        client_lat=client_lat,
        client_lon=client_lon,
        is_registration=False,
    )
    if fraud_eval.is_blocked:
        log_security_event(
            event_type="AUTH_LOGIN_FRAUD_BLOCKED",
            severity="CRITICAL",
            ip_address=client_ip,
            user_id=str(user.id),
            details={
                "email": username,
                "anomalies": fraud_eval.anomalies,
                "risk_score": fraud_eval.risk_score,
                "cert_in_alert": True
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Login rejected: High-risk security anomaly detected ({', '.join(fraud_eval.anomalies)}). Contact support."
        )

    # Record success and reset failed attempts
    brute_force_protector.record_success(client_ip, username)
    token = create_access_token({"sub": str(user.id)})

    log_security_event(
        event_type="AUTH_LOGIN_SUCCESS",
        severity="INFO",
        ip_address=client_ip,
        user_id=str(user.id),
        details={"email": username, "risk_level": fraud_eval.risk_level},
    )

    is_admin = bool(user.is_admin or user.email.lower().strip() == "admin@stockai.com")
    user_payload = {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "subscription_tier": "PRO" if is_admin else user.subscription_tier,
        "is_admin": is_admin,
        "pro_status": "APPROVED" if is_admin else (user.pro_status or "NONE"),
        "pro_requested_at": user.pro_requested_at.isoformat() if user.pro_requested_at else None,
    }

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_payload,
    }



@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile with role and pro status."""
    is_admin = bool(current_user.is_admin or current_user.email.lower().strip() == "admin@stockai.com")
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "name": current_user.name,
        "subscription_tier": "PRO" if is_admin else current_user.subscription_tier,
        "is_admin": is_admin,
        "pro_status": "APPROVED" if is_admin else (current_user.pro_status or "NONE"),
        "pro_requested_at": current_user.pro_requested_at.isoformat() if current_user.pro_requested_at else None,
    }


@router.post("/upgrade")
async def upgrade_tier(current_user: User = Depends(get_current_user)):
    """Guarded endpoint: direct free self-upgrade is disallowed."""
    if current_user.subscription_tier == "PRO":
        return {"message": "Already on PRO tier", "subscription_tier": "PRO"}
    
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail="Direct self-upgrade is disabled. Please complete payment checkout or request Admin approval at /api/subscription/request-pro.",
    )


@router.get("/ping")
async def ping_auth(token: str = Depends(oauth2_scheme)):
    """
    Ultra-lightweight JWT validation endpoint.
    Returns minimal user info from token claims without any DB query.
    Used for silent session heartbeat without burdening the DB pool.
    """
    from jose import JWTError, jwt
    from backend.core.config import settings
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return {"valid": True, "user_id": user_id}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired or invalid")


@router.get("/security/fraud-status")
async def get_fraud_status(
    req: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Returns the real-time security assessment, active anomalies, and
    CERT-In audit status for the authenticated user session.
    """
    client_ip = _get_client_ip(req)
    user_agent = req.headers.get("user-agent")
    
    # Evaluate current session status
    eval_res = fraud_detection_engine.evaluate_login_risk(
        email=current_user.email,
        user_id=str(current_user.id),
        ip_address=client_ip,
        user_agent=user_agent,
        is_registration=False
    )

    return {
        "status": "active",
        "risk_level": eval_res.risk_level,
        "risk_score": eval_res.risk_score,
        "anomalies": eval_res.anomalies,
        "client_ip": client_ip,
        "cert_in_retention_days": 180,
        "timestamp": eval_res.timestamp
    }


@router.post("/security/telemetry")
async def report_client_telemetry(
    telemetry: ClientTelemetryRequest,
    req: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Consumes opt-in client telemetry under Indian DPDPA 2023 consent
    to calibrate continuous impossible-travel and device drift defenses.
    """
    client_ip = _get_client_ip(req)
    user_agent = req.headers.get("user-agent")

    is_impossible = False
    dist = 0.0
    vel = 0.0
    if telemetry.lat is not None and telemetry.lon is not None:
        is_impossible, dist, vel, reason = fraud_detection_engine.check_impossible_travel(
            user_id=str(current_user.id),
            current_lat=telemetry.lat,
            current_lon=telemetry.lon
        )
        if is_impossible:
            log_security_event(
                event_type="AUTH_GEO_VELOCITY_ANOMALY",
                severity="WARNING",
                ip_address=client_ip,
                user_id=str(current_user.id),
                details={"velocity_kmh": vel, "distance_km": dist, "reason": reason}
            )

    return {
        "acknowledged": True,
        "impossible_travel_flagged": is_impossible,
        "evaluated_velocity_kmh": round(vel, 2)
    }



