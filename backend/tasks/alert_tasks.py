"""Alert evaluation Celery task — periodic alert condition checking."""

import asyncio
import re
import smtplib
from email.message import EmailMessage
from backend.celery_app import celery_app
from backend.core.logging_config import get_logger
from backend.core.config import settings
from backend.data.ingestion.nse_scraper import nse_scraper

logger = get_logger(__name__)

def send_high_priority_email(to_email: str, subject: str, body: str) -> bool:
    """Send SMTP mail only when it has been explicitly configured."""
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        logger.warning("HIGH alert email skipped: SMTP is not configured")
        return False
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as client:
            if settings.SMTP_USE_TLS:
                client.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            client.send_message(message)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        logger.error(f"Could not send HIGH alert email: {exc}")
        return False


@celery_app.task(name="backend.tasks.alert_tasks.evaluate_all_alerts")
def evaluate_all_alerts():
    """
    Evaluate all active alerts against current market prices.

    Rules:
    - Only run during market hours (09:15–15:30 IST)
    - De-duplicate alerts: don't re-trigger the same alert within 4 hours
    - Priority: HIGH alerts trigger immediately, MEDIUM within 1 min, LOW within 5 min
    - Quiet hours: no alerts outside market hours
    """
    if not nse_scraper.is_market_open():
        return {"skipped": True, "reason": "Outside market hours (quiet hours enforced)"}

    try:
        result = asyncio.run(_evaluate_alerts_async())
        return result
    except Exception as e:
        logger.error(f"Alert evaluation failed: {e}")
        return {"error": str(e)}


async def _evaluate_alerts_async():
    """Async alert evaluation logic."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from backend.core.database import AsyncSessionLocal
    from backend.models.alert import Alert
    from backend.models.user import User
    from backend.services.market_data import market_data_service
    from backend.services.indicators import indicator_service
    from backend.api.websocket import broadcast_alert

    triggered_count = 0
    DEDUP_HOURS = 4  # Don't re-trigger same alert within 4 hours

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Alert).where(Alert.is_active == True)
        )
        alerts = result.scalars().all()

        PRICE_CONDITIONS = {
            "PRICE_ABOVE", "PRICE_BELOW",
            "BUY_PROXIMITY", "TARGET_PROXIMITY", "TARGET_HIT",
            "STOP_LOSS_PROXIMITY", "STOP_LOSS_HIT"
        }
        price_symbols = list({a.symbol for a in alerts if a.condition_type in PRICE_CONDITIONS})
        quotes_map = {}
        if price_symbols:
            try:
                quotes_map = await market_data_service.fetch_quotes_bulk(price_symbols)
            except Exception as e:
                logger.debug(f"Failed to prefetch bulk quotes in evaluate_all_alerts: {e}")

        for alert in alerts:
            # Deduplication check
            if alert.triggered_at:
                time_since = datetime.now(timezone.utc) - alert.triggered_at.replace(tzinfo=timezone.utc)
                if time_since.total_seconds() < DEDUP_HOURS * 3600:
                    continue

            try:
                triggered = False
                current_value = None
                extra_msg = ""

                # 1. Price and Proximity based conditions
                if alert.condition_type in PRICE_CONDITIONS:
                    quote = quotes_map.get(alert.symbol)
                    if not quote or quote.get("price", 0) <= 0:
                        quote = await market_data_service.fetch_quote(alert.symbol)
                    if quote:
                        current_value = quote["price"]
                        cond_val = float(alert.condition_value)
                        msg_str = alert.message or ""

                        if alert.condition_type == "BUY_PROXIMITY":
                            # Pre-Buy Alert: triggers strictly BEFORE the stock hits Best Buy from above
                            best_buy_bound = None
                            match = re.search(r"(?:Best Buy|Target Entry):?\s*₹\s*([\d\.]+)", msg_str, re.IGNORECASE)
                            if match:
                                try:
                                    best_buy_bound = float(match.group(1))
                                except Exception:
                                    pass

                            if best_buy_bound is not None:
                                # Pre-Buy corridor: price descending from above into [best_buy, buy_prox]
                                if best_buy_bound <= current_value <= cond_val:
                                    triggered = True
                            else:
                                if current_value <= cond_val:
                                    triggered = True

                        elif alert.condition_type == "TARGET_PROXIMITY":
                            # Sell Pre-Alert: triggers when price approaches Target from below before hitting it
                            target_bound = None
                            tgt_match = re.search(r"Target:?\s*₹\s*([\d\.]+)", msg_str, re.IGNORECASE)
                            if tgt_match:
                                try:
                                    target_bound = float(tgt_match.group(1))
                                except Exception:
                                    pass

                            if target_bound is not None:
                                if cond_val <= current_value < target_bound:
                                    triggered = True
                            else:
                                if current_value >= cond_val:
                                    triggered = True

                        elif alert.condition_type in ("PRICE_ABOVE", "TARGET_HIT") and current_value >= cond_val:
                            triggered = True
                        elif alert.condition_type in ("PRICE_BELOW", "STOP_LOSS_PROXIMITY", "STOP_LOSS_HIT") and current_value <= cond_val:
                            triggered = True

                # 2. Indicator based conditions requiring candles
                else:
                    candles = await market_data_service.fetch_candles(alert.symbol, "1d", limit=100)
                    if len(candles) >= 50:
                        indicators = indicator_service.compute_all(candles)
                        
                        if alert.condition_type in ("RSI_ABOVE", "RSI_BELOW"):
                            current_value = indicators.get("rsi_14")
                            if current_value:
                                if alert.condition_type == "RSI_ABOVE" and current_value >= float(alert.condition_value):
                                    triggered = True
                                elif alert.condition_type == "RSI_BELOW" and current_value <= float(alert.condition_value):
                                    triggered = True

                        elif alert.condition_type in ("MACD_CROSS_UP", "MACD_CROSS_DOWN"):
                            macd = indicators.get("macd", {})
                            hist = macd.get("histogram") if macd else None
                            if hist is not None:
                                current_value = hist
                                if alert.condition_type == "MACD_CROSS_UP" and hist > 0:
                                    triggered = True
                                elif alert.condition_type == "MACD_CROSS_DOWN" and hist < 0:
                                    triggered = True

                        elif alert.condition_type == "SUPERTREND_FLIP":
                            st = indicators.get("supertrend", {})
                            direction = st.get("direction")
                            current_value = direction
                            if alert.condition_value == 1 and direction == "up":
                                triggered = True
                            elif alert.condition_value == -1 and direction == "down":
                                triggered = True

                        elif alert.condition_type == "BB_SQUEEZE":
                            bb = indicators.get("bb", {})
                            upper = bb.get("upper")
                            lower = bb.get("lower")
                            if upper and lower:
                                bandwidth = (upper - lower) / lower * 100
                                current_value = bandwidth
                                if bandwidth < float(alert.condition_value):
                                    triggered = True

                        elif alert.condition_type == "VOLUME_SURGE":
                            avg_vol = indicators.get("vol_sma_20")
                            current_vol = candles[-1]["volume"]
                            if avg_vol and current_vol:
                                current_value = current_vol / avg_vol
                                if current_value >= float(alert.condition_value):
                                    triggered = True
                                    extra_msg = f"Volume surged {current_value:.1f}x above 20MA"

                        elif alert.condition_type == "PATTERN":
                            # Candlestick pattern detection mock
                            # In a real app we'd use talib CDL functions on the dataframe
                            # Here we just look at the last candle
                            c = candles[-1]
                            body = abs(c["close"] - c["open"])
                            wick = c["high"] - max(c["open"], c["close"])
                            tail = min(c["open"], c["close"]) - c["low"]
                            
                            # Simple Hammer logic
                            if alert.condition_value == 1: # 1 = Hammer
                                if tail > 2 * body and wick < 0.2 * body:
                                    triggered = True
                                    current_value = 1
                                    extra_msg = "Hammer pattern detected on daily chart"
                            # Engulfing logic
                            elif alert.condition_value == 2 and len(candles) > 1: # 2 = Bullish Engulfing
                                p = candles[-2]
                                if p["close"] < p["open"] and c["close"] > c["open"] and c["close"] > p["open"] and c["open"] < p["close"]:
                                    triggered = True
                                    current_value = 2
                                    extra_msg = "Bullish Engulfing detected on daily chart"
                            elif alert.condition_value == 3 and len(candles) > 1: # 3 = Bearish Engulfing
                                p = candles[-2]
                                if p["close"] > p["open"] and c["close"] < c["open"] and c["close"] < p["open"] and c["open"] > p["close"]:
                                    triggered = True
                                    current_value = 3
                                    extra_msg = "Bearish Engulfing detected on daily chart"
                            elif alert.condition_value == 4 and len(candles) > 2: # 4 = Order Block (Bullish)
                                p1 = candles[-3]
                                p2 = candles[-2]
                                if p1["close"] < p1["open"] and p2["close"] > p2["open"] and p2["close"] > p1["open"] and c["close"] > p2["close"]:
                                    triggered = True
                                    current_value = 4
                                    extra_msg = "Bullish Order Block detected on daily chart"

                if triggered:
                    alert.triggered_at = datetime.now(timezone.utc)
                    await db.flush()
                    triggered_count += 1

                    user_msg = alert.message or f"{alert.symbol}: {alert.condition_type} triggered. {extra_msg}"
                    payload = {
                        "type": "ALERT_TRIGGERED",
                        "alert_id": str(alert.id),
                        "symbol": alert.symbol,
                        "condition_type": alert.condition_type,
                        "condition_value": float(alert.condition_value),
                        "current_value": current_value,
                        "priority": alert.priority,
                        "message": user_msg,
                        "triggered_at": alert.triggered_at.isoformat(),
                    }
                    
                    # 1. In-App Notification (Database)
                    if getattr(alert, 'delivery_method', 'IN_APP') in ('IN_APP', 'BOTH'):
                        from backend.models.notification import Notification
                        notif = Notification(
                            user_id=alert.user_id,
                            title=f"{alert.symbol} Alert",
                            message=user_msg,
                            priority=alert.priority
                        )
                        res = db.add(notif)
                        if asyncio.iscoroutine(res):
                            await res
                    
                    # 2. WebSockets & Instant Global Toast
                    await broadcast_alert(payload, user_id=str(alert.user_id))

                    toast_type = "info"
                    if alert.condition_type == "TARGET_PROXIMITY":
                        toast_type = "warning"
                    elif alert.condition_type == "TARGET_HIT":
                        toast_type = "success"
                    elif alert.condition_type in ("STOP_LOSS_HIT", "STOP_LOSS_PROXIMITY"):
                        toast_type = "error"
                    elif alert.condition_type == "BUY_PROXIMITY":
                        toast_type = "info"
                    elif alert.priority == "HIGH":
                        toast_type = "warning"

                    await broadcast_alert({
                        "type": "alert_toast",
                        "data": {
                            "title": f"🚨 {alert.symbol} Alert Triggered",
                            "message": user_msg,
                            "type": toast_type
                        }
                    }, user_id=str(alert.user_id))
                    
                    # 3. Email (SMTP) - Only send for HIGH priority "main" alerts
                    if getattr(alert, 'delivery_method', 'IN_APP') in ('EMAIL', 'BOTH') and alert.priority == 'HIGH':
                        user = await db.get(User, alert.user_id)
                        if user:
                            send_high_priority_email(
                            to_email=user.email,
                            subject=f"Stock Alert: {alert.symbol} Triggered {alert.condition_type}",
                            body=user_msg,
                            )
                    
                    logger.info(f"Alert triggered: {alert.symbol} {alert.condition_type} = {current_value}")

            except Exception as e:
                logger.error(f"Error evaluating alert {alert.id}: {e}")

        await db.commit()

    return {"evaluated": len(alerts), "triggered": triggered_count}
