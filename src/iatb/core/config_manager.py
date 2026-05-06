"""
Configuration manager for dynamic watchlist management.

Provides environment-based config overlay and runtime updates.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError

_LOGGER = logging.getLogger(__name__)

# Config file paths (relative to project root)
WATCHLIST_CONFIG_PATH = Path("config/watchlist.toml")
WATCHLIST_CONFIG_ENV_VAR = "IATB_WATCHLIST_CONFIG_PATH"
WEIGHTS_CONFIG_PATH = Path("config/weights.toml")
WEIGHTS_CONFIG_ENV_VAR = "IATB_WEIGHTS_CONFIG_PATH"


@dataclass(frozen=True)
class WatchlistEntry:
    """A single watchlist entry."""

    exchange: Exchange
    symbol: str


@dataclass(frozen=True)
class WatchlistConfig:
    """Watchlist configuration for all exchanges."""

    nse: list[str] = field(default_factory=list)
    bse: list[str] = field(default_factory=list)
    mcx: list[str] = field(default_factory=list)
    cds: list[str] = field(default_factory=list)

    def get_symbols(self, exchange: Exchange) -> list[str]:
        """Get watchlist symbols for a specific exchange.

        Args:
            exchange: The exchange to get symbols for.

        Returns:
            List of symbol strings for the exchange.
        """
        exchange_map = {
            Exchange.NSE: self.nse,
            Exchange.BSE: self.bse,
            Exchange.MCX: self.mcx,
            Exchange.CDS: self.cds,
        }
        return exchange_map.get(exchange, []).copy()

    def get_all_entries(self) -> list[WatchlistEntry]:
        """Get all watchlist entries across all exchanges.

        Returns:
            List of WatchlistEntry objects.
        """
        entries: list[WatchlistEntry] = []
        for exchange in [Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS]:
            symbols = self.get_symbols(exchange)
            for symbol in symbols:
                entries.append(WatchlistEntry(exchange=exchange, symbol=symbol))
        return entries


class ConfigManager:
    """Manages watchlist and weight configurations with environment overlay support."""

    def __init__(
        self,
        config_path: Path | None = None,
        weights_path: Path | None = None,
    ) -> None:
        """Initialize config manager.

        Args:
            config_path: Optional path to watchlist.toml. If not provided,
                uses default or environment variable.
            weights_path: Optional path to weights.toml. If not provided,
                uses default or environment variable.
        """
        self._config_path = self._resolve_config_path(config_path)
        self._weights_path = self._resolve_weights_path(weights_path)
        self._config = self._load_config()
        self._weights_config = self._load_weights_config()

    def _resolve_config_path(self, config_path: Path | None) -> Path:
        """Resolve the config file path with environment overlay.

        Args:
            config_path: Optional explicit config path.

        Returns:
            Resolved Path to watchlist config file.
        """
        if config_path is not None:
            return config_path

        # Check environment variable for override
        env_path = os.environ.get(WATCHLIST_CONFIG_ENV_VAR)
        if env_path:
            _LOGGER.info(
                "Using watchlist config from environment variable",
                extra={"env_var": WATCHLIST_CONFIG_ENV_VAR, "path": env_path},
            )
            return Path(env_path)

        # Use default path
        return WATCHLIST_CONFIG_PATH

    def _resolve_weights_path(self, weights_path: Path | None) -> Path:
        """Resolve the weights config file path with environment overlay.

        Args:
            weights_path: Optional explicit weights path.

        Returns:
            Resolved Path to weights config file.
        """
        if weights_path is not None:
            return weights_path

        # Check environment variable for override
        env_path = os.environ.get(WEIGHTS_CONFIG_ENV_VAR)
        if env_path:
            _LOGGER.info(
                "Using weights config from environment variable",
                extra={"env_var": WEIGHTS_CONFIG_ENV_VAR, "path": env_path},
            )
            return Path(env_path)

        # Use default path
        return WEIGHTS_CONFIG_PATH

    def _load_config_file(self, config_path: Path) -> dict[str, Any]:
        """Load TOML config file.

        Args:
            config_path: Path to TOML config file.

        Returns:
            Parsed config as dictionary.

        Raises:
            ConfigError: If config file cannot be loaded or parsed.
        """
        import tomli

        try:
            with config_path.open("rb") as f:
                return tomli.load(f)
        except FileNotFoundError:
            _LOGGER.warning(
                "Watchlist config file not found, using defaults",
                extra={"config_path": str(config_path)},
            )
            return {}
        except Exception as e:
            msg = f"Failed to load watchlist config from {config_path}: {e}"
            raise ConfigError(msg) from e

    def _load_weights_config_file(self, weights_path: Path) -> dict[str, Any]:
        """Load TOML weights config file.

        Args:
            weights_path: Path to TOML weights config file.

        Returns:
            Parsed weights config as dictionary.

        Raises:
            ConfigError: If weights config file cannot be loaded or parsed.
        """
        import tomli

        try:
            with weights_path.open("rb") as f:
                return tomli.load(f)
        except FileNotFoundError:
            _LOGGER.warning(
                "Weights config file not found, using defaults",
                extra={"weights_path": str(weights_path)},
            )
            return {}
        except Exception as e:
            msg = f"Failed to load weights config from {weights_path}: {e}"
            raise ConfigError(msg) from e

    def _load_config(self) -> WatchlistConfig:
        """Load watchlist configuration from file.

        Returns:
            WatchlistConfig object with loaded or default values.
        """
        try:
            raw_config = self._load_config_file(self._config_path)

            nse_symbols = raw_config.get("nse", {}).get("symbols", [])
            bse_symbols = raw_config.get("bse", {}).get("symbols", [])
            mcx_symbols = raw_config.get("mcx", {}).get("symbols", [])
            cds_symbols = raw_config.get("cds", {}).get("symbols", [])

            config = WatchlistConfig(
                nse=nse_symbols,
                bse=bse_symbols,
                mcx=mcx_symbols,
                cds=cds_symbols,
            )

            _LOGGER.info(
                "Loaded watchlist configuration",
                extra={
                    "nse_count": len(nse_symbols),
                    "bse_count": len(bse_symbols),
                    "mcx_count": len(mcx_symbols),
                    "cds_count": len(cds_symbols),
                },
            )

            return config
        except ConfigError:
            # Return empty config if loading fails
            return WatchlistConfig()

    def _load_weights_config(self) -> dict[str, dict[str, str]]:
        """Load weights configuration from file.

        Returns:
            Dictionary with regime weights configuration.
            Structure: {"regime_name": {"sentiment": "value", "strength": "value", ...}}
        """
        try:
            raw_config = self._load_weights_config_file(self._weights_path)
            _LOGGER.info(
                "Loaded weights configuration",
                extra={"weights_path": str(self._weights_path)},
            )
            weights = raw_config.get("weights", {})
            return dict(weights) if isinstance(weights, dict) else {}
        except ConfigError:
            # Return empty config if loading fails
            return {}

    def reload_config(self) -> WatchlistConfig:
        """Reload configuration from file.

        This allows runtime updates without restarting the application.

        Returns:
            Reloaded WatchlistConfig object.
        """
        _LOGGER.info("Reloading watchlist configuration")
        self._config = self._load_config()
        return self._config

    def reload_weights_config(self) -> dict[str, dict[str, str]]:
        """Reload weights configuration from file.

        This allows runtime updates without restarting the application.

        Returns:
            Reloaded weights configuration dictionary.
        """
        _LOGGER.info("Reloading weights configuration")
        self._weights_config = self._load_weights_config()
        return self._weights_config

    def get_config(self) -> WatchlistConfig:
        """Get current watchlist configuration.

        Returns:
            Current WatchlistConfig object.
        """
        return self._config

    def get_weights_config(self) -> dict[str, dict[str, str]]:
        """Get current weights configuration.

        Returns:
            Current weights configuration dictionary.
        """
        return self._weights_config

    def _merge_config_updates(
        self,
        nse: list[str] | None,
        bse: list[str] | None,
        mcx: list[str] | None,
        cds: list[str] | None,
    ) -> WatchlistConfig:
        """Merge updates with current config.

        Args:
            nse: New NSE symbols list (optional).
            bse: New BSE symbols list (optional).
            mcx: New MCX symbols list (optional).
            cds: New CDS symbols list (optional).

        Returns:
            New WatchlistConfig with merged values.
        """
        current_nse = self._config.nse if nse is None else nse
        current_bse = self._config.bse if bse is None else bse
        current_mcx = self._config.mcx if mcx is None else mcx
        current_cds = self._config.cds if cds is None else cds

        return WatchlistConfig(
            nse=current_nse,
            bse=current_bse,
            mcx=current_mcx,
            cds=current_cds,
        )

    def _merge_weights_config_updates(
        self,
        regime_weights: dict[str, dict[str, str]] | None,
    ) -> dict[str, dict[str, str]]:
        """Merge weights updates with current config.

        Args:
            regime_weights: New regime weights dictionary (optional).

        Returns:
            New weights configuration with merged values.
        """
        current_weights = self._weights_config if regime_weights is None else regime_weights
        return current_weights

    def _serialize_to_toml(self, config: WatchlistConfig) -> dict[str, dict[str, Any]]:
        """Serialize config to TOML structure.

        Args:
            config: Configuration to serialize.

        Returns:
            TOML data structure.
        """
        return {
            "nse": {"symbols": config.nse},
            "bse": {"symbols": config.bse},
            "mcx": {"symbols": config.mcx},
            "cds": {"symbols": config.cds},
        }

    def _serialize_weights_to_toml(
        self, weights_config: dict[str, dict[str, str]]
    ) -> dict[str, Any]:
        """Serialize weights config to TOML structure.

        Args:
            weights_config: Weights configuration to serialize.

        Returns:
            TOML data structure.
        """
        return {"weights": weights_config}

    def _write_toml_file(
        self, toml_data: dict[str, dict[str, Any]], config: WatchlistConfig
    ) -> None:
        """Write TOML data to file.

        Args:
            toml_data: TOML data to write.
            config: Configuration being written (for logging).

        Raises:
            ConfigError: If write operation fails.
        """
        import tomli_w

        try:
            # Ensure parent directory exists
            self._config_path.parent.mkdir(parents=True, exist_ok=True)

            with self._config_path.open("wb") as f:
                tomli_w.dump(toml_data, f)

            _LOGGER.info(
                "Updated watchlist configuration",
                extra={
                    "config_path": str(self._config_path),
                    "nse_count": len(config.nse),
                    "bse_count": len(config.bse),
                    "mcx_count": len(config.mcx),
                    "cds_count": len(config.cds),
                },
            )
        except Exception as e:
            msg = f"Failed to write watchlist config to {self._config_path}: {e}"
            raise ConfigError(msg) from e

    def _write_weights_toml_file(
        self, toml_data: dict[str, Any], weights_config: dict[str, dict[str, str]]
    ) -> None:
        """Write weights TOML data to file.

        Args:
            toml_data: TOML data to write.
            weights_config: Weights configuration being written (for logging).

        Raises:
            ConfigError: If write operation fails.
        """
        import tomli_w

        try:
            # Ensure parent directory exists
            self._weights_path.parent.mkdir(parents=True, exist_ok=True)

            with self._weights_path.open("wb") as f:
                tomli_w.dump(toml_data, f)

            _LOGGER.info(
                "Updated weights configuration",
                extra={
                    "weights_path": str(self._weights_path),
                    "regimes_count": len(weights_config),
                },
            )
        except Exception as e:
            msg = f"Failed to write weights config to {self._weights_path}: {e}"
            raise ConfigError(msg) from e

    def update_config(
        self,
        nse: list[str] | None = None,
        bse: list[str] | None = None,
        mcx: list[str] | None = None,
        cds: list[str] | None = None,
    ) -> WatchlistConfig:
        """Update watchlist configuration and persist to file.

        Args:
            nse: New NSE symbols list (optional).
            bse: New BSE symbols list (optional).
            mcx: New MCX symbols list (optional).
            cds: New CDS symbols list (optional).

        Returns:
            Updated WatchlistConfig object.

        Raises:
            ConfigError: If config cannot be written to file.
        """
        # Merge updates with current config
        new_config = self._merge_config_updates(nse, bse, mcx, cds)

        # Serialize to TOML
        toml_data = self._serialize_to_toml(new_config)

        # Write to file
        self._write_toml_file(toml_data, new_config)

        # Update in-memory config
        self._config = new_config
        return new_config

    def update_weights_config(
        self, regime_weights: dict[str, dict[str, str]]
    ) -> dict[str, dict[str, str]]:
        """Update weights configuration and persist to file.

        Args:
            regime_weights: Dictionary of regime weights to update.
                Structure: {"regime_name": {"sentiment": "value", "strength": "value", ...}}

        Returns:
            Updated weights configuration dictionary.

        Raises:
            ConfigError: If weights config cannot be written to file.
        """
        # Merge updates with current config
        new_weights_config = self._merge_weights_config_updates(regime_weights)

        # Serialize to TOML
        toml_data = self._serialize_weights_to_toml(new_weights_config)

        # Write to file
        self._write_weights_toml_file(toml_data, new_weights_config)

        # Update in-memory config
        self._weights_config = new_weights_config
        return new_weights_config

    def get_regime_weights(self, regime: str) -> dict[str, str] | None:
        """Get weights for a specific regime.

        Args:
            regime: Name of the regime (e.g., "BULL", "BEAR", "SIDEWAYS").

        Returns:
            Dictionary of weights for the regime, or None if not found.
        """
        return self._weights_config.get(regime)

    def set_regime_weights(self, regime: str, weights: dict[str, str]) -> None:
        """Set weights for a specific regime.

        Args:
            regime: Name of the regime (e.g., "BULL", "BEAR", "SIDEWAYS").
            weights: Dictionary of weights to set.
        """
        self._weights_config[regime] = weights
        toml_data = self._serialize_weights_to_toml(self._weights_config)
        self._write_weights_toml_file(toml_data, self._weights_config)


# Global config manager instance
_config_manager: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    """Get or create the global config manager instance.

    Returns:
        ConfigManager instance.
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def reset_config_manager() -> None:
    """Reset the global config manager instance (mainly for testing)."""
    global _config_manager
    _config_manager = None
