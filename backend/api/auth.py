"""Auth API router — registration and login."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import verify_password, hash_password, create_access_token, get_current_user
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


@router.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    existing = await db.execute(select(User).where(User.email == request.email))
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
    return RegisterResponse(user_id=str(user.id), email=user.email, name=user.name, token=token)


@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """Login and obtain JWT token."""
    result = await db.execute(select(User).where(User.email == form_data.username.lower()))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account deactivated")

    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "name": current_user.name,
        "subscription_tier": current_user.subscription_tier
    }

@router.post("/upgrade")
async def upgrade_tier(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Mock endpoint to upgrade user to PRO tier."""
    if current_user.subscription_tier == "PRO":
        return {"message": "Already on PRO tier", "subscription_tier": "PRO"}
    
    current_user.subscription_tier = "PRO"
    db.add(current_user)
    await db.commit()
    
    return {"message": "Successfully upgraded to PRO tier", "subscription_tier": "PRO"}
