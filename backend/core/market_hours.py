"""
Market Hours & Dynamic Cache TTL Manager for Indian Exchanges (NSE/BSE).

Provides real-time determination of active market trading sessions (09:15 to 15:30 IST, Monday-Friday)
and computes dynamic, market-status-aware cache TTLs to guarantee that:
1. When market is OPEN: daily and intraday candles expire in seconds, keeping AI predictions fresh.
2. When market is CLOSED: candles and indicators are cached for extended durations (hours) to eliminate
   unnecessary network and compute overhead on immutable historical data.
"""

from datetime import datetime, time as dtime, timezone, timedelta
from typing import Optional
from backend.core.config import settings

# Indian Standard Time (IST) is UTC+05:30
IST_OFFSET = timedelta(hours=5, minutes=30)
IST_TZ = timezone(IST_OFFSET)

# NSE/BSE Equity Normal Trading Hours: 09:15:00 to 15:30:00 IST
MARKET_OPEN_TIME = dtime(9, 15, 0)
MARKET_CLOSE_TIME = dtime(15, 30, 0)

# Major Indian Exchange Holidays (year-agnostic month-day or specific dates)
# Standard fixed holiday dates (Republic Day, Independence Day, Gandhi Jayanti, Christmas, etc.)
FIXED_HOLIDAYS_MM_DD = {
    (1, 26),   # Republic Day
    (5, 1),    # Maharashtra Day
    (8, 15),   # Independence Day
    (10, 2),   # Gandhi Jayanti
    (12, 25),  # Christmas
}


def get_current_ist_time(dt_utc: Optional[datetime] = None) -> datetime:
    """Return the current time in Indian Standard Time (IST)."""
    if dt_utc is None:
        dt_utc = datetime.now(timezone.utc)
    elif dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(IST_TZ)


def is_indian_market_open(dt_utc: Optional[datetime] = None) -> bool:
    """
    Returns True if Indian equities markets (NSE/BSE) are currently in an active trading session.
    Trading sessions are:
    - Monday through Friday (weekday < 5)
    - Between 09:15:00 AM and 03:30:00 PM IST
    - Not on recognized National Holidays
    """
    ist = get_current_ist_time(dt_utc)

    # Weekday check: Monday is 0, Sunday is 6
    if ist.weekday() >= 5:  # Saturday (5) or Sunday (6)
        return False

    # Holiday check
    if (ist.month, ist.day) in FIXED_HOLIDAYS_MM_DD:
        return False

    # Time-of-day check (09:15 to 15:30 IST)
    current_time = ist.time()
    return MARKET_OPEN_TIME <= current_time <= MARKET_CLOSE_TIME


def get_dynamic_candle_ttl(timeframe: str, dt_utc: Optional[datetime] = None) -> int:
    """
    Compute optimal Cache TTL (seconds) based on market state and candle resolution.

    - Intraday (1m, 5m, 15m, 30m, 1h):
        - Market Open: 5-10s (sub-minute freshness)
        - Market Closed: 1,800s (30 minutes)
    - Daily / Weekly / Monthly (1d, 1w, 1mo):
        - Market Open: 30s (real-time day candle updates)
        - Market Closed: 43,200s (12 hours) — historical bars are frozen
    """
    tf = timeframe.lower().strip()
    is_open = is_indian_market_open(dt_utc)

    if tf in ("1m", "5m", "15m", "30m", "1h"):
        if is_open:
            return getattr(settings, "CACHE_TTL_INTRADAY", 5)
        else:
            return 1800  # 30 minutes when market is closed

    # Daily, weekly, monthly timeframes
    if is_open:
        return getattr(settings, "CACHE_TTL_DAILY_MARKET_OPEN", 30)
    else:
        return getattr(settings, "CACHE_TTL_DAILY_MARKET_CLOSED", 43200)


def get_dynamic_screener_ttl(dt_utc: Optional[datetime] = None) -> int:
    """
    Compute optimal Screener and AI Analysis Cache TTL.
    - Market Open: 60 seconds (ensures swing trade setups and ML scores stay aligned with live price)
    - Market Closed: 3,600 seconds (1 hour)
    """
    if is_indian_market_open(dt_utc):
        return getattr(settings, "CACHE_TTL_SCREENER_OPEN", 60)
    return getattr(settings, "CACHE_TTL_SCREENER_CLOSED", 3600)
