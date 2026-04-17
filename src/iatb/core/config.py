"""
Configuration management for IATB.

Uses Pydantic BaseSettings for type-safe configuration from environment variables.
"""

import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from iatb.core.exceptions import ConfigError

logger = logging.getLogger(__name__)


class Config(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Application settings
    app_name: str = "IATB"
    app_version: str = "0.1.0"
    debug: bool = False

    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Zerodha (Kite Connect) Configuration
    zerodha_api_key: str = ""
    zerodha_api_secret: str = ""

    # Data Provider Configuration
    data_provider_default: str = "kite"

    # Event bus settings
    event_bus_max_queue_size: int = 1000
    event_bus_batch_size: int = 100

    # Engine settings
    engine_max_tasks: int = 100

    # Trading settings
    default_exchange: str = "NSE"
    default_market_type: str = "SPOT"
    live_trading_enabled: bool = False

    # Paths
    data_dir: Path = Path("data")
    log_dir: Path = Path("logs")
    cache_dir: Path = Path("cache")

    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        """Initialize configuration with validation."""
        super().__init__(**kwargs)
        self._validate_config()
        self._ensure_directories()

    def _validate_config(self) -> None:
        """Validate configuration values."""
        valid_exchanges = ["NSE", "BSE", "MCX", "CDS", "BINANCE", "COINDCX"]
        if self.default_exchange not in valid_exchanges:
            msg = f"Invalid default_exchange: {self.default_exchange}"
            raise ConfigError(msg)

        valid_market_types = ["SPOT", "FUTURES", "OPTIONS", "CURRENCY_FO"]
        if self.default_market_type not in valid_market_types:
            msg = f"Invalid default_market_type: {self.default_market_type}"
            raise ConfigError(msg)

        if self.event_bus_max_queue_size <= 0:
            msg = "event_bus_max_queue_size must be positive"
            raise ConfigError(msg)

        if self.engine_max_tasks <= 0:
            msg = "engine_max_tasks must be positive"
            raise ConfigError(msg)

    def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            msg = f"Failed to create directories: {e}"
            raise ConfigError(msg) from e

    @classmethod
    def load(cls, env_file: str | None = None) -> "Config":
        """Load configuration from environment file."""
        try:
            if env_file:
                return cls(_env_file=env_file)
            return cls()
        except Exception as e:
            msg = f"Failed to load configuration: {e}"
            raise ConfigError(msg) from e


# Global config instance for easy access
_config_instance: Config | None = None


def get_config() -> Config:
    """Get or create the global configuration instance.

    Returns:
        Config instance (singleton).
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config.load()
    return _config_instance
