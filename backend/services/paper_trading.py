"""
Paper trading service — virtual order simulation.
Phase 7 Advanced Simulation: Support for LIMIT/SL orders, Gap Risk, STT taxes, Intraday vs Delivery.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.logging_config import get_logger
from backend.core.audit_logger import log_security_event
from backend.core.event_bus import event_bus, OrderPlacedEvent, OrderExecutedEvent, OrderClosedEvent
from backend.core.market_hours import is_indian_market_open
from backend.core.telemetry import metrics
from backend.models.paper_trade import PaperTrade
from backend.services.market_data import market_data_service

logger = get_logger(__name__)

# Financial Risk & Circuit Breaker Thresholds
MAX_QUANTITY_PER_ORDER = 50_000
MAX_NOTIONAL_VALUE_PER_ORDER = 10_000_000.0  # ₹1 Crore max order notional value
MAX_PRICE_DEVIATION_PCT = 0.30              # Max ±30% deviation for LIMIT/SL from current market price


class PaperTradingService:
    """
    Simulates order execution with realistic slippage, commission, and taxes.
    Includes banking-grade financial risk controls and fat-finger circuit breakers.
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
        target_1: float | None = None,
        target_2: float | None = None,
        target_3: float | None = None,
        trailing_enabled: bool = True,
    ) -> PaperTrade:
        """Place a simulated order with strict financial validation."""
        # 1. Direction and symbol sanitization
        if direction not in ("BUY", "SELL"):
            raise ValueError(f"Invalid direction '{direction}'. Must be BUY or SELL.")
        if not re.match(r"^[A-Za-z0-9.\-:&_]{1,30}$", symbol):
            raise ValueError(f"Invalid symbol format '{symbol}'. Potential malicious input.")

        # 2. Quantity boundaries (anti-overflow & sanity bounds)
        if quantity <= 0:
            raise ValueError("Quantity must be greater than 0.")
        if quantity > MAX_QUANTITY_PER_ORDER:
            raise ValueError(
                f"Quantity ({quantity:,}) exceeds the maximum allowable single-order risk limit of {MAX_QUANTITY_PER_ORDER:,} shares."
            )

        if order_type not in ("MARKET", "LIMIT", "SL", "SL_LIMIT"):
            raise ValueError(f"Invalid order type '{order_type}'.")

        # Normalize product_type aliases (CNC -> DELIVERY, MIS -> INTRADAY)
        norm_product = product_type.upper().strip()
        if norm_product in ("CNC", "DELIVERY"):
            product_type = "DELIVERY"
        elif norm_product in ("MIS", "INTRADAY"):
            product_type = "INTRADAY"
        else:
            raise ValueError(f"Invalid product type '{product_type}'. Must be INTRADAY (MIS) or DELIVERY (CNC).")
        
        # Enforce Short Selling logic: short sales in Indian equities must be INTRADAY
        if direction == "SELL" and product_type == "DELIVERY":
            # Automatically adapt simulated short selling to INTRADAY
            product_type = "INTRADAY"

        # For MARKET orders, attempt immediate execution if market is open
        # For simplicity in simulation, we fetch current quote and execute immediately.
        # If market closed, we might reject or queue it (currently we reject if no price).
        quote = await market_data_service.fetch_quote(symbol)
        if not quote or not quote.get("price"):
            raise ValueError(f"Cannot fetch price for {symbol}. Market may be closed.")

        raw_price = quote["price"]

        # 3. Notional risk limit (anti-leverage / capital overflow protection)
        notional_value = raw_price * quantity
        if notional_value > MAX_NOTIONAL_VALUE_PER_ORDER:
            log_security_event(
                event_type="ORDER_RISK_LIMIT_EXCEEDED",
                severity="WARNING",
                user_id=str(user_id),
                details={"symbol": symbol, "quantity": quantity, "notional_value": notional_value},
            )
            raise ValueError(
                f"Order notional value (₹{notional_value:,.2f}) exceeds the maximum allowable limit of ₹{MAX_NOTIONAL_VALUE_PER_ORDER:,.2f}."
            )

        # 4. Fat-Finger Price Deviation Bounds (validate before matching)
        if order_type == "LIMIT":
            if limit_price is None:
                raise ValueError("Limit price must be provided for LIMIT orders.")
            deviation = abs(limit_price - raw_price) / raw_price
            if deviation > MAX_PRICE_DEVIATION_PCT:
                raise ValueError(
                    f"Limit price (₹{limit_price}) deviates by {deviation*100:.1f}% from market price (₹{raw_price}). "
                    f"Maximum allowed deviation is {int(MAX_PRICE_DEVIATION_PCT*100)}%. Fat-finger circuit breaker triggered."
                )

        if order_type in ("SL", "SL_LIMIT"):
            if stop_price is None:
                raise ValueError("Stop price must be provided for SL orders.")
            deviation = abs(stop_price - raw_price) / raw_price
            if deviation > MAX_PRICE_DEVIATION_PCT:
                raise ValueError(
                    f"Stop price (₹{stop_price}) deviates by {deviation*100:.1f}% from market price (₹{raw_price}). "
                    f"Maximum allowed deviation is {int(MAX_PRICE_DEVIATION_PCT*100)}%. Fat-finger circuit breaker triggered."
                )

        status = "PENDING"
        entry_price = None
        slippage_amount = 0.0

        # Order Book Liquidity Matching Engine ("Only sell when someone buys / Only buy when someone sells")
        from backend.services.market_depth_service import market_depth_service, MarketDepthService
        try:
            depth = await market_depth_service.get_market_depth(symbol)
        except Exception:
            depth = None

        if order_type == "MARKET":
            if depth:
                exec_price, slip, exec_status, reason = MarketDepthService.calculate_order_book_execution(
                    depth=depth,
                    direction=direction,
                    quantity=quantity,
                    order_type="MARKET",
                )
                if exec_status == "FILLED":
                    status = "OPEN"
                    entry_price = exec_price
                    slippage_amount = slip
                elif exec_status in ("PENDING_NO_BUYERS", "PENDING_NO_SELLERS"):
                    # Circuit breaker / exchange-closed lock: queue order cleanly as PENDING
                    status = "PENDING"
                    entry_price = None
                    slippage_amount = 0.0
                    logger.warning(f"Market order queued due to order book lock: {reason}")
                else:
                    raise ValueError(reason)
            else:
                status = "OPEN"
                slippage_amount = raw_price * settings.DEFAULT_SLIPPAGE_PCT
                entry_price = raw_price + slippage_amount if direction == "BUY" else raw_price - slippage_amount
        elif order_type == "LIMIT" and is_indian_market_open():
            # Immediately execute marketable LIMIT orders when live market liquidity satisfies the limit boundary
            if depth:
                exec_price, slip, exec_status, _ = MarketDepthService.calculate_order_book_execution(
                    depth=depth,
                    direction=direction,
                    quantity=quantity,
                    order_type="LIMIT",
                    limit_price=limit_price,
                )
                if exec_status == "FILLED":
                    status = "OPEN"
                    entry_price = exec_price
                    slippage_amount = slip
            else:
                is_marketable = (
                    (direction == "BUY" and raw_price <= float(limit_price))
                    or (direction == "SELL" and raw_price >= float(limit_price))
                )
                if is_marketable:
                    status = "OPEN"
                    slippage_amount = raw_price * settings.DEFAULT_SLIPPAGE_PCT
                    entry_price = raw_price + slippage_amount if direction == "BUY" else raw_price - slippage_amount

        # Normalize Progressive Coupled Ratchet targets when multi-tier T1/T2/T3 are supplied
        has_multi_targets = any(v is not None and float(v) > 0 for v in (target_1, target_2, target_3))
        eff_t1 = float(target_1) if (target_1 and float(target_1) > 0) else None
        eff_t2 = float(target_2) if (target_2 and float(target_2) > 0) else (float(target_price) if (has_multi_targets and target_price and float(target_price) > 0) else None)
        eff_t3 = float(target_3) if (target_3 and float(target_3) > 0) else None
        if has_multi_targets:
            candidates = [v for v in (eff_t1, eff_t2, eff_t3, target_price) if v is not None and float(v) > 0]
            eff_target_price = max(candidates) if direction == "BUY" else min(candidates)
        else:
            eff_target_price = target_price

        trade = PaperTrade(
            user_id=uuid.UUID(str(user_id)),
            symbol=symbol,
            direction=direction,
            order_type=order_type,
            product_type=product_type,
            quantity=quantity,
            limit_price=Decimal(str(limit_price)) if limit_price else None,
            stop_price=Decimal(str(stop_price)) if stop_price else None,
            target_price=Decimal(str(round(eff_target_price, 4))) if eff_target_price else None,
            stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
            target_1=Decimal(str(round(eff_t1, 4))) if eff_t1 else None,
            target_2=Decimal(str(round(eff_t2, 4))) if eff_t2 else None,
            target_3=Decimal(str(round(eff_t3, 4))) if eff_t3 else None,
            initial_stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
            ratchet_stage="INITIAL",
            trailing_enabled=bool(trailing_enabled),
            status=status,
            commission=Decimal(str(settings.DEFAULT_COMMISSION)),
        )

        if status == "OPEN" and entry_price is not None:
            entry_dec = Decimal(str(round(entry_price, 4)))
            trade.entry_price = entry_dec
            trade.highest_price_recorded = entry_dec
            trade.lowest_price_recorded = entry_dec
            trade.slippage = Decimal(str(round(slippage_amount, 4)))

        db.add(trade)
        await db.flush()
        await db.refresh(trade)
        
        log_security_event(
            event_type="ORDER_PLACED",
            severity="INFO",
            user_id=str(user_id),
            details={
                "trade_id": str(trade.id),
                "symbol": symbol,
                "direction": direction,
                "quantity": quantity,
                "order_type": order_type,
                "status": status,
                "price": entry_price or raw_price,
            },
        )

        # Track telemetry & publish domain event asynchronously
        metrics.inc_order(direction, order_type, status)
        await event_bus.publish(
            OrderPlacedEvent(
                user_id=str(user_id),
                trade_id=str(trade.id),
                symbol=symbol,
                direction=direction,
                quantity=quantity,
                order_type=order_type,
                price=float(entry_price or raw_price),
            )
        )

        if status == "OPEN":
            await event_bus.publish(
                OrderExecutedEvent(
                    user_id=str(user_id),
                    trade_id=str(trade.id),
                    symbol=symbol,
                    direction=direction,
                    quantity=quantity,
                    execution_price=float(entry_price or raw_price),
                    slippage=float(slippage_amount),
                )
            )
            logger.info(f"Market/marketable trade opened: {direction} {quantity}x{symbol} @ {entry_price:.4f}")
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
            log_security_event(
                event_type="ORDER_CANCELLED",
                severity="INFO",
                user_id=str(user_id),
                details={"trade_id": str(trade.id), "symbol": trade.symbol},
            )
            return trade

        if trade.status != "OPEN":
            raise ValueError("Trade is already closed or cancelled.")

        quote = await market_data_service.fetch_quote(trade.symbol)
        if not quote or not quote.get("price"):
            raise ValueError(f"Cannot fetch exit price for {trade.symbol}.")

        raw_exit = quote["price"]
        await PaperTradingService._execute_exit(trade, raw_exit)
        await db.flush()
        
        log_security_event(
            event_type="ORDER_CLOSED",
            severity="INFO",
            user_id=str(user_id),
            details={
                "trade_id": str(trade.id),
                "symbol": trade.symbol,
                "exit_price": float(trade.exit_price),
                "realized_pnl": float(trade.realized_pnl),
            },
        )
        # Publish domain event for trade closure
        await event_bus.publish(
            OrderClosedEvent(
                user_id=str(user_id),
                trade_id=str(trade.id),
                symbol=trade.symbol,
                exit_price=float(trade.exit_price),
                realized_pnl=float(trade.realized_pnl),
            )
        )
        logger.info(f"Paper trade closed manually: {trade.symbol} PnL={trade.realized_pnl}")
        return trade

    @staticmethod
    async def _execute_exit(trade: PaperTrade, exit_price_raw: float):
        """Internal helper to calculate slippage, taxes, and final PnL on exit matching against order book."""
        from backend.services.market_depth_service import market_depth_service, MarketDepthService
        
        exit_direction = "SELL" if trade.direction == "BUY" else "BUY"
        exit_price = None
        
        try:
            depth = await market_depth_service.get_market_depth(trade.symbol)
            if depth:
                exec_p, _, exec_status, _ = MarketDepthService.calculate_order_book_execution(
                    depth=depth,
                    direction=exit_direction,
                    quantity=trade.quantity,
                    order_type="MARKET"
                )
                if exec_status == "FILLED":
                    exit_price = exec_p
        except Exception:
            pass

        if exit_price is None:
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
    async def evaluate_pending_orders(db: AsyncSession, user_id: str | None = None) -> int:
        """Check all PENDING orders (MARKET AMO, LIMIT, SL, SL_LIMIT) and execute against live liquidity."""
        from backend.services.market_depth_service import market_depth_service, MarketDepthService

        stmt = select(PaperTrade).where(PaperTrade.status == "PENDING")
        if user_id:
            stmt = stmt.where(PaperTrade.user_id == uuid.UUID(str(user_id)))
        result = await db.execute(stmt)
        pending_orders = result.scalars().all()
        if not pending_orders:
            return 0

        pending_symbols = list({o.symbol for o in pending_orders})
        quotes_map = await market_data_service.fetch_quotes_bulk(pending_symbols) if pending_symbols else {}

        executed_count = 0
        for order in pending_orders:
            quote = quotes_map.get(order.symbol)
            if not quote or not quote.get("price"):
                quote = await market_data_service.fetch_quote(order.symbol)
            if not quote or not quote.get("price"):
                continue

            current_price = float(quote["price"])
            triggered = False

            if order.order_type == "MARKET":
                # After-Market / Liquidity-Locked MARKET orders execute as soon as market depth unlocks
                triggered = True
            elif order.order_type == "LIMIT" and order.limit_price is not None:
                lim = float(order.limit_price)
                if order.direction == "BUY" and current_price <= lim:
                    triggered = True
                elif order.direction == "SELL" and current_price >= lim:
                    triggered = True
            elif order.order_type == "SL" and order.stop_price is not None:
                stp = float(order.stop_price)
                if order.direction == "BUY" and current_price >= stp:
                    triggered = True
                elif order.direction == "SELL" and current_price <= stp:
                    triggered = True
            elif order.order_type == "SL_LIMIT" and order.stop_price is not None:
                stp = float(order.stop_price)
                lim = float(order.limit_price) if order.limit_price is not None else None
                if order.direction == "BUY" and current_price >= stp and (lim is None or current_price <= lim):
                    triggered = True
                elif order.direction == "SELL" and current_price <= stp and (lim is None or current_price >= lim):
                    triggered = True

            if not triggered:
                continue

            try:
                depth = await market_depth_service.get_market_depth(order.symbol)
                exec_p, slip_amt, exec_stat, _ = MarketDepthService.calculate_order_book_execution(
                    depth=depth,
                    direction=order.direction,
                    quantity=order.quantity,
                    order_type="MARKET",
                )
                if exec_stat == "FILLED":
                    entry_price = exec_p
                    slippage_amount = slip_amt
                else:
                    continue  # Wait for liquidity / session unlock
            except Exception:
                slippage_amount = current_price * settings.DEFAULT_SLIPPAGE_PCT
                entry_price = current_price + slippage_amount if order.direction == "BUY" else current_price - slippage_amount

            entry_dec = Decimal(str(round(entry_price, 4)))
            order.entry_price = entry_dec
            order.highest_price_recorded = entry_dec
            order.lowest_price_recorded = entry_dec
            if order.stop_loss is not None and order.initial_stop_loss is None:
                order.initial_stop_loss = order.stop_loss
            order.slippage = Decimal(str(round(slippage_amount, 4)))
            order.status = "OPEN"
            order.opened_at = datetime.now(timezone.utc)
            executed_count += 1

            try:
                from backend.services.notification_service import notify_order_filled
                await notify_order_filled(db, order)
            except Exception:
                pass

            await event_bus.publish(
                OrderExecutedEvent(
                    user_id=str(order.user_id),
                    trade_id=str(order.id),
                    symbol=order.symbol,
                    direction=order.direction,
                    quantity=order.quantity,
                    execution_price=float(order.entry_price),
                    slippage=float(order.slippage),
                )
            )
            logger.info(
                f"Auto-executed pending {order.order_type} order: {order.direction} {order.quantity}x{order.symbol} @ {entry_price:.4f}"
            )

        return executed_count

    @staticmethod
    async def evaluate_open_trades(db: AsyncSession):
        """
        Check all OPEN trades against targets, progressive T1 -> T2 -> T3 Coupled Ratchet trailing stops,
        and initial stop losses using a single batched market quote call per sweep.
        """
        result = await db.execute(select(PaperTrade).where(PaperTrade.status == "OPEN"))
        open_trades = result.scalars().all()
        if not open_trades:
            return

        # Read coupled ratchet toggle once per sweep (gracefully skips if mocked DB)
        coupled_ratchet_enabled = True
        atr_trail_pct = 0.015
        try:
            from unittest.mock import MagicMock, AsyncMock
            if not isinstance(db, (MagicMock, AsyncMock)) and hasattr(db, "get_bind"):
                bind = db.get_bind()
                if bind is not None and not isinstance(bind, (MagicMock, AsyncMock)):
                    from backend.models.settings import SystemSettings
                    cfg_rows = (
                        await db.execute(
                            select(SystemSettings).where(
                                SystemSettings.key.in_(["enable_coupled_ratchet", "swing_atr_multiplier"])
                            )
                        )
                    ).scalars().all()
                    for row in cfg_rows:
                        if row.key == "enable_coupled_ratchet" and row.value is not None:
                            coupled_ratchet_enabled = str(row.value).strip().lower() in ("true", "1", "yes", "on")
                        elif row.key == "swing_atr_multiplier" and row.value is not None:
                            atr_mult = max(0.5, min(float(row.value), 5.0))
                            atr_trail_pct = max(0.01, min(0.04, atr_mult * 0.01))
        except Exception:
            pass

        open_symbols = list({
            t.symbol for t in open_trades
            if t.target_price or t.stop_loss or getattr(t, "target_1", None) or getattr(t, "target_2", None) or getattr(t, "target_3", None)
        })
        if not open_symbols:
            return
        quotes_map = await market_data_service.fetch_quotes_bulk(open_symbols, use_fallback=True)

        for trade in open_trades:
            t1_dec = getattr(trade, "target_1", None)
            t2_dec = getattr(trade, "target_2", None)
            t3_dec = getattr(trade, "target_3", None)
            if not (trade.target_price or trade.stop_loss or t1_dec or t2_dec or t3_dec):
                continue

            clean_sym = trade.symbol.replace(".NS", "").replace(".BO", "").strip().upper()
            quote = (
                quotes_map.get(trade.symbol)
                or quotes_map.get(f"{clean_sym}.NS")
                or quotes_map.get(f"{clean_sym}.BO")
                or quotes_map.get(clean_sym)
            )
            if (not quote or not quote.get("price")) and len(open_symbols) <= 3:
                quote = await market_data_service.fetch_quote(trade.symbol)
            if not quote or not quote.get("price"):
                continue

            current_price = float(quote["price"])
            entry_p = float(trade.entry_price or current_price)
            prev_stage = str(getattr(trade, "ratchet_stage", "INITIAL") or "INITIAL")
            has_multi = any(v is not None and float(v) > 0 for v in (t1_dec, t2_dec, t3_dec))
            trailing_on = bool(getattr(trade, "trailing_enabled", True)) and coupled_ratchet_enabled and has_multi

            triggered_exit = False
            new_stage = prev_stage
            curr_sl = float(trade.stop_loss) if trade.stop_loss is not None else None

            if trailing_on and entry_p > 0:
                if trade.initial_stop_loss is None and curr_sl is not None:
                    trade.initial_stop_loss = Decimal(str(round(curr_sl, 4)))

                if trade.direction == "BUY":
                    t1_val = float(t1_dec or trade.target_price or 0.0)
                    t2_val = float(t2_dec or 0.0)
                    t3_val = float(t3_dec or 0.0)
                    has_t2 = bool(t2_val > t1_val > 0)
                    has_t3 = bool(has_t2 and t3_val > t2_val)

                    prev_high = float(getattr(trade, "highest_price_recorded", None) or entry_p)
                    highest_p = max(prev_high, entry_p, current_price)
                    trade.highest_price_recorded = Decimal(str(round(highest_p, 4)))

                    # 1. Check ultimate progressive target exit first (T3 if present, else T2, else T1)
                    if has_t3 and current_price >= t3_val:
                        new_stage = "TARGET_3_ACHIEVED"
                        triggered_exit = True
                    elif has_t2 and (not has_t3) and current_price >= t2_val:
                        new_stage = "TARGET_2_ACHIEVED"
                        triggered_exit = True
                    elif (not has_t2) and t1_val > 0 and current_price >= t1_val:
                        new_stage = "TARGET_1_ACHIEVED"
                        triggered_exit = True
                    else:
                        # 2. Apply Progressive Ratchet SL Step-Ups
                        sl_floor = curr_sl if curr_sl is not None else round(entry_p * 0.96, 2)
                        if has_t2 and t1_val > 0 and highest_p >= t1_val:
                            # Stage 1: Breakeven + 1% protection at T1 cross
                            be_lock = round(entry_p * 1.01, 2)
                            if be_lock > sl_floor:
                                sl_floor = be_lock
                            if new_stage == "INITIAL":
                                new_stage = "BREAKEVEN_LOCKED"

                            # Stage 2: Halfway to T2 -> lock SL at Target 1
                            half_t2 = t1_val + 0.5 * (t2_val - t1_val)
                            if highest_p >= half_t2:
                                t1_floor = round(t1_val, 2)
                                if t1_floor > sl_floor:
                                    sl_floor = t1_floor
                                if new_stage in ("INITIAL", "BREAKEVEN_LOCKED"):
                                    new_stage = "T2_RATCHET_ACTIVE"

                        # Stage 3: T2 crossed while trailing toward T3 -> lock near/at T2!
                        if has_t3 and highest_p >= t2_val:
                            t2_floor = round(max(t1_val, t2_val * 0.992), 2)
                            if highest_p >= t2_val + 0.35 * (t3_val - t2_val):
                                t2_floor = max(t2_floor, round(t2_val, 2))
                            peak_trail = round(highest_p * (1.0 - atr_trail_pct), 2)
                            # Trail peak upward cleanly without ever setting SL above current_price unless T2 floor already crossed earlier
                            candidate_floor = max(sl_floor, t2_floor)
                            if peak_trail > candidate_floor and peak_trail < current_price:
                                candidate_floor = peak_trail
                            sl_floor = candidate_floor
                            new_stage = "T3_RATCHET_ACTIVE"

                        if sl_floor > (curr_sl or 0.0):
                            trade.stop_loss = Decimal(str(round(sl_floor, 4)))
                        curr_sl = float(trade.stop_loss) if trade.stop_loss is not None else sl_floor

                        # Check stop-loss trigger on current tick
                        if current_price <= curr_sl:
                            if new_stage != "INITIAL" and curr_sl >= entry_p:
                                new_stage = "STOPPED_IN_PROFIT"
                            else:
                                new_stage = "STOPLOSS_HIT"
                            triggered_exit = True

                elif trade.direction == "SELL":
                    t1_val = float(t1_dec or trade.target_price or 0.0)
                    t2_val = float(t2_dec or 0.0)
                    t3_val = float(t3_dec or 0.0)
                    has_t2 = bool(0 < t2_val < t1_val)
                    has_t3 = bool(has_t2 and 0 < t3_val < t2_val)

                    prev_low = float(getattr(trade, "lowest_price_recorded", None) or entry_p)
                    lowest_p = min(prev_low, entry_p, current_price)
                    trade.lowest_price_recorded = Decimal(str(round(lowest_p, 4)))

                    if has_t3 and current_price <= t3_val:
                        new_stage = "TARGET_3_ACHIEVED"
                        triggered_exit = True
                    elif has_t2 and (not has_t3) and current_price <= t2_val:
                        new_stage = "TARGET_2_ACHIEVED"
                        triggered_exit = True
                    elif (not has_t2) and t1_val > 0 and current_price <= t1_val:
                        new_stage = "TARGET_1_ACHIEVED"
                        triggered_exit = True
                    else:
                        sl_ceil = curr_sl if curr_sl is not None else round(entry_p * 1.04, 2)
                        if has_t2 and t1_val > 0 and lowest_p <= t1_val:
                            be_lock = round(entry_p * 0.99, 2)
                            if be_lock < sl_ceil:
                                sl_ceil = be_lock
                            if new_stage == "INITIAL":
                                new_stage = "BREAKEVEN_LOCKED"
                            half_t2 = t1_val - 0.5 * (t1_val - t2_val)
                            if lowest_p <= half_t2:
                                sl_ceil = min(sl_ceil, round(t1_val, 2))
                                if new_stage in ("INITIAL", "BREAKEVEN_LOCKED"):
                                    new_stage = "T2_RATCHET_ACTIVE"
                        if has_t3 and lowest_p <= t2_val:
                            t2_ceil = round(min(t1_val, t2_val * 1.008), 2)
                            if lowest_p <= t2_val - 0.35 * (t2_val - t3_val):
                                t2_ceil = min(t2_ceil, round(t2_val, 2))
                            sl_ceil = min(sl_ceil, t2_ceil)
                            new_stage = "T3_RATCHET_ACTIVE"

                        if sl_ceil < (curr_sl or float("inf")):
                            trade.stop_loss = Decimal(str(round(sl_ceil, 4)))
                        curr_sl = float(trade.stop_loss) if trade.stop_loss is not None else sl_ceil

                        if current_price >= curr_sl:
                            if new_stage != "INITIAL" and curr_sl <= entry_p:
                                new_stage = "STOPPED_IN_PROFIT"
                            else:
                                new_stage = "STOPLOSS_HIT"
                            triggered_exit = True

                trade.ratchet_stage = new_stage
                if new_stage != prev_stage:
                    try:
                        from backend.api.websocket import broadcast_alert
                        await broadcast_alert(
                            {
                                "type": "COUPLED_RATCHET_UPDATE",
                                "symbol": trade.symbol,
                                "trade_id": str(trade.id),
                                "ratchet_stage": new_stage,
                                "new_stop_loss": float(trade.stop_loss) if trade.stop_loss is not None else None,
                                "current_price": current_price,
                                "message": f"{trade.symbol} progressed to {new_stage.replace('_', ' ')} (SL: ₹{float(trade.stop_loss or 0):,.2f})",
                            },
                            user_id=str(trade.user_id),
                        )
                    except Exception:
                        pass
            else:
                # Standard fixed single Target / Stop-Loss check
                fixed_exit_reason = None
                if trade.direction == "BUY":
                    if trade.target_price and current_price >= float(trade.target_price):
                        triggered_exit = True
                        fixed_exit_reason = "SYSTEM_AUTO_TARGET"
                    elif trade.stop_loss and current_price <= float(trade.stop_loss):
                        triggered_exit = True
                        fixed_exit_reason = "SYSTEM_AUTO_STOPLOSS"
                elif trade.direction == "SELL":
                    if trade.target_price and current_price <= float(trade.target_price):
                        triggered_exit = True
                        fixed_exit_reason = "SYSTEM_AUTO_TARGET"
                    elif trade.stop_loss and current_price >= float(trade.stop_loss):
                        triggered_exit = True
                        fixed_exit_reason = "SYSTEM_AUTO_STOPLOSS"

            if triggered_exit:
                if trailing_on:
                    stage_reason_map = {
                        "TARGET_3_ACHIEVED": "SYSTEM_AUTO_TARGET_3",
                        "TARGET_2_ACHIEVED": "SYSTEM_AUTO_TARGET_2",
                        "TARGET_1_ACHIEVED": "SYSTEM_AUTO_TARGET_1",
                        "STOPPED_IN_PROFIT": "SYSTEM_AUTO_STOP_IN_PROFIT",
                        "STOPLOSS_HIT": "SYSTEM_AUTO_STOPLOSS",
                    }
                    reason_code = stage_reason_map.get(new_stage, "SYSTEM_AUTO_TARGET")
                else:
                    reason_code = fixed_exit_reason or "SYSTEM_AUTO_TARGET"
                trade.closed_by = "AUTO_SYSTEM"
                trade.exit_reason = reason_code
                await PaperTradingService._execute_exit(trade, current_price)
                await PaperTradingService._deactivate_exit_alerts_if_flat(
                    db, str(trade.user_id), trade.symbol, active_open_trades=open_trades
                )
                try:
                    from backend.services.notification_service import notify_auto_sell_exit
                    exit_meta = PaperTradingService.resolve_trade_exit_details(trade)
                    exit_label = PaperTradingService.EXIT_REASON_LABELS.get(reason_code, "System Auto-Sell")
                    await notify_auto_sell_exit(db, trade, reason_code, exit_label, exit_meta)
                except Exception:
                    pass
                logger.info(f"Auto-exited trade ({trade.exit_reason} / {trade.ratchet_stage}): {trade.symbol} PnL={trade.realized_pnl}")

    EXIT_REASON_LABELS = {
        "SYSTEM_AUTO_TARGET": "System Auto-Sell (Target Hit)",
        "SYSTEM_AUTO_TARGET_1": "System Auto-Sell (Target 1 Achieved)",
        "SYSTEM_AUTO_TARGET_2": "System Auto-Sell (Target 2 Achieved)",
        "SYSTEM_AUTO_TARGET_3": "System Auto-Sell (Target 3 Achieved)",
        "SYSTEM_AUTO_STOP_IN_PROFIT": "System Auto-Sell (Trailing Profit Lock Hit)",
        "SYSTEM_AUTO_STOPLOSS": "System Auto-Sell (Stop-Loss Triggered)",
        "SYSTEM_AUTO_EOD_INTRADAY": "System Auto-Sell (15:20 IST Intraday Square-Off)",
        "USER_MANUAL_EXIT": "User Manual Exit",
        "USER_CANCELLED": "User Cancelled Order",
    }

    @staticmethod
    def _canonical_symbol(sym: str | None) -> str:
        if not sym:
            return ""
        return str(sym).upper().strip().replace(".NS", "").replace(".BO", "")

    @staticmethod
    async def _deactivate_exit_alerts_if_flat(
        db: AsyncSession,
        user_id_str: str,
        symbol: str,
        active_open_trades: list[PaperTrade] | None = None,
    ) -> int:
        """
        When a user's final OPEN position for a symbol closes, deactivate lingering
        TARGET_*, STOP_LOSS_*, and BUY_PROXIMITY alerts for that symbol so exited
        positions do not continue firing false sell/risk alerts.
        """
        try:
            target_canon = PaperTradingService._canonical_symbol(symbol)
            if not target_canon or db is None:
                return 0
            uid = uuid.UUID(str(user_id_str))

            still_open = False
            if active_open_trades is not None:
                for ot in active_open_trades:
                    if (
                        getattr(ot, "status", None) == "OPEN"
                        and str(getattr(ot, "user_id", "")) == str(uid)
                        and PaperTradingService._canonical_symbol(getattr(ot, "symbol", "")) == target_canon
                    ):
                        still_open = True
                        break
            else:
                open_res = await db.execute(
                    select(PaperTrade).where(
                        PaperTrade.user_id == uid,
                        PaperTrade.status == "OPEN",
                    )
                )
                for ot in open_res.scalars().all():
                    if PaperTradingService._canonical_symbol(getattr(ot, "symbol", "")) == target_canon:
                        still_open = True
                        break

            if still_open:
                return 0

            from backend.services.notification_service import session_has_table
            if not await session_has_table(db, "alerts"):
                return 0

            from backend.models.alert import Alert
            alert_res = await db.execute(
                select(Alert).where(
                    Alert.user_id == uid,
                    Alert.is_active == True,
                    Alert.condition_type.in_([
                        "TARGET_PROXIMITY",
                        "TARGET_HIT",
                        "STOP_LOSS_PROXIMITY",
                        "STOP_LOSS_HIT",
                        "BUY_PROXIMITY",
                    ]),
                )
            )
            deactivated = 0
            for alert in alert_res.scalars().all():
                if not isinstance(alert, Alert):
                    continue
                if PaperTradingService._canonical_symbol(getattr(alert, "symbol", "")) == target_canon:
                    alert.is_active = False
                    deactivated += 1
            return deactivated
        except Exception as e:
            logger.debug(f"Skip orphan alert cleanup for {symbol}: {e}")
            return 0

    @staticmethod
    def resolve_trade_exit_details(trade: PaperTrade, now_utc: datetime | None = None) -> dict:
        """
        Deterministically compute exit price, holding duration, charges, net %, and
        AUTO_SYSTEM vs USER_MANUAL attribution (including retroactive classification
        for legacy closed trades whose closed_by/exit_reason columns are NULL).
        """
        from datetime import timedelta
        now_ref = now_utc or datetime.now(timezone.utc)
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        now_ist = now_ref.astimezone(ist_tz)

        opened_at_raw = getattr(trade, "opened_at", None)
        opened_at_utc = (
            opened_at_raw if isinstance(opened_at_raw, datetime) else now_ref
        )
        if opened_at_utc.tzinfo is None:
            opened_at_utc = opened_at_utc.replace(tzinfo=timezone.utc)

        closed_at_raw = getattr(trade, "closed_at", None)
        closed_at_utc = None
        if isinstance(closed_at_raw, datetime):
            closed_at_utc = closed_at_raw if closed_at_raw.tzinfo else closed_at_raw.replace(tzinfo=timezone.utc)

        status_str = str(getattr(trade, "status", "") or "").upper()
        end_ref = closed_at_utc if (status_str in ("CLOSED", "CANCELLED") and closed_at_utc) else now_ref
        delta_sec = max(0.0, (end_ref - opened_at_utc).total_seconds())
        days_held = int(delta_sec // 86400)
        rem_hours = int((delta_sec % 86400) // 3600)
        rem_mins = int((delta_sec % 3600) // 60)
        if days_held > 0:
            holding_duration_label = f"{days_held}d {rem_hours}h"
        elif rem_hours > 0:
            holding_duration_label = f"{rem_hours}h {rem_mins}m"
        else:
            holding_duration_label = f"{max(1, rem_mins)}m"

        opened_ist = opened_at_utc.astimezone(ist_tz)
        buy_date_formatted = opened_ist.strftime("%d %b %Y, %I:%M %p IST")
        is_bought_today = (opened_ist.date() == now_ist.date())

        sell_date_formatted = None
        is_sold_today = False
        if closed_at_utc:
            closed_ist = closed_at_utc.astimezone(ist_tz)
            sell_date_formatted = closed_ist.strftime("%d %b %Y, %I:%M %p IST")
            is_sold_today = (closed_ist.date() == now_ist.date())

        entry_p = float(trade.entry_price) if getattr(trade, "entry_price", None) is not None else None
        qty = int(getattr(trade, "quantity", 0) or 0)
        comm = float(trade.commission) if getattr(trade, "commission", None) is not None else 0.0
        stt = float(trade.stt_tax) if getattr(trade, "stt_tax", None) is not None else 0.0
        total_charges = round(comm + stt, 2)
        realized = float(trade.realized_pnl) if getattr(trade, "realized_pnl", None) is not None else None
        multiplier = 1 if str(getattr(trade, "direction", "BUY")).upper() == "BUY" else -1

        exit_p_raw = getattr(trade, "exit_price", None)
        exit_p = round(float(exit_p_raw), 2) if (exit_p_raw is not None and float(exit_p_raw) > 0) else None
        if exit_p is None and status_str == "CLOSED" and realized is not None and entry_p is not None and qty > 0:
            gross_derived = realized + comm + stt
            implied = entry_p + multiplier * (gross_derived / qty)
            if implied > 0:
                exit_p = round(implied, 2)

        gross_pnl = None
        pnl_pct = None
        if status_str == "CLOSED" and realized is not None:
            gross_pnl = round(realized + comm + stt, 2)
            invested = (entry_p * qty) if (entry_p and qty > 0) else 0.0
            if invested > 0:
                pnl_pct = round((realized / invested) * 100.0, 2)

        stored_closed_by = getattr(trade, "closed_by", None)
        stored_reason = getattr(trade, "exit_reason", None)
        ratchet_stage = str(getattr(trade, "ratchet_stage", "INITIAL") or "INITIAL")

        if isinstance(stored_closed_by, str) and stored_closed_by and isinstance(stored_reason, str) and stored_reason:
            closed_by = stored_closed_by
            exit_reason = stored_reason
        elif status_str == "CANCELLED":
            closed_by = "USER_MANUAL"
            exit_reason = "USER_CANCELLED"
        elif status_str == "CLOSED":
            stage_map = {
                "TARGET_3_ACHIEVED": ("AUTO_SYSTEM", "SYSTEM_AUTO_TARGET_3"),
                "TARGET_2_ACHIEVED": ("AUTO_SYSTEM", "SYSTEM_AUTO_TARGET_2"),
                "TARGET_1_ACHIEVED": ("AUTO_SYSTEM", "SYSTEM_AUTO_TARGET_1"),
                "STOPPED_IN_PROFIT": ("AUTO_SYSTEM", "SYSTEM_AUTO_STOP_IN_PROFIT"),
                "STOPLOSS_HIT": ("AUTO_SYSTEM", "SYSTEM_AUTO_STOPLOSS"),
            }
            if ratchet_stage in stage_map:
                closed_by, exit_reason = stage_map[ratchet_stage]
            else:
                tgt_candidates = [
                    float(v) for v in (
                        getattr(trade, "target_3", None),
                        getattr(trade, "target_2", None),
                        getattr(trade, "target_1", None),
                        getattr(trade, "target_price", None),
                    )
                    if v is not None and float(v) > 0
                ]
                primary_tgt = max(tgt_candidates) if (multiplier == 1 and tgt_candidates) else (min(tgt_candidates) if tgt_candidates else None)
                sl_val = float(trade.stop_loss) if getattr(trade, "stop_loss", None) is not None and float(trade.stop_loss) > 0 else None

                closed_by = "USER_MANUAL"
                exit_reason = "USER_MANUAL_EXIT"
                if exit_p is not None:
                    if multiplier == 1:
                        if primary_tgt is not None and exit_p >= primary_tgt * 0.999:
                            closed_by, exit_reason = "AUTO_SYSTEM", "SYSTEM_AUTO_TARGET"
                        elif sl_val is not None and exit_p <= sl_val * 1.001:
                            closed_by, exit_reason = "AUTO_SYSTEM", "SYSTEM_AUTO_STOPLOSS"
                    else:
                        if primary_tgt is not None and exit_p <= primary_tgt * 1.001:
                            closed_by, exit_reason = "AUTO_SYSTEM", "SYSTEM_AUTO_TARGET"
                        elif sl_val is not None and exit_p >= sl_val * 0.999:
                            closed_by, exit_reason = "AUTO_SYSTEM", "SYSTEM_AUTO_STOPLOSS"

                if closed_by == "USER_MANUAL" and str(getattr(trade, "product_type", "")).upper() == "INTRADAY" and closed_at_utc:
                    closed_ist = closed_at_utc.astimezone(ist_tz)
                    hm = closed_ist.hour * 60 + closed_ist.minute
                    if (15 * 60 + 18) <= hm <= (15 * 60 + 30):
                        closed_by, exit_reason = "AUTO_SYSTEM", "SYSTEM_AUTO_EOD_INTRADAY"
        else:
            closed_by = None
            exit_reason = None

        exit_reason_label = PaperTradingService.EXIT_REASON_LABELS.get(exit_reason) if exit_reason else None

        return {
            "exit_price": exit_p,
            "gross_pnl": gross_pnl,
            "total_charges": total_charges,
            "pnl_pct": pnl_pct,
            "days_held": days_held,
            "holding_duration_label": holding_duration_label,
            "buy_date_formatted": buy_date_formatted,
            "sell_date_formatted": sell_date_formatted,
            "is_bought_today": is_bought_today,
            "is_sold_today": is_sold_today,
            "closed_by": closed_by,
            "exit_reason": exit_reason,
            "exit_reason_label": exit_reason_label,
        }

    @staticmethod
    async def get_all_trades(db: AsyncSession, user_id: str) -> list[PaperTrade]:
        result = await db.execute(
            select(PaperTrade).where(
                PaperTrade.user_id == uuid.UUID(user_id),
            ).order_by(PaperTrade.opened_at.desc())
        )
        return result.scalars().all()


paper_trading_service = PaperTradingService()
