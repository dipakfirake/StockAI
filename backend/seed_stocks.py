import asyncio
from backend.core.database import AsyncSessionLocal
from backend.models.stock import Stock

POPULAR_STOCKS = [
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "exchange": "NSE", "sector": "Energy"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "exchange": "NSE", "sector": "Technology"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "exchange": "NSE", "sector": "Financials"},
    {"symbol": "ICICIBANK.NS", "name": "ICICI Bank", "exchange": "NSE", "sector": "Financials"},
    {"symbol": "INFY.NS", "name": "Infosys", "exchange": "NSE", "sector": "Technology"},
    {"symbol": "SBIN.NS", "name": "State Bank of India", "exchange": "NSE", "sector": "Financials"},
    {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel", "exchange": "NSE", "sector": "Communication Services"},
    {"symbol": "ITC.NS", "name": "ITC Limited", "exchange": "NSE", "sector": "Consumer Defensive"},
    {"symbol": "HINDUNILVR.NS", "name": "Hindustan Unilever", "exchange": "NSE", "sector": "Consumer Defensive"},
    {"symbol": "LT.NS", "name": "Larsen & Toubro", "exchange": "NSE", "sector": "Industrials"},
    {"symbol": "BAJFINANCE.NS", "name": "Bajaj Finance", "exchange": "NSE", "sector": "Financials"},
    {"symbol": "MARUTI.NS", "name": "Maruti Suzuki", "exchange": "NSE", "sector": "Consumer Cyclical"},
    {"symbol": "TATAMOTORS.NS", "name": "Tata Motors", "exchange": "NSE", "sector": "Consumer Cyclical"},
    {"symbol": "SUNPHARMA.NS", "name": "Sun Pharmaceutical", "exchange": "NSE", "sector": "Healthcare"},
    {"symbol": "TATASTEEL.NS", "name": "Tata Steel", "exchange": "NSE", "sector": "Basic Materials"},
    {"symbol": "AXISBANK.NS", "name": "Axis Bank", "exchange": "NSE", "sector": "Financials"},
    {"symbol": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank", "exchange": "NSE", "sector": "Financials"},
    {"symbol": "^NSEI", "name": "Nifty 50 Index", "exchange": "NSE", "sector": "Index"},
    {"symbol": "^BSESN", "name": "BSE Sensex Index", "exchange": "BSE", "sector": "Index"},
    {"symbol": "^NSEBANK", "name": "Nifty Bank Index", "exchange": "NSE", "sector": "Index"},
    {"symbol": "^INDIAVIX", "name": "India VIX", "exchange": "NSE", "sector": "Index"},
]

async def seed_stocks():
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        for s in POPULAR_STOCKS:
            existing = (await db.execute(select(Stock).filter(Stock.symbol == s["symbol"]))).scalar_one_or_none()
            if not existing:
                stock = Stock(
                    symbol=s["symbol"],
                    name=s["name"],
                    exchange=s["exchange"],
                    sector=s["sector"]
                )
                db.add(stock)
        await db.commit()
        print("Stocks seeded successfully.")

if __name__ == "__main__":
    asyncio.run(seed_stocks())
