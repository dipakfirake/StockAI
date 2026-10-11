"""
Asymmetric Crash-Penalty Focal Loss for Financial Directional Classification.

Features:
- Class-weighted Focal Loss to address class imbalance (BUY / HOLD / SELL).
- Downside Crash Penalty: Asymmetric loss that heavily penalizes false BUY
  predictions when the actual market move is a sharp drop/crash.
  In financial trading: a missed opportunity (buying when it stays flat) is a minor error,
  but buying right before a -5% or -10% plunge is catastrophic.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class AsymmetricCrashFocalLoss(nn.Module):
    """
    Focal Loss with Asymmetric Downside Crash Penalty.

    Args:
        gamma: Focusing parameter for modulating factor (1 - p_t)^gamma. Default 2.0.
        alpha: Class weights tensor [w_sell, w_hold, w_buy]. Default None (balanced).
        crash_penalty_weight: Multiplier for penalizing false BUY predictions on SELL samples.
    """

    def __init__(
        self,
        gamma: float = 2.0,
        alpha: torch.Tensor | list[float] | None = None,
        crash_penalty_weight: float = 2.5,
    ):
        super().__init__()
        self.gamma = gamma
        self.crash_penalty_weight = crash_penalty_weight

        if alpha is not None:
            if not isinstance(alpha, torch.Tensor):
                alpha = torch.tensor(alpha, dtype=torch.float32)
            self.register_buffer("alpha", alpha)
        else:
            self.alpha = None

    def forward(
        self,
        logits: torch.Tensor,
        targets: torch.Tensor,
        fwd_returns: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """
        Args:
            logits: (batch, num_classes=3) raw unnormalized scores
            targets: (batch,) integer class labels (0=SELL, 1=HOLD, 2=BUY)
            fwd_returns: optional (batch,) float tensor of forward returns
                         for amplifying penalty based on drop magnitude.
        """
        num_classes = logits.size(-1)
        probs = F.softmax(logits, dim=-1)
        log_probs = F.log_softmax(logits, dim=-1)

        # Gather probability of true class
        target_one_hot = F.one_hot(targets, num_classes=num_classes).float()
        p_t = (probs * target_one_hot).sum(dim=-1)
        log_p_t = (log_probs * target_one_hot).sum(dim=-1)

        # Standard Focal Loss term
        focal_weight = (1.0 - p_t).clamp(min=0.0).pow(self.gamma)
        if self.alpha is not None:
            alpha_t = (self.alpha.to(logits.device) * target_one_hot).sum(dim=-1)
            loss = -alpha_t * focal_weight * log_p_t
        else:
            loss = -focal_weight * log_p_t

        # ── Asymmetric Downside Crash Penalty ──────────────────────────────────
        # Identify catastrophic errors: Actual is SELL (class 0), but model predicts high BUY (class 2) prob.
        is_sell_sample = (targets == 0).float()
        buy_prob = probs[:, 2]  # Probability assigned to BUY

        if fwd_returns is not None:
            # Scale penalty with drop severity (e.g. -10% drop gets higher penalty than -2% drop)
            drop_severity = fwd_returns.abs().clamp(min=0.02, max=0.20)
            crash_penalty = self.crash_penalty_weight * is_sell_sample * buy_prob * (drop_severity / 0.04)
        else:
            crash_penalty = self.crash_penalty_weight * is_sell_sample * buy_prob.pow(2)

        total_loss = loss + crash_penalty
        return total_loss.mean()
