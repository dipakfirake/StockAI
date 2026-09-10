import asyncio
from backend.core.logging_config import get_logger
from backend.services.screener import screener_service

logger = get_logger(__name__)

async def poll_screener_cache():
    """
    Background loop that continuously iterates over top symbols
    and calls the screener service to compute and cache their scores,
    ensuring ultra-fast UI loading times.
    """
    from backend.services.ai_engine import LARGE_CAP_SYMBOLS
    
    # We will poll the Large Cap universe + some popular mid/small caps
    universe = list(LARGE_CAP_SYMBOLS)
    
    logger.info(f"Starting Background Screener Poller for {len(universe)} symbols...")
    
    while True:
        try:
            for symbol in universe:
                # We bypass the cache lookup inside _analyze_symbol by explicitly 
                # passing a force_refresh flag or letting it overwrite the cache.
                # However, _analyze_symbol caches for 15 mins by default and returns 
                # early if cached. 
                # Let's modify the behavior or just let it naturally refresh 
                # when the TTL expires (which means the poller acts as a cache warmer).
                
                # To ensure it warms up any expired items, we just call it. 
                # The service will fetch from cache if valid, or compute if expired.
                await screener_service._analyze_symbol(symbol)
                
                # Sleep between each symbol to avoid hammering APIs or DB
                await asyncio.sleep(2.0)
                
            # Sleep at the end of a full loop
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Error in screener poller: {e}")
            await asyncio.sleep(30)
