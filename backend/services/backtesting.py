"""
Backtesting engine — walk-forward strategy simulation.

Applies realistic slippage, commission, and position sizing.
Computes: total return, Sharpe ratio, max drawdown, win rate, profit factor.
"""

from __future__ import annotations

from typing import Optional
import pandas as pd
import numpy as np

from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service, candles_to_df
from backend.core.config import settings
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

SUPPORTED_STRATEGIES = {"rsi_mean_reversion", "ema_crossover", "macd_signal", "ai_machine_learning"}


class BacktestEngine:
    """
    Simulates a trading strategy on historical OHLCV data.
    Every backtest includes: entry/exit logic, slippage, commission, metrics.
    """

    @staticmethod
    async def run(
        symbol: str,
        strategy: str,
        params: dict,
        start_date: str,
        end_date: str,
        initial_capital: float = 100000.0,
    ) -> dict:
        """Run a backtest for a given strategy and symbol."""
        if strategy not in SUPPORTED_STRATEGIES:
            raise ValueError(f"Unsupported strategy '{strategy}'. Choose from: {SUPPORTED_STRATEGIES}")

        # Fetch dynamic settings
        from backend.core.database import AsyncSessionLocal
        from backend.models.settings import SystemSettings
        from sqlalchemy import select
        
        dynamic_settings = {}
        async with AsyncSessionLocal() as db:
            db_settings = (await db.execute(select(SystemSettings))).scalars().all()
            for s in db_settings:
                dynamic_settings[s.key] = s.get_typed_value()
                
        slippage_pct = dynamic_settings.get("default_slippage", 0.001) # 0.1%
        commission = dynamic_settings.get("default_commission", 20.0)

        # Fetch historical candles
        candles = await market_data_service.fetch_candles(
            symbol=symbol,
            timeframe="1d",
            start_date=start_date,
            end_date=end_date,
            limit=2000,
        )

        if len(candles) < 50:
            raise ValueError(f"Insufficient historical data for {symbol} (got {len(candles)} candles, need ≥ 50)")

        df = candles_to_df(candles)

        # Calculate Benchmark (NIFTY 50)
        benchmark_metrics = {"total_return_pct": 0.0, "max_drawdown_pct": 0.0}
        try:
            nifty_candles = await market_data_service.fetch_candles(
                symbol="^NSEI", timeframe="1d", start_date=start_date, end_date=end_date, limit=2000
            )
            if len(nifty_candles) > 1:
                closes = [c["close"] for c in nifty_candles if c.get("close")]
                if closes:
                    b_ret = (closes[-1] - closes[0]) / closes[0] * 100
                    b_peak = closes[0]
                    b_max_dd = 0.0
                    for c in closes:
                        if c > b_peak: b_peak = c
                        dd = (c - b_peak) / b_peak * 100
                        if dd < b_max_dd: b_max_dd = dd
                    benchmark_metrics = {"total_return_pct": round(b_ret, 2), "max_drawdown_pct": round(b_max_dd, 2)}
        except Exception as e:
            logger.warning(f"Failed to fetch NIFTY50 benchmark: {e}")

        res = {}
        if strategy == "rsi_mean_reversion":
            res = BacktestEngine._rsi_mean_reversion(df, params, initial_capital, symbol, slippage_pct, commission)
        elif strategy == "ema_crossover":
            res = BacktestEngine._ema_crossover(df, params, initial_capital, symbol, slippage_pct, commission)
        elif strategy == "macd_signal":
            res = BacktestEngine._macd_signal(df, params, initial_capital, symbol, slippage_pct, commission)
        elif strategy == "ai_machine_learning":
            res = BacktestEngine._ai_machine_learning(df, params, initial_capital, symbol, slippage_pct, commission)
        
        res["benchmark"] = benchmark_metrics
        return res

    @staticmethod
    def _compute_metrics(trades: list[dict], equity_curve: list[dict], initial_capital: float) -> dict:
        if not trades:
            return {
                "total_return_pct": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "win_rate": 0.0,
                "total_trades": 0,
                "profit_factor": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "final_equity": initial_capital,
            }

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
        total_return_pct = (final_equity - initial_capital) / initial_capital * 100

        # Sharpe ratio (annualised, assuming 252 trading days)
        if len(equity_curve) > 1:
            eq_vals = [e["equity"] for e in equity_curve]
            returns = pd.Series(eq_vals).pct_change().dropna()
            sharpe = float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0
            
            # Sortino
            downside_returns = returns[returns < 0]
            downside_std = downside_returns.std()
            sortino = float(returns.mean() / downside_std * np.sqrt(252)) if pd.notna(downside_std) and downside_std > 0 else 0.0
        else:
            sharpe = 0.0
            sortino = 0.0

        # Max drawdown
        if equity_curve:
            eq_series = pd.Series([e["equity"] for e in equity_curve])
            rolling_max = eq_series.cummax()
            drawdown = (eq_series - rolling_max) / rolling_max * 100
            max_drawdown_pct = float(drawdown.min())
        else:
            max_drawdown_pct = 0.0

        # Calmar
        if len(equity_curve) > 0 and max_drawdown_pct < 0:
            # Check for negative returns causing complex numbers with fractional powers
            ann_ret = (1 + (total_return_pct/100)) ** (252 / len(equity_curve)) - 1 if (1 + (total_return_pct/100)) >= 0 else 0
            calmar = float(ann_ret / abs(max_drawdown_pct / 100))
        else:
            calmar = 0.0

        profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 9999.0

        return {
            "total_return_pct": round(total_return_pct, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "calmar_ratio": round(calmar, 3),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "win_rate": round(len(wins) / len(pnls), 4) if pnls else 0,
            "total_trades": len(pnls),
            "profit_factor": round(profit_factor, 3),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
            "final_equity": round(final_equity, 2),
        }

    @staticmethod
    def _rsi_mean_reversion(df: pd.DataFrame, params: dict, capital: float, symbol: str, slippage_pct: float, commission: float) -> dict:
        from ta.momentum import RSIIndicator
        rsi_buy = params.get("rsi_buy", 30)
        rsi_sell = params.get("rsi_sell", 70)
        qty = params.get("quantity", 10)

        df["rsi"] = RSIIndicator(df["Close"], window=14).rsi()
        df = df.dropna()

        trades, equity_curve = [], []
        position = None
        equity = capital

        for i, (ts, row) in enumerate(df.iterrows()):
            rsi_val = row["rsi"]
            price = float(row["Close"])

            if position is None and rsi_val < rsi_buy:
                entry = price * (1 + slippage_pct)
                position = {"entry": entry, "qty": qty, "entry_date": ts.isoformat()}

            elif position is not None and rsi_val > rsi_sell:
                exit_p = price * (1 - slippage_pct)
                pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
                equity += pnl
                trades.append({"entry": position["entry"], "exit": exit_p, "pnl": pnl, "entry_date": position["entry_date"], "exit_date": ts.isoformat()})
                equity_curve.append({"date": ts.isoformat(), "equity": round(equity, 2)})
                position = None

        metrics = BacktestEngine._compute_metrics(trades, equity_curve, capital)
        return {"symbol": symbol, "strategy": "rsi_mean_reversion", "params": params, "metrics": metrics, "trades": trades[-20:], "equity_curve": equity_curve}

    @staticmethod
    def _ema_crossover(df: pd.DataFrame, params: dict, capital: float, symbol: str, slippage_pct: float, commission: float) -> dict:
        from ta.trend import EMAIndicator
        fast = params.get("fast_ema", 9)
        slow = params.get("slow_ema", 21)
        qty = params.get("quantity", 10)

        df[f"ema_{fast}"] = EMAIndicator(df["Close"], window=fast).ema_indicator()
        df[f"ema_{slow}"] = EMAIndicator(df["Close"], window=slow).ema_indicator()
        df = df.dropna()

        trades, equity_curve = [], []
        position = None
        equity = capital

        prev_fast = prev_slow = None
        for ts, row in df.iterrows():
            cur_fast = float(row[f"ema_{fast}"])
            cur_slow = float(row[f"ema_{slow}"])
            price = float(row["Close"])

            if prev_fast and prev_slow:
                crossed_up = prev_fast <= prev_slow and cur_fast > cur_slow
                crossed_down = prev_fast >= prev_slow and cur_fast < cur_slow

                if position is None and crossed_up:
                    entry = price * (1 + slippage_pct)
                    position = {"entry": entry, "qty": qty, "entry_date": ts.isoformat()}

                elif position is not None and crossed_down:
                    exit_p = price * (1 - slippage_pct)
                    pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
                    equity += pnl
                    trades.append({"entry": position["entry"], "exit": exit_p, "pnl": pnl, "entry_date": position["entry_date"], "exit_date": ts.isoformat()})
                    equity_curve.append({"date": ts.isoformat(), "equity": round(equity, 2)})
                    position = None

            prev_fast, prev_slow = cur_fast, cur_slow

        metrics = BacktestEngine._compute_metrics(trades, equity_curve, capital)
        return {"symbol": symbol, "strategy": "ema_crossover", "params": params, "metrics": metrics, "trades": trades[-20:], "equity_curve": equity_curve}

    @staticmethod
    def _macd_signal(df: pd.DataFrame, params: dict, capital: float, symbol: str, slippage_pct: float, commission: float) -> dict:
        from ta.trend import MACD
        qty = params.get("quantity", 10)

        macd_indicator = MACD(df["Close"], window_slow=26, window_fast=12, window_sign=9)
        df["hist"] = macd_indicator.macd_diff()
        df = df.dropna()

        trades, equity_curve = [], []
        position = None
        equity = capital

        prev_hist = None
        for ts, row in df.iterrows():
            hist = float(row["hist"])
            price = float(row["Close"])

            if prev_hist is not None:
                if position is None and prev_hist < 0 and hist > 0:
                    entry = price * (1 + slippage_pct)
                    position = {"entry": entry, "qty": qty, "entry_date": ts.isoformat()}
                elif position is not None and prev_hist > 0 and hist < 0:
                    exit_p = price * (1 - slippage_pct)
                    pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
                    equity += pnl
                    trades.append({"entry": position["entry"], "exit": exit_p, "pnl": pnl, "entry_date": position["entry_date"], "exit_date": ts.isoformat()})
                    equity_curve.append({"date": ts.isoformat(), "equity": round(equity, 2)})
                    position = None

            prev_hist = hist

        metrics = BacktestEngine._compute_metrics(trades, equity_curve, capital)
        return {"symbol": symbol, "strategy": "macd_signal", "params": params, "metrics": metrics, "trades": trades[-20:], "equity_curve": equity_curve}

    @staticmethod
    def _ai_machine_learning(df: pd.DataFrame, params: dict, capital: float, symbol: str, slippage_pct: float, commission: float) -> dict:
        from ta.momentum import RSIIndicator, StochasticOscillator
        from ta.trend import MACD, EMAIndicator, SMAIndicator, ADXIndicator, CCIIndicator
        from ta.volatility import BollingerBands, AverageTrueRange
        from backend.services.ai_engine import ai_engine_service

        qty_mode = params.get("qty_mode", "fixed") # "fixed" or "atr"
        fixed_qty = params.get("quantity", 10)
        risk_pct = params.get("risk_pct", 0.02) # 2% risk per trade if atr mode

        df["rsi_14"] = RSIIndicator(df["Close"], window=14).rsi()
        
        macd_indicator = MACD(df["Close"])
        df["macd"] = macd_indicator.macd()
        df["macd_hist"] = macd_indicator.macd_diff()
        
        df["ema_9"] = EMAIndicator(df["Close"], window=9).ema_indicator()
        df["ema_21"] = EMAIndicator(df["Close"], window=21).ema_indicator()
        df["ema_50"] = EMAIndicator(df["Close"], window=50).ema_indicator()
        df["sma_200"] = SMAIndicator(df["Close"], window=200).sma_indicator()
        
        bb = BollingerBands(df["Close"], window=20, window_dev=2)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_mid"] = bb.bollinger_mavg()
        
        adx = ADXIndicator(df["High"], df["Low"], df["Close"], window=14)
        df["adx_14"] = adx.adx()
        
        atr = AverageTrueRange(df["High"], df["Low"], df["Close"], window=14)
        df["atr"] = atr.average_true_range()
        
        stoch = StochasticOscillator(df["High"], df["Low"], df["Close"], window=14, smooth_window=3)
        df["stoch_k"] = stoch.stoch()
        
        cci = CCIIndicator(df["High"], df["Low"], df["Close"], window=20)
        df["cci_20"] = cci.cci()
        
        df["vol_sma_20"] = SMAIndicator(df["Volume"], window=20).sma_indicator()
        
        df = df.dropna()

        trades, equity_curve = [], []
        position = None
        equity = capital

        for ts, row in df.iterrows():
            # Construct indicator dict exactly as ai_engine expects
            indicators = {
                "close": float(row["Close"]),
                "volume": float(row["Volume"]),
                "rsi_14": float(row["rsi_14"]),
                "macd": {"macd": float(row["macd"]), "histogram": float(row["macd_hist"])},
                "ema_9": float(row["ema_9"]),
                "ema_21": float(row["ema_21"]),
                "ema_50": float(row["ema_50"]),
                "sma_200": float(row["sma_200"]),
                "bb": {"upper": float(row["bb_upper"]), "lower": float(row["bb_lower"]), "middle": float(row["bb_mid"])},
                "adx_14": float(row["adx_14"]),
                "stoch_k": float(row["stoch_k"]),
                "cci_20": float(row["cci_20"]),
                "atr_14": float(row["atr"]),
                "vol_sma_20": float(row["vol_sma_20"])
            }
            
            # Use LightGBM scoring method to simulate the AI fast (without computing SHAP explanations)
            ai_result = ai_engine_service.score(indicators, symbol, compute_shap=False)
            score = ai_result.get("score", "HOLD")
            probs = ai_result.get("probabilities", {})
            buy_prob = probs.get("buy", 0.0)
            
            price = float(row["Close"])
            current_atr = float(row["atr"]) if float(row["atr"]) > 0 else 1.0

            # Dynamic Position Sizing (Phase 2.2)
            if qty_mode == "atr":
                risk_amount = equity * risk_pct
                stop_distance = current_atr * 1.5
                qty = int(risk_amount / stop_distance) if stop_distance > 0 else fixed_qty
                if qty == 0: qty = 1
            else:
                qty = fixed_qty

            if position is None:
                if score == "BUY" or buy_prob > 0.55:
                    entry = price * (1 + slippage_pct)
                    sl = entry - (current_atr * 1.5)
                    position = {"entry": entry, "qty": qty, "entry_date": ts.isoformat(), "highest_price": entry, "sl": sl}
            else:
                # Update trailing stop loss (Phase 2.2)
                if price > position["highest_price"]:
                    position["highest_price"] = price
                    new_sl = price - (current_atr * 1.5)
                    if new_sl > position["sl"]:
                        position["sl"] = new_sl

                # Exit logic (AI says SELL or Stop Loss hit)
                if score == "SELL" or price <= position["sl"]:
                    exit_p = price * (1 - slippage_pct)
                    pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
                    equity += pnl
                    trades.append({"entry": position["entry"], "exit": exit_p, "pnl": pnl, "entry_date": position["entry_date"], "exit_date": ts.isoformat()})
                    equity_curve.append({"date": ts.isoformat(), "equity": round(equity, 2)})
                    position = None

        metrics = BacktestEngine._compute_metrics(trades, equity_curve, capital)
        return {"symbol": symbol, "strategy": "ai_machine_learning", "params": params, "metrics": metrics, "trades": trades[-20:], "equity_curve": equity_curve}

backtest_engine = BacktestEngine()
