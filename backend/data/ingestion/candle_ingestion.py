"""Candle data ingestion — fetches and stores OHLCV candles via Fyers API v3."""

from __future__ import annotations

import asyncio
from datetime import datetime

import yfinance as yf
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from backend.core.database import AsyncSessionLocal
from backend.core.logging_config import get_logger
from backend.models.candle import Candle
from backend.data.validation.data_quality import validate_candles

logger = get_logger(__name__)

NSE_NIFTY50_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "HINDUNILVR.NS", "LT.NS",
    "AXISBANK.NS", "KOTAKBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
    "ULTRACEMCO.NS", "ASIANPAINT.NS", "NTPC.NS", "TATAMOTORS.NS", "BAJFINANCE.NS",
    "POWERGRID.NS", "M&M.NS", "ADANIENT.NS", "TATASTEEL.NS", "COALINDIA.NS",
    "JSWSTEEL.NS", "HCLTECH.NS", "BAJAJFINSV.NS", "ONGC.NS", "GRASIM.NS",
    "TECHM.NS", "NESTLEIND.NS", "HDFCLIFE.NS", "BRITANNIA.NS", "ADANIPORTS.NS",
    "SBILIFE.NS", "DRREDDY.NS", "EICHERMOT.NS", "INDUSINDBK.NS", "WIPRO.NS",
    "CIPLA.NS", "DIVISLAB.NS", "BPCL.NS", "TATACONSUM.NS", "APOLLOHOSP.NS",
    "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "HINDALCO.NS", "LTIM.NS", "BEL.NS"
]

TIMEFRAME_MAP = {
    "1d": "1d",
    "1h": "1h",
    "15m": "15m",
    "5m": "5m",
    "1m": "1m",
}


async def ingest_candles(
    symbol: str,
    timeframe: str = "1d",
    period: str = "2y",
) -> int:
    """
    Fetch OHLCV data via MarketDataService (Fyers API v3) and store in TimescaleDB.
    Returns number of rows inserted.
    """
    logger.info(f"Ingesting {symbol} {timeframe} ({period})")

    try:
        from backend.services.market_data import market_data_service
        candles = await market_data_service.fetch_candles(symbol, timeframe, limit=500)
        
        if not candles:
            # Fallback to yfinance if Fyers returns empty (e.g. broker token refresh or ticker renames)
            yf_interval = TIMEFRAME_MAP.get(timeframe, "1d")
            import requests
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            ticker = yf.Ticker(symbol, session=session)
            df: pd.DataFrame = await asyncio.to_thread(
                ticker.history, interval=yf_interval, period=period, auto_adjust=True
            )
            if not df.empty:
                df = validate_candles(df, symbol)
                candles = [
                    {
                        "timestamp": ts.isoformat(),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"]),
                    }
                    for ts, row in df.iterrows()
                ]

        if not candles:
            logger.warning(f"No data returned for {symbol} {timeframe}")
            return 0

        # Build rows
        rows = []
        for c in candles:
            ts_str = c["timestamp"]
            ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            rows.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": ts_dt,
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": int(c["volume"]),
            })

        # Upsert (on conflict do nothing)
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = insert(Candle).values(rows)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["symbol", "timeframe", "timestamp"]
                )
                result = await session.execute(stmt)
                inserted = result.rowcount

        logger.info(f"Ingested {inserted}/{len(rows)} candles for {symbol} {timeframe}")
        return inserted

    except Exception as e:
        logger.error(f"Ingestion failed for {symbol} {timeframe}: {e}")
        return 0


async def backfill_nifty50(timeframe: str = "1d"):
    """Backfill all Nifty 50 symbols with 2 years of daily data."""
    logger.info(f"Starting Nifty 50 backfill ({timeframe})")
    total = 0
    for sym in NSE_NIFTY50_SYMBOLS:
        inserted = await ingest_candles(sym, timeframe, period="2y")
        total += inserted
        await asyncio.sleep(0.5)  # Rate limit
    logger.info(f"Backfill complete: {total} total candles ingested")
    return total
