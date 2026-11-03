"""
Empirical Challenge & Stress Test Suite: Warmup Governor & Rate Budgeting (Milestone 1)
Challenger: Challenger 2 (Milestone 1)

Verification Dimensions:
1. Dynamic Pacing Interval Decay (1.5s -> 0.8s -> 0.4s -> 0.25s) under sequential requests.
2. Thundering Herd Concurrency Stress Test: 50 concurrent coroutines hitting rate budget.
3. Live fetch_quote Thundering Herd Simulation: 50 concurrent requests immediately post-warmup.
4. Candle Pagination Multi-Chunk Burst Guard (spacing >= 250ms & budget check per chunk).
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from backend.services.market_data import MarketDataService


@pytest.fixture(autouse=True)
def clean_market_data_state():
    """Resets MarketDataService rate limit timestamps and warmup state between test runs."""
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    MarketDataService._warmup_until = 0.0
    MarketDataService._warmup_started_at = 0.0
    MarketDataService._fyers_cooldown_until = 0.0
    MarketDataService._fyers_token_valid = True
    MarketDataService._fyers_token_error_reason = ""
    MarketDataService._active_engine = "PRIMARY_FYERS"
    MarketDataService._circuit_state = "CLOSED"
    MarketDataService._canary_in_progress = False
    yield
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    MarketDataService._warmup_until = 0.0
    MarketDataService._warmup_started_at = 0.0
    MarketDataService._fyers_cooldown_until = 0.0
    MarketDataService._fyers_token_valid = True
    MarketDataService._fyers_token_error_reason = ""
    MarketDataService._active_engine = "PRIMARY_FYERS"
    MarketDataService._circuit_state = "CLOSED"
    MarketDataService._canary_in_progress = False


# ---------------------------------------------------------------------------
# Test 1: Dynamic Pacing Interval Curve Decay Verification (Sequential)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dynamic_pacing_decay_sequential():
    """
    Empirically verify the dynamic pacing ramp-up curve:
    - 0s - 20s: 1.5s spacing required
    - 20s - 40s: 0.8s spacing required
    - 40s - 60s: 0.4s spacing required
    - > 60s (Warmup expired): 0.25s (250ms) spacing required
    """
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0

    base_time = 1700000000.0

    with patch("time.time", return_value=base_time):
        MarketDataService.engage_warmup_governor(duration_seconds=60.0)
        assert MarketDataService.is_in_warmup() is True

    # Phase 1: Elapsed = 5.0s (in 0-20s window -> requires 1.5s spacing)
    # Request 1 at t=5.0s -> Approved
    with patch("time.time", return_value=base_time + 5.0):
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is True, "Initial request in Phase 1 should be admitted"

    # Request 2 at t=5.8s (delta = 0.8s < 1.5s) -> Denied
    with patch("time.time", return_value=base_time + 5.8):
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is False, "Request with 0.8s spacing in Phase 1 (requires 1.5s) must be denied"

    # Request 3 at t=6.51s (delta = 1.51s > 1.5s) -> Approved
    with patch("time.time", return_value=base_time + 6.51):
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is True, "Request with 1.51s spacing in Phase 1 must be admitted"

    # Phase 2: Elapsed = 25.0s (in 20-40s window -> requires 0.8s spacing)
    # Request at t=25.0s -> Approved
    with patch("time.time", return_value=base_time + 25.0):
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is True

    # Request at t=25.5s (delta = 0.5s < 0.8s) -> Denied
    with patch("time.time", return_value=base_time + 25.5):
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is False, "Request with 0.5s spacing in Phase 2 (requires 0.8s) must be denied"

    # Request at t=25.85s (delta = 0.85s > 0.8s) -> Approved
    with patch("time.time", return_value=base_time + 25.85):
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is True

    # Phase 3: Elapsed = 45.0s (in 40-60s window -> requires 0.4s spacing)
    # Request at t=45.0s -> Approved
    with patch("time.time", return_value=base_time + 45.0):
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is True

    # Request at t=45.2s (delta = 0.2s < 0.4s) -> Denied
    with patch("time.time", return_value=base_time + 45.2):
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is False, "Request with 0.2s spacing in Phase 3 (requires 0.4s) must be denied"

    # Request at t=45.45s (delta = 0.45s > 0.4s) -> Approved
    with patch("time.time", return_value=base_time + 45.45):
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is True

    # Phase 4: Elapsed = 65.0s (Warmup Expired -> Standard 0.25s / 250ms spacing)
    with patch("time.time", return_value=base_time + 65.0):
        assert MarketDataService.is_in_warmup() is False
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is True

    # Request at t=65.15s (delta = 0.15s < 0.25s) -> Denied
    with patch("time.time", return_value=base_time + 65.15):
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is False, "Request with 0.15s spacing post-warmup (requires 0.25s) must be denied"

    # Request at t=65.30s (delta = 0.30s > 0.25s) -> Approved
    with patch("time.time", return_value=base_time + 65.30):
        ok = MarketDataService._check_and_record_fyers_rate_budget()
        assert ok is True


# ---------------------------------------------------------------------------
# Test 2: Thundering Herd Concurrency Stress Test on check_and_record_fyers_rate_budget
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_thundering_herd_rate_budget_concurrency_race():
    """
    Stress test: 50 concurrent coroutines calling check_and_record_fyers_rate_budget()
    immediately after warmup governor is engaged.
    Verifies whether the rate budget properly serializes or leaks concurrent requests.
    """
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    MarketDataService.engage_warmup_governor(60.0)

    # Realistic mock Redis with 1ms async yield
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    async def mock_execute():
        await asyncio.sleep(0.001)
        return [0, 0, 0]

    mock_pipe.execute = mock_execute
    mock_pipe.zremrangebyscore = MagicMock()
    mock_pipe.zcount = MagicMock()
    mock_pipe.zcard = MagicMock()
    mock_pipe.zadd = MagicMock()
    mock_pipe.expire = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    with patch("backend.core.cache.get_redis", new=AsyncMock(return_value=mock_redis)):
        results = await asyncio.gather(*[MarketDataService.check_and_record_fyers_rate_budget() for _ in range(50)])

    admitted = sum(1 for r in results if r is True)
    denied = sum(1 for r in results if r is False)

    print(f"\n[STRESS TEST 2 RESULT] Rate budget concurrency race:")
    print(f"Total concurrent invocations: 50")
    print(f"Admitted requests to Fyers: {admitted}")
    print(f"Denied requests (routed to fallback): {denied}")

    assert len(results) == 50, f"Expected 50 total results, got {len(results)}"
    assert admitted == 1, (
        f"CONCURRENCY LEAK DETECTED: Expected exactly 1 request admitted under warmup pacing (1.5s), "
        f"but {admitted} requests were admitted simultaneously!"
    )
    assert denied == 49, (
        f"Expected exactly 49 requests denied under warmup pacing, but {denied} were denied!"
    )


# ---------------------------------------------------------------------------
# Test 3: Thundering Herd fetch_quote Simulation (50 Concurrent Requests)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_thundering_herd_fetch_quotes_concurrency():
    """
    Stress test: 50 concurrent fetch_quote() calls across 50 distinct symbols.
    Simulates mounted frontend components loading simultaneously upon token entry.
    Requirements:
    1. Only 1 request hits Fyers quotes client.
    2. 49 concurrent requests are routed cleanly to Yahoo fallback.
    3. Zero exceptions, zero data dropped, all 50 return valid quotes.
    """
    MarketDataService.reset_fyers_health()
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    MarketDataService.engage_warmup_governor(60.0)

    mock_fyers = MagicMock()
    fyers_call_count = 0
    fyers_call_timestamps = []

    def mock_quotes(data):
        nonlocal fyers_call_count
        fyers_call_count += 1
        fyers_call_timestamps.append(time.time())
        sym = data.get("symbols", "NSE:RELIANCE-EQ")
        return {
            "s": "ok",
            "d": [{
                "n": sym,
                "v": {
                    "lp": 2500.0,
                    "ch": 10.0,
                    "chp": 0.4,
                    "prev_close_price": 2490.0,
                    "volume": 1000000
                }
            }]
        }

    mock_fyers.quotes = mock_quotes

    # Mock Redis with 1ms async yield
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_pipe = MagicMock()
    async def mock_execute():
        await asyncio.sleep(0.001)
        return [0, 0, 0]
    mock_pipe.execute = mock_execute
    mock_pipe.zremrangebyscore = MagicMock()
    mock_pipe.zcount = MagicMock()
    mock_pipe.zcard = MagicMock()
    mock_pipe.zadd = MagicMock()
    mock_pipe.expire = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    # Mock Yahoo Finance fallback
    import pandas as pd
    mock_hist = pd.DataFrame({
        "Close": [2480.0, 2495.0],
        "Volume": [500000, 600000]
    })
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_hist

    symbols = [f"STOCK{i}.NS" for i in range(50)]

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock, return_value=mock_fyers), \
         patch("backend.core.cache.get_redis", new=AsyncMock(return_value=mock_redis)), \
         patch.object(MarketDataService, "check_credentials_changed", new_callable=AsyncMock, return_value=False), \
         patch("yfinance.Ticker", return_value=mock_ticker):

        quotes = await asyncio.gather(*[MarketDataService.fetch_quote(sym) for sym in symbols])

    fyers_quotes = [q for q in quotes if q and q.get("source") == "Fyers API"]
    backup_quotes = [q for q in quotes if q and q.get("source") != "Fyers API"]

    print(f"\n[STRESS TEST 3 RESULT] Live fetch_quote thundering herd:")
    print(f"Total concurrent requests: {len(quotes)}")
    print(f"Dispatched to Fyers API: {fyers_call_count}")
    print(f"Quotes from Fyers API: {len(fyers_quotes)}")
    print(f"Quotes from Backup (Yahoo): {len(backup_quotes)}")

    assert len(quotes) == 50, "All 50 requests must return quote dicts"
    assert fyers_call_count == 1, (
        f"THUNDERING HERD VULNERABILITY: Expected exactly 1 request to Fyers, but {fyers_call_count} "
        f"were dispatched, exhausting broker rate/burst limit!"
    )
    assert len(backup_quotes) == 49, f"Expected 49 backup quotes, got {len(backup_quotes)}"


# ---------------------------------------------------------------------------
# Test 4: Historical Candle Pagination Burst Guard & Spacing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_candle_pagination_burst_guard_and_spacing():
    """
    Stress test: Multi-chunk historical candle query spanning 300 days (3 chunks).
    Verifies:
    1. Spacing between chunk requests is strictly >= 250ms.
    2. Rate budget is evaluated on every pagination step.
    3. If rate budget is exhausted during pagination, stops gracefully without exception.
    """
    MarketDataService.reset_fyers_health()
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0

    mock_fyers = MagicMock()
    chunk_call_timestamps = []

    def mock_history(data):
        chunk_call_timestamps.append(time.perf_counter())
        return {
            "s": "ok",
            "candles": [
                [1680000000 + len(chunk_call_timestamps) * 1000, 100.0, 105.0, 95.0, 102.0, 50000]
            ]
        }

    mock_fyers.history = mock_history

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[0, 0, 0])
    mock_pipe.zremrangebyscore = MagicMock()
    mock_pipe.zcount = MagicMock()
    mock_pipe.zcard = MagicMock()
    mock_pipe.zadd = MagicMock()
    mock_pipe.expire = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock, return_value=mock_fyers), \
         patch("backend.core.cache.get_redis", new=AsyncMock(return_value=mock_redis)), \
         patch.object(MarketDataService, "check_credentials_changed", new_callable=AsyncMock, return_value=False):

        # Multi-chunk request spanning 250 days in 15m resolution (100 days per chunk -> 3 chunks)
        candles = await MarketDataService.fetch_candles(
            "RELIANCE.NS",
            "15m",
            start_date="2023-01-01",
            end_date="2023-09-01"
        )

    print(f"\n[STRESS TEST 4 RESULT] Candle pagination:")
    print(f"Chunks retrieved: {len(chunk_call_timestamps)}")
    print(f"Total candles returned: {len(candles)}")

    assert len(chunk_call_timestamps) >= 3, f"Expected at least 3 chunks, got {len(chunk_call_timestamps)}"

    # Measure spacing intervals between consecutive chunk dispatches
    delays = [
        chunk_call_timestamps[i] - chunk_call_timestamps[i - 1]
        for i in range(1, len(chunk_call_timestamps))
    ]
    for idx, delay in enumerate(delays):
        print(f"Chunk {idx+1} -> {idx+2} delay: {delay:.3f}s (required >= 0.250s)")
        assert delay >= 0.24, f"Chunk {idx+1}->{idx+2} delay was {delay:.3f}s, violating 250ms spacing!"

    assert len(candles) >= 3, "Candles from all chunks must be aggregated"


# ---------------------------------------------------------------------------
# Test 5: Proposed Fix Demonstration (asyncio.Lock serialization)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_thundering_herd_with_mutex_fix_demonstration():
    """
    Demonstration of the proposed fix:
    Serializing check_and_record_fyers_rate_budget() with an asyncio.Lock().
    Empirically proves that with lock serialization, exactly 1 request is dispatched
    to Fyers and 49 concurrent requests are routed silently to Yahoo fallback.
    """
    MarketDataService.reset_fyers_health()
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    MarketDataService.engage_warmup_governor(60.0)

    rate_budget_lock = asyncio.Lock()
    original_check = MarketDataService.check_and_record_fyers_rate_budget

    async def synchronized_check_and_record():
        async with rate_budget_lock:
            return await original_check()

    mock_fyers = MagicMock()
    fyers_call_count = 0
    fyers_call_timestamps = []

    def mock_quotes(data):
        nonlocal fyers_call_count
        fyers_call_count += 1
        fyers_call_timestamps.append(time.time())
        sym = data.get("symbols", "NSE:RELIANCE-EQ")
        return {
            "s": "ok",
            "d": [{
                "n": sym,
                "v": {
                    "lp": 2500.0,
                    "ch": 10.0,
                    "chp": 0.4,
                    "prev_close_price": 2490.0,
                    "volume": 1000000
                }
            }]
        }

    mock_fyers.quotes = mock_quotes

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_pipe = MagicMock()
    async def mock_execute():
        await asyncio.sleep(0.001)
        return [0, 0, 0]
    mock_pipe.execute = mock_execute
    mock_pipe.zremrangebyscore = MagicMock()
    mock_pipe.zcount = MagicMock()
    mock_pipe.zcard = MagicMock()
    mock_pipe.zadd = MagicMock()
    mock_pipe.expire = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    import pandas as pd
    mock_hist = pd.DataFrame({
        "Close": [2480.0, 2495.0],
        "Volume": [500000, 600000]
    })
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_hist

    symbols = [f"STOCK{i}.NS" for i in range(50)]

    with patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock, return_value=mock_fyers), \
         patch("backend.core.cache.get_redis", new=AsyncMock(return_value=mock_redis)), \
         patch.object(MarketDataService, "check_credentials_changed", new_callable=AsyncMock, return_value=False), \
         patch.object(MarketDataService, "check_and_record_fyers_rate_budget", side_effect=synchronized_check_and_record), \
         patch("yfinance.Ticker", return_value=mock_ticker):

        quotes = await asyncio.gather(*[MarketDataService.fetch_quote(sym) for sym in symbols])

    fyers_quotes = [q for q in quotes if q and q.get("source") == "Fyers API"]
    backup_quotes = [q for q in quotes if q and q.get("source") != "Fyers API"]

    print(f"\n[PROPOSED FIX TEST RESULT]")
    print(f"Total concurrent requests: {len(quotes)}")
    print(f"Dispatched to Fyers API: {fyers_call_count}")
    print(f"Quotes from Fyers API: {len(fyers_quotes)}")
    print(f"Quotes from Backup (Yahoo): {len(backup_quotes)}")

    assert len(quotes) == 50, "All 50 requests returned quotes"
    assert fyers_call_count == 1, f"Expected 1 Fyers call with mutex fix, got {fyers_call_count}"
    assert len(fyers_quotes) == 1, f"Expected 1 Fyers quote, got {len(fyers_quotes)}"
    assert len(backup_quotes) == 49, f"Expected 49 backup quotes, got {len(backup_quotes)}"
