"""Candle (OHLCV) model — TimescaleDB hypertable."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, BigInteger, DateTime, Numeric, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class Candle(Base):
    """
    OHLCV time-series data.
    This table is converted to a TimescaleDB hypertable in the migration.
    Chunk interval: 7 days. Compression after 30 days.
    """
    __tablename__ = "candles"
    __table_args__ = (
        PrimaryKeyConstraint("symbol", "timeframe", "timestamp"),
    )

    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False)   # 1m, 5m, 15m, 30m, 1h, 1d, 1w
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": self.volume,
        }

    def __repr__(self) -> str:
        return f"<Candle {self.symbol} {self.timeframe} {self.timestamp}>"
