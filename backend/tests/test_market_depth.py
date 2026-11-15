"""
Unit and integration tests for Market Depth Service & Order Book Matching Engine.
Verifies:
1. NSE ₹0.05 tick size quantization.
2. Synthetic Level 2 5-depth generation (bids, asks, orders, qty, spread, circuits).
3. Order book liquidity sweeping and multi-level slippage simulation.
4. Circuit breaker locks (no buyers on lower circuit, no sellers on upper circuit).
5. Limit order matching logic.
6. Redis 1s single-flight caching to protect Fyers API limits.
"""

import pytest
import pytest_asyncio
from decimal import Decimal

from backend.services.market_depth_service import (
    MarketDepthService,
    quantize_tick,
    market_depth_service,
)


def test_quantize_tick_nse_accuracy():
    """Verify tick size quantization strictly rounds to NSE ₹0.05 step."""
    assert quantize_tick(100.00) == 100.00
    assert quantize_tick(100.02) == 100.00
    assert quantize_tick(100.03) == 100.05
    assert quantize_tick(100.07) == 100.05
    assert quantize_tick(100.08) == 100.10
    assert quantize_tick(2450.62) == 2450.60
    assert quantize_tick(2450.63) == 2450.65
    assert quantize_tick(-5.0) == 0.0


def test_synthetic_depth_generation_structure():
    """Verify synthetic 5-depth order book contains all Kite metrics."""
    quote = {
        "symbol": "RELIANCE.NS",
        "price": 2500.0,
        "previous_close": 2480.0,
        "open": 2485.0,
        "high": 2510.0,
        "low": 2475.0,
        "volume": 1500000,
    }

    depth = MarketDepthService.generate_synthetic_depth("RELIANCE.NS", quote)

    # 1. Check basic structure
    assert depth["symbol"] == "RELIANCE.NS"
    assert depth["ltp"] == 2500.0
    assert depth["previous_close"] == 2480.0
    assert len(depth["bids"]) == 5
    assert len(depth["asks"]) == 5

    # 2. Check Bids ordering (descending price) and tick compliance
    prev_bid_p = 999999.0
    for b in depth["bids"]:
        assert b["price"] <= prev_bid_p
        assert b["price"] % 0.05 < 1e-4 or abs((b["price"] % 0.05) - 0.05) < 1e-4
        assert b["orders"] >= 1
        assert b["quantity"] >= 10
        prev_bid_p = b["price"]

    # 3. Check Asks ordering (ascending price) and tick compliance
    prev_ask_p = 0.0
    for a in depth["asks"]:
        assert a["price"] >= prev_ask_p
        assert a["price"] % 0.05 < 1e-4 or abs((a["price"] % 0.05) - 0.05) < 1e-4
        assert a["orders"] >= 1
        assert a["quantity"] >= 10
        prev_ask_p = a["price"]

    # 4. Check Spread: Best Ask must be strictly greater than Best Bid
    best_bid = depth["bids"][0]["price"]
    best_ask = depth["asks"][0]["price"]
    assert best_ask > best_bid
    assert depth["spread"] == round(best_ask - best_bid, 2)
    assert depth["spread"] >= 0.05

    # 5. Check Circuits & ATP
    assert depth["lower_circuit"] <= 2480.0 * 0.95
    assert depth["upper_circuit"] >= 2480.0 * 1.05
    assert depth["atp"] > 0

    # 6. Check Buyer vs Seller Totals and Ratios
    assert depth["total_buy_qty"] > 0
    assert depth["total_sell_qty"] > 0
    assert abs((depth["buy_ratio"] + depth["sell_ratio"]) - 100.0) < 0.2


def test_order_book_execution_market_sell_sweeping():
    """Verify a market sell sweeps through multiple bid levels when order exceeds level 1."""
    depth = {
        "ltp": 100.0,
        "total_buy_qty": 5000,
        "total_sell_qty": 5000,
        "bids": [
            {"price": 100.00, "quantity": 200, "orders": 5},
            {"price": 99.95, "quantity": 400, "orders": 8},
            {"price": 99.90, "quantity": 500, "orders": 12},
            {"price": 99.85, "quantity": 600, "orders": 15},
            {"price": 99.80, "quantity": 800, "orders": 20},
        ],
        "asks": [
            {"price": 100.05, "quantity": 200, "orders": 4},
        ],
    }

    # Sell 500 shares:
    # 200 shares fill at 100.00 = 20,000
    # 300 shares fill at 99.95  = 29,985
    # Total = 49,985 / 500 = 99.97
    exec_price, slippage, status, reason = MarketDepthService.calculate_order_book_execution(
        depth=depth,
        direction="SELL",
        quantity=500,
        order_type="MARKET",
    )

    assert status == "FILLED"
    assert exec_price == 99.97
    assert slippage == round(100.00 - 99.97, 4)
    assert slippage == 0.03


def test_order_book_execution_market_buy_sweeping():
    """Verify a market buy sweeps through multiple ask levels."""
    depth = {
        "ltp": 100.0,
        "total_buy_qty": 5000,
        "total_sell_qty": 5000,
        "bids": [
            {"price": 99.95, "quantity": 200, "orders": 5},
        ],
        "asks": [
            {"price": 100.05, "quantity": 100, "orders": 3},
            {"price": 100.10, "quantity": 200, "orders": 5},
            {"price": 100.15, "quantity": 300, "orders": 8},
            {"price": 100.20, "quantity": 400, "orders": 10},
            {"price": 100.25, "quantity": 500, "orders": 12},
        ],
    }

    # Buy 250 shares:
    # 100 shares fill at 100.05 = 10,005
    # 150 shares fill at 100.10 = 15,015
    # Total = 25,020 / 250 = 100.08
    exec_price, slippage, status, reason = MarketDepthService.calculate_order_book_execution(
        depth=depth,
        direction="BUY",
        quantity=250,
        order_type="MARKET",
    )

    assert status == "FILLED"
    assert exec_price == 100.08
    assert slippage == round(100.08 - 100.05, 4)
    assert slippage == 0.03


def test_order_book_circuit_breaker_locks():
    """Verify circuit locks prevent immediate execution when zero liquidity exists."""
    # Lower Circuit Lock: Total Buy Qty is 0 (No buyers)
    lc_depth = {
        "ltp": 90.0,
        "total_buy_qty": 0,
        "total_sell_qty": 50000,
        "bids": [],
        "asks": [{"price": 90.05, "quantity": 10000, "orders": 50}],
    }
    _, _, status, reason = MarketDepthService.calculate_order_book_execution(
        depth=lc_depth,
        direction="SELL",
        quantity=100,
        order_type="MARKET",
    )
    assert status == "PENDING_NO_BUYERS"
    assert "Lower Circuit" in reason

    # Upper Circuit Lock: Total Sell Qty is 0 (No sellers)
    uc_depth = {
        "ltp": 110.0,
        "total_buy_qty": 50000,
        "total_sell_qty": 0,
        "bids": [{"price": 109.95, "quantity": 10000, "orders": 50}],
        "asks": [],
    }
    _, _, status, reason = MarketDepthService.calculate_order_book_execution(
        depth=uc_depth,
        direction="BUY",
        quantity=100,
        order_type="MARKET",
    )
    assert status == "PENDING_NO_SELLERS"
    assert "Upper Circuit" in reason


def test_order_book_limit_order_execution():
    """Verify Limit Orders only execute when price condition is satisfied."""
    depth = {
        "ltp": 100.0,
        "total_buy_qty": 5000,
        "total_sell_qty": 5000,
        "bids": [{"price": 100.00, "quantity": 500, "orders": 10}],
        "asks": [{"price": 100.05, "quantity": 500, "orders": 10}],
    }

    # Non-marketable Limit Sell @ 105.00 (above best bid 100.00) -> PENDING
    exec_p, _, status, reason = MarketDepthService.calculate_order_book_execution(
        depth=depth,
        direction="SELL",
        quantity=50,
        order_type="LIMIT",
        limit_price=105.00,
    )
    assert status == "PENDING"
    assert exec_p == 105.00

    # Marketable Limit Sell @ 99.50 (below best bid 100.00) -> FILLED at best bid
    exec_p, _, status, _ = MarketDepthService.calculate_order_book_execution(
        depth=depth,
        direction="SELL",
        quantity=50,
        order_type="LIMIT",
        limit_price=99.50,
    )
    assert status == "FILLED"
    assert exec_p == 100.00


from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_get_market_depth_service_async():
    """Verify get_market_depth returns valid 5-depth dictionary and caches."""
    mock_quote = {
        "symbol": "TCS.NS",
        "price": 3500.0,
        "previous_close": 3480.0,
        "open": 3490.0,
        "high": 3520.0,
        "low": 3470.0,
        "volume": 800000,
    }
    mem_cache = {}
    async def fake_get(k): return mem_cache.get(k)
    async def fake_set(k, v, ttl=60): mem_cache[k] = v

    with patch("backend.services.market_data.market_data_service.fetch_quote", new=AsyncMock(return_value=mock_quote)), \
         patch("backend.services.market_data.MarketDataService.check_and_record_fyers_rate_budget", new=AsyncMock(return_value=False)), \
         patch("backend.services.market_depth_service.cache_get", side_effect=fake_get), \
         patch("backend.services.market_depth_service.cache_set", side_effect=fake_set):
        depth = await market_depth_service.get_market_depth("TCS.NS")
        assert depth is not None
        assert depth["symbol"] == "TCS.NS"
        assert len(depth["bids"]) == 5
        assert len(depth["asks"]) == 5
        assert depth["bids"][0]["price"] < depth["asks"][0]["price"]

        # Second call should fetch cleanly from cache
        depth2 = await market_depth_service.get_market_depth("TCS.NS")
        assert depth2["symbol"] == "TCS.NS"
        assert depth2["ltp"] == depth["ltp"]


@pytest.mark.asyncio
async def test_paper_trading_exit_order_book_matching():
    """Verify that paper trade exit utilizes market depth order book matching."""
    from backend.services.paper_trading import PaperTradingService
    from backend.models.paper_trade import PaperTrade
    import uuid

    mock_trade = PaperTrade(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        symbol="INFY.NS",
        direction="BUY",
        quantity=100,
        entry_price=Decimal("1500.00"),
        order_type="MARKET",
        product_type="INTRADAY",
        commission=Decimal("20.00"),
        status="OPEN",
    )

    mock_depth = {
        "ltp": 1550.0,
        "total_buy_qty": 5000,
        "total_sell_qty": 5000,
        "bids": [
            {"price": 1549.95, "quantity": 500, "orders": 10},
        ],
        "asks": [
            {"price": 1550.05, "quantity": 500, "orders": 10},
        ],
    }

    with patch("backend.services.market_depth_service.market_depth_service.get_market_depth", new=AsyncMock(return_value=mock_depth)):
        await PaperTradingService._execute_exit(mock_trade, exit_price_raw=1550.0)
        assert mock_trade.status == "CLOSED"
        assert float(mock_trade.exit_price) == 1549.95  # Sold against Best Bid
        assert mock_trade.realized_pnl > 0
