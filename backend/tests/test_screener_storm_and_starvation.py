"""
Regression & Adversarial Tests for Swing Screener 504 Cascade & Rate-Limit Remediation.

Covers:
1. FyersRateGovernor preemptible priority queue + lock-free single-flight coalescing.
2. Event-loop responsiveness under heavy BeautifulSoup Screener.in HTML parsing & ML scoring.
3. ScreenerService single-flight coalescing under concurrent force_refresh=True scans.
4. Non-blocking async scan job API (/api/market/screener/scan + poll) and non-blocking /api/presence/heartbeat.
5. Incremental same-day daily base candle synthesis + spaced Fyers slot waiting.
6. Admin /api/settings/fyers/status expired-reason attribute fix and fast_control_executor isolation.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.core.executors import run_in_scraper_executor
from backend.main import app
from backend.services.fyers_rate_governor import (
    FyersRateGovernor,
    PRIORITY_BACKGROUND,
    PRIORITY_USER_ACTION,
)
from backend.services.market_data import MarketDataService
from backend.services.screener import ScreenerService


@pytest.fixture(autouse=True)
def clean_state():
    MarketDataService.reset_fyers_health()
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    yield
    MarketDataService.reset_fyers_health()
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_governor_priority_preemption_and_lock_free_coalescing():
    """
    High-priority user actions must preempt queued background requests after backoff,
    and duplicate coalescing keys must not block behind rate sleeps.
    """
    gov = FyersRateGovernor(min_spacing_seconds=0.08)
    gov.trigger_backoff(0.25, reason="sim_429")
    order: list[str] = []

    async def bg_job(idx: int):
        async def _fn():
            order.append(f"bg_{idx}")
            return f"bg_{idx}"

        return await gov.execute(_fn, priority=PRIORITY_BACKGROUND, timeout=3.0)

    async def user_job():
        async def _fn():
            await asyncio.sleep(0.02)
            order.append("user_0")
            return {"ok": True}

        return await gov.execute(
            _fn,
            priority=PRIORITY_USER_ACTION,
            coalescing_key="user:RELIANCE",
            timeout=3.0,
        )

    bg1 = asyncio.create_task(bg_job(1))
    bg2 = asyncio.create_task(bg_job(2))
    await asyncio.sleep(0.02)  # Both bg tasks waiting during backoff

    # Launch high-priority user call + coalesced duplicate
    u1 = asyncio.create_task(user_job())
    u2 = asyncio.create_task(user_job())

    res = await asyncio.gather(bg1, bg2, u1, u2)
    assert res[2] == {"ok": True}
    assert res[3] == {"ok": True}
    assert order.count("user_0") == 1  # Coalesced into 1 execution
    # User action must execute BEFORE queued background work once backoff clears
    assert order[0] == "user_0"
    metrics = gov.get_metrics()
    assert metrics["coalesced_hits"] >= 1
    assert metrics["priority_preemptions"] >= 1


@pytest.mark.asyncio
async def test_event_loop_responsive_during_heavy_html_parsing():
    """
    Offloading Screener.in HTML parsing to scraper_io_executor keeps asyncio tick latency
    well below blocking thresholds even when parsing multiple 200KB HTML pages concurrently.
    """
    sample_html = (
        '<html><body><h1>Test Corp</h1><ul id="top-ratios">'
        + "".join(
            f'<li class="flex"><span class="name">Stock P/E</span><span class="value"><span class="number">{20.5 + i*0.01:.2f}</span></span></li>'
            for i in range(1200)
        )
        + "</ul></body></html>"
    )

    max_tick_lag = 0.0
    stop_probe = False

    async def heartbeat_probe():
        nonlocal max_tick_lag
        while not stop_probe:
            t0 = time.perf_counter()
            await asyncio.sleep(0.01)
            lag = (time.perf_counter() - t0) - 0.01
            if lag > max_tick_lag:
                max_tick_lag = lag

    probe_task = asyncio.create_task(heartbeat_probe())
    parse_tasks = [
        run_in_scraper_executor(MarketDataService._parse_screener_html_sync, sample_html)
        for _ in range(8)
    ]
    parsed = await asyncio.gather(*parse_tasks)
    stop_probe = True
    await probe_task

    assert len(parsed) == 8
    assert parsed[0]["name"] == "Test Corp"
    # Event loop stays responsive (< 250ms tick lag even under 8x 120KB+ HTML parses)
    assert max_tick_lag < 0.25, f"Event loop stalled for {max_tick_lag:.3f}s"


@pytest.mark.asyncio
async def test_screener_singleflight_coalesces_concurrent_force_refresh():
    """
    Multiple concurrent force_refresh=True scans for the same sector must coalesce
    into ONE upstream execution instead of launching duplicate storms.
    """
    analyze_calls = 0

    async def fake_analyze(symbol: str, force_refresh: bool = False, **kwargs):
        nonlocal analyze_calls
        analyze_calls += 1
        await asyncio.sleep(0.05)
        return {
            "symbol": symbol,
            "name": symbol,
            "action": "BUY",
            "total_score": 80.0,
            "scores": {"technical": 80, "fundamental": 80, "sentiment": 80},
            "trade_plan": {"expected_gain_pct": 10.0, "reward_to_risk": 2.0},
        }

    with patch.object(MarketDataService, "fetch_quotes_bulk", new_callable=AsyncMock, return_value={}), \
         patch.object(MarketDataService, "fetch_candles", new_callable=AsyncMock, return_value=[]), \
         patch.object(ScreenerService, "_analyze_symbol", side_effect=fake_analyze), \
         patch("backend.services.screener.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("backend.services.screener.cache_set", new_callable=AsyncMock):

        r1, r2, r3 = await asyncio.gather(
            ScreenerService.run_screener(symbols=["AAA.NS", "BBB.NS"], sector="SF_TEST", force_refresh=True, pace_seconds=0.0),
            ScreenerService.run_screener(symbols=["AAA.NS", "BBB.NS"], sector="SF_TEST", force_refresh=True, pace_seconds=0.0),
            ScreenerService.run_screener(symbols=["AAA.NS", "BBB.NS"], sector="SF_TEST", force_refresh=True, pace_seconds=0.0),
        )

    assert analyze_calls == 2  # 1 scan of 2 symbols, shared across all 3 callers
    assert r1["summary"]["buy_count"] == 2
    assert r2["summary"]["buy_count"] == 2
    assert r3["summary"]["buy_count"] == 2


@pytest.mark.asyncio
async def test_async_screener_scan_job_endpoints_and_fast_heartbeat():
    """
    POST /api/market/screener/scan returns 202 immediately and GET /scan/{job_id}
    completes cleanly; POST /api/presence/heartbeat responds without blocking on external ip-api.com.
    """
    mock_user = MagicMock()
    mock_user.id = "00000000-0000-0000-0000-000000000001"
    mock_user.is_pro = True
    app.dependency_overrides[get_current_user] = lambda: mock_user

    fake_output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sector": "NIFTY_50",
        "total_scanned": 25,
        "stocks_scanned": 25,
        "setups_found": 1,
        "summary": {
            "total_scanned": 25,
            "valid_results": 1,
            "buy_count": 1,
            "sell_count": 0,
            "hold_count": 0,
            "avg_buy_gain_pct": 10.0,
            "avg_buy_rr": 2.0,
            "avg_sell_drop_pct": 0.0,
            "market_breadth": "BULLISH",
            "top_buy_pick": "RELIANCE.NS",
            "top_sell_pick": None,
        },
        "buy_stocks": [{"symbol": "RELIANCE.NS", "action": "BUY", "total_score": 82.0}],
        "sell_stocks": [],
        "hold_stocks": [],
        "top_setups": [],
        "all_results": [],
    }

    async def slow_screener(*args, **kwargs):
        await asyncio.sleep(0.04)
        return fake_output

    async def slow_geo_lookup(*args, **kwargs):
        await asyncio.sleep(0.6)
        return "Mumbai, India"

    ScreenerService._scan_jobs.clear()
    ScreenerService._active_sector_jobs.clear()

    with patch.object(ScreenerService, "run_screener", side_effect=slow_screener), \
         patch("backend.services.screener.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("backend.services.screener.cache_set", new_callable=AsyncMock), \
         patch("backend.core.geoip.get_redis", new_callable=AsyncMock, return_value=None), \
         patch("backend.services.presence.get_redis", new_callable=AsyncMock, return_value=None), \
         patch("backend.core.geoip.resolve_ip_location", side_effect=slow_geo_lookup):

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            t0 = time.perf_counter()
            start_resp = await client.post("/api/market/screener/scan?sector=NIFTY_50&force_refresh=true")
            start_elapsed = time.perf_counter() - t0
            assert start_resp.status_code == 202
            job_data = start_resp.json()
            assert job_data["job_id"].startswith("scan_NIFTY_50_")
            assert start_elapsed < 0.5

            # Duplicate launch reuses active job_id instead of spawning another scan
            dup_resp = await client.post("/api/market/screener/scan?sector=NIFTY_50&force_refresh=true")
            assert dup_resp.json()["job_id"] == job_data["job_id"]

            # Public IP heartbeat must return immediately (<250ms) WITHOUT waiting on 600ms slow geo lookup
            hb_t0 = time.perf_counter()
            hb_resp = await client.post(
                "/api/presence/heartbeat",
                json={"session_id": "test-sess-1", "path": "/screener"},
                headers={"X-Forwarded-For": "8.8.8.8"},
            )
            hb_elapsed = time.perf_counter() - hb_t0
            assert hb_resp.status_code == 200
            assert hb_elapsed < 0.25

            # Poll background scan job to completion
            final_job = None
            for _ in range(20):
                await asyncio.sleep(0.02)
                poll_resp = await client.get(f"/api/market/screener/scan/{job_data['job_id']}")
                assert poll_resp.status_code == 200
                final_job = poll_resp.json()
                if final_job["status"] == "completed":
                    break

            assert final_job is not None
            assert final_job["status"] == "completed"
            assert final_job["result"]["summary"]["top_buy_pick"] == "RELIANCE.NS"


@pytest.mark.asyncio
async def test_fetch_candles_daily_base_cache_tip_sync_and_slot_wait():
    """
    1. acquire_fyers_rate_budget_slot paces sequential callers outside locks rather than dropping them.
    2. Same-day daily base candle cache synthesizes live tip from bulk quote without upstream fetches.
    """
    calls = 0

    async def delayed_admission():
        nonlocal calls
        calls += 1
        return calls >= 2

    MarketDataService._last_fyers_request_time = time.time() - 0.10
    with patch.object(MarketDataService, "check_and_record_fyers_rate_budget", side_effect=delayed_admission):
        ok = await MarketDataService.acquire_fyers_rate_budget_slot(max_wait_seconds=1.0)
        assert ok is True
        assert calls == 2

    # Base daily candle fast-path check
    base_bars = [
        {
            "timestamp": "2026-11-24T09:15:00+05:30",
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 103.0,
            "volume": 1000,
        }
    ] * 25
    live_quote = {"price": 108.5, "high": 109.0, "low": 102.0, "volume": 2500, "open": 103.5}

    async def mock_cache_get(key: str):
        if key.startswith("candles_daily_base:"):
            return base_bars
        if key == "quote:TESTTIP.NS":
            return live_quote
        return None

    with patch("backend.services.market_data.cache_get", side_effect=mock_cache_get), \
         patch("backend.services.market_data.cache_set", new_callable=AsyncMock), \
         patch("backend.services.market_data.is_indian_market_open", return_value=True), \
         patch.object(MarketDataService, "_get_fyers_client", side_effect=AssertionError("Should not call Fyers on base-cache hit")):

        candles = await MarketDataService.fetch_candles("TESTTIP.NS", "1d", limit=250)
        assert len(candles) >= 25
        assert candles[-1]["close"] == 108.5


@pytest.mark.asyncio
async def test_settings_expired_token_reason_no_attribute_error():
    """
    /api/settings/fyers/status must return gracefully when Fyers token is marked invalid
    without raising AttributeError on _fyers_token_error_reason.
    """
    from backend.api.settings import get_fyers_status

    MarketDataService.mark_fyers_token_expired("Unit test daily 06:00 AM expiry", cooldown_seconds=300.0)
    mock_db = AsyncMock()
    mock_db.execute.side_effect = Exception("No DB")
    mock_user = MagicMock()

    with patch("backend.api.settings.settings") as mock_settings, \
         patch("backend.core.cache.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("backend.core.cache.cache_set", new_callable=AsyncMock):
        mock_settings.FYERS_CLIENT_ID = "XC12345"
        mock_settings.FYERS_ACCESS_TOKEN = "expired_tok_123456"

        res = await get_fyers_status(force_refresh=False, db=mock_db, current_user=mock_user)
        assert res["token_status"] == "EXPIRED"
        assert "Unit test daily 06:00 AM expiry" in res["message"]


@pytest.mark.asyncio
async def test_fyers_websocket_invalid_symbol_minus300_does_not_expire_token():
    """
    Fyers WebSocket -300 'Please provide a valid symbol' errors (e.g. NSE:TATAMOTORS-EQ)
    must quarantine the bad symbol and NEVER mark the valid Fyers token as expired.
    """
    from backend.services.fyers_stream import FyersStreamService

    MarketDataService.reset_fyers_health()
    stream = FyersStreamService()
    try:
        err_payload = {
            "code": -300,
            "message": "Please provide a valid symbol",
            "s": "error",
            "type": "sub",
            "invalid_symbols": ["NSE:TATAMOTORS-EQ"],
        }
        stream._on_error(err_payload)

        assert MarketDataService._fyers_token_valid is True
        assert "NSE:TATAMOTORS-EQ" in stream._invalid_symbols
        assert "NSE:TATAMOTORS-EQ" in MarketDataService._invalid_fyers_symbols
    finally:
        stream._invalid_symbols.clear()
        MarketDataService.reset_fyers_health()


@pytest.mark.asyncio
async def test_bulk_quotes_quarantines_invalid_symbol_and_retries_valid_symbols():
    """
    When Fyers bulk quotes returns -300 invalid_symbols for one symbol in a chunk,
    it must quarantine that symbol, keep token health intact, and retry valid symbols.
    """
    MarketDataService.reset_fyers_health()
    mock_fyers = MagicMock()
    calls = []

    def mock_quotes(data):
        syms = data.get("symbols", "")
        calls.append(syms)
        if "NSE:TATAMOTORS-EQ" in syms:
            return {
                "code": -300,
                "message": "Please provide a valid symbol",
                "s": "error",
                "invalid_symbols": ["NSE:TATAMOTORS-EQ"],
            }
        return {
            "s": "ok",
            "d": [
                {
                    "n": "NSE:RELIANCE-EQ",
                    "v": {
                        "lp": 1350.0,
                        "ch": 12.0,
                        "chp": 0.9,
                        "volume": 500000,
                        "prev_close_price": 1338.0,
                        "open_price": 1340.0,
                        "high_price": 1355.0,
                        "low_price": 1335.0,
                    },
                }
            ],
        }

    mock_fyers.quotes.side_effect = mock_quotes

    try:
        with patch.object(MarketDataService, "check_credentials_changed", new_callable=AsyncMock), \
             patch.object(MarketDataService, "check_and_record_fyers_rate_budget", new_callable=AsyncMock, return_value=True), \
             patch.object(MarketDataService, "_get_fyers_client", new_callable=AsyncMock, return_value=mock_fyers), \
             patch("backend.services.market_data.cache_get", new_callable=AsyncMock, return_value=None), \
             patch("backend.services.market_data.cache_set", new_callable=AsyncMock):
            quotes = await MarketDataService.fetch_quotes_bulk(["TATAMOTORS.NS", "RELIANCE.NS"], use_fallback=False)

        assert MarketDataService._fyers_token_valid is True
        assert "NSE:TATAMOTORS-EQ" in MarketDataService._invalid_fyers_symbols
        assert len(calls) == 2
        assert "NSE:TATAMOTORS-EQ" not in calls[1]
        assert quotes["RELIANCE.NS"]["price"] == 1350.0
    finally:
        MarketDataService.reset_fyers_health()


@pytest.mark.asyncio
async def test_get_scan_job_status_omits_cached_data_and_fast_auth_skips_db_on_hit():
    """
    1. ScreenerService.get_scan_job_status must strip large cached_data payloads on poll calls.
    2. get_current_user_fast must resolve cached JWT users without opening a Neon Postgres session.
    """
    from fastapi import Depends, FastAPI
    from httpx import ASGITransport, AsyncClient
    from backend.core.auth import CachedAuthUser, _AUTH_USER_CACHE, create_access_token, get_current_user_fast
    from backend.services.screener import ScreenerService

    job_id = "job_lightweight_test_1"
    ScreenerService._scan_jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
        "progress": 2,
        "total": 25,
        "percent": 8,
        "cached_data": {"buy_stocks": [{"symbol": "BIG.NS"}] * 50},
    }
    try:
        status = await ScreenerService.get_scan_job_status(job_id)
        assert status is not None
        assert status["status"] == "running"
        assert "cached_data" not in status
    finally:
        ScreenerService._scan_jobs.pop(job_id, None)

    uid = "fast-cache-user-test"
    token = create_access_token({"sub": uid})
    cached_u = CachedAuthUser(
        id=uid,
        email="fast@example.com",
        name="Fast User",
        is_active=True,
        is_admin=True,
        subscription_tier="PRO",
    )
    _AUTH_USER_CACHE[uid] = (cached_u, time.monotonic() + 30.0)

    mini_app = FastAPI()

    @mini_app.get("/fast-check")
    async def fast_check(user=Depends(get_current_user_fast)):
        return {"email": user.email, "is_admin": user.is_admin}

    try:
        with patch("backend.core.database.AsyncSessionLocal", side_effect=AssertionError("DB must not be opened on fast auth cache hit")):
            async with AsyncClient(transport=ASGITransport(app=mini_app), base_url="http://test") as client:
                resp = await client.get("/fast-check", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "fast@example.com"
    finally:
        _AUTH_USER_CACHE.pop(uid, None)
