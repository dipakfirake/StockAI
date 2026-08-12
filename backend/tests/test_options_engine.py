"""Unit tests for the Options Engine."""

import pytest
import math
from backend.services.options_engine import BlackScholesEngine

def test_black_scholes_call_price():
    """Verify European call option pricing matches known Black-Scholes outputs."""
    # S = Current Price (e.g. NIFTY at 22000)
    # K = Strike Price (e.g. 22000)
    # T = Time to expiry in years (e.g. 7 days / 365)
    # r = Risk-free rate (e.g. 0.065 for India)
    # sigma = Implied Volatility (e.g. 0.15 for India VIX)
    
    S = 22000.0
    K = 22000.0
    T = 7.0 / 365.0
    r = 0.065
    sigma = 0.15
    
    # Expected call price is roughly ~220-240 based on standard BS calculator
    call_price = BlackScholesEngine.call_price(S, K, T, r, sigma)
    
    assert call_price > 0
    # At-the-money call option with 7 days to expiry, 15% IV
    # S = 22000, K = 22000, T = 0.019178, r = 0.065, sigma = 0.15
    # BS Price ~= 196.23
    assert 190.0 < call_price < 200.0

def test_black_scholes_put_price():
    """Verify European put option pricing matches known Black-Scholes outputs."""
    S = 22000.0
    K = 22000.0
    T = 7.0 / 365.0
    r = 0.065
    sigma = 0.15
    
    put_price = BlackScholesEngine.put_price(S, K, T, r, sigma)
    
    assert put_price > 0
    # Put-Call Parity: C - P = S - K*e^(-rT)
    # 196.23 - P = 22000 - 22000*exp(-0.065 * 0.019178)
    # 196.23 - P = 22000 - 21972.6
    # 196.23 - P = 27.4
    # P = 168.83
    assert 165.0 < put_price < 175.0

def test_put_call_parity():
    """Verify put-call parity holds for generated prices."""
    S = 21500.0
    K = 22000.0
    T = 30.0 / 365.0
    r = 0.07  # 7%
    sigma = 0.20
    
    C = BlackScholesEngine.call_price(S, K, T, r, sigma)
    P = BlackScholesEngine.put_price(S, K, T, r, sigma)
    
    # C - P should equal S - K * exp(-r * T)
    left_side = C - P
    right_side = S - K * math.exp(-r * T)
    
    assert pytest.approx(left_side, rel=1e-4) == right_side

def test_delta_neutrality_atm():
    """Verify ATM Call Delta is ~0.5 and ATM Put Delta is ~-0.5."""
    S = 22000.0
    K = 22000.0
    T = 10.0 / 365.0
    r = 0.065
    sigma = 0.15
    
    call_delta = BlackScholesEngine.call_delta(S, K, T, r, sigma)
    put_delta = BlackScholesEngine.put_delta(S, K, T, r, sigma)
    
    assert 0.45 < call_delta < 0.55
    assert -0.55 < put_delta < -0.45
    # Call Delta - Put Delta should be ~1
    assert pytest.approx(call_delta - put_delta, rel=1e-2) == 1.0
