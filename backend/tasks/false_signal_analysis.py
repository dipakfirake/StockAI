"""False Signal Analysis Task - Phase 9."""

import asyncio
from datetime import datetime, timezone, timedelta
from backend.celery_app import celery_app
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

@celery_app.task(name="backend.tasks.false_signal_analysis.analyze_predictions")
def analyze_predictions():
    """
    Periodically analyzes the PredictionArchive table to find incorrect predictions,
    mark them, and generate basic root cause reasons (e.g. news event, high volatility).
    """
    logger.info("Starting False Signal Analysis...")
    try:
        asyncio.run(_analyze_async())
        return {"status": "Analysis complete"}
    except Exception as e:
        logger.error(f"False signal analysis failed: {e}")
        return {"error": str(e)}

async def _analyze_async():
    from backend.core.database import AsyncSessionLocal
    from backend.models.prediction_archive import PredictionArchive
    from backend.services.market_data import market_data_service
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as db:
        # Get pending predictions older than 1 day (or whatever horizon)
        threshold_date = datetime.now(timezone.utc) - timedelta(days=1)
        
        stmt = select(PredictionArchive).where(
            PredictionArchive.is_correct == None,
            PredictionArchive.created_at <= threshold_date
        )
        predictions = (await db.execute(stmt)).scalars().all()
        
        for pred in predictions:
            # 1. Fetch outcome
            try:
                # We need the close price on the creation day, and the close price 1 day later
                quote = await market_data_service.fetch_quote(pred.symbol)
                current_price = quote.get("price", 0)
                
                # For simplicity in MVP, we just check if it moved in the predicted direction
                # In real scenario, we compare precise dates
                last_price = pred.features_snapshot.get("last_price") if pred.features_snapshot else current_price
                
                if last_price and last_price > 0:
                    pct_change = (current_price - last_price) / last_price
                    actual_direction = "BULLISH" if pct_change > 0.01 else "BEARISH" if pct_change < -0.01 else "NEUTRAL"
                    
                    pred.actual_outcome = actual_direction
                    pred.is_correct = (pred.predicted_value == actual_direction)
                    
                    if not pred.is_correct:
                        # Dummy root cause analysis
                        if pred.confidence > 0.8:
                            pred.error_reason = "Model overconfidence / unexpected market gap"
                        else:
                            pred.error_reason = "Normal market noise"
                            
                        logger.info(f"False signal flagged for {pred.symbol}: predicted {pred.predicted_value}, got {actual_direction}")
            except Exception as e:
                logger.error(f"Failed evaluating prediction {pred.id}: {e}")
                
        await db.commit()
        logger.info(f"Evaluated {len(predictions)} archived predictions.")
