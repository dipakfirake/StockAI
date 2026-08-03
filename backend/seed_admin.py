import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.database import AsyncSessionLocal
from backend.models.user import User
from backend.core.auth import hash_password
from sqlalchemy import select

async def update_admin_password():
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == "admin@stockai.com"))
        user = existing.scalar_one_or_none()
        if user:
            user.hashed_password = hash_password("admin")
            user.subscription_tier = "PRO"
            await db.commit()
            print("Admin password updated to 'admin'.")
        else:
            user = User(
                email="admin@stockai.com",
                name="StockAI Admin",
                hashed_password=hash_password("admin"),
                subscription_tier="PRO",
                is_active=True,
            )
            db.add(user)
            await db.commit()
            print("Admin user created: admin@stockai.com / admin")

if __name__ == "__main__":
    asyncio.run(update_admin_password())
