"""Backtesting API router."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import get_current_user, require_pro_tier
from backend.services.backtesting import backtest_engine

router = APIRouter()

# In-memory store for demo (replace with DB in production)
_backtest_results: dict = {}


class BacktestRequest(BaseModel):
    symbol: str
    strategy: str              # rsi_mean_reversion | ema_crossover | macd_signal
    params: dict = {}
    start_date: str            # YYYY-MM-DD
    end_date: str              # YYYY-MM-DD
    initial_capital: float = 100000.0


@router.post("/run")
async def run_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_pro_tier),
    db: AsyncSession = Depends(get_db),
):
    """Submit a backtest job. Returns backtest_id for polling."""
    import uuid as _uuid
    backtest_id = str(_uuid.uuid4())
    _backtest_results[backtest_id] = {"status": "RUNNING"}

    async def _run():
        try:
            result = await backtest_engine.run(
                symbol=request.symbol.upper(),
                strategy=request.strategy,
                params=request.params,
                start_date=request.start_date,
                end_date=request.end_date,
                initial_capital=request.initial_capital,
            )
            _backtest_results[backtest_id] = {"status": "COMPLETED", **result}
        except Exception as e:
            _backtest_results[backtest_id] = {"status": "FAILED", "error": str(e)}

    background_tasks.add_task(_run)
    return {"backtest_id": backtest_id, "status": "QUEUED"}


@router.get("/{backtest_id}/results")
async def get_backtest_results(
    backtest_id: str,
    current_user=Depends(require_pro_tier),
):
    """Poll for backtest results."""
    result = _backtest_results.get(backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return {"backtest_id": backtest_id, **result}


@router.get("/strategies")
async def list_strategies(current_user=Depends(require_pro_tier)):
    """List all supported backtest strategies."""
    return {
        "strategies": [
            {
                "id": "ai_machine_learning",
                "name": "LightGBM Multi-Cap AI Model",
                "description": "Walk-forward trade execution powered by the trained LightGBM ML model with ATR trailing stops and SHAP confidence scoring",
                "params": {"confidence_threshold": 0.65, "quantity": 10, "qty_mode": "fixed"},
            },
            {
                "id": "rsi_mean_reversion",
                "name": "RSI Mean Reversion",
                "description": "Buy when RSI < 30 (oversold), sell when RSI > 70 (overbought)",
                "params": {"rsi_buy": 30, "rsi_sell": 70, "quantity": 10},
            },
            {
                "id": "ema_crossover",
                "name": "EMA Crossover",
                "description": "Buy when EMA9 crosses above EMA21, sell when EMA9 crosses below EMA21",
                "params": {"fast_ema": 9, "slow_ema": 21, "quantity": 10},
            },
            {
                "id": "macd_signal",
                "name": "MACD Signal Line Cross",
                "description": "Buy when MACD histogram turns positive, sell when it turns negative",
                "params": {"quantity": 10},
            },
        ]
    }
