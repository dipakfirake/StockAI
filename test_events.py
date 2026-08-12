import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.services.market_data import market_data_service

async def main():
    events = await market_data_service.fetch_corporate_events('TCS.NS')
    print(events)

if __name__ == "__main__":
    asyncio.run(main())
