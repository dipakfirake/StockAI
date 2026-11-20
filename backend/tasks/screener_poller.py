import os
import asyncio
from backend.core.logging_config import get_logger
from backend.services.screener import screener_service

logger = get_logger(__name__)


async def poll_screener_cache():
    """
    Background cache pre-warmer for the stock screener.
    Disabled by default on 1-OCPU production servers to eliminate CPU saturation
    and event loop starvation.
    """
    if os.getenv("ENABLE_SCREENER_POLLER", "false").lower() != "true":
        logger.info("[ScreenerPoller] Background screener warmer disabled by default (ENABLE_SCREENER_POLLER=false) to conserve CPU for HTTP requests.")
        return

    from backend.services.ai_engine import LARGE_CAP_SYMBOLS
    universe = list(LARGE_CAP_SYMBOLS)
    
    logger.info(f"Starting Background Screener Poller for {len(universe)} symbols (initial warmup delay: 120s)...")
    await asyncio.sleep(120.0)
    
    while True:
        try:
            for symbol in universe:
                await screener_service._analyze_symbol(symbol)
                await asyncio.sleep(15.0)
            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Error in screener poller: {e}")
            await asyncio.sleep(60)
