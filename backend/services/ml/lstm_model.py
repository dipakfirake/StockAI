"""
Bidirectional LSTM with Multi-Head Attention for Indian Stock Market Prediction.

Architecture:
  Input  : (batch, sequence=60, features=30)
  LSTM   : 3-layer Bidirectional LSTM, hidden=128, dropout=0.3
  Attention: Multi-head self-attention over LSTM outputs (4 heads)
  Head   : Linear(256 → 64) → ReLU → Dropout(0.2) → Linear(64 → 3)
  Output : 3-class logits (0=SELL, 1=HOLD, 2=BUY)

This model learns temporal patterns across 60 bars that LightGBM cannot:
  e.g., "RSI divergence over 3 days + volume spike → reversal"
"""

from __future__ import annotations

import os
import logging
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from backend.services.ml.feature_engineering import N_FEATURES, SEQUENCE_LENGTH

logger = logging.getLogger(__name__)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "models", "lstm_model.pt")


class BidirectionalLSTMModel(nn.Module):
    """
    3-layer Bidirectional LSTM with Multi-Head Self-Attention for 3-class stock prediction.
    """

    def __init__(
        self,
        input_size: int = N_FEATURES,
        hidden_size: int = 128,
        num_layers: int = 3,
        num_heads: int = 4,
        dropout: float = 0.3,
        num_classes: int = 3,
    ):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        # Input projection — normalises raw feature scale
        self.input_proj = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
        )

        # Bidirectional LSTM
        self.lstm = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        # Multi-head self-attention over the LSTM sequence
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_size * 2,  # bidirectional doubles hidden
            num_heads=num_heads,
            dropout=0.1,
            batch_first=True,
        )
        self.attn_norm = nn.LayerNorm(hidden_size * 2)

        # Classification head
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size * 2, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_size) float tensor
        Returns:
            logits: (batch, num_classes)
        """
        # Project to LSTM input size
        x = self.input_proj(x)                          # (B, T, H)

        # BiLSTM
        lstm_out, _ = self.lstm(x)                      # (B, T, 2H)

        # Self-attention
        attn_out, _ = self.attention(lstm_out, lstm_out, lstm_out)
        attn_out = self.attn_norm(lstm_out + attn_out)  # residual

        # Global average pooling over time
        pooled = attn_out.mean(dim=1)                   # (B, 2H)

        return self.classifier(pooled)                  # (B, 3)


class LSTMPredictor:
    """
    Wrapper around BidirectionalLSTMModel for inference in the AI engine.
    Handles model loading, device management, and probability computation.
    """

    def __init__(self):
        self.model: BidirectionalLSTMModel | None = None
        self.device = torch.device("cpu")
        self._load()

    def _load(self):
        """Load saved model weights if they exist."""
        if not os.path.exists(MODEL_PATH):
            logger.info("LSTM model not found at %s — will be trained first.", MODEL_PATH)
            return
        try:
            state_dict = torch.load(MODEL_PATH, map_location=self.device, weights_only=True)
            self.model = BidirectionalLSTMModel()
            self.model.load_state_dict(state_dict)
            self.model.eval()
            logger.info("LSTM model loaded from %s", MODEL_PATH)
        except Exception as e:
            logger.warning("LSTM model weights mismatch or incompatible at %s (%s). Will reinitialize during training.", MODEL_PATH, e)
            self.model = None

    def is_ready(self) -> bool:
        return self.model is not None

    def predict_proba(self, sequence: np.ndarray) -> np.ndarray:
        """
        Predict class probabilities for a single sequence.

        Args:
            sequence: (seq_len, n_features) float32 numpy array
        Returns:
            probs: (3,) probability array [sell, hold, buy]
        """
        if self.model is None:
            return np.array([1 / 3, 1 / 3, 1 / 3], dtype=np.float32)

        try:
            x = torch.tensor(sequence, dtype=torch.float32).unsqueeze(0)  # (1, T, F)
            with torch.no_grad():
                logits = self.model(x)
                probs = F.softmax(logits, dim=-1).squeeze(0).numpy()
            return probs
        except Exception as e:
            logger.error("LSTM inference error: %s", e)
            return np.array([1 / 3, 1 / 3, 1 / 3], dtype=np.float32)

    def reload(self):
        """Hot-reload model from disk (called after training completes)."""
        self.model = None
        self._load()


# Singleton instance
lstm_predictor = LSTMPredictor()
