import asyncio
import sys
import os

# Ensure backend modules can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.institutional_hunter import smc_engine
from backend.services.market_data import market_data_service

async def test_smc_profitability():
    print("Testing SMC Engine V2 Profitability across NIFTY Universe...")
    # List of liquid stocks to test
    universe = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", 
        "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "BAJFINANCE.NS"
    ]
    
    total_setups = 0
    high_confluence_setups = 0
    profitable_setups = 0
    loss_making_setups = 0
    total_rr = 0.0
    
    # We fetch a larger chunk of historical data (e.g., 200 days)
    # Then we run the engine on windows of 60 days to simulate "daily" generation
    # And check if the subsequent days hit the target or the stop loss
    
    for symbol in universe:
        print(f"\\n--- Processing {symbol} ---")
        try:
            # Fetch 200 days of data
            candles = await market_data_service.fetch_candles(symbol, "1d", limit=200)
            if not candles or len(candles) < 100:
                print(f"Not enough data for {symbol}")
                continue
                
            # Iterate through history simulating each day as "today"
            # Start from day 60 up to day 180
            for current_day_idx in range(60, len(candles) - 10):
                # Window of 60 days up to current day
                window = candles[current_day_idx-60:current_day_idx]
                
                # Use engine to find FVGs for this window
                fvgs = smc_engine.calculate_fvg(window, min_gap_pct=0.3)
                if not fvgs:
                    continue
                    
                for fvg in fvgs:
                    # Only test recent FVGs within the last 5 days of the window
                    if fvg != fvgs[-1]:
                        continue
                        
                    confluence = smc_engine._compute_confluence(window, fvg)
                    trade_plan = smc_engine._compute_trade_plan(window, fvg)
                    
                    if confluence["score"] >= 70:  # Grade A or A+
                        total_setups += 1
                        high_confluence_setups += 1
                        
                        entry_price = trade_plan["entry"]
                        target_price = trade_plan["target"]
                        stop_loss = trade_plan["stop_loss"]
                        fvg_type = fvg["type"]
                        
                        # Simulate next 10 days to see what hits first
                        future_candles = candles[current_day_idx:current_day_idx+10]
                        trade_triggered = False
                        trade_won = False
                        trade_lost = False
                        
                        for fc in future_candles:
                            f_low = fc.get("low", 0)
                            f_high = fc.get("high", 0)
                            
                            if not trade_triggered:
                                # Did price reach our entry zone?
                                if fvg_type == "bullish_fvg" and f_low <= entry_price:
                                    trade_triggered = True
                                elif fvg_type == "bearish_fvg" and f_high >= entry_price:
                                    trade_triggered = True
                                    
                            if trade_triggered:
                                if fvg_type == "bullish_fvg":
                                    if f_low <= stop_loss:
                                        trade_lost = True
                                        break
                                    if f_high >= target_price:
                                        trade_won = True
                                        break
                                else:
                                    if f_high >= stop_loss:
                                        trade_lost = True
                                        break
                                    if f_low <= target_price:
                                        trade_won = True
                                        break
                                        
                        if trade_triggered:
                            if trade_won:
                                profitable_setups += 1
                                total_rr += trade_plan["rr_ratio"]
                            elif trade_lost:
                                loss_making_setups += 1
                                total_rr -= 1 # Risk is 1R
                                
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            
    print("\\n==========================================")
    print("SMC ENGINE V2 BACKTEST RESULTS")
    print("==========================================")
    print(f"Total Grade A/A+ Setups Triggered: {profitable_setups + loss_making_setups}")
    if (profitable_setups + loss_making_setups) > 0:
        win_rate = (profitable_setups / (profitable_setups + loss_making_setups)) * 100
        print(f"Profitable Trades: {profitable_setups}")
        print(f"Losing Trades: {loss_making_setups}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Net R:R Generated: {total_rr:.2f}R")
    else:
        print("No setups triggered in the tested timeframe.")

if __name__ == "__main__":
    asyncio.run(test_smc_profitability())
