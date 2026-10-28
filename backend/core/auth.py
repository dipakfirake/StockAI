"""JWT authentication utilities."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, HTTPBasic, HTTPBasicCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
security_basic_optional = HTTPBasic(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """FastAPI dependency — validates JWT and returns current user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Import here to avoid circular imports
    from backend.models.user import User
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
):
    """FastAPI dependency — returns User if valid JWT provided, None otherwise without raising 401."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    from backend.models.user import User
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
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

    # 1. Check JWT token if provided via Authorization header, query parameter, or cookie
    jwt_candidate = token or request.query_params.get("token") or request.cookies.get("access_token")
    if jwt_candidate:
        try:
            payload = jwt.decode(jwt_candidate, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                result = await db.execute(select(User).where(User.id == user_id))
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
            is_valid = await asyncio.to_thread(verify_password, credentials.password, user.hashed_password)
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
    db: AsyncSession = Depends(get_db),
):
    """
    Allows internal system probes (from localhost or container network without external proxy headers).
    For external requests over the internet, requires Admin credentials (Basic Auth or JWT).
    """
    client_ip = request.client.host if request.client else ""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    x_real_ip = request.headers.get("x-real-ip")

    # Internal Docker / local health checks have no external proxy headers
    is_external = bool(x_forwarded_for or x_real_ip)
    is_local_ip = client_ip in ("127.0.0.1", "::1", "localhost", "testclient")

    if is_local_ip and not is_external:
        return None  # Local probe allowed

    # External access: require Admin credentials
    return await verify_admin_docs_access(request, credentials, token, db)
