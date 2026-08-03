"""Application configuration — loaded from environment variables."""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_NAME: str = "AI Stock Research Platform"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://stockuser:stockpass@localhost:5432/stockdb"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_QUOTE: int = 60          # 1 minute
    CACHE_TTL_DAILY_CANDLES: int = 3600 # 1 hour
    CACHE_TTL_INTRADAY: int = 60       # 1 minute
    CACHE_TTL_INDEX_QUOTE: int = 15    # 15 seconds; indices change faster than reference data

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Market hours (IST = UTC+5:30)
    MARKET_OPEN_HOUR: int = 9
    MARKET_OPEN_MINUTE: int = 15
    MARKET_CLOSE_HOUR: int = 15
    MARKET_CLOSE_MINUTE: int = 30
    MARKET_TIMEZONE: str = "Asia/Kolkata"

    # Data sources
    DEFAULT_EXCHANGE_SUFFIX: str = ".NS"  # NSE suffix for yfinance
    DATA_BACKFILL_DAYS: int = 730        # 2 years of daily data on startup

    # Paper trading defaults
    DEFAULT_COMMISSION: float = 20.0     # ₹20 flat per trade
    DEFAULT_SLIPPAGE_PCT: float = 0.001  # 0.1% slippage

    # AI / ML
    MODEL_VERSION: str = "rule_based_v1"
    SHAP_MAX_FEATURES: int = 10

    # SMTP is intentionally reserved for HIGH-priority alert delivery.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_USE_TLS: bool = True


settings = Settings()
