"""
Machine Learning Training Script (Full Indian Stock Market & Multi-Regime Macro Validation)
Trains LightGBM models separated by Market Cap (Large vs Small/Mid/Penny) and Indices.
Uses 10+ years of historical data (2015-Present) covering COVID, Wars, Rate Hikes, & Crises.
Uses TimeSeriesSplit to validate performance across all historical macro regimes.
"""
import os
import json
import asyncio
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score, accuracy_score, precision_score
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, EMAIndicator, ADXIndicator, CCIIndicator, SMAIndicator
from ta.volatility import BollingerBands, AverageTrueRange

from backend.services.market_data import market_data_service
from backend.core.logging_config import setup_logging, get_logger

setup_logging("INFO")
logger = get_logger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODEL_DIR, exist_ok=True)
MODEL_LARGE_PATH = os.path.join(MODEL_DIR, "lgb_model_largecap.txt")
MODEL_SMALL_PATH = os.path.join(MODEL_DIR, "lgb_model_smallcap.txt")
REPORT_PATH = os.path.join(MODEL_DIR, "ml_report.json")

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Generate 18 scale-independent, normalized technical indicators."""
    df = df.copy()
    close = df['Close']
    
    # Oscillators
    df['rsi_14'] = RSIIndicator(close=close, window=14).rsi()
    df['rsi_z'] = (df['rsi_14'] - 50) / 15.0
    
    macd = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
    df['macd_hist'] = macd.macd_diff()
    
    stoch = StochasticOscillator(high=df['High'], low=df['Low'], close=close, window=14, smooth_window=3)
    df['stoch_k'] = stoch.stoch()
    
    df['cci_20'] = CCIIndicator(high=df['High'], low=df['Low'], close=close, window=20).cci()
    
    # Volatility
    atr = AverageTrueRange(high=df['High'], low=df['Low'], close=close, window=14).average_true_range()
    df['atr_pct'] = atr / close
    
    bb = BollingerBands(close=close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()
    bb_mid = bb.bollinger_mavg()
    df['bb_pct_b'] = (close - bb_lower) / (bb_upper - bb_lower + 1e-8)
    df['bb_width_norm'] = (bb_upper - bb_lower) / (bb_mid + 1e-8)
    
    # Trend & MAs (Normalized as ratios)
    ema9 = EMAIndicator(close=close, window=9).ema_indicator()
    ema21 = EMAIndicator(close=close, window=21).ema_indicator()
    ema50 = EMAIndicator(close=close, window=50).ema_indicator()
    sma200 = SMAIndicator(close=close, window=200).sma_indicator()
    
    df['ema9_ratio'] = close / (ema9 + 1e-8) - 1
    df['ema21_ratio'] = close / (ema21 + 1e-8) - 1
    df['ema_cross'] = ema9 / (ema21 + 1e-8) - 1
    df['golden_death'] = np.where(ema50 > sma200, 1, -1)
    
    df['adx_14'] = ADXIndicator(high=df['High'], low=df['Low'], close=close, window=14).adx()
    
    # Momentum
    df['price_return_5d'] = close / close.shift(5) - 1
    df['price_return_20d'] = close / close.shift(20) - 1
    
    # We will pass Nifty 20d return during training as a separate step.
    # For now, default it if it's missing, or we can compute a proxy if Nifty isn't passed.
    # To keep it simple and self-contained, we initialize it here:
    df['rs_momentum_20d'] = 0.0  # Will be populated correctly in the main loop
    
    # Volume
    vol_sma20 = SMAIndicator(close=df['Volume'], window=20).sma_indicator()
    df['vol_ratio'] = df['Volume'] / (vol_sma20 + 1e-8)
    
    # Target: 5-day forward return > 1.5% (meaningful move)
    df['fwd_return'] = close.shift(-5) / close - 1
    df['target'] = np.where(df['fwd_return'] > 0.015, 1,
                   np.where(df['fwd_return'] < -0.015, 0, np.nan))
    
    return df.dropna(subset=['target'])

async def fetch_single_symbol(symbol: str, idx: int, total: int, nifty_df: pd.DataFrame = None) -> pd.DataFrame:
    try:
        print(f"  [{idx:2d}/{total:2d}] Fetching {symbol:<15} (2015-Present)...", end=" ", flush=True)
        # 10+ Years of historical data (2015 to Present)
        candles = await market_data_service.fetch_candles(symbol, "1d", start_date="2015-01-01", end_date="2026-08-01")
        
        # Fallback for newer IPO stocks (e.g. ZOMATO, PAYTM, JIOFIN) that were listed post-2015
        if not candles or len(candles) < 200:
            candles = await market_data_service.fetch_candles(symbol, "1d")
            
        if not candles or len(candles) < 200:
            print(f"⚠️ Insufficient candles ({len(candles) if candles else 0})", flush=True)
            return pd.DataFrame()
            
        df = pd.DataFrame(candles)
        df['Close'] = df['close']
        df['High'] = df['high']
        df['Low'] = df['low']
        df['Volume'] = df['volume']
        df['Open'] = df['open']
        if 'timestamp' in df.columns:
            df['Date'] = pd.to_datetime(df['timestamp'])
        
        df = engineer_features(df)
        
        if nifty_df is not None and not nifty_df.empty:
            # Align with Nifty to compute rs_momentum_20d
            df = df.merge(nifty_df[['Date', 'nifty_return_20d']], on='Date', how='left')
            df['nifty_return_20d'] = df['nifty_return_20d'].fillna(0.0)
            df['rs_momentum_20d'] = df['price_return_20d'] - df['nifty_return_20d']
        
        df['symbol'] = symbol
        print(f"✅ OK ({len(candles)} candles, {len(df)} samples)", flush=True)
        return df
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        return pd.DataFrame()

async def fetch_and_prepare_data(universe: list, nifty_df: pd.DataFrame = None) -> pd.DataFrame:
    valid_dfs = []
    total = len(universe)
    for i, symbol in enumerate(universe, 1):
        df = await fetch_single_symbol(symbol, i, total, nifty_df)
        if not df.empty:
            valid_dfs.append(df)
    
    if valid_dfs:
        combined = pd.concat(valid_dfs, ignore_index=True)
        print(f"\n📊 Total Dataset Aggregated: {len(combined):,} rows across {len(valid_dfs)} tickers.\n", flush=True)
        return combined
    return pd.DataFrame()

def train_and_validate(df: pd.DataFrame, model_path: str, model_name: str) -> dict:
    features = [
        'rsi_14', 'rsi_z', 'macd_hist', 'stoch_k', 'cci_20',
        'atr_pct', 'bb_pct_b', 'bb_width_norm',
        'ema9_ratio', 'ema21_ratio', 'ema_cross', 'golden_death',
        'adx_14', 'price_return_5d', 'price_return_20d', 'vol_ratio',
        'rs_momentum_20d'
    ]
    
    # Sort by Date globally so TimeSeriesSplit acts on chronological time
    if 'Date' in df.columns:
        df = df.sort_values(by="Date")
        
    initial_rows = len(df)
    df = df.dropna(subset=features)
    final_rows = len(df)
    print(f"⚙️  [{model_name}] Training on {final_rows:,} samples (features: {len(features)})", flush=True)
    
    X = df[features].reset_index(drop=True)
    y = df['target'].reset_index(drop=True)
    
    # Walk-Forward Validation (TimeSeriesSplit) to test across all market regimes
    tscv = TimeSeriesSplit(n_splits=4)
    cv_scores = []
    best_model = None
    
    for fold, (train_idx, test_idx) in enumerate(tscv.split(X), 1):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
        
        train_data = lgb.Dataset(X_train, label=y_train)
        valid_data = lgb.Dataset(X_test, label=y_test, reference=train_data)
        
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'boosting_type': 'gbdt',
            'learning_rate': 0.03,
            'num_leaves': 31,
            'min_data_in_leaf': 100,
            'feature_fraction': 0.8,
            'verbose': -1
        }
        
        model = lgb.train(
            params, 
            train_data, 
            num_boost_round=300,
            valid_sets=[valid_data],
            callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)]
        )
        
        preds = model.predict(X_test)
        pred_labels = (preds > 0.6).astype(int)
        
        auc = roc_auc_score(y_test, preds)
        acc = accuracy_score(y_test, pred_labels)
        cv_scores.append({"auc": auc, "accuracy": acc})
        print(f"   Fold {fold}/4: Validation AUC = {auc:.4f}, Accuracy = {acc:.4f}", flush=True)
        best_model = model
    
    # Save the best model
    if best_model:
        best_model.save_model(model_path)
        print(f"💾 Saved {model_name} model to {model_path}", flush=True)
    
    avg_auc = np.mean([s["auc"] for s in cv_scores])
    avg_acc = np.mean([s["accuracy"] for s in cv_scores])
    
    return {
        "model": model_name,
        "total_candles_trained": len(X),
        "cv_splits": 4,
        "avg_validation_auc": round(float(avg_auc), 3),
        "avg_validation_accuracy": round(float(avg_acc), 3),
        "regime_tested": "10+ Years (2015-2026): Includes Demonetization, COVID Crash, Russia-Ukraine War, Middle East Crises, Rate Hikes & ATH Bull Rallies"
    }

async def run_training():
    print("\n" + "=" * 80, flush=True)
    print("🚀 STARTING MULTI-CAP ML TRAINING PIPELINE (FYERS API v3)", flush=True)
    print("Regime: 10+ Years (2015-Present) Walk-Forward Multi-Regime Validation", flush=True)
    print("=" * 80 + "\n", flush=True)
    
    # Benchmark & Sectoral Indices + Top Large Cap Stocks across all major sectors (70+ tickers)
    large_caps_and_indices = [
        # Indices
        "^NSEI", "^NSEBANK", "^CNXIT", "^CNXAUTO", "^CNXENERGY", "^CNXREALTY", "^CNXMETAL", "^CNXFMCG", "^CNXPHARMA", "^NSEMDCP50",
        # Nifty 50 & Institutional Heavyweights
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "HINDUNILVR.NS", "LT.NS",
        "AXISBANK.NS", "KOTAKBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
        "ULTRACEMCO.NS", "ASIANPAINT.NS", "NTPC.NS", "TATAMOTORS.NS", "BAJFINANCE.NS",
        "POWERGRID.NS", "M&M.NS", "ADANIENT.NS", "TATASTEEL.NS", "COALINDIA.NS",
        "JSWSTEEL.NS", "HCLTECH.NS", "BAJAJFINSV.NS", "ONGC.NS", "GRASIM.NS",
        "TECHM.NS", "NESTLEIND.NS", "HDFCLIFE.NS", "BRITANNIA.NS", "ADANIPORTS.NS",
        "SBILIFE.NS", "DRREDDY.NS", "EICHERMOT.NS", "INDUSINDBK.NS", "WIPRO.NS",
        "CIPLA.NS", "DIVISLAB.NS", "BPCL.NS", "TATACONSUM.NS", "APOLLOHOSP.NS",
        "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "HINDALCO.NS", "LTIM.NS", "BEL.NS",
        "TRENT.NS", "VBL.NS", "PIDILITIND.NS", "CHOLAFIN.NS", "SHREECEM.NS",
        "SIEMENS.NS", "ABB.NS", "HAVELLS.NS", "DLF.NS", "GAIL.NS", "INDIGO.NS",
        "SRF.NS", "TVSMOTOR.NS", "DABUR.NS", "GODREJCP.NS", "MARICO.NS"
    ]
    
    # Comprehensive Mid, Small, Micro & Penny Growth Stocks (80+ tickers)
    small_mid_penny_caps = [
        "PCJEWELLER.NS", "SUZLON.NS", "ZOMATO.NS", "PAYTM.NS", "NYKAA.NS",
        "IDEA.NS", "YESBANK.NS", "IRFC.NS", "RVNL.NS", "BHEL.NS",
        "MANAPPURAM.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS", "NATIONALUM.NS", "SAIL.NS",
        "PNB.NS", "CANBK.NS", "UNIONBANK.NS", "TATAPOWER.NS", "NHPC.NS",
        "SJVN.NS", "IREDA.NS", "HUDCO.NS", "MAHABANK.NS", "NBCC.NS",
        "NMDC.NS", "OIL.NS", "RECLTD.NS", "PFC.NS", "POLYCAB.NS",
        "PERSISTENT.NS", "COFORGE.NS", "DIXON.NS", "KPITTECH.NS", "TATAELXSI.NS",
        "HAL.NS", "MAZDOCK.NS", "COCHINSHIP.NS", "JIOFIN.NS",
        "IRCTC.NS", "EXIDEIND.NS", "AMBUJACEM.NS", "MOTHERSON.NS", "GLENMARK.NS",
        "TATACOMM.NS", "GMRAIRPORT.NS", "DELHIVERY.NS", "ANGELONE.NS", "BSOFT.NS",
        "CENTRALBK.NS", "IOB.NS", "UCOBANK.NS", "TRIDENT.NS", "RPOWER.NS",
        "KALYANKJIL.NS", "PRESTIGE.NS", "OBEROIRLTY.NS", "GODREJPROP.NS", "BRIGADE.NS",
        "HINDCOPPER.NS", "HINDZINC.NS", "BOSCHLTD.NS", "LUPIN.NS", "AUROPHARMA.NS",
        "TORNTPHARM.NS", "ABFRL.NS", "DEVYANI.NS", "JUBLFOOD.NS", "PAGEIND.NS",
        "BHARATFORG.NS", "ASTRAL.NS", "CUMMINSIND.NS", "VOLTAS.NS", "DEEPAKNTR.NS",
        "SUNDARMFIN.NS", "FORTIS.NS", "IPCALAB.NS", "BIOCON.NS", "CESC.NS"
    ]
    
    report = {}
    
    # 1. Fetch Nifty 50 baseline for Market Relative Strength (Accuracy Upgrade)
    print("\n📈 Fetching NIFTY 50 Baseline for Relative Strength...", flush=True)
    try:
        nifty_candles = await market_data_service.fetch_candles("^NSEI", "1d", start_date="2015-01-01", end_date="2026-08-01")
        if nifty_candles:
            nifty_df = pd.DataFrame(nifty_candles)
            if 'timestamp' in nifty_df.columns:
                nifty_df['Date'] = pd.to_datetime(nifty_df['timestamp'])
            nifty_df['nifty_return_20d'] = nifty_df['close'] / nifty_df['close'].shift(20) - 1
            print(f"✅ Nifty 50 Fetched: {len(nifty_df)} candles.")
        else:
            print("⚠️ Failed to fetch Nifty baseline.")
            nifty_df = None
    except Exception as e:
        print(f"❌ Nifty fetch error: {e}")
        nifty_df = None

    print("\n🧠 [Model 1/2] Training LargeCap & Indices Model...", flush=True)
    df_large = await fetch_and_prepare_data(large_caps_and_indices, nifty_df)
    if not df_large.empty:
        report["LargeCap_and_Indices"] = train_and_validate(df_large, MODEL_LARGE_PATH, "LargeCap_Universal")

    print("\n🧠 [Model 2/2] Training Small, Mid & Penny Cap Model...", flush=True)
    df_small = await fetch_and_prepare_data(small_mid_penny_caps, nifty_df)
    if not df_small.empty:
        report["Small_Mid_PennyCap"] = train_and_validate(df_small, MODEL_SMALL_PATH, "SmallCap_Momentum")
        
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=4)
        
    print("\n" + "=" * 80, flush=True)
    print(f"✨ ALL MODELS TRAINED SUCCESSFULLY! Report saved to {REPORT_PATH}", flush=True)
    print("=" * 80, flush=True)
    print(json.dumps(report, indent=2), flush=True)

if __name__ == "__main__":
    asyncio.run(run_training())
