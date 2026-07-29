"""yfinance data ingestion — fetches and stores OHLCV candles."""

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
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BAJFINANCE.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "TITAN.NS", "NTPC.NS", "POWERGRID.NS", "ULTRACEMCO.NS", "WIPRO.NS",
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
    Fetch OHLCV data from yfinance and store in TimescaleDB.
    Returns number of rows inserted.
    """
    yf_interval = TIMEFRAME_MAP.get(timeframe, "1d")
    logger.info(f"Ingesting {symbol} {timeframe} ({period})")

    try:
        import requests
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        ticker = yf.Ticker(symbol, session=session)
        df: pd.DataFrame = await asyncio.to_thread(
            ticker.history, interval=yf_interval, period=period, auto_adjust=True
        )

        if df.empty:
            logger.warning(f"No data returned for {symbol} {timeframe}")
            return 0

        # Validate
        df = validate_candles(df, symbol)
        if df.empty:
            logger.warning(f"All candles for {symbol} failed validation")
            return 0

        # Build rows
        rows = []
        for ts, row in df.iterrows():
            rows.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": ts.to_pydatetime(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
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
