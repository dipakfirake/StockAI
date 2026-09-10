"""Legacy alias for candle_ingestion — re-exports all members for compatibility."""

from backend.data.ingestion.candle_ingestion import (
    NSE_NIFTY50_SYMBOLS,
    TIMEFRAME_MAP,
    ingest_candles,
    backfill_nifty50,
)

__all__ = [
    "NSE_NIFTY50_SYMBOLS",
    "TIMEFRAME_MAP",
    "ingest_candles",
    "backfill_nifty50",
]
