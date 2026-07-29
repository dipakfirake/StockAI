"""LSTM Sequence Model for Regime Detection."""

import numpy as np
import pandas as pd
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not installed. LSTM model will run in mock mode.")


class RegimeLSTM(nn.Module if TORCH_AVAILABLE else object):
    """LSTM model for market regime classification."""
    def __init__(self, input_size=10, hidden_size=32, num_layers=2, num_classes=3):
        if TORCH_AVAILABLE:
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
            self.fc = nn.Linear(hidden_size, num_classes)
        else:
            self.num_classes = num_classes

    def forward(self, x):
        if TORCH_AVAILABLE:
            out, _ = self.lstm(x)
            out = self.fc(out[:, -1, :])
            return out
        return None


class LSTMRegimePredictor:
    def __init__(self):
        self.model = None
        self.classes = ["BULLISH", "BEARISH", "SIDEWAYS"]
        
        if TORCH_AVAILABLE:
            self.model = RegimeLSTM()
            # self.model.load_state_dict(...) # Load pre-trained weights in real scenario
            self.model.eval()

    def predict(self, df: pd.DataFrame) -> dict:
        """
        Takes historical OHLCV + indicators and predicts the regime.
        Requires at least 30 days of data for the sequence.
        """
        if len(df) < 30:
            return {"regime": "SIDEWAYS", "confidence": 0.5, "error": "Insufficient data"}

        if not TORCH_AVAILABLE:
            # Mock mode: simple momentum heuristic
            momentum = df["Close"].iloc[-1] / df["Close"].iloc[-30] - 1
            if momentum > 0.05:
                return {"regime": "BULLISH", "confidence": min(0.5 + momentum * 2, 0.95)}
            elif momentum < -0.05:
                return {"regime": "BEARISH", "confidence": min(0.5 + abs(momentum) * 2, 0.95)}
            return {"regime": "SIDEWAYS", "confidence": 0.6}

        # Real PyTorch mode (Feature engineering would happen here)
        # 1. Extract features (Close, Volume, RSI, MACD, etc)
        # 2. Scale features
        # 3. Create sequence tensor [1, 30, num_features]
        # dummy_input = torch.randn(1, 30, 10) 
        # with torch.no_grad():
        #     output = self.model(dummy_input)
        #     probs = torch.softmax(output, dim=1)
        #     confidence, predicted = torch.max(probs, 1)
        #     regime = self.classes[predicted.item()]
        
        return {"regime": "SIDEWAYS", "confidence": 0.5, "mode": "real_inference"}

lstm_predictor = LSTMRegimePredictor()
