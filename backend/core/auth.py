"""JWT, HttpOnly cookie, MFA challenge, step-up auth, WebSocket ticket & revocation utilities."""

import asyncio
import time as _time_mod
import uuid as _uuid_mod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, HTTPBasic, HTTPBasicCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_db
from backend.core.executors import run_in_fast_executor

AUTH_COOKIE_NAME = "stockai_access_token"
CSRF_COOKIE_NAME = "stockai_csrf_token"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
security_basic_optional = HTTPBasic(auto_error=False)


@dataclass(frozen=True)
class CachedAuthUser:
    """Lightweight immutable user identity returned by non-blocking JWT cache."""
    id: object
    email: str
    name: str
    is_active: bool
    is_admin: bool
    subscription_tier: str
    pro_status: Optional[str] = None
    token_version: int = 1
    totp_enabled: bool = False


# Short in-memory auth cache (30s TTL) to eliminate per-request Neon DB round-trips
# on high-frequency read/poll endpoints and /health/live checks.
_AUTH_USER_CACHE: dict[str, tuple[CachedAuthUser, float]] = {}
_AUTH_CACHE_TTL_SECONDS = 30.0
_LOCAL_REVOKED_JTIS: dict[str, float] = {}


def invalidate_user_auth_cache(user_id: object) -> None:
    """Evict a user from in-process auth cache (called on logout/role/session revocation)."""
    if user_id is not None:
        _AUTH_USER_CACHE.pop(str(user_id), None)


def _prune_revoked_jtis() -> None:
    now = _time_mod.time()
    if len(_LOCAL_REVOKED_JTIS) > 2000:
        expired = [k for k, exp_ts in _LOCAL_REVOKED_JTIS.items() if exp_ts <= now]
        for k in expired:
            _LOCAL_REVOKED_JTIS.pop(k, None)


async def revoke_token_jti(jti: Optional[str], exp_timestamp: float | int | None = None) -> None:
    """Persist JWT ID revocation in Redis (with local memory mirror)."""
    if not jti:
        return
    now = _time_mod.time()
    exp_ts = float(exp_timestamp) if exp_timestamp else (now + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    ttl = max(60, int(exp_ts - now))
    _prune_revoked_jtis()
    _LOCAL_REVOKED_JTIS[str(jti)] = exp_ts
    try:
        from backend.core.cache import get_redis

        async def _store_revoked():
            r = await get_redis()
            await r.setex(f"revoked_jti:{jti}", ttl, "1")

        await asyncio.wait_for(_store_revoked(), timeout=0.08)
    except Exception:
        pass


async def is_token_revoked(jti: Optional[str]) -> bool:
    """Return True if JWT `jti` was explicitly logged out / revoked."""
    if not jti:
        return False
    exp_ts = _LOCAL_REVOKED_JTIS.get(str(jti))
    if exp_ts is not None:
        if exp_ts > _time_mod.time():
            return True
        _LOCAL_REVOKED_JTIS.pop(str(jti), None)
    try:
        from backend.core.cache import get_redis

        async def _check_revoked():
            r = await get_redis()
            return bool(await r.exists(f"revoked_jti:{jti}"))

        if await asyncio.wait_for(_check_revoked(), timeout=0.08):
            return True
    except Exception:
        pass
    return False


def extract_request_jwt(request: Optional[Request], bearer_token: Optional[str] = None) -> Optional[str]:
    """Read JWT from Authorization header first, else HttpOnly session cookie."""
    if bearer_token:
        return bearer_token
    if request is not None:
        cookies = getattr(request, "cookies", None) or {}
        cookie_tok = cookies.get(AUTH_COOKIE_NAME) or cookies.get("access_token")
        if cookie_tok:
            return cookie_tok
    return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    *,
    token_version: int = 1,
    scope: str = "session",
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update(
        {
            "exp": expire,
            "jti": str(_uuid_mod.uuid4()),
            "tv": int(token_version or 1),
            "scope": scope,
        }
    )
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_mfa_challenge_token(user_id: str) -> str:
    """Short-lived 5-minute MFA verification challenge token (cannot access normal API routes)."""
    return create_access_token(
        {"sub": str(user_id)},
        expires_delta=timedelta(minutes=5),
        scope="mfa_challenge",
    )


def decode_mfa_challenge_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("scope") != "mfa_challenge":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def create_stepup_token(user_id: str) -> str:
    """Short-lived 10-minute step-up authorization token for sensitive Admin actions."""
    return create_access_token(
        {"sub": str(user_id)},
        expires_delta=timedelta(minutes=10),
        scope="admin_stepup",
    )


def verify_stepup_token(token: str | None, user_id: object) -> bool:
    if not token or not user_id:
        return False
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("scope") == "admin_stepup" and str(payload.get("sub")) == str(user_id)
    except JWTError:
        return False


def create_ws_ticket(user_id: object, is_admin: bool, token_version: int = 1) -> str:
    """Short-lived 45-second ticket so persistent JWTs never appear in WebSocket URLs."""
    return create_access_token(
        {"sub": str(user_id), "is_admin": bool(is_admin)},
        expires_delta=timedelta(seconds=45),
        token_version=int(token_version or 1),
        scope="ws",
    )


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
):
    """FastAPI dependency — validates JWT (Bearer header or HttpOnly cookie) and returns current user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    jwt_token = extract_request_jwt(request, token)
    if not jwt_token:
        raise credentials_exception

    try:
        payload = jwt.decode(jwt_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("scope", "session") != "session":
            raise credentials_exception
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        if await is_token_revoked(payload.get("jti")):
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    from backend.models.user import User
    from sqlalchemy import select
    import uuid as _uuid

    parsed_uuid = None
    try:
        parsed_uuid = _uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        parsed_uuid = None

    if parsed_uuid is not None:
        result = await db.execute(select(User).where(User.id == parsed_uuid))
    else:
        result = await db.execute(select(User).where(User.email == user_id))

    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception

    db_tv = getattr(user, "token_version", None)
    if isinstance(db_tv, int) and int(payload.get("tv", 1) or 1) < db_tv:
        raise credentials_exception
    return user


async def get_current_user_fast(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme_optional),
):
    """
    Non-blocking JWT auth dependency (Bearer header or HttpOnly cookie) with 30s in-memory user cache.
    Honors FastAPI test dependency overrides on get_current_user cleanly and
    avoids holding a remote Neon Postgres session across read/poll requests.
    """
    override = request.app.dependency_overrides.get(get_current_user)
    if override is not None:
        if callable(override):
            import inspect
            res = override()
            return await res if inspect.isawaitable(res) else res
        return override

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    jwt_token = extract_request_jwt(request, token)
    if not jwt_token:
        raise credentials_exception

    try:
        payload = jwt.decode(jwt_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("scope", "session") != "session":
            raise credentials_exception
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        if await is_token_revoked(payload.get("jti")):
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    token_tv = int(payload.get("tv", 1) or 1)
    cache_key = str(user_id)
    now = _time_mod.monotonic()
    cached_entry = _AUTH_USER_CACHE.get(cache_key)
    if cached_entry and cached_entry[1] > now:
        cached_u = cached_entry[0]
        if not cached_u.is_active or token_tv < int(cached_u.token_version or 1):
            raise credentials_exception
        return cached_u

    from backend.core.database import AsyncSessionLocal
    from backend.models.user import User
    from sqlalchemy import select
    import uuid as _uuid

    parsed_uuid = None
    try:
        parsed_uuid = _uuid.UUID(cache_key)
    except (ValueError, TypeError):
        parsed_uuid = None

    async with AsyncSessionLocal() as db:
        if parsed_uuid is not None:
            result = await db.execute(select(User).where(User.id == parsed_uuid))
        else:
            result = await db.execute(select(User).where(User.email == cache_key))
        user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception

    db_tv = int(getattr(user, "token_version", 1) or 1)
    if token_tv < db_tv:
        raise credentials_exception

    cached_user = CachedAuthUser(
        id=user.id,
        email=user.email,
        name=user.name or "",
        is_active=bool(user.is_active),
        is_admin=bool(user.is_admin),
        subscription_tier=user.subscription_tier or "FREE",
        pro_status=getattr(user, "pro_status", None),
        token_version=db_tv,
        totp_enabled=bool(getattr(user, "totp_enabled", False)),
    )
    _AUTH_USER_CACHE[cache_key] = (cached_user, _time_mod.monotonic() + _AUTH_CACHE_TTL_SECONDS)
    if len(_AUTH_USER_CACHE) > 2000:
        _AUTH_USER_CACHE.clear()
    return cached_user


async def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
):
    """FastAPI dependency — returns User if valid JWT (header or cookie) provided, None otherwise."""
    jwt_token = extract_request_jwt(request, token)
    if not jwt_token:
        return None
    try:
        payload = jwt.decode(jwt_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("scope", "session") != "session":
            return None
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            return None
        if await is_token_revoked(payload.get("jti")):
            return None
    except JWTError:
        return None

    from backend.models.user import User
    from sqlalchemy import select
    import uuid as _uuid

    parsed_uuid = None
    try:
        parsed_uuid = _uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        parsed_uuid = None

    if parsed_uuid is not None:
        result = await db.execute(select(User).where(User.id == parsed_uuid))
    else:
        result = await db.execute(select(User).where(User.email == user_id))

    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    db_tv = getattr(user, "token_version", None)
    if isinstance(db_tv, int) and int(payload.get("tv", 1) or 1) < db_tv:
        return None
    return user


async def require_pro_tier(current_user=Depends(get_current_user)):
    """Dependency that ensures the current user has the PRO subscription tier."""
    if current_user.subscription_tier != "PRO":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature requires a PRO subscription.",
        )
    return current_user


async def verify_admin_docs_access(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security_basic_optional),
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Guards administrative documentation and endpoints (/docs, /redoc, /openapi.json).
    Allows access if:
    1. A valid JWT token with an active Admin user is provided (in header, cookie 'access_token', or '?token=' query param).
    2. OR valid HTTP Basic Auth credentials for an active Admin user in PostgreSQL are provided.
    Otherwise, raises HTTP 401 with WWW-Authenticate: Basic challenge.
    """
    import asyncio
    from backend.models.user import User
    from sqlalchemy import select

    # 1. Check JWT token if provided via Authorization header, query parameter, or HttpOnly cookie
    jwt_candidate = (
        token
        or request.query_params.get("token")
        or request.cookies.get(AUTH_COOKIE_NAME)
        or request.cookies.get("access_token")
    )
    if jwt_candidate:
        try:
            payload = jwt.decode(jwt_candidate, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                import uuid as _uuid
                parsed_uuid = None
                try:
                    parsed_uuid = _uuid.UUID(str(user_id))
                except (ValueError, TypeError):
                    parsed_uuid = None

                if parsed_uuid is not None:
                    result = await db.execute(select(User).where(User.id == parsed_uuid))
                else:
                    result = await db.execute(select(User).where(User.email == user_id))
                user = result.scalar_one_or_none()
                if user and user.is_active and user.is_admin:
                    return user
        except JWTError:
            pass

    # 2. Check HTTP Basic Auth credentials (native browser login prompt)
    if credentials:
        email = credentials.username.strip().lower()
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user and user.is_active and user.is_admin:
            is_valid = await run_in_fast_executor(verify_password, credentials.password, user.hashed_password)
            if is_valid:
                return user

    # 3. Unauthorized: challenge with HTTP Basic Auth
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Administrator credentials required to view API documentation",
        headers={"WWW-Authenticate": 'Basic realm="StockAI Administrative API Documentation"'},
    )


async def verify_admin_or_local(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security_basic_optional),
    token: Optional[str] = Depends(oauth2_scheme_optional),
):
    """
    Allows internal system probes (from localhost or container network without external proxy headers).
    For external requests over the internet, requires Admin credentials (Basic Auth or JWT).
    Zero DB connection checkout for local/internal probes.
    """
    client_ip = request.client.host if request.client else ""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    x_real_ip = request.headers.get("x-real-ip")

    # Internal Docker / local health checks have no external proxy headers
    is_external = bool(x_forwarded_for or x_real_ip)
    is_local_ip = client_ip in ("127.0.0.1", "::1", "localhost", "testclient")

    if is_local_ip and not is_external:
        return None  # Local probe allowed with zero DB overhead

    # Fast-fail external unauthenticated requests with ZERO DB connection checkout
    jwt_candidate = (
        token
        or request.query_params.get("token")
        or request.cookies.get(AUTH_COOKIE_NAME)
        or request.cookies.get("access_token")
    )
    if not credentials and not jwt_candidate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Administrator credentials required",
            headers={"WWW-Authenticate": 'Basic realm="StockAI Administrative API"'},
        )

    # Fast in-memory admin JWT check avoids Neon DB latency on /health/live polls
    if jwt_candidate:
        try:
            payload = jwt.decode(jwt_candidate, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            uid = str(payload.get("sub") or "")
            if uid:
                cached = _AUTH_USER_CACHE.get(uid)
                if cached and cached[1] > _time_mod.monotonic():
                    if cached[0].is_active and cached[0].is_admin:
                        return cached[0]
        except JWTError:
            pass

    # External access: require Admin credentials with isolated session
    from backend.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        admin_user = await verify_admin_docs_access(request, credentials, token, session)
        if admin_user is not None:
            _AUTH_USER_CACHE[str(admin_user.id)] = (
                CachedAuthUser(
                    id=admin_user.id,
                    email=admin_user.email,
                    name=admin_user.name or "",
                    is_active=bool(admin_user.is_active),
                    is_admin=bool(admin_user.is_admin),
                    subscription_tier=admin_user.subscription_tier or "FREE",
                    pro_status=getattr(admin_user, "pro_status", None),
                ),
                _time_mod.monotonic() + _AUTH_CACHE_TTL_SECONDS,
            )
        return admin_user
