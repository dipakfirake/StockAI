"""
Options pricing engine using Black-Scholes model.
Generates realistic options chains for educational / paper trading.
"""
import math
import numpy as np
from scipy.stats import norm
from datetime import datetime, timedelta

class BlackScholesEngine:
    @staticmethod
    def d1(S, K, T, r, sigma):
        if T <= 0:
            return 0
        return (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))

    @staticmethod
    def d2(S, K, T, r, sigma):
        if T <= 0:
            return 0
        return BlackScholesEngine.d1(S, K, T, r, sigma) - sigma * math.sqrt(T)

    @staticmethod
    def call_price(S, K, T, r, sigma):
        if T <= 0:
            return max(0.0, S - K)
        d1 = BlackScholesEngine.d1(S, K, T, r, sigma)
        d2 = BlackScholesEngine.d2(S, K, T, r, sigma)
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)

    @staticmethod
    def put_price(S, K, T, r, sigma):
        if T <= 0:
            return max(0.0, K - S)
        d1 = BlackScholesEngine.d1(S, K, T, r, sigma)
        d2 = BlackScholesEngine.d2(S, K, T, r, sigma)
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    @staticmethod
    def call_delta(S, K, T, r, sigma):
        if T <= 0:
            return 1.0 if S > K else 0.0
        d1 = BlackScholesEngine.d1(S, K, T, r, sigma)
        return norm.cdf(d1)

    @staticmethod
    def put_delta(S, K, T, r, sigma):
        if T <= 0:
            return -1.0 if K > S else 0.0
        d1 = BlackScholesEngine.d1(S, K, T, r, sigma)
        return norm.cdf(d1) - 1

    @staticmethod
    def gamma(S, K, T, r, sigma):
        if T <= 0:
            return 0.0
        d1 = BlackScholesEngine.d1(S, K, T, r, sigma)
        return norm.pdf(d1) / (S * sigma * math.sqrt(T))

    @staticmethod
    def call_theta(S, K, T, r, sigma):
        if T <= 0:
            return 0.0
        d1 = BlackScholesEngine.d1(S, K, T, r, sigma)
        d2 = BlackScholesEngine.d2(S, K, T, r, sigma)
        p1 = -(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
        p2 = r * K * math.exp(-r * T) * norm.cdf(d2)
        return (p1 - p2) / 365.0  # Daily theta

    @staticmethod
    def put_theta(S, K, T, r, sigma):
        if T <= 0:
            return 0.0
        d1 = BlackScholesEngine.d1(S, K, T, r, sigma)
        d2 = BlackScholesEngine.d2(S, K, T, r, sigma)
        p1 = -(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
        p2 = r * K * math.exp(-r * T) * norm.cdf(-d2)
        return (p1 + p2) / 365.0

    @staticmethod
    def vega(S, K, T, r, sigma):
        if T <= 0:
            return 0.0
        d1 = BlackScholesEngine.d1(S, K, T, r, sigma)
        return (S * norm.pdf(d1) * math.sqrt(T)) / 100.0  # Per 1% change

    @staticmethod
    def calculate_greeks(S, K, T, r, sigma, is_call=True):
        if is_call:
            return {
                "premium": round(BlackScholesEngine.call_price(S, K, T, r, sigma), 2),
                "delta": round(BlackScholesEngine.call_delta(S, K, T, r, sigma), 4),
                "gamma": round(BlackScholesEngine.gamma(S, K, T, r, sigma), 4),
                "theta": round(BlackScholesEngine.call_theta(S, K, T, r, sigma), 2),
                "vega": round(BlackScholesEngine.vega(S, K, T, r, sigma), 2)
            }
        else:
            return {
                "premium": round(BlackScholesEngine.put_price(S, K, T, r, sigma), 2),
                "delta": round(BlackScholesEngine.put_delta(S, K, T, r, sigma), 4),
                "gamma": round(BlackScholesEngine.gamma(S, K, T, r, sigma), 4),
                "theta": round(BlackScholesEngine.put_theta(S, K, T, r, sigma), 2),
                "vega": round(BlackScholesEngine.vega(S, K, T, r, sigma), 2)
            }


class OptionsChainGenerator:
    """Generates realistic options chain based on spot price."""
    
    @staticmethod
    def get_step_size(symbol: str, spot: float) -> int:
        sym = symbol.upper()
        if "NIFTY" in sym and "BANK" not in sym:
            return 50
        elif "BANKNIFTY" in sym or "NSEBANK" in sym:
            return 100
        elif "FINNIFTY" in sym:
            return 50
        
        # General equity rule (rough approximation for NSE stocks)
        if spot < 500: return 5
        elif spot < 2000: return 10
        elif spot < 5000: return 20
        else: return 50

    @staticmethod
    def generate_chain(symbol: str, spot_price: float, current_vix: float = 15.0):
        if spot_price <= 0:
            return []
            
        step = OptionsChainGenerator.get_step_size(symbol, spot_price)
        atm_strike = round(spot_price / step) * step
        
        # Generate 15 strikes ITM, 1 ATM, 15 strikes OTM (31 strikes total)
        strikes = [atm_strike + (i * step) for i in range(-15, 16)]
        
        # Indian risk-free rate approx 7%
        r = 0.07 
        
        # Calculate time to expiry (Simulating next Thursday for weekly)
        now = datetime.now()
        days_ahead = 3 - now.weekday()
        if days_ahead <= 0: # Today is Thu/Fri/Sat/Sun
            days_ahead += 7
        
        expiry_date = now + timedelta(days=days_ahead)
        T = max(0.01, days_ahead / 365.0)  # Time to expiry in years
        
        chain = []
        for K in strikes:
            # Introduce IV skew (OTM puts have higher IV, OTM calls slightly lower)
            moneyness = K / spot_price
            iv_skew = (1 - moneyness) * 0.15 
            sigma_call = max(0.1, (current_vix / 100.0) + (iv_skew if K > spot_price else iv_skew * 0.5))
            sigma_put = max(0.1, (current_vix / 100.0) + (iv_skew if K < spot_price else iv_skew * 0.5))
            
            call_data = BlackScholesEngine.calculate_greeks(spot_price, K, T, r, sigma_call, is_call=True)
            put_data = BlackScholesEngine.calculate_greeks(spot_price, K, T, r, sigma_put, is_call=False)
            
            # Synthetic OI based on proximity to ATM and round numbers
            base_oi = 1000000 if K == atm_strike else 500000 / (abs(K - atm_strike) / step + 1)
            if K % (step * 2) == 0: base_oi *= 1.5 # Round number bias
            
            call_oi = int(base_oi * np.random.uniform(0.8, 1.2) * (1.2 if K >= spot_price else 0.4))
            put_oi = int(base_oi * np.random.uniform(0.8, 1.2) * (1.2 if K <= spot_price else 0.4))
            
            chain.append({
                "strike": K,
                "CE": {
                    "lastPrice": call_data["premium"],
                    "openInterest": call_oi,
                    "impliedVolatility": round(sigma_call * 100, 2),
                    "delta": call_data["delta"],
                    "gamma": call_data["gamma"],
                    "theta": call_data["theta"],
                    "vega": call_data["vega"]
                },
                "PE": {
                    "lastPrice": put_data["premium"],
                    "openInterest": put_oi,
                    "impliedVolatility": round(sigma_put * 100, 2),
                    "delta": put_data["delta"],
                    "gamma": put_data["gamma"],
                    "theta": put_data["theta"],
                    "vega": put_data["vega"]
                }
            })
            
        # Calculate Max Pain and PCR
        total_ce_oi = sum(r["CE"]["openInterest"] for r in chain)
        total_pe_oi = sum(r["PE"]["openInterest"] for r in chain)
        pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 1.0
        
        # Max Pain logic (strike where option buyers lose max value)
        min_pain = float('inf')
        max_pain_strike = atm_strike
        for row in chain:
            strike = row["strike"]
            pain = 0
            for r in chain:
                # Call intrinsic value at this strike
                if strike > r["strike"]:
                    pain += (strike - r["strike"]) * r["CE"]["openInterest"]
                # Put intrinsic value at this strike
                if strike < r["strike"]:
                    pain += (r["strike"] - strike) * r["PE"]["openInterest"]
            if pain < min_pain:
                min_pain = pain
                max_pain_strike = strike

        return {
            "symbol": symbol,
            "spot_price": round(spot_price, 2),
            "expiry_date": expiry_date.strftime("%Y-%m-%d"),
            "days_to_expiry": days_ahead,
            "pcr": pcr,
            "max_pain": max_pain_strike,
            "chain": chain
        }

    @staticmethod
    def recommend_strategy(chain_data: dict, action: str, score: float, vix: float) -> dict:
        """
        AI Strategy Recommendation based on ML signal and VIX.
        """
        spot = chain_data.get("spot_price", 0)
        chain = chain_data.get("chain", [])
        if not chain:
            return None
            
        # Sort chain by strike
        chain = sorted(chain, key=lambda x: x["strike"])
        
        # Find ATM strike
        atm_row = min(chain, key=lambda x: abs(x["strike"] - spot))
        atm_idx = chain.index(atm_row)
        
        high_iv = vix > 18.0
        
        strategy_name = ""
        legs = []
        max_profit = 0
        max_loss = 0
        breakeven = 0
        reasoning = ""
        
        if action == "BUY":
            if high_iv:
                strategy_name = "Bull Put Spread (Credit)"
                sell_put = chain[atm_idx]
                buy_put = chain[max(0, atm_idx - 2)]
                credit = sell_put["PE"]["lastPrice"] - buy_put["PE"]["lastPrice"]
                spread = sell_put["strike"] - buy_put["strike"]
                max_profit = credit * 100
                max_loss = (spread - credit) * 100 if spread > credit else 0
                breakeven = sell_put["strike"] - credit
                legs = [
                    {"action": "SELL", "type": "PE", "strike": sell_put["strike"], "price": sell_put["PE"]["lastPrice"]},
                    {"action": "BUY", "type": "PE", "strike": buy_put["strike"], "price": buy_put["PE"]["lastPrice"]}
                ]
                reasoning = f"AI Conviction Score is {score} (BULLISH). High Implied Volatility ({vix}) makes credit spreads optimal. Selling the {sell_put['strike']} Put."
            else:
                strategy_name = "Bull Call Spread (Debit)"
                buy_call = chain[atm_idx]
                sell_call = chain[min(len(chain)-1, atm_idx + 2)]
                debit = buy_call["CE"]["lastPrice"] - sell_call["CE"]["lastPrice"]
                spread = sell_call["strike"] - buy_call["strike"]
                max_loss = debit * 100
                max_profit = (spread - debit) * 100 if spread > debit else 0
                breakeven = buy_call["strike"] + debit
                legs = [
                    {"action": "BUY", "type": "CE", "strike": buy_call["strike"], "price": buy_call["CE"]["lastPrice"]},
                    {"action": "SELL", "type": "CE", "strike": sell_call["strike"], "price": sell_call["CE"]["lastPrice"]}
                ]
                reasoning = f"AI Conviction Score is {score} (BULLISH). Low Volatility ({vix}) favors debit spreads. Buying the {buy_call['strike']} Call."
                
        elif action == "SELL":
            if high_iv:
                strategy_name = "Bear Call Spread (Credit)"
                sell_call = chain[atm_idx]
                buy_call = chain[min(len(chain)-1, atm_idx + 2)]
                credit = sell_call["CE"]["lastPrice"] - buy_call["CE"]["lastPrice"]
                spread = buy_call["strike"] - sell_call["strike"]
                max_profit = credit * 100
                max_loss = (spread - credit) * 100 if spread > credit else 0
                breakeven = sell_call["strike"] + credit
                legs = [
                    {"action": "SELL", "type": "CE", "strike": sell_call["strike"], "price": sell_call["CE"]["lastPrice"]},
                    {"action": "BUY", "type": "CE", "strike": buy_call["strike"], "price": buy_call["CE"]["lastPrice"]}
                ]
                reasoning = f"AI Conviction Score is {score} (BEARISH). High IV favors credit spreads to capture Theta decay."
            else:
                strategy_name = "Bear Put Spread (Debit)"
                buy_put = chain[atm_idx]
                sell_put = chain[max(0, atm_idx - 2)]
                debit = buy_put["PE"]["lastPrice"] - sell_put["PE"]["lastPrice"]
                spread = buy_put["strike"] - sell_put["strike"]
                max_loss = debit * 100
                max_profit = (spread - debit) * 100 if spread > debit else 0
                breakeven = buy_put["strike"] - debit
                legs = [
                    {"action": "BUY", "type": "PE", "strike": buy_put["strike"], "price": buy_put["PE"]["lastPrice"]},
                    {"action": "SELL", "type": "PE", "strike": sell_put["strike"], "price": sell_put["PE"]["lastPrice"]}
                ]
                reasoning = f"AI Conviction Score is {score} (BEARISH). Low IV favors debit put spreads."
        else:
            strategy_name = "Iron Condor (Neutral)"
            sell_call = chain[min(len(chain)-1, atm_idx + 3)]
            buy_call = chain[min(len(chain)-1, atm_idx + 5)]
            sell_put = chain[max(0, atm_idx - 3)]
            buy_put = chain[max(0, atm_idx - 5)]
            
            credit = (sell_call["CE"]["lastPrice"] + sell_put["PE"]["lastPrice"]) - (buy_call["CE"]["lastPrice"] + buy_put["PE"]["lastPrice"])
            spread_call = buy_call["strike"] - sell_call["strike"]
            spread_put = sell_put["strike"] - buy_put["strike"]
            max_spread = max(spread_call, spread_put)
            
            max_profit = credit * 100
            max_loss = (max_spread - credit) * 100 if max_spread > credit else 0
            breakeven = f"{sell_put['strike'] - credit:.2f} to {sell_call['strike'] + credit:.2f}"
            legs = [
                {"action": "SELL", "type": "CE", "strike": sell_call["strike"], "price": sell_call["CE"]["lastPrice"]},
                {"action": "BUY", "type": "CE", "strike": buy_call["strike"], "price": buy_call["CE"]["lastPrice"]},
                {"action": "SELL", "type": "PE", "strike": sell_put["strike"], "price": sell_put["PE"]["lastPrice"]},
                {"action": "BUY", "type": "PE", "strike": buy_put["strike"], "price": buy_put["PE"]["lastPrice"]}
            ]
            reasoning = f"AI Conviction Score is {score} (NEUTRAL). Price is expected to consolidate. Selling OTM calls and puts captures Theta decay safely."

        return {
            "name": strategy_name,
            "max_profit_per_lot": round(max_profit, 2),
            "max_loss_per_lot": round(max_loss, 2),
            "breakeven": breakeven if isinstance(breakeven, str) else round(breakeven, 2),
            "reasoning": reasoning,
            "legs": legs
        }

options_engine = OptionsChainGenerator()
