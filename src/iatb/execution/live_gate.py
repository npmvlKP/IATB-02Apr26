"""
Live trading safety gate with dual-confirmation enforcement.

Prevents accidental live execution by requiring:
1. LIVE_TRADING_ENABLED environment variable = true
2. Config setting live_trading_enabled = true
3. CLI flag --enable-live-trading provided

All three layers must be satisfied to allow live trading.
SEBI-compliant logging for all live trading attempts.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from iatb.core.exceptions import ConfigError

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveGateConfig:
    """Configuration for live trading safety gate."""

    env_var_enabled: bool
    config_enabled: bool
    cli_flag_enabled: bool
    require_all_three: bool = True
    log_all_attempts: bool = True


class LiveTradingSafetyGate:
    """Enforces dual-confirmation safety gate for live trading."""

    def __init__(
        self,
        *,
        env_var_name: str = "LIVE_TRADING_ENABLED",
        config_enabled: bool = False,
        cli_flag_enabled: bool = False,
        require_all_three: bool = True,
    ) -> None:
        self._env_var_name = env_var_name
        self._require_all_three = require_all_three
        self._config = LiveGateConfig(
            env_var_enabled=self._check_env_var(),
            config_enabled=config_enabled,
            cli_flag_enabled=cli_flag_enabled,
            require_all_three=require_all_three,
        )

    def _check_env_var(self) -> bool:
        """Check if environment variable is set to true."""
        import os  # noqa: PLC0415

        value = os.getenv(self._env_var_name, "").strip().lower()
        return value in {"true", "1", "yes", "on"}

    def is_live_trading_allowed(self) -> bool:
        """Check if live trading is allowed based on all three layers."""
        if self._require_all_three:
            return (
                self._config.env_var_enabled
                and self._config.config_enabled
                and self._config.cli_flag_enabled
            )
        return (
            self._config.env_var_enabled
            or self._config.config_enabled
            or self._config.cli_flag_enabled
        )

    def assert_live_trading_allowed(self, *, context: str | None = None) -> None:
        """Assert live trading is allowed, raise ConfigError if not."""
        if self.is_live_trading_allowed():
            self._log_success(context)
            return

        self._log_failure(context)
        self._raise_blocked_error()

    def _log_success(self, context: str | None) -> None:
        """Log successful live trading safety gate check."""
        _LOGGER.info(
            "Live trading safety gate PASSED",
            extra={
                "event": "live_gate_check",
                "status": "PASSED",
                "context": context or "unknown",
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "env_var": self._env_var_name,
                "env_enabled": self._config.env_var_enabled,
                "config_enabled": self._config.config_enabled,
                "cli_enabled": self._config.cli_flag_enabled,
                "require_all_three": self._require_all_three,
            },
        )

    def _log_failure(self, context: str | None) -> None:
        """Log failed live trading safety gate check."""
        _LOGGER.warning(
            "Live trading safety gate BLOCKED",
            extra={
                "event": "live_gate_check",
                "status": "BLOCKED",
                "context": context or "unknown",
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "env_var": self._env_var_name,
                "env_enabled": self._config.env_var_enabled,
                "config_enabled": self._config.config_enabled,
                "cli_enabled": self._config.cli_flag_enabled,
                "require_all_three": self._require_all_three,
                "missing_checks": self._get_missing_checks(),
            },
        )

    def _get_missing_checks(self) -> list[str]:
        """Return list of missing safety gate checks."""
        missing: list[str] = []
        if not self._config.env_var_enabled:
            missing.append(f"environment_variable_{self._env_var_name}")
        if not self._config.config_enabled:
            missing.append("config_setting")
        if not self._config.cli_flag_enabled:
            missing.append("cli_flag_--enable-live-trading")
        return missing

    def _raise_blocked_error(self) -> None:
        """Raise ConfigError for blocked live trading attempt."""
        missing = self._get_missing_checks()
        missing_str = ", ".join(missing)
        if self._require_all_three:
            msg = (
                f"Live trading is DISABLED. Missing required checks: {missing_str}. "
                f"All three layers must be enabled: "
                f"{self._env_var_name}=true, config setting, and --enable-live-trading CLI flag."
            )
        else:
            msg = (
                f"Live trading is DISABLED. At least one check is required: "
                f"{self._env_var_name}=true, config setting, or --enable-live-trading CLI flag."
            )
        raise ConfigError(msg)


def require_live_trading_enabled(
    *,
    env_var_name: str = "LIVE_TRADING_ENABLED",
    config_enabled: bool = False,
    cli_flag_enabled: bool = False,
    require_all_three: bool = True,
) -> Callable[..., Any]:
    """Decorator to enforce live trading safety gate on a function.

    Args:
        env_var_name: Name of environment variable to check
        config_enabled: Whether config setting allows live trading
        cli_flag_enabled: Whether CLI flag enables live trading
        require_all_three: If True, all three layers must be enabled

    Returns:
        Decorator function

    Raises:
        ConfigError: If live trading safety gate is not satisfied

    Example:
        @require_live_trading_enabled(
            config_enabled=True,
            cli_flag_enabled=True,
        )
        def execute_live_order(order_request: OrderRequest) -> ExecutionResult:
            # This function will only execute if all three layers are enabled
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Create gate at call time to get fresh env var value
            gate = LiveTradingSafetyGate(
                env_var_name=env_var_name,
                config_enabled=config_enabled,
                cli_flag_enabled=cli_flag_enabled,
                require_all_three=require_all_three,
            )
            context = f"{func.__module__}.{func.__name__}"
            gate.assert_live_trading_allowed(context=context)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def assert_live_trading_allowed(
    *,
    env_var_name: str = "LIVE_TRADING_ENABLED",
    config_enabled: bool = False,
    cli_flag_enabled: bool = False,
    require_all_three: bool = True,
    context: str | None = None,
) -> None:
    """Assert live trading is allowed based on safety gate checks.

    This is a convenience function for non-decorator usage.

    Args:
        env_var_name: Name of environment variable to check
        config_enabled: Whether config setting allows live trading
        cli_flag_enabled: Whether CLI flag enables live trading
        require_all_three: If True, all three layers must be enabled
        context: Optional context string for logging

    Raises:
        ConfigError: If live trading safety gate is not satisfied

    Example:
        assert_live_trading_allowed(
            config_enabled=True,
            cli_flag_enabled=True,
            context="manual_order_placement",
        )
    """
    gate = LiveTradingSafetyGate(
        env_var_name=env_var_name,
        config_enabled=config_enabled,
        cli_flag_enabled=cli_flag_enabled,
        require_all_three=require_all_three,
    )
    gate.assert_live_trading_allowed(context=context)
