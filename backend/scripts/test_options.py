import asyncio
import sys
import os

# Ensure backend is in path
sys.path.append("/app")

from backend.services.options_engine import options_engine
from backend.services.screener import screener_service

async def run_test():
    symbol = "^NSEI"
    spot_price = 24200.0
    current_vix = 15.0
    
    print(f"Generating chain for {symbol} at {spot_price}")
    chain_data = options_engine.generate_chain(symbol, spot_price, current_vix)
    
    print(f"Fetching ML prediction for {symbol}")
    ai_insight = await screener_service._analyze_symbol(symbol)
    
    action = ai_insight.get("action", "HOLD")
    score = ai_insight.get("total_score", 50.0)
    
    print(f"Action: {action}, Score: {score}")
    
    strategy = options_engine.recommend_strategy(chain_data, action, score, current_vix)
    
    if strategy:
        print("\n--- AI Recommended Strategy ---")
        print(f"Name: {strategy['name']}")
        print(f"Reasoning: {strategy['reasoning']}")
        print(f"Max Profit: {strategy['max_profit_per_lot']}")
        print(f"Max Loss: {strategy['max_loss_per_lot']}")
        print(f"Breakeven: {strategy['breakeven']}")
        for leg in strategy['legs']:
            print(f"  {leg['action']} {leg['strike']} {leg['type']} @ {leg['price']}")
    else:
        print("No strategy generated.")

if __name__ == "__main__":
    asyncio.run(run_test())
