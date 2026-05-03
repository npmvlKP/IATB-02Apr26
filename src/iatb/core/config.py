"""
Configuration management for IATB.

Uses Pydantic BaseSettings for type-safe configuration from environment variables
and TOML configuration files.
"""

import logging
from pathlib import Path
from typing import Any

import tomli
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

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

    @classmethod
    def _load_toml_settings(cls, settings_cls: type[BaseSettings]) -> PydanticBaseSettingsSource:
        """Load settings from TOML configuration file.

        Args:
            settings_cls: Settings class being configured.

        Returns:
            PydanticBaseSettingsSource with TOML configuration.
        """
        toml_path = Path("config/settings.toml")
        return TomlSettingsSource(settings_cls, toml_path)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources to load TOML configuration.

        Priority order (highest to lowest):
        1. Environment variables
        2. .env file
        3. TOML configuration file (config/settings.toml)
        4. Default values

        Args:
            settings_cls: Settings class being configured.
            init_settings: Settings from __init__ kwargs.
            env_settings: Settings from environment variables.
            dotenv_settings: Settings from .env file.
            file_secret_settings: Settings from file secrets.

        Returns:
            Tuple of settings sources in priority order.
        """
        toml_settings = cls._load_toml_settings(settings_cls)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            toml_settings,
            file_secret_settings,
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

    # Observability settings
    observability_enabled: bool = True
    observability_exporter_type: str = "otlp"
    observability_service_name: str = "iatb"
    observability_service_version: str = "0.1.0"

    # Storage settings
    storage_type: str = "duckdb"
    storage_path: Path = Path("data/iatb.duckdb")
    storage_backup_enabled: bool = True
    storage_backup_path: Path = Path("data/backups")

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
        """Load configuration from environment file.

        Args:
            env_file: Optional path to environment file.

        Returns:
            Config instance.

        Raises:
            ConfigError: If configuration loading fails.
        """
        try:
            if env_file:
                return cls(_env_file=env_file)
            return cls()
        except Exception as e:
            msg = f"Failed to load configuration: {e}"
            raise ConfigError(msg) from e


class TomlSettingsSource(PydanticBaseSettingsSource):
    """Custom settings source for TOML configuration."""

    def __init__(self, settings_cls: type[BaseSettings], toml_path: Path):
        super().__init__(settings_cls)
        self.toml_path = toml_path
        self._toml_data: dict[str, Any] = self._load_toml_data()

    def _load_toml_data(self) -> dict[str, Any]:
        """Load TOML data from file.

        Returns:
            Dictionary of TOML configuration values.
        """
        if not self.toml_path.exists():
            logger.info(
                "TOML config file not found, using defaults",
                extra={"toml_path": str(self.toml_path)},
            )
            return {}

        try:
            with self.toml_path.open("rb") as f:
                toml_data = tomli.load(f)

            logger.info(
                "Loaded TOML configuration",
                extra={"toml_path": str(self.toml_path)},
            )
            return self._flatten_toml_data(toml_data)
        except Exception as e:
            logger.warning(
                "Failed to load TOML config, using defaults",
                extra={"toml_path": str(self.toml_path), "error": str(e)},
            )
            return {}

    def _flatten_toml_data(self, toml_data: dict[str, Any]) -> dict[str, Any]:
        """Flatten nested TOML data structure.

        Args:
            toml_data: Nested TOML data.

        Returns:
            Flattened dictionary with dot-notation keys.
        """
        flattened: dict[str, Any] = {}
        for key, value in toml_data.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    flattened[sub_key] = sub_value
            else:
                flattened[key] = value
        return flattened

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        """Get field value from TOML configuration.

        Args:
            field: Pydantic field definition.
            field_name: Name of the field.

        Returns:
            Tuple of (value, source_name, value_is_complex).
        """
        field_value = self._toml_data.get(field_name, field.default)
        return field_value, "TOML", False

    def __call__(self) -> dict[str, Any]:
        """Load and parse TOML configuration.

        Returns:
            Dictionary of configuration values from TOML.
        """
        return self._toml_data


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
