import asyncio
import sys
from sqlalchemy import text
from backend.core.database import engine

async def delete_test_users():
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE email LIKE 'test_QA_%'"))
        print("Test users deleted successfully.")

if __name__ == "__main__":
    asyncio.run(delete_test_users())
