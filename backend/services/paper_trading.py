"""
Paper trading service — virtual order simulation.
Phase 7 Advanced Simulation: Support for LIMIT/SL orders, Gap Risk, STT taxes, Intraday vs Delivery.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.logging_config import get_logger
from backend.models.paper_trade import PaperTrade
from backend.services.market_data import market_data_service

logger = get_logger(__name__)


class PaperTradingService:
    """
    Simulates order execution with realistic slippage, commission, and taxes.
    """

    @staticmethod
    async def place_order(
        db: AsyncSession,
        user_id: str,
        symbol: str,
        direction: str,
        quantity: int,
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        limit_price: float | None = None,
        stop_price: float | None = None,
        target_price: float | None = None,
        stop_loss: float | None = None,
    ) -> PaperTrade:
        """Place a simulated order."""
        if direction not in ("BUY", "SELL"):
            raise ValueError(f"Invalid direction '{direction}'. Must be BUY or SELL.")
        if quantity <= 0:
            raise ValueError("Quantity must be greater than 0.")
        if order_type not in ("MARKET", "LIMIT", "SL", "SL_LIMIT"):
            raise ValueError(f"Invalid order type '{order_type}'.")
        if product_type not in ("INTRADAY", "DELIVERY"):
            raise ValueError(f"Invalid product type '{product_type}'.")
        
        # Enforce Short Selling logic (Phase 7 rule)
        if direction == "SELL" and product_type == "DELIVERY":
            raise ValueError("Short selling is not allowed for DELIVERY. Please use INTRADAY.")

        # For MARKET orders, attempt immediate execution if market is open
        # For simplicity in simulation, we fetch current quote and execute immediately.
        # If market closed, we might reject or queue it (currently we reject if no price).
        quote = await market_data_service.fetch_quote(symbol)
        if not quote or not quote.get("price"):
            raise ValueError(f"Cannot fetch price for {symbol}. Market may be closed.")

        raw_price = quote["price"]
        status = "PENDING"
        entry_price = None
        slippage_amount = 0.0

        if order_type == "MARKET":
            status = "OPEN"
            slippage_amount = raw_price * settings.DEFAULT_SLIPPAGE_PCT
            entry_price = raw_price + slippage_amount if direction == "BUY" else raw_price - slippage_amount

        # Validate limit/stop logic relative to current price
        if order_type == "LIMIT" and limit_price is None:
            raise ValueError("Limit price must be provided for LIMIT orders.")
        if order_type in ("SL", "SL_LIMIT") and stop_price is None:
            raise ValueError("Stop price must be provided for SL orders.")

        trade = PaperTrade(
            user_id=uuid.UUID(str(user_id)),
            symbol=symbol,
            direction=direction,
            order_type=order_type,
            product_type=product_type,
            quantity=quantity,
            limit_price=Decimal(str(limit_price)) if limit_price else None,
            stop_price=Decimal(str(stop_price)) if stop_price else None,
            target_price=Decimal(str(target_price)) if target_price else None,
            stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
            status=status,
            commission=Decimal(str(settings.DEFAULT_COMMISSION)),
        )

        if status == "OPEN" and entry_price is not None:
            trade.entry_price = Decimal(str(round(entry_price, 4)))
            trade.slippage = Decimal(str(round(slippage_amount, 4)))

        db.add(trade)
        await db.flush()
        await db.refresh(trade)
        
        if status == "OPEN":
            logger.info(f"Market trade opened: {direction} {quantity}x{symbol} @ {entry_price:.4f}")
        else:
            logger.info(f"Pending order placed: {direction} {quantity}x{symbol} Type={order_type}")
            
        return trade

    @staticmethod
    async def close_trade(
        db: AsyncSession,
        trade_id: str,
        user_id: str,
    ) -> PaperTrade:
        """Manually close an open paper trade at current market price."""
        result = await db.execute(
            select(PaperTrade).where(
                PaperTrade.id == uuid.UUID(trade_id),
                PaperTrade.user_id == uuid.UUID(user_id),
            )
        )
        trade = result.scalar_one_or_none()
        if not trade:
            raise ValueError("Trade not found.")

        if trade.status == "PENDING":
            trade.status = "CANCELLED"
            trade.closed_at = datetime.now(timezone.utc)
            await db.flush()
            return trade

        if trade.status != "OPEN":
            raise ValueError("Trade is already closed or cancelled.")

        quote = await market_data_service.fetch_quote(trade.symbol)
        if not quote or not quote.get("price"):
            raise ValueError(f"Cannot fetch exit price for {trade.symbol}.")

        raw_exit = quote["price"]
        await PaperTradingService._execute_exit(trade, raw_exit)
        await db.flush()
        logger.info(f"Paper trade closed manually: {trade.symbol} PnL={trade.realized_pnl}")
        return trade

    @staticmethod
    async def _execute_exit(trade: PaperTrade, exit_price_raw: float):
        """Internal helper to calculate slippage, taxes, and final PnL on exit."""
        slippage = exit_price_raw * settings.DEFAULT_SLIPPAGE_PCT
        exit_price = exit_price_raw - slippage if trade.direction == "BUY" else exit_price_raw + slippage
        
        multiplier = 1 if trade.direction == "BUY" else -1
        
        # Calculate STT (0.1% on sell side for delivery)
        stt_tax = 0.0
        if trade.product_type == "DELIVERY":
            # Delivery Buy: no STT on entry, 0.1% on exit.
            # (In reality, STT is 0.1% on both sides, but for this simulation we apply 0.1% on exit value)
            stt_tax = exit_price * trade.quantity * 0.001

        realized_pnl = multiplier * (exit_price - float(trade.entry_price)) * trade.quantity - float(trade.commission) - stt_tax

        trade.exit_price = Decimal(str(round(exit_price, 4)))
        trade.stt_tax = Decimal(str(round(stt_tax, 2)))
        trade.realized_pnl = Decimal(str(round(realized_pnl, 4)))
        trade.status = "CLOSED"
        trade.closed_at = datetime.now(timezone.utc)

    @staticmethod
    async def evaluate_pending_orders(db: AsyncSession):
        """Check all PENDING orders and execute if price levels are hit."""
        result = await db.execute(select(PaperTrade).where(PaperTrade.status == "PENDING"))
        pending_orders = result.scalars().all()
        
        for order in pending_orders:
            quote = await market_data_service.fetch_quote(order.symbol)
            if not quote or not quote.get("price"):
                continue
                
            current_price = quote["price"]
            triggered = False
            
            if order.order_type == "LIMIT":
                if order.direction == "BUY" and current_price <= float(order.limit_price):
                    triggered = True
                elif order.direction == "SELL" and current_price >= float(order.limit_price):
                    triggered = True
            
            elif order.order_type == "SL":
                if order.direction == "BUY" and current_price >= float(order.stop_price):
                    triggered = True
                elif order.direction == "SELL" and current_price <= float(order.stop_price):
                    triggered = True
            
            if triggered:
                slippage_amount = current_price * settings.DEFAULT_SLIPPAGE_PCT
                entry_price = current_price + slippage_amount if order.direction == "BUY" else current_price - slippage_amount
                
                order.entry_price = Decimal(str(round(entry_price, 4)))
                order.slippage = Decimal(str(round(slippage_amount, 4)))
                order.status = "OPEN"
                logger.info(f"Auto-executed pending order: {order.direction} {order.quantity}x{order.symbol} @ {entry_price:.4f}")

    @staticmethod
    async def evaluate_open_trades(db: AsyncSession):
        """Check all OPEN trades against targets and stop losses."""
        result = await db.execute(select(PaperTrade).where(PaperTrade.status == "OPEN"))
        open_trades = result.scalars().all()
        
        for trade in open_trades:
            if not trade.target_price and not trade.stop_loss:
                continue
                
            quote = await market_data_service.fetch_quote(trade.symbol)
            if not quote or not quote.get("price"):
                continue
                
            current_price = quote["price"]
            triggered_exit = False
            
            if trade.direction == "BUY":
                if trade.target_price and current_price >= float(trade.target_price):
                    triggered_exit = True
                elif trade.stop_loss and current_price <= float(trade.stop_loss):
                    triggered_exit = True
            elif trade.direction == "SELL":
                if trade.target_price and current_price <= float(trade.target_price):
                    triggered_exit = True
                elif trade.stop_loss and current_price >= float(trade.stop_loss):
                    triggered_exit = True
                    
            if triggered_exit:
                await PaperTradingService._execute_exit(trade, current_price)
                logger.info(f"Auto-exited trade (Target/SL hit): {trade.symbol} PnL={trade.realized_pnl}")

    @staticmethod
    async def get_all_trades(db: AsyncSession, user_id: str) -> list[PaperTrade]:
        result = await db.execute(
            select(PaperTrade).where(
                PaperTrade.user_id == uuid.UUID(user_id),
            ).order_by(PaperTrade.opened_at.desc())
        )
        return result.scalars().all()


paper_trading_service = PaperTradingService()
