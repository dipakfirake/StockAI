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

options_engine = OptionsChainGenerator()
