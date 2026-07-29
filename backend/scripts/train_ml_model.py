"""
Machine Learning Training Script (Phase 9)
Trains a LightGBM model to predict the 5-day forward return direction for Nifty 50 stocks.
Saves the trained model to backend/models/lgb_model.txt.
"""
import os
import asyncio
import pandas as pd
import numpy as np
import lightgbm as lgb
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands

from backend.services.market_data import market_data_service
from backend.data.ingestion.yfinance_ingestion import NSE_NIFTY50_SYMBOLS
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODEL_DIR, exist_ok=True)
MODEL_PATH = os.path.join(MODEL_DIR, "lgb_model.txt")

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Generate technical indicators using the 'ta' library."""
    df = df.copy()
    
    # RSI
    df['rsi_14'] = RSIIndicator(close=df['Close'], window=14).rsi()
    
    # MACD
    macd = MACD(close=df['Close'], window_slow=26, window_fast=12, window_sign=9)
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_hist'] = macd.macd_diff()
    
    # EMAs
    df['ema_9'] = EMAIndicator(close=df['Close'], window=9).ema_indicator()
    df['ema_21'] = EMAIndicator(close=df['Close'], window=21).ema_indicator()
    df['ema_50'] = EMAIndicator(close=df['Close'], window=50).ema_indicator()
    
    # Bollinger Bands
    bb = BollingerBands(close=df['Close'], window=20, window_dev=2)
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_lower']
    
    # ADX
    adx = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=14)
    df['adx_14'] = adx.adx()
    
    # Target: 5-day forward return direction (1 if up, 0 if down)
    df['fwd_return'] = df['Close'].shift(-5) / df['Close'] - 1
    df['target'] = (df['fwd_return'] > 0).astype(int)
    
    return df.dropna()

async def train_model():
    logger.info("Starting ML Training Pipeline (LightGBM)")
    all_data = []
    
    for symbol in NSE_NIFTY50_SYMBOLS[:10]: # Train on a subset for speed in MVP
        logger.info(f"Fetching data for {symbol}...")
        candles = await market_data_service.fetch_candles(symbol, "1d", start_date="2020-01-01", end_date="2024-01-01")
        if len(candles) < 100:
            continue
            
        df = pd.DataFrame(candles)
        df['Close'] = df['close']
        df['High'] = df['high']
        df['Low'] = df['low']
        
        df = engineer_features(df)
        all_data.append(df)
        
    if not all_data:
        logger.error("No data fetched. Aborting training.")
        return
        
    master_df = pd.concat(all_data, ignore_index=True)
    features = ['rsi_14', 'macd', 'macd_hist', 'ema_9', 'ema_21', 'ema_50', 'bb_width', 'adx_14']
    X = master_df[features]
    y = master_df['target']
    
    logger.info(f"Training on {len(X)} samples with {len(features)} features...")
    
    train_data = lgb.Dataset(X, label=y)
    params = {
        'objective': 'binary',
        'metric': 'binary_logloss',
        'boosting_type': 'gbdt',
        'learning_rate': 0.05,
        'num_leaves': 31,
        'verbose': -1
    }
    
    model = lgb.train(params, train_data, num_boost_round=100)
    model.save_model(MODEL_PATH)
    logger.info(f"Model saved successfully to {MODEL_PATH}")

if __name__ == "__main__":
    asyncio.run(train_model())
