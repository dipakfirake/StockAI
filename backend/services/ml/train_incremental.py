"""
Universal Industrial Deep Learning Incremental Training Pipeline (CPU-Optimized).

Features:
- Stratified 90-Stock Cross-Cap Universe:
    * 30 Large Caps (Nifty 50)
    * 30 Mid Caps (Nifty Midcap 150)
    * 30 Small & High-Beta Caps (Nifty Smallcap 250)
  Directly exposed to:
    * Crude Oil Shocks (ONGC, BPCL vs Asian Paints, Indigo)
    * Geopolitical Wars & Defense (BEL, HAL, Mazagon Dock)
    * Global Inflation & Commodities (Tata Steel, JSW Steel, Vedanta, Hindalco)
    * High-Growth Domestic Retail Catalysts (Trent, Titan, Zomato, D-Mart)
    * Capital Market Momentum (CDSL, BSE, Angel One)
- Multi-Regime 5-Year History (2019-2024+):
    * COVID-19 crash & negative oil shock (March 2020)
    * Post-COVID small-cap expansion rally (2020-2021)
    * Russia-Ukraine war & $130 crude oil surge (2022)
    * Global 40-year peak inflation & rate-hike tech drawdown (2022)
    * Middle East geopolitical escalations (2023)
    * 2024 General Election volatility shock & recovery to ATH
- Scale-Invariant Feature Architecture: 36 normalized technical & macro features
- Dynamic Volatility-Adaptive Target Labeling (Triple Barrier calibrated by ATR)
- Asymmetric Crash-Penalty Focal Loss (penalizes false BUYs during drawdowns 2.5x)
- Chunked memory management with explicit gc.collect() and safe checkpointing
"""

import os
import sys
import gc
import json
import time
import random
import logging
import yfinance as yf
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

# Ensure the root app directory is in the path for absolute imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from backend.services.ml.lstm_model import BidirectionalLSTMModel, MODEL_PATH as LSTM_PATH
from backend.services.ml.transformer_model import StockTransformer, MODEL_PATH as TF_PATH
from backend.services.ml.feature_engineering import (
    engineer_features,
    compute_target_volatility_adaptive,
    SEQUENCE_LENGTH,
    N_FEATURES,
    FEATURE_NAMES,
)
from backend.services.ml.losses import AsymmetricCrashFocalLoss

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEVICE = torch.device("cpu")
BATCH_SIZE = 64
EPOCHS_PER_SUBSET = 8
SUBSET_SIZE = 10  # 10 stocks per training chunk for bounded CPU memory usage
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "models", "dl_training_report.json")

# ─────────────────────────────────────────────────────────────────────────────
# Stratified 90-Stock Cross-Cap Universe across all Market Regimes
# ─────────────────────────────────────────────────────────────────────────────
STRATIFIED_UNIVERSE = [
    # ── Tier 1: Large Caps (Nifty 50 Institutional Baseline - 30 stocks) ──────
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "SBIN.NS", "BAJFINANCE.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "ITC.NS", "LT.NS", "MARUTI.NS", "SUNPHARMA.NS", "ULTRACEMCO.NS",
    "WIPRO.NS", "NTPC.NS", "POWERGRID.NS", "TECHM.NS", "HCLTECH.NS",
    "M&M.NS", "ADANIENT.NS", "ADANIPORTS.NS", "GRASIM.NS", "BRITANNIA.NS",
    "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS", "EICHERMOT.NS", "TATACONSUM.NS",

    # ── Tier 2: Mid Caps (Nifty Midcap 150 Growth & Cyclicals - 30 stocks) ───
    "TRENT.NS", "DIXON.NS", "POLYCAB.NS", "PERSISTENT.NS", "CUMMINSIND.NS",
    "FEDERALBNK.NS", "ASTRAL.NS", "VOLTAS.NS", "ASHOKLEY.NS", "INDHOTEL.NS",
    "BHARATFORG.NS", "COFORGE.NS", "SUPREMEIND.NS", "TATACOMM.NS", "GODREJPROP.NS",
    "OBEROIRLTY.NS", "AUROPHARMA.NS", "LUPIN.NS", "BALKRISIND.NS", "COLPAL.NS",
    "MPHASIS.NS", "MAXHEALTH.NS", "ABCAPITAL.NS", "DALBHARAT.NS", "PIIND.NS",
    "PAGEIND.NS", "JUBLFOOD.NS", "TORNTPOWER.NS", "APOLLOTYRE.NS", "IDFCFIRSTB.NS",

    # ── Tier 3: Small & High-Beta Caps (Nifty Smallcap 250 - 30 stocks) ──────
    "CDSL.NS", "BSE.NS", "ANGELONE.NS", "KAYNES.NS", "SUZLON.NS",
    "KEI.NS", "GRANULES.NS", "KTKBANK.NS", "CASTROLIND.NS", "MOTILALOFS.NS",
    "SONATSOFTW.NS", "REDINGTON.NS", "AMBER.NS", "CENTURYPLY.NS", "CAMS.NS",
    "RBLBANK.NS", "ECLERX.NS", "RADICO.NS", "BSOFT.NS", "CYIENT.NS",
    # Macro Geopolitical & Oil Shock Constraints Bellwethers:
    "ONGC.NS", "BPCL.NS", "IOC.NS",          # Oil shock gainers
    "ASIANPAINT.NS", "BERGEPAINT.NS", "INDIGO.NS", # Oil shock margin-squeezed
    "BEL.NS", "HAL.NS",                       # Geopolitical defense & capex
    "TATASTEEL.NS", "JSWSTEEL.NS",           # Global inflation & commodity cycles
]

# De-duplicate while preserving order
ALL_STOCKS = list(dict.fromkeys(STRATIFIED_UNIVERSE))


class StockSequenceDataset(Dataset):
    def __init__(self, sequences: np.ndarray, labels: np.ndarray, fwd_returns: np.ndarray):
        self.sequences = torch.tensor(sequences, dtype=torch.float32)
        self.labels = torch.tensor(labels, dtype=torch.long)
        self.fwd_returns = torch.tensor(fwd_returns, dtype=torch.float32)

    def __len__(self):
        return len(self.sequences)

    def __getitem__(self, idx):
        return self.sequences[idx], self.labels[idx], self.fwd_returns[idx]


def download_5y_ohlcv(sym: str) -> pd.DataFrame:
    """Download 5-year OHLCV using direct Yahoo Chart API with browser User-Agent fallback."""
    import requests
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5y"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("chart", {}).get("result", [])
            if result:
                item = result[0]
                timestamps = item.get("timestamp", [])
                indicators = item.get("indicators", {}).get("quote", [{}])[0]
                opens = indicators.get("open", [])
                highs = indicators.get("high", [])
                lows = indicators.get("low", [])
                closes = indicators.get("close", [])
                volumes = indicators.get("volume", [])

                if timestamps and closes:
                    dates = pd.to_datetime(timestamps, unit="s")
                    df = pd.DataFrame({
                        "Open": opens,
                        "High": highs,
                        "Low": lows,
                        "Close": closes,
                        "Volume": volumes,
                    }, index=dates).dropna()
                    if not df.empty:
                        return df
    except Exception as e:
        logger.debug(f"Direct chart API for {sym} failed: {e}")

    try:
        session = requests.Session()
        session.headers.update(headers)
        ticker = yf.Ticker(sym, session=session)
        df = ticker.history(period="5y", interval="1d", auto_adjust=True)
        if not df.empty:
            return df
    except Exception:
        pass

    return pd.DataFrame()


def fetch_and_prepare_data(symbols: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Download 5-year OHLCV for symbols, compute scale-invariant features,
    and build volatility-adaptive 3-class sequence tensors.
    """
    all_sequences = []
    all_labels = []
    all_fwd_returns = []

    for sym in symbols:
        try:
            logger.info(f"Downloading 5y data for {sym}...")
            df = download_5y_ohlcv(sym)
            if df.empty or len(df) < (SEQUENCE_LENGTH + 40):
                logger.warning(f"Insufficient history for {sym} ({len(df)} bars). Skipping.")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)

            # 1. Feature Engineering with all 36 scale-invariant features
            df = engineer_features(df)

            # 2. Dynamic Volatility-Adaptive Target Labeling (ATR Triple Barrier)
            df = compute_target_volatility_adaptive(df, horizon=10, k_atr=1.75)

            # Extract features and targets
            valid_cols = [c for c in FEATURE_NAMES if c in df.columns]
            if len(valid_cols) != N_FEATURES:
                logger.warning(f"{sym} missing features: found {len(valid_cols)}/{N_FEATURES}. Skipping.")
                continue

            df_clean = df[valid_cols + ["target", "fwd_return"]].dropna()
            n = len(df_clean)
            if n < SEQUENCE_LENGTH + 1:
                continue

            feat_arr = df_clean[valid_cols].values.astype(np.float32)
            target_arr = df_clean["target"].values.astype(np.int64)
            fwd_arr = df_clean["fwd_return"].values.astype(np.float32)

            # Defensive clipping against extreme black swan spikes
            feat_arr = np.clip(feat_arr, -10.0, 10.0)
            feat_arr = np.nan_to_num(feat_arr, nan=0.0, posinf=10.0, neginf=-10.0)

            for i in range(SEQUENCE_LENGTH, n):
                seq = feat_arr[i - SEQUENCE_LENGTH:i]
                label = target_arr[i]
                fwd_ret = fwd_arr[i]

                if not np.isnan(seq).any() and not np.isinf(seq).any():
                    all_sequences.append(seq)
                    all_labels.append(label)
                    all_fwd_returns.append(fwd_ret)

        except Exception as e:
            logger.error(f"Error processing {sym}: {e}")

    if not all_sequences:
        return np.array([]), np.array([]), np.array([])

    return np.array(all_sequences, dtype=np.float32), np.array(all_labels, dtype=np.int64), np.array(all_fwd_returns, dtype=np.float32)


def train_model(
    model: nn.Module,
    dataloader: DataLoader,
    model_name: str,
    model_path: str,
    epochs: int = EPOCHS_PER_SUBSET,
) -> tuple[float, float]:
    """Train model on dataloader using Asymmetric Crash Focal Loss."""
    optimizer = optim.AdamW(model.parameters(), lr=1.5e-4, weight_decay=1e-4)
    criterion = AsymmetricCrashFocalLoss(gamma=2.0, crash_penalty_weight=2.5)

    final_loss = 0.0
    final_acc = 0.0

    model.train()
    for epoch in range(epochs):
        total_loss = 0.0
        correct = 0
        total = 0

        for inputs, targets, fwd_rets in dataloader:
            inputs, targets, fwd_rets = inputs.to(DEVICE), targets.to(DEVICE), fwd_rets.to(DEVICE)

            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, targets, fwd_returns=fwd_rets)
            loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            total_loss += loss.item()
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()

        final_acc = 100.0 * correct / max(total, 1)
        final_loss = total_loss / max(len(dataloader), 1)
        logger.info(f"{model_name} | Epoch [{epoch+1}/{epochs}] | Loss: {final_loss:.4f} | Acc: {final_acc:.2f}%")

    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    torch.save(model.state_dict(), model_path)
    logger.info(f"Saved {model_name} checkpoint to {model_path}")
    return final_loss, final_acc


def main():
    logger.info("=" * 60)
    logger.info("Starting Universal Industrial Deep Learning Training Pipeline")
    logger.info(f"Target Universe: {len(ALL_STOCKS)} Stratified Cross-Cap Stocks across 5 Years")
    logger.info(f"Features: {N_FEATURES} Scale-Invariant Features | Device: {DEVICE}")
    logger.info("=" * 60)

    stocks_to_train = ALL_STOCKS.copy()
    random.seed(42)
    random.shuffle(stocks_to_train)
    subsets = [stocks_to_train[i:i + SUBSET_SIZE] for i in range(0, len(stocks_to_train), SUBSET_SIZE)]

    lstm = BidirectionalLSTMModel(input_size=N_FEATURES).to(DEVICE)
    transformer = StockTransformer(input_size=N_FEATURES).to(DEVICE)

    # Safe resume check: Verify if existing weights match the 36-feature architecture
    if os.path.exists(LSTM_PATH):
        try:
            state = torch.load(LSTM_PATH, weights_only=True)
            lstm.load_state_dict(state)
            logger.info(f"Resumed existing LSTM model from {LSTM_PATH}")
        except Exception as ex:
            logger.warning(f"Initializing fresh BiLSTM with {N_FEATURES} features (previous was {ex})")

    if os.path.exists(TF_PATH):
        try:
            state = torch.load(TF_PATH, weights_only=True)
            transformer.load_state_dict(state)
            logger.info(f"Resumed existing Transformer model from {TF_PATH}")
        except Exception as ex:
            logger.warning(f"Initializing fresh StockTransformer with {N_FEATURES} features (previous was {ex})")

    metrics_log = []
    total_sequences_trained = 0
    start_subset_idx = 0

    if os.path.exists(REPORT_PATH):
        try:
            with open(REPORT_PATH, "r") as f:
                prev_report = json.load(f)
            if prev_report.get("n_features") == N_FEATURES:
                start_subset_idx = prev_report.get("subsets_completed", 0)
                metrics_log = prev_report.get("metrics", [])
                total_sequences_trained = prev_report.get("total_sequences", 0)
                if start_subset_idx >= len(subsets):
                    logger.info(f"All {len(subsets)} subsets already trained to completion! Models are fully trained.")
                    return
                logger.info(f"Resuming incremental training from subset {start_subset_idx + 1}/{len(subsets)} (cumulative {total_sequences_trained} sequences).")
        except Exception as e:
            logger.warning(f"Could not load previous training report: {e}")

    for i in range(start_subset_idx, len(subsets)):
        subset = subsets[i]
        logger.info(f"\n{'='*50}\nTraining Subset {i+1}/{len(subsets)}: {len(subset)} stocks\n{'='*50}")
        X, y, fwd_returns = fetch_and_prepare_data(subset)
        if len(X) == 0:
            logger.warning("No valid sequences for this subset. Skipping.")
            continue

        total_sequences_trained += len(X)
        logger.info(f"Prepared {len(X)} sequences. Cumulative: {total_sequences_trained}")

        dataset = StockSequenceDataset(X, y, fwd_returns)
        dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, drop_last=True)

        logger.info("Training BiLSTM with Asymmetric Crash Focal Loss...")
        lstm_loss, lstm_acc = train_model(lstm, dataloader, "BiLSTM", LSTM_PATH)

        logger.info("Training StockTransformer with Asymmetric Crash Focal Loss...")
        tf_loss, tf_acc = train_model(transformer, dataloader, "Transformer", TF_PATH)

        metrics_log.append({
            "subset_index": i + 1,
            "stocks": subset,
            "sequences": len(X),
            "lstm_loss": round(lstm_loss, 4),
            "lstm_acc": round(lstm_acc, 2),
            "transformer_loss": round(tf_loss, 4),
            "transformer_acc": round(tf_acc, 2),
            "timestamp": time.time(),
        })

        # Save cumulative training report
        with open(REPORT_PATH, "w") as f:
            json.dump({
                "n_features": N_FEATURES,
                "total_sequences": total_sequences_trained,
                "subsets_completed": i + 1,
                "total_subsets": len(subsets),
                "metrics": metrics_log,
            }, f, indent=2)

        # Explicit garbage collection to maintain lean memory footprint on CPU
        del X, y, fwd_returns, dataset, dataloader
        gc.collect()

    logger.info("\n" + "=" * 60)
    logger.info("Universal Industrial Deep Learning Training Complete!")
    logger.info(f"Total Sequences Processed: {total_sequences_trained}")
    logger.info(f"Models saved: {LSTM_PATH} and {TF_PATH}")
    logger.info(f"Report saved: {REPORT_PATH}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
