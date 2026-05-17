"""Tests for rl/environment.py — trading environment step/reset."""

from datetime import UTC, datetime, time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.rl.environment import (
    EnvironmentConfig,
    TradingEnvironment,
    _effective_lot_size,
    _must_auto_square_off,
    _next_position,
    _step_info,
    _validate_action,
    _validate_inputs,
)


def _utc_times(n: int) -> list[datetime]:
    return [datetime(2024, 6, 15, 9, 15 + i, 0, tzinfo=UTC) for i in range(n)]


def _observations(n: int, features: int = 3) -> list[list[Decimal]]:
    return [[Decimal(str(j)) for j in range(features)] for _ in range(n)]


def _prices(n: int, base: Decimal = Decimal("100")) -> list[Decimal]:
    return [base + Decimal(str(i)) for i in range(n)]


class TestEnvironmentConfig:
    def test_defaults(self) -> None:
        cfg = EnvironmentConfig()
        assert cfg.max_steps == 500
        assert cfg.intraday is True


class TestValidateInputs:
    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ConfigError, match="equal length"):
            _validate_inputs(_observations(5), _prices(3), _utc_times(5))

    def test_too_few_observations_raises(self) -> None:
        with pytest.raises(ConfigError, match="at least two"):
            _validate_inputs(_observations(1), _prices(1), _utc_times(1))

    def test_empty_observation_row_raises(self) -> None:
        with pytest.raises(ConfigError, match="at least one feature"):
            _validate_inputs(
                [[Decimal("1"), Decimal("2")], []],
                _prices(2),
                _utc_times(2),
            )

    def test_non_utc_timestamps_raises(self) -> None:
        with pytest.raises(ConfigError, match="timezone-aware UTC"):
            _validate_inputs(_observations(2), _prices(2), [datetime(2024, 1, 1)] * 2)


class TestValidateAction:
    def test_valid_actions(self) -> None:
        for a in (0, 1, 2):
            _validate_action(a)

    def test_invalid_action_raises(self) -> None:
        with pytest.raises(ConfigError, match="action must be 0, 1, or 2"):
            _validate_action(3)


class TestNextPosition:
    def test_hold_action(self) -> None:
        assert _next_position(0, 1, True) == 1

    def test_buy_action(self) -> None:
        assert _next_position(1, 0, True) == 1

    def test_sell_action(self) -> None:
        assert _next_position(2, 0, True) == -1

    def test_not_tradable_holds(self) -> None:
        assert _next_position(1, 1, False) == 1


class TestMustAutoSquareOff:
    def test_non_intraday(self) -> None:
        cfg = EnvironmentConfig(intraday=False)
        ts = datetime(2024, 6, 15, 10, 15, 0, tzinfo=UTC)
        assert _must_auto_square_off(ts, cfg) is False

    def test_intraday_before_square_off(self) -> None:
        cfg = EnvironmentConfig(intraday=True, auto_square_off_ist=time(15, 10))
        ts = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        with patch("iatb.rl.environment.Clock") as mock_clock:
            mock_ist = MagicMock()
            mock_ist.time.return_value = time(14, 0)
            mock_clock.to_ist.return_value = mock_ist
            assert _must_auto_square_off(ts, cfg) is False


class TestEffectiveLotSize:
    def test_nse_returns_default(self) -> None:
        cfg = EnvironmentConfig()
        assert _effective_lot_size(cfg) == Decimal("1")

    def test_mcx_returns_mcx_lot(self) -> None:
        cfg = EnvironmentConfig(exchange=Exchange.MCX)
        assert _effective_lot_size(cfg) == Decimal("50")


class TestStepInfo:
    def test_output_dict(self) -> None:
        info = _step_info(5, True, False)
        assert info["index"] == "5"
        assert info["in_session"] == "1"
        assert info["auto_square_off"] == "0"


class TestTradingEnvironment:
    def test_reset_returns_observation(self) -> None:
        env = TradingEnvironment(_observations(5), _prices(5), _utc_times(5))
        obs, info = env.reset()
        assert len(obs) == 3
        assert "seed" in info

    def test_step_returns_tuple(self) -> None:
        with patch("iatb.rl.environment.session_masks") as mock_sm:
            mock_sm.is_in_session.return_value = True
            env = TradingEnvironment(_observations(5), _prices(5), _utc_times(5))
            obs, reward, done, truncated, info = env.step(1)
            assert isinstance(reward, Decimal)
            assert isinstance(done, bool)
            assert "index" in info

    def test_invalid_action_raises(self) -> None:
        env = TradingEnvironment(_observations(5), _prices(5), _utc_times(5))
        with pytest.raises(ConfigError, match="action must be"):
            env.step(5)

    def test_terminal_step_raises(self) -> None:
        with patch("iatb.rl.environment.session_masks") as mock_sm:
            mock_sm.is_in_session.return_value = True
            env = TradingEnvironment(_observations(3), _prices(3), _utc_times(3))
            env.step(0)
            env.step(0)
            with pytest.raises(ConfigError, match="cannot step beyond"):
                env.step(0)

    def test_action_space_n(self) -> None:
        env = TradingEnvironment(_observations(3), _prices(3), _utc_times(3))
        assert env.action_space_n == 3
