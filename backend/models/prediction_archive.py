from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from backend.core.database import Base

class PredictionArchive(Base):
    __tablename__ = "prediction_archive"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    prediction_type = Column(String, nullable=False) # e.g. 'ensemble', 'lstm_regime'
    target_date = Column(DateTime(timezone=True), nullable=True) # when this prediction should be evaluated
    
    # Model Outputs
    predicted_value = Column(String, nullable=False) # e.g. 'BULLISH', 'BEARISH'
    confidence = Column(Float, nullable=False)
    features_snapshot = Column(JSON, nullable=True) # stores RSI, MACD, etc at time of prediction
    
    # Evaluation (populated later by false_signal_analysis)
    actual_outcome = Column(String, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    error_reason = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
