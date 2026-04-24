"""
Configuration management for IATB.

Uses Pydantic BaseSettings for type-safe configuration from environment variables.
"""

import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from iatb.core.exceptions import ConfigError

logger = logging.getLogger(__name__)

# Global flag to track if live mode confirmation has been given
_live_mode_confirmed: bool = False


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

    # Execution Mode Configuration
    execution_mode: str = "paper"  # "paper" | "live"
    live_trading_enabled: bool = False  # Safety: defaults to False

    # Trading settings
    default_exchange: str = "NSE"
    default_market_type: str = "SPOT"

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

        # Validate execution_mode
        valid_execution_modes = ["paper", "live"]
        if self.execution_mode not in valid_execution_modes:
            msg = (
                f"Invalid execution_mode: {self.execution_mode}. "
                f"Must be one of: {valid_execution_modes}"
            )
            raise ConfigError(msg)

        # Safety check: live mode requires live_trading_enabled=True
        if self.execution_mode == "live" and not self.live_trading_enabled:
            logger.warning(
                "execution_mode is 'live' but live_trading_enabled=False. "
                "This configuration is inconsistent. Setting execution_mode to 'paper' for safety."
            )
            self.execution_mode = "paper"

        # Safety check: live_trading_enabled=True without confirmation is dangerous
        if self.execution_mode == "live" and self.live_trading_enabled:
            if not _live_mode_confirmed:
                logger.warning(
                    "LIVE TRADING MODE DETECTED. This will execute REAL trades with REAL money. "
                    "Confirm live mode activation using confirm_live_mode() to proceed."
                )
                self.execution_mode = "paper"
                self.live_trading_enabled = False

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


def _log_live_trading_warning() -> None:
    """Log live trading warning messages."""
    logger.warning("=" * 80)
    logger.warning("LIVE TRADING CONFIRMATION REQUIRED")
    logger.warning("=" * 80)
    logger.warning("You are about to enable LIVE TRADING MODE.")
    logger.warning("This will execute REAL trades with REAL money.")
    logger.warning("")
    logger.warning("Risks:")
    logger.warning("- Financial loss from algorithmic trading")
    logger.warning("- Potential technical errors")
    logger.warning("- Market volatility risks")
    logger.warning("")
    logger.warning("Make sure you have:")
    logger.warning("- Thoroughly tested your strategy in paper trading mode")
    logger.warning("- Set appropriate risk management parameters")
    logger.warning("- Monitored the system for stability")
    logger.warning("- Sufficient capital to withstand losses")
    logger.warning("=" * 80)
    logger.warning("")


def _process_confirmation_response(response: str) -> None:
    """Process user confirmation response.

    Args:
        response: User's input response.

    Raises:
        ConfigError: If confirmation is denied.
    """
    global _config_instance

    if response != "CONFIRM":
        msg = "Live trading activation cancelled by user."
        logger.error(msg)
        raise ConfigError(msg)

    global _live_mode_confirmed
    _live_mode_confirmed = True
    logger.warning("LIVE TRADING MODE CONFIRMED. Real trades will be executed.")

    if _config_instance is not None:
        _config_instance.execution_mode = "live"
        _config_instance.live_trading_enabled = True


def confirm_live_mode() -> None:
    """Confirm live trading mode activation.

    This function must be called explicitly to enable live trading.
    It requires user confirmation through an interactive dialog.

    Raises:
        ConfigError: If confirmation is denied or if not running in an interactive session.
    """
    global _live_mode_confirmed

    if _live_mode_confirmed:
        logger.warning("Live mode has already been confirmed.")
        return

    _log_live_trading_warning()

    try:
        response = input("Type 'CONFIRM' to enable live trading: ").strip().upper()
        _process_confirmation_response(response)
    except (EOFError, KeyboardInterrupt):
        msg = "Live trading activation cancelled (non-interactive session or interrupted)."
        logger.error(msg)
        raise ConfigError(msg) from None
