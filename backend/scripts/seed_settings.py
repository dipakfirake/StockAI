import asyncio
import sys
sys.path.append("/app")

from backend.core.database import AsyncSessionLocal
from backend.models.settings import SystemSettings
from sqlalchemy import select

async def seed_new_settings():
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(SystemSettings.key))).scalars().all()
        if "enable_auto_trader" not in existing:
            print("Seeding enable_auto_trader...")
            db.add(SystemSettings(key="enable_auto_trader", value="false", value_type="boolean", description="Master toggle switch for AI Auto-Trader daemon"))
            await db.commit()
            print("Done")

if __name__ == "__main__":
    asyncio.run(seed_new_settings())
