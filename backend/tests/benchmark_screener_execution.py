import asyncio
import time
from backend.services.screener import ScreenerService

async def test_run():
    print("Testing run_screener for NIFTY_50...")
    t0 = time.time()
    def prog(c, tot):
        print(f"Progress: {c}/{tot} ({time.time()-t0:.2f}s)")
    res = await ScreenerService.run_screener(sector="NIFTY_50", force_refresh=True, progress_cb=prog)
    d = time.time() - t0
    all_res = res.get("all_results", [])
    buys = res.get("buy_stocks", [])
    sells = res.get("sell_stocks", [])
    holds = res.get("hold_stocks", [])
    print(f"Done in {d:.2f}s! All: {len(all_res)}, Buys: {len(buys)}, Sells: {len(sells)}, Holds: {len(holds)}")

if __name__ == "__main__":
    asyncio.run(test_run())
