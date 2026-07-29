"""Probability Calibration for Machine Learning Models."""

import numpy as np
from sklearn.isotonic import IsotonicRegression
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

class ProbabilityCalibrator:
    def __init__(self):
        # In a real scenario, this would be fitted on an out-of-sample validation set.
        self.calibrator = IsotonicRegression(out_of_bounds="clip")
        self.is_fitted = False

    def fit(self, y_true: np.ndarray, y_prob: np.ndarray):
        """Fit the isotonic regression model on true labels and predicted probabilities."""
        try:
            self.calibrator.fit(y_prob, y_true)
            self.is_fitted = True
            logger.info("Calibrator successfully fitted.")
        except Exception as e:
            logger.error(f"Error fitting calibrator: {e}")

    def calibrate(self, y_prob: float) -> float:
        """Calibrate a single probability score."""
        if not self.is_fitted:
            # Fallback mock scaling if not fitted (pushes extreme values closer to reality)
            # A common phenomenon is that uncalibrated models are overconfident.
            if y_prob > 0.8: return y_prob * 0.9
            if y_prob < 0.2: return min(y_prob * 1.1, 0.2)
            return y_prob

        try:
            return float(self.calibrator.predict([y_prob])[0])
        except Exception as e:
            logger.error(f"Calibration failed: {e}")
            return y_prob

calibrator = ProbabilityCalibrator()
