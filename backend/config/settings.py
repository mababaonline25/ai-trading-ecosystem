"""
Configuration management for different environments
"""

import os
from typing import List, Optional
from pydantic import BaseSettings, validator
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """অ্যাপ্লিকেশন কনফিগারেশন"""
    
    # Environment
    ENV: str = os.getenv("ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION: int = 3600 * 24 * 7  # 7 days
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "*").split(",")
    
    # Database
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", 5432))
    DB_NAME: str = os.getenv("DB_NAME", "trading_ecosystem")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "postgres")
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")
    
    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"
    
    # MongoDB
    MONGO_HOST: str = os.getenv("MONGO_HOST", "localhost")
    MONGO_PORT: int = int(os.getenv("MONGO_PORT", 27017))
    MONGO_DB: str = os.getenv("MONGO_DB", "trading_ecosystem")
    MONGO_USER: Optional[str] = os.getenv("MONGO_USER")
    MONGO_PASSWORD: Optional[str] = os.getenv("MONGO_PASSWORD")
    
    @property
    def MONGO_URL(self) -> str:
        if self.MONGO_USER and self.MONGO_PASSWORD:
            return f"mongodb://{self.MONGO_USER}:{self.MONGO_PASSWORD}@{self.MONGO_HOST}:{self.MONGO_PORT}"
        return f"mongodb://{self.MONGO_HOST}:{self.MONGO_PORT}"
    
    # Exchange APIs
    BINANCE_API_KEY: Optional[str] = os.getenv("BINANCE_API_KEY")
    BINANCE_SECRET_KEY: Optional[str] = os.getenv("BINANCE_SECRET_KEY")
    
    KUCOIN_API_KEY: Optional[str] = os.getenv("KUCOIN_API_KEY")
    KUCOIN_SECRET_KEY: Optional[str] = os.getenv("KUCOIN_SECRET_KEY")
    KUCOIN_PASSPHRASE: Optional[str] = os.getenv("KUCOIN_PASSPHRASE")
    
    BYBIT_API_KEY: Optional[str] = os.getenv("BYBIT_API_KEY")
    BYBIT_SECRET_KEY: Optional[str] = os.getenv("BYBIT_SECRET_KEY")
    
    COINBASE_API_KEY: Optional[str] = os.getenv("COINBASE_API_KEY")
    COINBASE_SECRET_KEY: Optional[str] = os.getenv("COINBASE_SECRET_KEY")
    
    KRAKEN_API_KEY: Optional[str] = os.getenv("KRAKEN_API_KEY")
    KRAKEN_SECRET_KEY: Optional[str] = os.getenv("KRAKEN_SECRET_KEY")
    
    OKX_API_KEY: Optional[str] = os.getenv("OKX_API_KEY")
    OKX_SECRET_KEY: Optional[str] = os.getenv("OKX_SECRET_KEY")
    OKX_PASSPHRASE: Optional[str] = os.getenv("OKX_PASSPHRASE")
    
    GATEIO_API_KEY: Optional[str] = os.getenv("GATEIO_API_KEY")
    GATEIO_SECRET_KEY: Optional[str] = os.getenv("GATEIO_SECRET_KEY")
    
    HUOBI_API_KEY: Optional[str] = os.getenv("HUOBI_API_KEY")
    HUOBI_SECRET_KEY: Optional[str] = os.getenv("HUOBI_SECRET_KEY")
    
    MEXC_API_KEY: Optional[str] = os.getenv("MEXC_API_KEY")
    MEXC_SECRET_KEY: Optional[str] = os.getenv("MEXC_SECRET_KEY")
    
    BITGET_API_KEY: Optional[str] = os.getenv("BITGET_API_KEY")
    BITGET_SECRET_KEY: Optional[str] = os.getenv("BITGET_SECRET_KEY")
    
    # AI APIs
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")
    
    # Blockchain
    ETH_RPC_URL: Optional[str] = os.getenv("ETH_RPC_URL", "https://mainnet.infura.io/v3/your-project-id")
    BSC_RPC_URL: Optional[str] = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org")
    POLYGON_RPC_URL: Optional[str] = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
    
    # Social Media APIs
    TWITTER_BEARER_TOKEN: Optional[str] = os.getenv("TWITTER_BEARER_TOKEN")
    REDDIT_CLIENT_ID: Optional[str] = os.getenv("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET: Optional[str] = os.getenv("REDDIT_CLIENT_SECRET")
    DISCORD_BOT_TOKEN: Optional[str] = os.getenv("DISCORD_BOT_TOKEN")
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    
    # Trading Parameters
    DEFAULT_RISK_PERCENT: float = float(os.getenv("DEFAULT_RISK_PERCENT", 2.0))
    MAX_LEVERAGE: int = int(os.getenv("MAX_LEVERAGE", 10))
    MIN_SIGNAL_CONFIDENCE: int = int(os.getenv("MIN_SIGNAL_CONFIDENCE", 70))
    
    # Cache
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", 300))  # 5 minutes
    MARKET_DATA_CACHE_TTL: int = int(os.getenv("MARKET_DATA_CACHE_TTL", 10))  # 10 seconds
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", 100))
    RATE_LIMIT_PERIOD: int = int(os.getenv("RATE_LIMIT_PERIOD", 60))  # 60 seconds
    
    # File Upload
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))  # 10MB
    ALLOWED_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "gif", "pdf", "csv", "xlsx"]
    
    @validator("ENV")
    def validate_env(cls, v):
        allowed = ["development", "staging", "production", "test"]
        if v not in allowed:
            raise ValueError(f"ENV must be one of {allowed}")
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Environment specific settings
class DevelopmentSettings(Settings):
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"


class StagingSettings(Settings):
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"


class ProductionSettings(Settings):
    DEBUG: bool = False
    LOG_LEVEL: str = "WARNING"
    CORS_ORIGINS: List[str] = ["https://your-domain.com"]


class TestSettings(Settings):
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    DB_NAME: str = "test_trading_ecosystem"


# কনফিগ নির্বাচন
env = os.getenv("ENV", "development")
if env == "development":
    settings = DevelopmentSettings()
elif env == "staging":
    settings = StagingSettings()
elif env == "production":
    settings = ProductionSettings()
elif env == "test":
    settings = TestSettings()
else:
    settings = Settings()

# Singleton instance
config = settings