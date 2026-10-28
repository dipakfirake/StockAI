import pytest
from datetime import datetime, timezone, timedelta
from backend.core.market_hours import (
    is_indian_market_open,
    get_dynamic_candle_ttl,
    get_dynamic_screener_ttl,
    get_current_ist_time,
    IST_TZ,
)
from backend.services.market_data import MarketDataService


def test_market_hours_open_during_active_trading_session():
    # Wednesday at 11:30 AM IST is 06:00 AM UTC
    wed_market_time_utc = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)
    assert is_indian_market_open(wed_market_time_utc) is True


def test_market_hours_closed_pre_market():
    # Wednesday at 08:30 AM IST is 03:00 AM UTC
    wed_pre_market_utc = datetime(2026, 10, 28, 3, 0, 0, tzinfo=timezone.utc)
    assert is_indian_market_open(wed_pre_market_utc) is False


def test_market_hours_closed_post_market():
    # Wednesday at 04:30 PM IST is 11:00 AM UTC
    wed_post_market_utc = datetime(2026, 10, 28, 11, 0, 0, tzinfo=timezone.utc)
    assert is_indian_market_open(wed_post_market_utc) is False


def test_market_hours_closed_on_weekend():
    # Saturday at 11:30 AM IST is 06:00 AM UTC
    sat_market_time_utc = datetime(2026, 10, 24, 6, 0, 0, tzinfo=timezone.utc)
    assert is_indian_market_open(sat_market_time_utc) is False


def test_market_hours_closed_on_national_holiday():
    # Republic Day (Jan 26, 2026) at 11:30 AM IST
    holiday_utc = datetime(2026, 1, 26, 6, 0, 0, tzinfo=timezone.utc)
    assert is_indian_market_open(holiday_utc) is False


from backend.core.config import settings

def test_dynamic_candle_ttl_market_open():
    wed_open_utc = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)
    expected_intraday = getattr(settings, "CACHE_TTL_INTRADAY", 5)
    assert get_dynamic_candle_ttl("1m", wed_open_utc) == expected_intraday
    assert get_dynamic_candle_ttl("5m", wed_open_utc) == expected_intraday
    assert get_dynamic_candle_ttl("15m", wed_open_utc) == expected_intraday
    assert get_dynamic_candle_ttl("1h", wed_open_utc) == expected_intraday
    assert get_dynamic_candle_ttl("1d", wed_open_utc) == 30
    assert get_dynamic_candle_ttl("1w", wed_open_utc) == 30


def test_dynamic_candle_ttl_market_closed():
    wed_closed_utc = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)
    assert get_dynamic_candle_ttl("5m", wed_closed_utc) == 1800
    assert get_dynamic_candle_ttl("1d", wed_closed_utc) == 43200


def test_dynamic_screener_ttl():
    wed_open_utc = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)
    wed_closed_utc = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)
    assert get_dynamic_screener_ttl(wed_open_utc) == 60
    assert get_dynamic_screener_ttl(wed_closed_utc) == 3600


def test_synchronize_candle_tip_empty_guard():
    candles = []
    quote = {"price": 2500.0}
    assert MarketDataService.synchronize_candle_tip(candles, quote) == []
    
    candles = [{"close": 2400.0}]
    assert MarketDataService.synchronize_candle_tip(candles, None) == candles


def test_synchronize_candle_tip_updates_forming_candle():
    today_str = get_current_ist_time().strftime("%Y-%m-%d")
    candles = [
        {"timestamp": f"{today_str}T09:15:00+05:30", "open": 2400.0, "high": 2450.0, "low": 2390.0, "close": 2420.0, "volume": 100000}
    ]
    quote = {
        "price": 2480.0,
        "high": 2490.0,
        "low": 2380.0,
        "volume": 150000
    }
    synced = MarketDataService.synchronize_candle_tip(candles, quote)
    assert len(synced) == 1
    assert synced[0]["close"] == 2480.0
    assert synced[0]["high"] == 2490.0
    assert synced[0]["low"] == 2380.0
    assert synced[0]["volume"] == 150000
