"""
Temporal Transformer for Indian Stock Market Prediction.

Architecture:
  Input  : (batch, sequence=60, features=30)
  Embed  : Linear(30 → 64) + sinusoidal positional encoding
  Encoder: 4x TransformerEncoder layers (4 heads, FFN dim=256)
  Pool   : CLS token extraction
  Head   : Linear(64 → 32) → ReLU → Linear(32 → 3)
  Output : 3-class logits (0=SELL, 1=HOLD, 2=BUY)

Why Transformer:
  - Learns non-local temporal dependencies (e.g. monthly seasonal patterns)
  - Attention weights show which historical bars influenced the prediction
  - Complements LSTM which excels at local sequential patterns
"""

from __future__ import annotations

import os
import math
import logging
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    torch = None
    nn = None
    F = None
    HAS_TORCH = False

from backend.services.ml.feature_engineering import N_FEATURES, SEQUENCE_LENGTH

logger = logging.getLogger(__name__)

MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "models", "transformer_model.pt"
)

_ModuleBase = nn.Module if HAS_TORCH else object


class PositionalEncoding(_ModuleBase):
    """Standard sinusoidal positional encoding."""

    def __init__(self, d_model: int, max_len: int = 256, dropout: float = 0.1):
        if not HAS_TORCH:
            return
        super().__init__()

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # (1, max_len, d_model)
        self.register_buffer("pe", pe)
        self.dropout = nn.Dropout(p=dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, : x.size(1), :]
        return self.dropout(x)


class StockTransformer(_ModuleBase):
    """
    Transformer Encoder for 3-class stock direction prediction.
    Uses a learnable CLS token prepended to the sequence for classification.
    """

    def __init__(
        self,
        input_size: int = N_FEATURES,
        d_model: int = 64,
        nhead: int = 4,
        num_encoder_layers: int = 4,
        dim_feedforward: int = 256,
        dropout: float = 0.1,
        num_classes: int = 3,
    ):
        super().__init__()

        # Input projection to d_model
        self.input_proj = nn.Sequential(
            nn.Linear(input_size, d_model),
            nn.LayerNorm(d_model),
        )

        # Learnable CLS token (prepended; classification reads its final state)
        self.cls_token = nn.Parameter(torch.randn(1, 1, d_model))

        # Positional encoding
        self.pos_enc = PositionalEncoding(d_model, max_len=SEQUENCE_LENGTH + 1, dropout=dropout)

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
            norm_first=True,  # Pre-LN for better training stability
        )
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=num_encoder_layers
        )

        # Classification head (reads the CLS token)
        self.classifier = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Linear(d_model, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_size) float tensor
        Returns:
            logits: (batch, num_classes)
        """
        B = x.size(0)

        # Project input
        x = self.input_proj(x)                          # (B, T, d_model)

        # Prepend CLS token
        cls = self.cls_token.expand(B, -1, -1)          # (B, 1, d_model)
        x = torch.cat([cls, x], dim=1)                  # (B, T+1, d_model)

        # Add positional encoding
        x = self.pos_enc(x)

        # Transformer encoding
        x = self.transformer_encoder(x)                  # (B, T+1, d_model)

        # Extract CLS token for classification
        cls_out = x[:, 0, :]                             # (B, d_model)

        return self.classifier(cls_out)                  # (B, 3)


class TransformerPredictor:
    """
    Wrapper around StockTransformer for inference in the AI ensemble.
    """

    def __init__(self):
        self.model: StockTransformer | None = None
        self.device = torch.device("cpu") if HAS_TORCH else None
        if HAS_TORCH:
            self._load()

    def _load(self):
        """Load saved model weights if they exist."""
        if not HAS_TORCH or not os.path.exists(MODEL_PATH):
            logger.info("Transformer model not found or torch unavailable at %s.", MODEL_PATH)
            return
        try:
            state_dict = torch.load(MODEL_PATH, map_location=self.device, weights_only=True)
            self.model = StockTransformer()
            self.model.load_state_dict(state_dict)
            self.model.eval()
            logger.info("Transformer model loaded from %s", MODEL_PATH)
        except Exception as e:
            logger.warning("Transformer model weights mismatch or incompatible at %s (%s). Will reinitialize during training.", MODEL_PATH, e)
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
            logger.error("Transformer inference error: %s", e)
            return np.array([1 / 3, 1 / 3, 1 / 3], dtype=np.float32)

    def reload(self):
        """Hot-reload model from disk (called after training completes)."""
        self.model = None
        self._load()


# Singleton instance
transformer_predictor = TransformerPredictor()
