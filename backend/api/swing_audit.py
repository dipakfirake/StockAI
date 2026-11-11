"""FastAPI router for the 11-Day Swing Trade Audit System."""

import os
from datetime import date
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import get_current_user, get_current_user_optional
from backend.services.swing_audit_service import swing_audit_service

router = APIRouter(prefix="/swing-audit", tags=["Swing Trade Audit"])


class TrackSwingAuditRequest(BaseModel):
    symbol: str = Field(..., description="Stock symbol (e.g. POWERGRID, RELIANCE)")
    buy_price: float = Field(..., gt=0, description="Entry / CMP price")
    target_price: float = Field(..., gt=0, description="Target price (T2)")
    stop_loss: float = Field(..., gt=0, description="Stop loss level")
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_3: Optional[float] = None
    reward_to_risk: Optional[float] = None
    total_score: Optional[float] = None
    company_name: Optional[str] = None
    recommendation_date: Optional[date] = None
    allocated_capital: float = Field(100000.0, description="Capital allocation in ₹ for PnL tracking")
    user_bought: bool = Field(False, description="Whether user explicitly executed/bought this recommendation")
    user_buy_price: Optional[float] = Field(None, description="Actual price at which user bought the stock")
    notes: Optional[str] = None


@router.post("/track")
async def track_swing_recommendation(
    req: TrackSwingAuditRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional)
):
    """
    Catalog a stock recommendation from Swing Trade Analysis into the 11-Day Audit Ledger.
    """
    try:
        trade_plan = {
            "entry_price": req.buy_price,
            "target_price": req.target_price,
            "stop_loss": req.stop_loss,
            "target_1": req.target_1,
            "target_2": req.target_2 or req.target_price,
            "target_3": req.target_3,
            "reward_to_risk": req.reward_to_risk or 2.0
        }
        audit = await swing_audit_service.track_swing_trade(
            db=db,
            symbol=req.symbol,
            trade_plan=trade_plan,
            company_name=req.company_name,
            recommendation_date=req.recommendation_date,
            total_score=req.total_score,
            allocated_capital=req.allocated_capital,
            user_bought=req.user_bought,
            user_buy_price=req.user_buy_price,
            notes=req.notes
        )
        return {
            "status": "success",
            "message": f"Successfully cataloged {audit.symbol} into 11-Day Swing Audit",
            "audit_id": str(audit.id),
            "symbol": audit.symbol,
            "buy_price": float(audit.buy_price),
            "user_bought": audit.user_bought,
            "user_buy_price": float(audit.user_buy_price) if audit.user_buy_price is not None else None,
            "target_price": float(audit.target_price),
            "stop_loss": float(audit.stop_loss),
            "status_code": audit.status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to track swing audit: {e}")


@router.get("/current-cycle")
async def get_current_audit_cycle(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional)
):
    """
    Retrieve live status and scorecard of the active 11-day audit cycle.
    """
    try:
        data = await swing_audit_service.get_cycle_summary(db)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load audit cycle: {e}")


@router.post("/sync")
async def sync_audit_prices(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user_optional)
):
    """
    Evaluate daily price milestones (Day 1..11), check Stop Loss and Target hits,
    update booked PnL, and refresh the Excel report file.
    """
    try:
        res = await swing_audit_service.update_daily_prices(db)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync audit prices: {e}")


@router.get("/download-latest")
async def download_latest_audit_excel(
    db: AsyncSession = Depends(get_db)
):
    """
    Download the latest 11-day audit Excel workbook (.xlsx) with formatting and formulas.
    """
    cycle = await swing_audit_service.get_or_create_active_cycle(db)
    
    # Ensure Excel workbook is generated and up to date
    excel_path = cycle.excel_file_path
    if not excel_path or not os.path.exists(excel_path):
        excel_path_obj = await swing_audit_service.generate_excel_workbook(db, cycle.id)
        excel_path = str(excel_path_obj) if excel_path_obj else None

    # Defensive fallback: check target filename directly in audit directory
    if not excel_path or not os.path.exists(excel_path):
        filename = f"Swing_Trade_Audit_{cycle.from_date}_to_{cycle.to_date}.xlsx"
        fallback_file = swing_audit_service.get_audit_dir() / filename
        if fallback_file.exists():
            excel_path = str(fallback_file)

    if not excel_path or not os.path.exists(excel_path):
        raise HTTPException(status_code=404, detail="Audit Excel file has not been generated yet.")

    filename = os.path.basename(excel_path)
    return FileResponse(
        path=excel_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

