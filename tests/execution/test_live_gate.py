"""
Tests for live trading safety gate.

Covers happy path, edge cases, error paths, type handling, and timezone handling.
"""

import os
from unittest.mock import patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.execution import live_gate
from iatb.execution.live_gate import (
    LiveGateConfig,
    LiveTradingSafetyGate,
    assert_live_trading_allowed,
    require_live_trading_enabled,
)


class TestLiveTradingSafetyGate:
    """Test LiveTradingSafetyGate class."""

    def test_init_default_values(self) -> None:
        """Test initialization with default values."""
        gate = LiveTradingSafetyGate()
        assert gate._require_all_three is True
        assert isinstance(gate._config, LiveGateConfig)

    def test_init_custom_env_var_name(self) -> None:
        """Test initialization with custom environment variable name."""
        gate = LiveTradingSafetyGate(env_var_name="CUSTOM_LIVE_TRADING")
        assert gate._env_var_name == "CUSTOM_LIVE_TRADING"

    def test_check_env_var_true_variations(self) -> None:
        """Test environment variable check with various true values."""
        true_values = ["true", "True", "TRUE", "1", "yes", "YES", "on", "ON"]
        for value in true_values:
            with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": value}):
                gate = LiveTradingSafetyGate()
                assert gate._config.env_var_enabled is True

    def test_check_env_var_false_variations(self) -> None:
        """Test environment variable check with various false values."""
        false_values = ["false", "False", "FALSE", "0", "no", "NO", "off", "OFF", ""]
        for value in false_values:
            with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": value}):
                gate = LiveTradingSafetyGate()
                assert gate._config.env_var_enabled is False

    def test_check_env_var_not_set(self) -> None:
        """Test environment variable check when not set."""
        with patch.dict(os.environ, {}, clear=True):
            gate = LiveTradingSafetyGate()
            assert gate._config.env_var_enabled is False

    def test_is_live_trading_allowed_all_three_required_all_true(self) -> None:
        """Test is_live_trading_allowed when all three layers are enabled."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            gate = LiveTradingSafetyGate(
                config_enabled=True,
                cli_flag_enabled=True,
                require_all_three=True,
            )
            assert gate.is_live_trading_allowed() is True

    def test_is_live_trading_allowed_all_three_required_one_false(self) -> None:
        """Test is_live_trading_allowed when one layer is missing."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            gate = LiveTradingSafetyGate(
                config_enabled=False,
                cli_flag_enabled=True,
                require_all_three=True,
            )
            assert gate.is_live_trading_allowed() is False

    def test_is_live_trading_allowed_any_one_required(self) -> None:
        """Test is_live_trading_allowed when only one layer needed."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            gate = LiveTradingSafetyGate(
                config_enabled=False,
                cli_flag_enabled=False,
                require_all_three=False,
            )
            assert gate.is_live_trading_allowed() is True

    def test_assert_live_trading_allowed_passes(self) -> None:
        """Test assert_live_trading_allowed passes when all layers enabled."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            gate = LiveTradingSafetyGate(
                config_enabled=True,
                cli_flag_enabled=True,
                require_all_three=True,
            )
            gate.assert_live_trading_allowed()  # Should not raise

    def test_assert_live_trading_allowed_raises_config_error(self) -> None:
        """Test assert_live_trading_allowed raises ConfigError when blocked."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            gate = LiveTradingSafetyGate(
                config_enabled=False,
                cli_flag_enabled=True,
                require_all_three=True,
            )
            with pytest.raises(ConfigError, match="Live trading is DISABLED"):
                gate.assert_live_trading_allowed()

    def test_get_missing_checks_all_missing(self) -> None:
        """Test _get_missing_checks returns all missing checks."""
        with patch.dict(os.environ, {}, clear=True):
            gate = LiveTradingSafetyGate(
                config_enabled=False,
                cli_flag_enabled=False,
                require_all_three=True,
            )
            missing = gate._get_missing_checks()
            assert "environment_variable_LIVE_TRADING_ENABLED" in missing
            assert "config_setting" in missing
            assert "cli_flag_--enable-live-trading" in missing

    def test_get_missing_checks_one_missing(self) -> None:
        """Test _get_missing_checks returns one missing check."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            gate = LiveTradingSafetyGate(
                config_enabled=True,
                cli_flag_enabled=False,
                require_all_three=True,
            )
            missing = gate._get_missing_checks()
            assert missing == ["cli_flag_--enable-live-trading"]

    def test_log_success_uses_utc_datetime(self) -> None:
        """Test _log_success uses UTC datetime for logging."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            with patch.object(live_gate, "_LOGGER") as mock_logger:
                gate = LiveTradingSafetyGate(
                    config_enabled=True,
                    cli_flag_enabled=True,
                    require_all_three=True,
                )
                gate.assert_live_trading_allowed(context="test_context")
                call_kwargs = mock_logger.info.call_args.kwargs
                assert "extra" in call_kwargs
                extra = call_kwargs["extra"]
                assert "timestamp_utc" in extra
                # Verify ISO format with timezone
                assert "T" in extra["timestamp_utc"]
                assert "Z" in extra["timestamp_utc"] or "+" in extra["timestamp_utc"]

    def test_log_failure_uses_utc_datetime(self) -> None:
        """Test _log_failure uses UTC datetime for logging."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            with patch.object(live_gate, "_LOGGER") as mock_logger:
                gate = LiveTradingSafetyGate(
                    config_enabled=False,
                    cli_flag_enabled=True,
                    require_all_three=True,
                )
                with pytest.raises(ConfigError):
                    gate.assert_live_trading_allowed(context="test_context")
                call_kwargs = mock_logger.warning.call_args.kwargs
                assert "extra" in call_kwargs
                extra = call_kwargs["extra"]
                assert "timestamp_utc" in extra
                # Verify ISO format with timezone
                assert "T" in extra["timestamp_utc"]
                assert "Z" in extra["timestamp_utc"] or "+" in extra["timestamp_utc"]


class TestRequireLiveTradingEnabledDecorator:
    """Test require_live_trading_enabled decorator."""

    def test_decorator_allows_execution_when_gate_passes(self) -> None:
        """Test decorator allows function execution when gate passes."""

        @require_live_trading_enabled(
            config_enabled=True,
            cli_flag_enabled=True,
        )
        def test_function() -> str:
            return "executed"

        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            result = test_function()
            assert result == "executed"

    def test_decorator_blocks_execution_when_gate_fails(self) -> None:
        """Test decorator blocks function execution when gate fails."""

        @require_live_trading_enabled(
            config_enabled=True,
            cli_flag_enabled=True,
        )
        def test_function() -> str:
            return "executed"

        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "false"}):
            with pytest.raises(ConfigError, match="Live trading is DISABLED"):
                test_function()

    def test_decorator_preserves_function_name_and_docstring(self) -> None:
        """Test decorator preserves function metadata."""

        @require_live_trading_enabled(
            config_enabled=True,
            cli_flag_enabled=True,
        )
        def test_function() -> str:
            """Test function docstring."""
            return "executed"

        assert test_function.__name__ == "test_function"
        assert "Test function docstring" in test_function.__doc__

    def test_decorator_with_arguments(self) -> None:
        """Test decorator works with function arguments."""

        @require_live_trading_enabled(
            config_enabled=True,
            cli_flag_enabled=True,
        )
        def test_function(x: int, y: int) -> int:
            return x + y

        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            result = test_function(5, 3)
            assert result == 8

    def test_decorator_with_keyword_arguments(self) -> None:
        """Test decorator works with keyword arguments."""

        @require_live_trading_enabled(
            config_enabled=True,
            cli_flag_enabled=True,
        )
        def test_function(x: int, y: int) -> int:
            return x + y

        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            result = test_function(x=5, y=3)
            assert result == 8


class TestAssertLiveTradingAllowedFunction:
    """Test assert_live_trading_allowed standalone function."""

    def test_function_passes_when_all_layers_enabled(self) -> None:
        """Test function passes when all three layers are enabled."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            assert_live_trading_allowed(
                config_enabled=True,
                cli_flag_enabled=True,
                context="test_context",
            )  # Should not raise

    def test_function_raises_when_blocked(self) -> None:
        """Test function raises ConfigError when blocked."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            with pytest.raises(ConfigError, match="Live trading is DISABLED"):
                assert_live_trading_allowed(
                    config_enabled=False,
                    cli_flag_enabled=True,
                    context="test_context",
                )

    def test_function_with_custom_env_var_name(self) -> None:
        """Test function with custom environment variable name."""
        with patch.dict(os.environ, {"CUSTOM_LIVE_VAR": "true"}):
            assert_live_trading_allowed(
                env_var_name="CUSTOM_LIVE_VAR",
                config_enabled=True,
                cli_flag_enabled=True,
                require_all_three=True,
            )  # Should not raise

    def test_function_with_require_all_three_false(self) -> None:
        """Test function with require_all_three=False."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            assert_live_trading_allowed(
                config_enabled=False,
                cli_flag_enabled=False,
                require_all_three=False,
            )  # Should not raise


class TestLiveGateConfig:
    """Test LiveGateConfig dataclass."""

    def test_live_gate_config_creation(self) -> None:
        """Test LiveGateConfig can be created."""
        config = LiveGateConfig(
            env_var_enabled=True,
            config_enabled=True,
            cli_flag_enabled=True,
        )
        assert config.env_var_enabled is True
        assert config.config_enabled is True
        assert config.cli_flag_enabled is True
        assert config.require_all_three is True

    def test_live_gate_config_defaults(self) -> None:
        """Test LiveGateConfig default values."""
        config = LiveGateConfig(
            env_var_enabled=False,
            config_enabled=False,
            cli_flag_enabled=False,
        )
        assert config.require_all_three is True
        assert config.log_all_attempts is True


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_env_var_value(self) -> None:
        """Test empty environment variable value is treated as false."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": ""}):
            gate = LiveTradingSafetyGate()
            assert gate._config.env_var_enabled is False

    def test_whitespace_only_env_var_value(self) -> None:
        """Test whitespace-only environment variable value is treated as false."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "   "}):
            gate = LiveTradingSafetyGate()
            assert gate._config.env_var_enabled is False

    def test_env_var_value_with_whitespace(self) -> None:
        """Test environment variable value with surrounding whitespace."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "  true  "}):
            gate = LiveTradingSafetyGate()
            assert gate._config.env_var_enabled is True

    def test_error_message_includes_missing_checks(self) -> None:
        """Test error message includes list of missing checks."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            gate = LiveTradingSafetyGate(
                config_enabled=False,
                cli_flag_enabled=False,
                require_all_three=True,
            )
            with pytest.raises(ConfigError) as exc_info:
                gate.assert_live_trading_allowed()
            error_msg = str(exc_info.value)
            assert "config_setting" in error_msg
            assert "cli_flag_--enable-live-trading" in error_msg

    def test_error_message_different_when_require_all_false(self) -> None:
        """Test error message is different when require_all_three=False."""
        with patch.dict(os.environ, {}, clear=True):
            gate = LiveTradingSafetyGate(
                config_enabled=False,
                cli_flag_enabled=False,
                require_all_three=False,
            )
            with pytest.raises(ConfigError) as exc_info:
                gate.assert_live_trading_allowed()
            error_msg = str(exc_info.value)
            assert "At least one check is required" in error_msg

    def test_context_passed_to_logs(self) -> None:
        """Test context parameter is passed to log messages."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            with patch.object(live_gate, "_LOGGER") as mock_logger:
                gate = LiveTradingSafetyGate(
                    config_enabled=True,
                    cli_flag_enabled=True,
                    require_all_three=True,
                )
                gate.assert_live_trading_allowed(context="custom_context")
                call_kwargs = mock_logger.info.call_args.kwargs
                assert call_kwargs["extra"]["context"] == "custom_context"

    def test_sebi_compliance_logging_structure(self) -> None:
        """Test logging follows SEBI compliance structure."""
        with patch.dict(os.environ, {"LIVE_TRADING_ENABLED": "true"}):
            with patch.object(live_gate, "_LOGGER") as mock_logger:
                gate = LiveTradingSafetyGate(
                    config_enabled=True,
                    cli_flag_enabled=True,
                    require_all_three=True,
                )
                gate.assert_live_trading_allowed()
                call_kwargs = mock_logger.info.call_args.kwargs
                extra = call_kwargs["extra"]
                # Verify all required SEBI compliance fields
                assert extra["event"] == "live_gate_check"
                assert extra["status"] == "PASSED"
                assert "timestamp_utc" in extra
                assert "env_var" in extra
                assert "env_enabled" in extra
                assert "config_enabled" in extra
                assert "cli_enabled" in extra
                assert "require_all_three" in extra
