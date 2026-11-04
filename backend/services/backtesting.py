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

SUPPORTED_STRATEGIES = {
    "rsi_mean_reversion",
    "ema_crossover",
    "macd_signal",
    "ai_machine_learning",
    "supertrend_trend_rider",
    "smc_liquidity_fvg",
}


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
        elif strategy == "supertrend_trend_rider":
            res = BacktestEngine._supertrend_trend_rider(df, params, initial_capital, symbol, slippage_pct, commission)
        elif strategy == "smc_liquidity_fvg":
            res = BacktestEngine._smc_liquidity_fvg(df, params, initial_capital, symbol, slippage_pct, commission)
        
        res["benchmark"] = benchmark_metrics
        return res

    @staticmethod
    def _compute_metrics(trades: list[dict], equity_curve: list[dict], initial_capital: float) -> dict:
        if not trades:
            return {
                "total_return_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "calmar_ratio": 0.0,
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
            
            # Sortino ratio
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

        # Calmar ratio (Annualized return / Max Drawdown)
        if len(equity_curve) > 0 and max_drawdown_pct < 0:
            years = max(1.0 / 252.0, len(equity_curve) / 252.0)
            if total_return_pct > -100:
                ann_ret = ((1.0 + (total_return_pct / 100.0)) ** (1.0 / years)) - 1.0
            else:
                ann_ret = -1.0
            calmar = float(ann_ret / abs(max_drawdown_pct / 100.0))
        else:
            calmar = 0.0

        if losses and sum(losses) != 0:
            profit_factor = abs(sum(wins) / sum(losses))
        elif wins:
            profit_factor = round(sum(wins), 2)
        else:
            profit_factor = 0.0

        # Institutional metrics: Expectancy, Payoff Ratio, Streak Tracking
        max_consec_wins = 0
        max_consec_losses = 0
        cur_consec_wins = 0
        cur_consec_losses = 0
        for p in pnls:
            if p > 0:
                cur_consec_wins += 1
                cur_consec_losses = 0
                if cur_consec_wins > max_consec_wins:
                    max_consec_wins = cur_consec_wins
            elif p < 0:
                cur_consec_losses += 1
                cur_consec_wins = 0
                if cur_consec_losses > max_consec_losses:
                    max_consec_losses = cur_consec_losses

        avg_win_val = sum(wins) / len(wins) if wins else 0.0
        avg_loss_val = sum(losses) / len(losses) if losses else 0.0
        win_rate_val = len(wins) / len(pnls) if pnls else 0.0
        loss_rate_val = len(losses) / len(pnls) if pnls else 0.0
        expectancy = (win_rate_val * avg_win_val) + (loss_rate_val * avg_loss_val)
        payoff_ratio = abs(avg_win_val / avg_loss_val) if avg_loss_val != 0 else round(avg_win_val, 2)

        return {
            "total_return_pct": round(total_return_pct, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "calmar_ratio": round(calmar, 3),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "win_rate": round(win_rate_val, 4),
            "total_trades": len(pnls),
            "profit_factor": round(profit_factor, 3),
            "avg_win": round(avg_win_val, 2),
            "avg_loss": round(avg_loss_val, 2),
            "expectancy_per_trade": round(expectancy, 2),
            "win_loss_ratio": round(payoff_ratio, 2),
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
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
                position = None

            # Mark to market for daily equity curve
            cur_pnl = ((price * (1 - slippage_pct) - position["entry"]) * position["qty"] - commission * 2) if position else 0.0
            equity_curve.append({"date": ts.isoformat(), "equity": round(equity + cur_pnl, 2)})

        # Close any lingering open position at final candle
        if position is not None and not df.empty:
            final_ts = df.index[-1].isoformat()
            final_price = float(df["Close"].iloc[-1])
            exit_p = final_price * (1 - slippage_pct)
            pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
            equity += pnl
            trades.append({"entry": position["entry"], "exit": exit_p, "pnl": pnl, "entry_date": position["entry_date"], "exit_date": final_ts})
            if equity_curve:
                equity_curve[-1]["equity"] = round(equity, 2)

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
                    position = None

            prev_fast, prev_slow = cur_fast, cur_slow

            # Mark to market daily equity curve
            cur_pnl = ((price * (1 - slippage_pct) - position["entry"]) * position["qty"] - commission * 2) if position else 0.0
            equity_curve.append({"date": ts.isoformat(), "equity": round(equity + cur_pnl, 2)})

        # Close any lingering open position at final candle
        if position is not None and not df.empty:
            final_ts = df.index[-1].isoformat()
            final_price = float(df["Close"].iloc[-1])
            exit_p = final_price * (1 - slippage_pct)
            pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
            equity += pnl
            trades.append({"entry": position["entry"], "exit": exit_p, "pnl": pnl, "entry_date": position["entry_date"], "exit_date": final_ts})
            if equity_curve:
                equity_curve[-1]["equity"] = round(equity, 2)

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
                    position = None

            prev_hist = hist

            # Mark to market daily equity curve
            cur_pnl = ((price * (1 - slippage_pct) - position["entry"]) * position["qty"] - commission * 2) if position else 0.0
            equity_curve.append({"date": ts.isoformat(), "equity": round(equity + cur_pnl, 2)})

        # Close any lingering open position at final candle
        if position is not None and not df.empty:
            final_ts = df.index[-1].isoformat()
            final_price = float(df["Close"].iloc[-1])
            exit_p = final_price * (1 - slippage_pct)
            pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
            equity += pnl
            trades.append({"entry": position["entry"], "exit": exit_p, "pnl": pnl, "entry_date": position["entry_date"], "exit_date": final_ts})
            if equity_curve:
                equity_curve[-1]["equity"] = round(equity, 2)

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
            
            ai_result = ai_engine_service.score(indicators, symbol, compute_shap=False)
            score = ai_result.get("score", "HOLD")
            probs = ai_result.get("probabilities", {})
            buy_prob = probs.get("buy", 0.0)
            
            price = float(row["Close"])
            current_atr = float(row["atr"]) if float(row["atr"]) > 0 else 1.0

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
                if price > position["highest_price"]:
                    position["highest_price"] = price
                    new_sl = price - (current_atr * 1.5)
                    if new_sl > position["sl"]:
                        position["sl"] = new_sl

                if score == "SELL" or price <= position["sl"]:
                    exit_p = price * (1 - slippage_pct)
                    pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
                    equity += pnl
                    trades.append({"entry": position["entry"], "exit": exit_p, "pnl": pnl, "entry_date": position["entry_date"], "exit_date": ts.isoformat()})
                    position = None

            # Mark to market daily equity curve
            cur_pnl = ((price * (1 - slippage_pct) - position["entry"]) * position["qty"] - commission * 2) if position else 0.0
            equity_curve.append({"date": ts.isoformat(), "equity": round(equity + cur_pnl, 2)})

        # Close any lingering open position at final candle
        if position is not None and not df.empty:
            final_ts = df.index[-1].isoformat()
            final_price = float(df["Close"].iloc[-1])
            exit_p = final_price * (1 - slippage_pct)
            pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
            equity += pnl
            trades.append({"entry": position["entry"], "exit": exit_p, "pnl": pnl, "entry_date": position["entry_date"], "exit_date": final_ts})
            if equity_curve:
                equity_curve[-1]["equity"] = round(equity, 2)

        metrics = BacktestEngine._compute_metrics(trades, equity_curve, capital)
        return {"symbol": symbol, "strategy": "ai_machine_learning", "params": params, "metrics": metrics, "trades": trades[-20:], "equity_curve": equity_curve}

    @staticmethod
    def _supertrend_trend_rider(df: pd.DataFrame, params: dict, capital: float, symbol: str, slippage_pct: float, commission: float) -> dict:
        """
        SuperTrend Trend Rider (ATR Volatility Trend Following).
        Enters when price is above 200 EMA and SuperTrend turns bullish.
        Uses dynamic ATR trailing stop loss to lock in runaway profits.
        """
        from ta.trend import EMAIndicator
        from ta.volatility import AverageTrueRange
        from backend.services.indicators import calculate_supertrend

        period = int(params.get("period", 10))
        multiplier = float(params.get("multiplier", 3.0))
        qty = int(params.get("quantity", 10))

        st_df = calculate_supertrend(df, period=period, multiplier=multiplier)
        df["supertrend"] = st_df["SuperTrend"]
        df["direction"] = st_df["Direction"]
        df["ema_200"] = EMAIndicator(df["Close"], window=min(200, max(20, len(df) // 2))).ema_indicator()
        df["atr"] = AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14).average_true_range()
        df = df.dropna()

        trades, equity_curve = [], []
        position = None
        equity = capital
        prev_dir = 0

        for ts, row in df.iterrows():
            price = float(row["Close"])
            cur_dir = int(row["direction"])
            ema_200 = float(row["ema_200"])
            atr = float(row["atr"]) if float(row["atr"]) > 0 else 1.0

            # Entry: SuperTrend flips from -1 (bearish) to 1 (bullish) and price > EMA 200
            if position is None:
                if cur_dir == 1 and prev_dir == -1 and price > ema_200:
                    entry = price * (1 + slippage_pct)
                    sl = entry - (1.5 * atr)
                    position = {
                        "entry": entry,
                        "qty": qty,
                        "entry_date": ts.isoformat(),
                        "highest_price": entry,
                        "sl": sl,
                    }
            else:
                # Update trailing stop on winning trends
                if price > position["highest_price"]:
                    position["highest_price"] = price
                    new_sl = price - (1.5 * atr)
                    if new_sl > position["sl"]:
                        position["sl"] = new_sl

                # Exit condition: SuperTrend flips bearish (-1) OR trailing stop is hit
                if cur_dir == -1 or price <= position["sl"]:
                    exit_p = price * (1 - slippage_pct)
                    pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
                    equity += pnl
                    trades.append({
                        "entry": position["entry"],
                        "exit": exit_p,
                        "pnl": pnl,
                        "entry_date": position["entry_date"],
                        "exit_date": ts.isoformat(),
                    })
                    position = None

            prev_dir = cur_dir

            # Mark to market equity curve
            cur_pnl = ((price * (1 - slippage_pct) - position["entry"]) * position["qty"] - commission * 2) if position else 0.0
            equity_curve.append({"date": ts.isoformat(), "equity": round(equity + cur_pnl, 2)})

        # Close lingering open position
        if position is not None and not df.empty:
            final_ts = df.index[-1].isoformat()
            final_price = float(df["Close"].iloc[-1])
            exit_p = final_price * (1 - slippage_pct)
            pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
            equity += pnl
            trades.append({
                "entry": position["entry"],
                "exit": exit_p,
                "pnl": pnl,
                "entry_date": position["entry_date"],
                "exit_date": final_ts,
            })
            if equity_curve:
                equity_curve[-1]["equity"] = round(equity, 2)

        metrics = BacktestEngine._compute_metrics(trades, equity_curve, capital)
        return {
            "symbol": symbol,
            "strategy": "supertrend_trend_rider",
            "params": params,
            "metrics": metrics,
            "trades": trades[-20:],
            "equity_curve": equity_curve,
        }

    @staticmethod
    def _smc_liquidity_fvg(df: pd.DataFrame, params: dict, capital: float, symbol: str, slippage_pct: float, commission: float) -> dict:
        """
        Smart Money Concepts (SMC) Institutional FVG Hunter.
        Identifies unmitigated Fair Value Gaps in established trends.
        Enters upon pullback into FVG zone with tight stop and asymmetric 2.5R target.
        """
        from ta.trend import EMAIndicator
        from ta.volatility import AverageTrueRange

        qty = int(params.get("quantity", 10))
        rr_multiplier = float(params.get("risk_reward", 2.5))
        min_gap_pct = float(params.get("gap_pct", 0.3))

        df["ema_50"] = EMAIndicator(df["Close"], window=min(50, max(10, len(df) // 4))).ema_indicator()
        df["ema_200"] = EMAIndicator(df["Close"], window=min(200, max(20, len(df) // 2))).ema_indicator()
        df["atr"] = AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14).average_true_range()
        df = df.dropna()

        trades, equity_curve = [], []
        position = None
        equity = capital
        active_fvgs = []

        for i in range(2, len(df)):
            ts = df.index[i]
            row = df.iloc[i]
            price = float(row["Close"])
            high_price = float(row["High"])
            low_price = float(row["Low"])
            ema_50 = float(row["ema_50"])
            ema_200 = float(row["ema_200"])

            # 1. Detect new Bullish FVG formed at i-1: candle[i-2].high < candle[i].low
            c1_high = float(df.iloc[i-2]["High"])
            c3_low = float(df.iloc[i]["Low"])
            c2_close = float(df.iloc[i-1]["Close"])
            if c2_close > 0 and c3_low > c1_high:
                gap_size = c3_low - c1_high
                gap_pct = (gap_size / c2_close) * 100.0
                if gap_pct >= min_gap_pct and ema_50 > ema_200:
                    active_fvgs.append({
                        "top": c3_low,
                        "bottom": c1_high,
                        "created_idx": i,
                    })

            # 2. Check position exits
            if position is not None:
                if high_price >= position["target"]:
                    exit_p = position["target"] * (1 - slippage_pct)
                    pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
                    equity += pnl
                    trades.append({
                        "entry": position["entry"],
                        "exit": exit_p,
                        "pnl": pnl,
                        "entry_date": position["entry_date"],
                        "exit_date": ts.isoformat(),
                        "outcome": "TARGET_HIT",
                    })
                    position = None
                elif low_price <= position["sl"]:
                    exit_p = position["sl"] * (1 - slippage_pct)
                    pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
                    equity += pnl
                    trades.append({
                        "entry": position["entry"],
                        "exit": exit_p,
                        "pnl": pnl,
                        "entry_date": position["entry_date"],
                        "exit_date": ts.isoformat(),
                        "outcome": "STOP_LOSS",
                    })
                    position = None

            # 3. Check entry into active FVG zone
            if position is None and active_fvgs:
                surviving_fvgs = []
                for fvg in active_fvgs:
                    if low_price <= fvg["top"] and low_price >= fvg["bottom"] and position is None:
                        entry = price * (1 + slippage_pct)
                        sl = fvg["bottom"] * 0.995
                        risk = entry - sl
                        if risk > 0:
                            target = entry + (rr_multiplier * risk)
                            position = {
                                "entry": entry,
                                "qty": qty,
                                "entry_date": ts.isoformat(),
                                "sl": sl,
                                "target": target,
                            }
                    elif low_price < fvg["bottom"]:
                        pass  # Invalidated/mitigated
                    else:
                        surviving_fvgs.append(fvg)
                active_fvgs = surviving_fvgs

            cur_pnl = ((price * (1 - slippage_pct) - position["entry"]) * position["qty"] - commission * 2) if position else 0.0
            equity_curve.append({"date": ts.isoformat(), "equity": round(equity + cur_pnl, 2)})

        # Close open position at end
        if position is not None and not df.empty:
            final_ts = df.index[-1].isoformat()
            final_price = float(df["Close"].iloc[-1])
            exit_p = final_price * (1 - slippage_pct)
            pnl = (exit_p - position["entry"]) * position["qty"] - commission * 2
            equity += pnl
            trades.append({
                "entry": position["entry"],
                "exit": exit_p,
                "pnl": pnl,
                "entry_date": position["entry_date"],
                "exit_date": final_ts,
            })
            if equity_curve:
                equity_curve[-1]["equity"] = round(equity, 2)

        metrics = BacktestEngine._compute_metrics(trades, equity_curve, capital)
        return {
            "symbol": symbol,
            "strategy": "smc_liquidity_fvg",
            "params": params,
            "metrics": metrics,
            "trades": trades[-20:],
            "equity_curve": equity_curve,
        }

backtest_engine = BacktestEngine()
