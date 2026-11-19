"""Alerts API router."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import get_current_user
from backend.models.alert import Alert
from backend.services.market_data import market_data_service
from backend.services.paper_trading import paper_trading_service
from backend.api.websocket import broadcast_alert

router = APIRouter()

from typing import Any, Union

VALID_CONDITIONS = {
    "PRICE_ABOVE", "PRICE_BELOW",
    "BUY_PROXIMITY", "TARGET_PROXIMITY", "TARGET_HIT",
    "STOP_LOSS_PROXIMITY", "STOP_LOSS_HIT",
    "RSI_BELOW", "RSI_ABOVE",
    "MACD_CROSS_UP", "MACD_CROSS_DOWN",
    "SUPERTREND_FLIP", "BB_SQUEEZE", "VOLUME_SURGE", "PATTERN",
}


class CreateAlertRequest(BaseModel):
    symbol: str
    condition_type: str
    condition_value: Union[float, str]
    message: str | None = None
    priority: str = "MEDIUM"
    delivery_method: str = "IN_APP"


class ScreenerAlertSetupRequest(BaseModel):
    symbol: str
    current_price: float
    best_buy_price: float | None = None
    target_price: float | None = None
    stop_loss: float | None = None
    proximity_pct: float = 1.0


def _format_cond_value(val: Any) -> Union[float, str]:
    if val is None:
        return 0.0
    try:
        fval = float(val)
        return fval if not str(val).isalpha() else str(val)
    except (ValueError, TypeError):
        return str(val)


@router.get("")
async def list_alerts(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all alerts for the current user."""
    result = await db.execute(
        select(Alert).where(Alert.user_id == current_user.id).order_by(Alert.created_at.desc())
    )
    alerts = result.scalars().all()
    return {"alerts": [
        {
            "alert_id": str(a.id),
            "symbol": a.symbol,
            "condition_type": a.condition_type,
            "condition_value": _format_cond_value(a.condition_value),
            "message": a.message,
            "is_active": a.is_active,
            "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
            "created_at": a.created_at.isoformat(),
        }
        for a in alerts
    ]}


@router.post("")
async def create_alert(
    request: CreateAlertRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new alert and broadcast toast event."""
    if request.condition_type not in VALID_CONDITIONS:
        raise HTTPException(status_code=400, detail=f"Invalid condition_type. Valid: {VALID_CONDITIONS}")
    if request.priority not in {"HIGH", "MEDIUM", "LOW"}:
        raise HTTPException(status_code=400, detail="priority must be HIGH, MEDIUM, or LOW")
    if request.delivery_method not in {"IN_APP", "EMAIL", "BOTH"}:
        raise HTTPException(status_code=400, detail="delivery_method must be IN_APP, EMAIL, or BOTH")

    alert = Alert(
        user_id=current_user.id,
        symbol=request.symbol.upper(),
        condition_type=request.condition_type,
        condition_value=request.condition_value,
        message=request.message,
        priority=request.priority,
        delivery_method=request.delivery_method,
        is_active=True,
    )
    db.add(alert)
    await db.flush()

    # Broadcast instant creation toast across all active sessions/windows
    try:
        cond_label = request.condition_type.replace('_', ' ').title()
        toast_msg = request.message or f"{cond_label} alert set for ₹{request.condition_value}"
        await broadcast_alert({
            "type": "alert_toast",
            "data": {
                "title": f"🔔 Alert Created: {alert.symbol}",
                "message": toast_msg,
                "type": "info"
            }
        }, user_id=str(current_user.id))
    except Exception:
        pass

    return {"alert_id": str(alert.id), "created": True}


@router.post("/screener-setup")
async def setup_screener_coupled_alerts(
    request: ScreenerAlertSetupRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Setup coupled pre-alerts for a Swing Screener stock:
    1. Buy Proximity Pre-Alert (triggers before hitting Best Buy zone so user doesn't miss it)
    2. Target Proximity Pre-Alert (triggers before hitting Target so user can prepare exit without loss)
    3. Target Hit Alert (triggers when price reaches Target)
    4. Stop Loss Proximity & Breach Alerts (guards against downside losses)
    """
    symbol = request.symbol.upper()
    prox_pct = max(0.2, min(5.0, request.proximity_pct))
    created_alerts = []

    # 1. Buy Proximity Pre-Alert
    if request.best_buy_price and request.best_buy_price > 0:
        buy_prox_price = round(request.best_buy_price * (1.0 + prox_pct / 100.0), 2)
        alert_buy = Alert(
            user_id=current_user.id,
            symbol=symbol,
            condition_type="BUY_PROXIMITY",
            condition_value=buy_prox_price,
            message=f"{symbol}: Approaching Best Buy Zone! Price near ₹{buy_prox_price:.2f} (Target Entry: ₹{request.best_buy_price:.2f})",
            priority="MEDIUM",
            delivery_method="IN_APP",
            is_active=True,
        )
        db.add(alert_buy)
        created_alerts.append({"type": "BUY_PROXIMITY", "value": buy_prox_price})

    # 2. Target Proximity Pre-Alert (Sell Pre-Alert before hitting target)
    if request.target_price and request.target_price > 0:
        target_prox_price = round(request.target_price * (1.0 - prox_pct / 100.0), 2)
        alert_target_prox = Alert(
            user_id=current_user.id,
            symbol=symbol,
            condition_type="TARGET_PROXIMITY",
            condition_value=target_prox_price,
            message=f"{symbol}: Approaching Target! Price near ₹{target_prox_price:.2f} (Target: ₹{request.target_price:.2f}) — Prepare to lock in gains!",
            priority="HIGH",
            delivery_method="IN_APP",
            is_active=True,
        )
        db.add(alert_target_prox)
        created_alerts.append({"type": "TARGET_PROXIMITY", "value": target_prox_price})

        # Target Hit
        alert_target_hit = Alert(
            user_id=current_user.id,
            symbol=symbol,
            condition_type="TARGET_HIT",
            condition_value=round(request.target_price, 2),
            message=f"{symbol}: 🎯 Target Reached at ₹{request.target_price:.2f}! Execute exit plan.",
            priority="HIGH",
            delivery_method="IN_APP",
            is_active=True,
        )
        db.add(alert_target_hit)
        created_alerts.append({"type": "TARGET_HIT", "value": round(request.target_price, 2)})

    # 3. Stop Loss Pre-Alert and Hit
    if request.stop_loss and request.stop_loss > 0:
        sl_prox_price = round(request.stop_loss * (1.0 + prox_pct / 100.0), 2)
        alert_sl_prox = Alert(
            user_id=current_user.id,
            symbol=symbol,
            condition_type="STOP_LOSS_PROXIMITY",
            condition_value=sl_prox_price,
            message=f"{symbol}: ⚠️ Approaching Stop Loss! Price near ₹{sl_prox_price:.2f} (SL: ₹{request.stop_loss:.2f})",
            priority="HIGH",
            delivery_method="IN_APP",
            is_active=True,
        )
        db.add(alert_sl_prox)
        created_alerts.append({"type": "STOP_LOSS_PROXIMITY", "value": sl_prox_price})

        alert_sl_hit = Alert(
            user_id=current_user.id,
            symbol=symbol,
            condition_type="STOP_LOSS_HIT",
            condition_value=round(request.stop_loss, 2),
            message=f"{symbol}: 🛑 Stop Loss Breached at ₹{request.stop_loss:.2f}! Cut losses immediately.",
            priority="HIGH",
            delivery_method="IN_APP",
            is_active=True,
        )
        db.add(alert_sl_hit)
        created_alerts.append({"type": "STOP_LOSS_HIT", "value": round(request.stop_loss, 2)})

    await db.flush()

    # Broadcast notification toast across windows
    try:
        await broadcast_alert({
            "type": "alert_toast",
            "data": {
                "title": f"🎯 Screener Alerts Active: {symbol}",
                "message": f"{len(created_alerts)} coupled alerts set (Buy Pre-Alert, Target Pre-Alert & SL)",
                "type": "success"
            }
        }, user_id=str(current_user.id))
    except Exception:
        pass

    return {
        "symbol": symbol,
        "created_count": len(created_alerts),
        "alerts": created_alerts
    }


@router.get("/holdings-monitor")
async def get_holdings_risk_monitor(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Live Holdings Guard:
    Continuously monitors all currently held (bought) stocks for the user:
    - Real-time Market Price (CMP) vs Entry Price
    - Distance to Target & Sell Proximity status
    - Distance to Stop Loss & Stop Loss Warning status
    - Status badges (SAFE_ZONE, TARGET_APPROACHING, TARGET_HIT, SL_APPROACHING, SL_HIT)
    """
    trades = await paper_trading_service.get_all_trades(db, str(current_user.id))
    # Filter only OPEN BUY positions (active user holdings)
    open_holdings = [t for t in trades if t.status == "OPEN" and t.direction == "BUY"]

    if not open_holdings:
        return {"holdings": [], "summary": {"total_held": 0, "targets_approaching": 0, "sl_warnings": 0}}

    symbols = list({t.symbol for t in open_holdings})
    quotes_map = await market_data_service.fetch_quotes_bulk(symbols)

    # Fetch all active alerts for this user to correlate coupled protection
    alerts_res = await db.execute(
        select(Alert).where(Alert.user_id == current_user.id, Alert.is_active == True)
    )
    user_alerts = alerts_res.scalars().all()
    alerts_by_symbol = {}
    for a in user_alerts:
        alerts_by_symbol.setdefault(a.symbol, []).append(a)

    holdings_data = []
    targets_approaching_count = 0
    sl_warnings_count = 0

    for t in open_holdings:
        quote = quotes_map.get(t.symbol)
        if not quote or quote.get("price", 0) <= 0:
            clean = t.symbol.replace(".BO", "").replace(".NS", "")
            quote = quotes_map.get(f"{clean}.NS") or quotes_map.get(f"{clean}.BO") or quotes_map.get(clean) or {}

        cmp = float(quote.get("price", 0.0))
        entry_price = float(t.entry_price) if t.entry_price is not None else cmp
        if cmp <= 0.0:
            cmp = entry_price

        invested = round(entry_price * t.quantity, 2)
        current_value = round(cmp * t.quantity, 2)
        unrealized_pnl = round(current_value - invested - float(t.commission or 0.0) - float(t.stt_tax or 0.0), 2)
        pnl_pct = round((unrealized_pnl / invested) * 100.0, 2) if invested > 0 else 0.0

        target_price = float(t.target_price) if t.target_price else round(entry_price * 1.08, 2)
        stop_loss = float(t.stop_loss) if t.stop_loss else round(entry_price * 0.96, 2)

        # Calculate distances
        distance_to_target_pct = round(((target_price - cmp) / cmp) * 100.0, 2) if cmp > 0 else 0.0
        distance_to_sl_pct = round(((cmp - stop_loss) / cmp) * 100.0, 2) if cmp > 0 else 0.0

        # Proximity thresholds (1.0% window)
        is_target_hit = cmp >= target_price
        is_target_approaching = (cmp >= target_price * 0.99) and not is_target_hit
        is_sl_hit = cmp <= stop_loss
        is_sl_approaching = (cmp <= stop_loss * 1.015) and not is_sl_hit

        if is_target_approaching or is_target_hit:
            targets_approaching_count += 1
        if is_sl_approaching or is_sl_hit:
            sl_warnings_count += 1

        if is_sl_hit:
            risk_status = "SL_HIT"
            risk_label = "Stop Loss Hit (Exit Position)"
        elif is_sl_approaching:
            risk_status = "SL_APPROACHING"
            risk_label = "Approaching Stop Loss"
        elif is_target_hit:
            risk_status = "TARGET_HIT"
            risk_label = "Target Hit (Sell Triggered)"
        elif is_target_approaching:
            risk_status = "TARGET_APPROACHING"
            risk_label = "Approaching Target (Prepare to Sell)"
        else:
            risk_status = "SAFE_ZONE"
            risk_label = "In Safe Zone"

        active_symbol_alerts = alerts_by_symbol.get(t.symbol, [])

        holdings_data.append({
            "trade_id": str(t.id),
            "symbol": t.symbol,
            "product_type": t.product_type,
            "quantity": t.quantity,
            "entry_price": entry_price,
            "cmp": cmp,
            "invested": invested,
            "current_value": current_value,
            "unrealized_pnl": unrealized_pnl,
            "pnl_pct": pnl_pct,
            "target_price": target_price,
            "stop_loss": stop_loss,
            "distance_to_target_pct": distance_to_target_pct,
            "distance_to_sl_pct": distance_to_sl_pct,
            "is_target_approaching": is_target_approaching,
            "is_target_hit": is_target_hit,
            "is_sl_approaching": is_sl_approaching,
            "is_sl_hit": is_sl_hit,
            "risk_status": risk_status,
            "risk_label": risk_label,
            "active_alerts_count": len(active_symbol_alerts),
            "opened_at": t.opened_at.isoformat() if t.opened_at else None,
        })

    return {
        "holdings": holdings_data,
        "summary": {
            "total_held": len(holdings_data),
            "targets_approaching": targets_approaching_count,
            "sl_warnings": sl_warnings_count,
        }
    }


@router.post("/holdings-sync")
async def sync_holdings_alerts(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ensure every active holding has coupled Target Pre-Alert and Stop Loss alerts."""
    trades = await paper_trading_service.get_all_trades(db, str(current_user.id))
    open_holdings = [t for t in trades if t.status == "OPEN" and t.direction == "BUY"]

    alerts_res = await db.execute(
        select(Alert).where(Alert.user_id == current_user.id, Alert.is_active == True)
    )
    existing_alerts = alerts_res.scalars().all()
    existing_symbols = {a.symbol for a in existing_alerts}

    synced_count = 0
    for t in open_holdings:
        if t.symbol not in existing_symbols:
            entry_p = float(t.entry_price) if t.entry_price else 100.0
            tgt = float(t.target_price) if t.target_price else round(entry_p * 1.08, 2)
            sl = float(t.stop_loss) if t.stop_loss else round(entry_p * 0.96, 2)

            # Target Proximity
            tgt_prox = round(tgt * 0.99, 2)
            db.add(Alert(
                user_id=current_user.id,
                symbol=t.symbol,
                condition_type="TARGET_PROXIMITY",
                condition_value=tgt_prox,
                message=f"{t.symbol}: Approaching Target! Price near ₹{tgt_prox:.2f} — Prepare to sell.",
                priority="HIGH",
                delivery_method="IN_APP",
                is_active=True,
            ))
            # Stop Loss Proximity
            sl_prox = round(sl * 1.015, 2)
            db.add(Alert(
                user_id=current_user.id,
                symbol=t.symbol,
                condition_type="STOP_LOSS_PROXIMITY",
                condition_value=sl_prox,
                message=f"{t.symbol}: ⚠️ Approaching Stop Loss! Price near ₹{sl_prox:.2f}",
                priority="HIGH",
                delivery_method="IN_APP",
                is_active=True,
            ))
            # Stop Loss Hit
            db.add(Alert(
                user_id=current_user.id,
                symbol=t.symbol,
                condition_type="STOP_LOSS_HIT",
                condition_value=sl,
                message=f"{t.symbol}: 🛑 Stop Loss Breached at ₹{sl:.2f}! Cut losses.",
                priority="HIGH",
                delivery_method="IN_APP",
                is_active=True,
            ))
            synced_count += 1

    if synced_count > 0:
        await db.flush()
        try:
            await broadcast_alert({
                "type": "alert_toast",
                "data": {
                    "title": "🛡️ Holdings Guard Synced",
                    "message": f"Coupled Target & Stop Loss alerts activated for {synced_count} open holdings.",
                    "type": "success"
                }
            }, user_id=str(current_user.id))
        except Exception:
            pass

    return {"synced_count": synced_count}


@router.delete("/{alert_id}")
async def delete_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an alert."""
    try:
        target_uuid = uuid.UUID(str(alert_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid alert_id format: '{alert_id}'. Must be a valid UUID.")

    result = await db.execute(
        select(Alert).where(Alert.id == target_uuid, Alert.user_id == current_user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
    return {"deleted": True}


@router.put("/{alert_id}/deactivate")
async def deactivate_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate an alert without deleting it."""
    try:
        target_uuid = uuid.UUID(str(alert_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid alert_id format: '{alert_id}'. Must be a valid UUID.")

    result = await db.execute(
        select(Alert).where(Alert.id == target_uuid, Alert.user_id == current_user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_active = False
    return {"deactivated": True}
