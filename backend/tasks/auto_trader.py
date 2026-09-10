import asyncio
from datetime import datetime
import uuid
import uuid as uuid_lib

from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.database import AsyncSessionLocal
from backend.core.logging_config import get_logger
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service
from backend.services.institutional_hunter import smc_engine
from backend.services.paper_trading import PaperTradingService
from backend.models.paper_trade import PaperTrade
from sqlalchemy import select, func

logger = get_logger(__name__)

# System User ID used for AI's own paper trading portfolio
AI_TRADER_ID = "00000000-0000-0000-0000-000000000000"
MAX_CAPITAL_PER_TRADE = 100000  # ₹1 Lakh virtual capital per trade

async def check_existing_position(db: AsyncSession, symbol: str) -> bool:
    """Check if the AI already holds an open position in this stock."""
    result = await db.execute(
        select(func.count(PaperTrade.id)).where(
            PaperTrade.user_id == uuid_lib.UUID(AI_TRADER_ID),
            PaperTrade.symbol == symbol,
            PaperTrade.status == "OPEN"
        )
    )
    count = result.scalar()
    return count > 0

async def execute_smc_trade_if_confirmed(db: AsyncSession, symbol: str, smc_data: dict, is_enabled: bool):
    """
    Multi-Timeframe Confirmation Logic.
    Takes a Daily FVG POI, fetches live 15-minute candles,
    and checks if there's a localized reversal confirmation.
    """
    try:
        fvgs = smc_data.get("fvgs", [])
        if not fvgs:
            return
            
        # Fetch 15-minute live candles for confirmation
        candles_15m = await market_data_service.fetch_candles(symbol, "15m", limit=30)
        if not candles_15m or len(candles_15m) < 15:
            return
            
        current_price = candles_15m[-1].get("close", 0)
        
        # Analyze the 15-minute structure
        indicators_15m = indicator_service.compute_all(candles_15m)
        rsi_15m = indicators_15m.get("rsi_14", 50)
        macd_val = indicators_15m.get("macd", 0)
        macd_signal = indicators_15m.get("macd_signal", 0)
        
        # Are we inside any POI?
        for fvg in fvgs:
            zone_top = fvg["top"]
            zone_bottom = fvg["bottom"]
            fvg_type = fvg["type"]
            
            # Check if current price is inside the Daily POI zone
            if zone_bottom <= current_price <= zone_top:
                
                action = None
                score = fvg.get("confluence", {}).get("score", 0)
                target = 0
                stop = 0
                
                # Check for 15-Minute Reversal Confirmation
                if fvg_type == "bullish_fvg":
                    # Bullish Confirmation: Price in POI, MACD crosses up OR RSI oversold and hooking up
                    prev_candle = candles_15m[-2]
                    curr_candle = candles_15m[-1]
                    
                    bullish_engulfing = (prev_candle["close"] < prev_candle["open"]) and \
                                        (curr_candle["close"] > curr_candle["open"]) and \
                                        (curr_candle["close"] > prev_candle["open"])
                                        
                    macd_bull_cross = macd_val > macd_signal
                    
                    if bullish_engulfing or (rsi_15m < 40 and macd_bull_cross):
                        action = "BUY"
                        # Localized stop loss below the 15m swing low
                        stop = min(c["low"] for c in candles_15m[-10:]) * 0.998
                        risk = current_price - stop
                        target = round(current_price + (risk * 2.5), 2)  # 2.5R Target
                        
                elif fvg_type == "bearish_fvg":
                    prev_candle = candles_15m[-2]
                    curr_candle = candles_15m[-1]
                    
                    bearish_engulfing = (prev_candle["close"] > prev_candle["open"]) and \
                                        (curr_candle["close"] < curr_candle["open"]) and \
                                        (curr_candle["close"] < prev_candle["open"])
                                        
                    macd_bear_cross = macd_val < macd_signal
                    
                    if bearish_engulfing or (rsi_15m > 60 and macd_bear_cross):
                        action = "SELL"
                        stop = max(c["high"] for c in candles_15m[-10:]) * 1.002
                        risk = stop - current_price
                        target = round(current_price - (risk * 2.5), 2)

                if action:
                    if await check_existing_position(db, symbol):
                        logger.debug(f"[AutoTrader] Skipping {symbol}, already have an OPEN position.")
                        return

                    quantity = int(MAX_CAPITAL_PER_TRADE / current_price) if current_price > 0 else 0
                    if quantity <= 0:
                        return
                        
                    stop = round(stop, 2)
                    
                    if not is_enabled:
                        # MANUAL MODE: Push Live Alert Toast to UI
                        from backend.api.websocket import broadcast_alert
                        alert_msg = {
                            "title": f"SMC Zone Hit: {action} {symbol}",
                            "message": f"15m Reversal Confirmed in Daily Zone! Target: {target}, SL: {stop}.",
                            "type": "info" if action == "BUY" else "warning"
                        }
                        await broadcast_alert(alert_msg)
                        logger.info(f"🔔 [AutoTrader] Sent manual alert for {symbol}: {action}")
                        return

                    logger.info(f"🤖 [AutoTrader] Multi-Timeframe Confirmation for {symbol}: {action}")
                    
                    # Execute Paper Trade
                    trade = await PaperTradingService.place_order(
                        db=db,
                        user_id=AI_TRADER_ID,
                        symbol=symbol,
                        direction=action,
                        quantity=quantity,
                        order_type="MARKET",
                        product_type="INTRADAY", 
                        target_price=target,
                        stop_loss=stop
                    )
                    logger.info(f"✅ [AutoTrader] Executed Virtual {action} for {symbol}. Target: {target}, SL: {stop}")
                    return # Exit after one valid setup per symbol
                
    except Exception as e:
        logger.error(f"[AutoTrader] Error executing multi-timeframe check for {symbol}: {e}")

async def auto_trader_loop():
    """Background loop that monitors Daily SMC zones and confirms on 15m candles."""
    logger.info("🤖 Starting AI Auto-Trader Daemon (SMC Multi-Timeframe)...")
    
    # We delay start to ensure DB and models are loaded
    await asyncio.sleep(10)
    
    while True:
        try:
            now = datetime.now()
            
            logger.info("🤖 [AutoTrader] Scanning 15-minute chart for SMC POI confirmations...")
            
            async with AsyncSessionLocal() as db:
                from backend.models.settings import SystemSettings
                settings_rows = (await db.execute(select(SystemSettings).where(SystemSettings.key == "enable_auto_trader"))).scalars().all()
                is_enabled = False
                if settings_rows:
                    is_enabled = settings_rows[0].value.lower() == "true"
                
                if not is_enabled:
                    logger.info("🤖 [AutoTrader] Master switch is OFF. Running in MANUAL ALERT mode.")
                    
                # 1. Get the pre-calculated Daily Watchlist POIs
                watchlist = smc_engine.get_watchlist()
                
                if not watchlist:
                    logger.debug("[AutoTrader] Watchlist is empty. Waiting for SMC Engine generation...")
                
                # 2. Monitor each symbol in the watchlist on a 15-minute basis
                for symbol, smc_data in watchlist.items():
                    await execute_smc_trade_if_confirmed(db, symbol, smc_data, is_enabled)
                    await asyncio.sleep(1) # Prevent rate limiting
                    
            logger.info("🤖 [AutoTrader] 15m Scan complete. Sleeping until next candle...")
            
        except asyncio.CancelledError:
            logger.info("🤖 Auto-Trader loop stopped.")
            break
        except Exception as e:
            logger.error(f"🤖 Auto-Trader loop error: {e}")
            
        # Run every 5 minutes (to aggressively catch 15m candle closes)
        await asyncio.sleep(300)
