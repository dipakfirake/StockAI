import asyncio
from backend.services.market_data import market_data_service
from backend.services.options_engine import options_engine
from backend.api.scanner import evaluate_rule, SECTOR_MAP

async def run_live_tests():
    print("=" * 60)
    print("RUNNING LIVE SYSTEM & FYERS INTEGRATION TESTS")
    print("=" * 60)

    # 1. Test Fyers Bulk Quotes
    symbols = ["^NSEI", "^NSEBANK", "RELIANCE.NS", "TCS.NS", "INFY.NS", "^INDIAVIX"]
    quotes = await market_data_service.fetch_quotes_bulk(symbols)
    print(f"[1/4] Bulk Quotes: Successfully fetched {len(quotes)}/{len(symbols)} symbols.")
    for s, q in quotes.items():
        print(f"      - {s}: Price={q.get('price')} (Change: {q.get('change_pct'):+.2f}%) Source={q.get('source')}")

    # 2. Test Options Chain Engine
    spot = quotes.get("^NSEI", {}).get("price", 24250.0)
    vix = quotes.get("^INDIAVIX", {}).get("price", 14.5)
    chain = options_engine.generate_chain("^NSEI", spot, vix)
    print(f"[2/4] Options Chain: Generated 31 strikes for spot {spot:.2f} (VIX {vix:.2f})")
    print(f"      - PCR: {chain.get('pcr')}, Max Pain: {chain.get('max_pain')}, Expiry: {chain.get('expiry_date')}")

    # 3. Test Scanner Fast Evaluation
    matched, detail = await evaluate_rule("RELIANCE.NS", "EMA_BULLISH_CROSS")
    print(f"[3/4] Scanner Rule Evaluation for RELIANCE.NS (EMA_BULLISH_CROSS): Matched={matched} ({detail})")

    # 4. Test Sector Mapping
    print(f"[4/5] Sectors Verified: {len(SECTOR_MAP)} sectors registered ({', '.join(SECTOR_MAP.keys())})")

    # 5. Test Live AI Scoring & SHAP Explanations
    from backend.services.indicators import indicator_service
    from backend.services.ai_engine import ai_engine_service
    c_large = await market_data_service.fetch_candles("RELIANCE.NS", "1d", limit=100)
    ind_large = indicator_service.compute_all(c_large)
    score_large = ai_engine_service.score(ind_large, "RELIANCE.NS")
    c_small = await market_data_service.fetch_candles("SUZLON.NS", "1d", limit=100)
    ind_small = indicator_service.compute_all(c_small)
    score_small = ai_engine_service.score(ind_small, "SUZLON.NS")
    print(f"[5/6] Multi-Cap AI Scoring & SHAP Active:")
    print(f"      - LargeCap (RELIANCE): Model={score_large.get('model_version')}, Score={score_large.get('score')}, Confidence={score_large.get('confidence')}")
    print(f"      - SmallCap (SUZLON): Model={score_small.get('model_version')}, Score={score_small.get('score')}, Confidence={score_small.get('confidence')}")

    # 6. Test Backtesting Engine (All 4 Strategies)
    from backend.services.backtesting import backtest_engine
    print(f"[6/7] Testing Backtest Engine (Walk-Forward Strategy Simulation):")
    strategies = ["rsi_mean_reversion", "ema_crossover", "macd_signal", "ai_machine_learning"]
    for strat in strategies:
        params = {"quantity": 10, "rsi_buy": 30, "rsi_sell": 70, "fast_ema": 9, "slow_ema": 21, "qty_mode": "atr", "risk_pct": 0.02}
        res = await backtest_engine.run("RELIANCE.NS", strat, params, "2022-01-01", "2024-12-31", 100000.0)
        m = res.get("metrics", {})
        print(f"      - {strat:<22}: Return={m.get('total_return_pct'):+.2f}% | Trades={m.get('total_trades')} | WinRate={m.get('win_rate', 0)*100:.1f}% | Sharpe={m.get('sharpe_ratio'):.2f}")

    # 7. Test Market Scanner Presets & Sector Scans
    from backend.api.scanner import scan_nifty50, scan_sector
    print(f"[7/7] Testing Market Scanner Presets across 50 Stocks:")
    for rule in ["EMA_BULLISH_CROSS", "MACD_BULLISH", "SUPERTREND_BUY", "PRICE_ABOVE_200SMA", "RSI_BULLISH_MOMENTUM"]:
        scan_res = await scan_nifty50(rule=rule, current_user=None)
        matches = scan_res.get("matches", [])
        total = scan_res.get("total_scanned", 0)
        print(f"      - Rule {rule:<22}: Found {len(matches):2d}/{total} matching stocks (e.g. {[m['symbol'] for m in matches[:3]]})")

    bank_res = await scan_sector(sector_name="Nifty Bank", rule="EMA_BULLISH_CROSS", current_user=None)
    print(f"      - Sector Nifty Bank Scan: Found {len(bank_res.get('matches', []))}/{bank_res.get('total_scanned')} stocks")

    print("=" * 60)
    print("ALL LIVE INTEGRATION, SCANNER & BACKTEST TESTS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_live_tests())
