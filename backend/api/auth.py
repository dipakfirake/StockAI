from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import verify_password, hash_password, create_access_token, get_current_user
from backend.core.auth_security import validate_password_strength, brute_force_protector
from backend.core.audit_logger import log_security_event
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


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


@router.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest, req: Request, db: AsyncSession = Depends(get_db)):
    """Register a new user with password strength validation."""
    client_ip = _get_client_ip(req)
    
    # Enforce password strength
    try:
        validate_password_strength(request.password)
    except ValueError as e:
        log_security_event(
            event_type="AUTH_REGISTER_REJECTED",
            severity="WARNING",
            ip_address=client_ip,
            details={"email": request.email, "reason": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e))

    existing = await db.execute(select(User).where(User.email == request.email.lower().strip()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    is_admin = request.email.lower().strip() == "admin@stockai.com"
    user = User(
        email=request.email.lower().strip(),
        name=request.name,
        hashed_password=hash_password(request.password),
        subscription_tier="PRO" if is_admin else "FREE"
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

    # Check brute-force lockout
    brute_force_protector.check_lockout(client_ip, username)

    result = await db.execute(select(User).where(User.email == username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        brute_force_protector.record_failure(client_ip, username)
        log_security_event(
            event_type="AUTH_LOGIN_FAILED",
            severity="WARNING",
            ip_address=client_ip,
            details={"email": username, "reason": "Invalid credentials"},
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

    # Record success and reset failed attempts
    brute_force_protector.record_success(client_ip, username)
    token = create_access_token({"sub": str(user.id)})

    log_security_event(
        event_type="AUTH_LOGIN_SUCCESS",
        severity="INFO",
        ip_address=client_ip,
        user_id=str(user.id),
        details={"email": username},
    )
    return {"access_token": token, "token_type": "bearer"}


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

