"""
Additional tests for rl/environment.py to improve coverage to 90%+.
"""

from datetime import UTC, datetime, time
from decimal import Decimal

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
    _step_reward,
    _transaction_cost,
    _validate_action,
    _validate_inputs,
)


class TestEnvironmentConfig:
    """Test EnvironmentConfig dataclass."""

    def test_config_initialization(self) -> None:
        """Test EnvironmentConfig initialization with all fields."""
        config = EnvironmentConfig(
            max_steps=1000,
            trade_notional=Decimal("50000"),
            market_segment="eq",
            exchange=Exchange.BSE,
            intraday=False,
            auto_square_off_ist=time(15, 30),
            lot_size=Decimal("10"),
            mcx_lot_size=Decimal("100"),
        )
        assert config.max_steps == 1000
        assert config.trade_notional == Decimal("50000")
        assert config.market_segment == "eq"
        assert config.exchange == Exchange.BSE
        assert config.intraday is False
        assert config.auto_square_off_ist == time(15, 30)
        assert config.lot_size == Decimal("10")
        assert config.mcx_lot_size == Decimal("100")

    def test_config_defaults(self) -> None:
        """Test EnvironmentConfig default values."""
        config = EnvironmentConfig()
        assert config.max_steps == 500
        assert config.trade_notional == Decimal("10000")
        assert config.market_segment == "fo"
        assert config.exchange == Exchange.NSE
        assert config.intraday is True
        assert config.auto_square_off_ist == time(15, 10)
        assert config.lot_size == Decimal("1")
        assert config.mcx_lot_size == Decimal("50")


class TestTradingEnvironment:
    """Test TradingEnvironment class."""

    def test_environment_init_valid(self) -> None:
        """Test TradingEnvironment initialization with valid inputs."""
        observations = [[Decimal("1")], [Decimal("2")], [Decimal("3")]]
        close_prices = [Decimal("100"), Decimal("101"), Decimal("102")]
        timestamps_utc = [
            datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
            datetime(2024, 1, 1, 9, 31, tzinfo=UTC),
            datetime(2024, 1, 1, 9, 32, tzinfo=UTC),
        ]
        env = TradingEnvironment(observations, close_prices, timestamps_utc)
        assert env.action_space_n == 3
        assert env.observation_size == 1

    def test_environment_init_mismatched_lengths_raises_error(self) -> None:
        """Test initialization with mismatched lengths raises ConfigError."""
        observations = [[Decimal("1")], [Decimal("2")]]
        close_prices = [Decimal("100")]  # Length mismatch
        timestamps_utc = [datetime(2024, 1, 1, 9, 30, tzinfo=UTC)]
        with pytest.raises(ConfigError, match="equal length"):
            TradingEnvironment(observations, close_prices, timestamps_utc)

    def test_environment_reset(self) -> None:
        """Test environment reset."""
        observations = [[Decimal("1")], [Decimal("2")]]
        close_prices = [Decimal("100"), Decimal("101")]
        timestamps_utc = [
            datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
            datetime(2024, 1, 1, 9, 31, tzinfo=UTC),
        ]
        env = TradingEnvironment(observations, close_prices, timestamps_utc)
        obs, info = env.reset()
        assert obs == [Decimal("1")]
        assert "seed" in info

    def test_environment_step_valid_action(self) -> None:
        """Test environment step with valid action."""
        observations = [[Decimal("1")], [Decimal("2")]]
        close_prices = [Decimal("100"), Decimal("101")]
        timestamps_utc = [
            datetime(2024, 1, 1, 4, 0, tzinfo=UTC),  # 09:30 IST - In session
            datetime(2024, 1, 1, 4, 1, tzinfo=UTC),
        ]
        env = TradingEnvironment(observations, close_prices, timestamps_utc)
        env.reset()
        obs, reward, done, truncated, info = env.step(1)
        assert obs == [Decimal("2")]
        assert isinstance(reward, Decimal)
        assert done is True  # Terminal state
        assert truncated is False
        assert info["in_session"] == "1"

    def test_environment_step_invalid_action_raises_error(self) -> None:
        """Test step with invalid action raises ConfigError."""
        observations = [[Decimal("1")], [Decimal("2")]]
        close_prices = [Decimal("100"), Decimal("101")]
        timestamps_utc = [
            datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
            datetime(2024, 1, 1, 9, 31, tzinfo=UTC),
        ]
        env = TradingEnvironment(observations, close_prices, timestamps_utc)
        env.reset()
        with pytest.raises(ConfigError, match="must be 0, 1, or 2"):
            env.step(5)

    def test_environment_auto_square_off(self) -> None:
        """Test auto square-off at end of day."""
        observations = [[Decimal("1")], [Decimal("2")]]
        close_prices = [Decimal("100"), Decimal("101")]
        timestamps_utc = [
            datetime(2024, 1, 1, 9, 45, tzinfo=UTC),  # Before square-off
            datetime(2024, 1, 1, 9, 50, tzinfo=UTC),  # 15:20 IST - After square-off
        ]
        env = TradingEnvironment(observations, close_prices, timestamps_utc)
        env.reset()
        obs, reward, done, truncated, info = env.step(1)
        assert info["auto_square_off"] == "1"


class TestValidateInputs:
    """Test _validate_inputs function."""

    def test_validate_inputs_valid(self) -> None:
        """Test validation with valid inputs."""
        observations = [[Decimal("1")], [Decimal("2")]]
        close_prices = [Decimal("100"), Decimal("101")]
        timestamps_utc = [
            datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
            datetime(2024, 1, 1, 9, 31, tzinfo=UTC),
        ]
        _validate_inputs(observations, close_prices, timestamps_utc)  # Should not raise

    def test_validate_inputs_mismatched_lengths(self) -> None:
        """Test validation with mismatched lengths raises ConfigError."""
        observations = [[Decimal("1")], [Decimal("2")]]
        close_prices = [Decimal("100")]  # Length mismatch
        timestamps_utc = [datetime(2024, 1, 1, 9, 30, tzinfo=UTC)]
        with pytest.raises(ConfigError, match="equal length"):
            _validate_inputs(observations, close_prices, timestamps_utc)

    def test_validate_inputs_insufficient_timesteps(self) -> None:
        """Test validation with insufficient timesteps raises ConfigError."""
        observations = [[Decimal("1")]]  # Only 1 timestep
        close_prices = [Decimal("100")]
        timestamps_utc = [datetime(2024, 1, 1, 9, 30, tzinfo=UTC)]
        with pytest.raises(ConfigError, match="at least two timesteps"):
            _validate_inputs(observations, close_prices, timestamps_utc)

    def test_validate_inputs_empty_observation_row(self) -> None:
        """Test validation with empty observation row raises ConfigError."""
        observations = [[], [Decimal("2")]]  # Empty first row
        close_prices = [Decimal("100"), Decimal("101")]
        timestamps_utc = [
            datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
            datetime(2024, 1, 1, 9, 31, tzinfo=UTC),
        ]
        with pytest.raises(ConfigError, match="must contain at least one feature"):
            _validate_inputs(observations, close_prices, timestamps_utc)

    def test_validate_inputs_non_utc_timestamp(self) -> None:
        """Test validation with non-UTC timestamp raises ConfigError."""
        observations = [[Decimal("1")], [Decimal("2")]]
        close_prices = [Decimal("100"), Decimal("101")]
        timestamps_utc = [
            datetime(2024, 1, 1, 9, 30),  # noqa: DTZ001 Naive datetime for error test
            datetime(2024, 1, 1, 9, 31, tzinfo=UTC),
        ]
        with pytest.raises(ConfigError, match="timezone-aware UTC"):
            _validate_inputs(observations, close_prices, timestamps_utc)


class TestValidateAction:
    """Test _validate_action function."""

    def test_validate_action_valid(self) -> None:
        """Test validation with valid actions."""
        for action in [0, 1, 2]:
            _validate_action(action)  # Should not raise

    def test_validate_action_invalid(self) -> None:
        """Test validation with invalid action raises ConfigError."""
        with pytest.raises(ConfigError, match="must be 0, 1, or 2"):
            _validate_action(3)
        with pytest.raises(ConfigError, match="must be 0, 1, or 2"):
            _validate_action(-1)


class TestNextPosition:
    """Test _next_position function."""

    def test_next_position_hold(self) -> None:
        """Test hold action keeps position."""
        assert _next_position(0, 0, True) == 0
        assert _next_position(0, 1, True) == 1
        assert _next_position(0, -1, True) == -1

    def test_next_position_buy(self) -> None:
        """Test buy action sets position to long."""
        assert _next_position(1, 0, True) == 1
        assert _next_position(1, 1, True) == 1
        assert _next_position(1, -1, True) == 1

    def test_next_position_sell(self) -> None:
        """Test sell action sets position to short."""
        assert _next_position(2, 0, True) == -1
        assert _next_position(2, 1, True) == -1
        assert _next_position(2, -1, True) == -1

    def test_next_position_not_tradable(self) -> None:
        """Test position unchanged when not tradable."""
        assert _next_position(0, 1, False) == 1
        assert _next_position(1, 1, False) == 1
        assert _next_position(2, 1, False) == 1


class TestMustAutoSquareOff:
    """Test _must_auto_square_off function."""

    def test_must_auto_square_off_intraday_true(self) -> None:
        """Test auto square-off for intraday environment."""
        config = EnvironmentConfig(intraday=True, auto_square_off_ist=time(15, 10))
        # IST = UTC + 5:30, so 15:10 IST = 09:40 UTC
        before = datetime(2024, 1, 1, 9, 35, tzinfo=UTC)  # 15:05 IST (before 15:10)
        assert not _must_auto_square_off(before, config)
        after = datetime(2024, 1, 1, 9, 45, tzinfo=UTC)  # 15:15 IST (after 15:10)
        assert _must_auto_square_off(after, config)

    def test_must_auto_square_off_intraday_false(self) -> None:
        """Test no auto square-off for non-intraday environment."""
        config = EnvironmentConfig(intraday=False)
        stamp = datetime(2024, 1, 1, 9, 45, tzinfo=UTC)
        assert not _must_auto_square_off(stamp, config)


class TestStepReward:
    """Test _step_reward function."""

    def test_step_reward_long(self) -> None:
        """Test step reward for long position."""
        close_prices = [Decimal("100"), Decimal("105")]
        config = EnvironmentConfig()
        reward = _step_reward(close_prices, 0, 1, config)
        assert reward == Decimal("5")  # 105 - 100

    def test_step_reward_short(self) -> None:
        """Test step reward for short position."""
        close_prices = [Decimal("100"), Decimal("95")]
        config = EnvironmentConfig()
        reward = _step_reward(close_prices, 0, -1, config)
        assert reward == Decimal("5")  # (95 - 100) * -1

    def test_step_reward_flat(self) -> None:
        """Test step reward for flat position."""
        close_prices = [Decimal("100"), Decimal("105")]
        config = EnvironmentConfig()
        reward = _step_reward(close_prices, 0, 0, config)
        assert reward == Decimal("0")


class TestTransactionCost:
    """Test _transaction_cost function."""

    def test_transaction_cost_calculated(self) -> None:
        """Test transaction cost calculation."""
        config = EnvironmentConfig(trade_notional=Decimal("10000"))
        cost = _transaction_cost(config)
        assert isinstance(cost, Decimal)
        assert cost > Decimal("0")


class TestEffectiveLotSize:
    """Test _effective_lot_size function."""

    def test_effective_lot_size_nse(self) -> None:
        """Test effective lot size for NSE."""
        config = EnvironmentConfig(exchange=Exchange.NSE, lot_size=Decimal("5"))
        lot_size = _effective_lot_size(config)
        assert lot_size == Decimal("5")

    def test_effective_lot_size_mcx(self) -> None:
        """Test effective lot size for MCX."""
        config = EnvironmentConfig(
            exchange=Exchange.MCX, lot_size=Decimal("5"), mcx_lot_size=Decimal("50")
        )
        lot_size = _effective_lot_size(config)
        assert lot_size == Decimal("50")


class TestStepInfo:
    """Test _step_info function."""

    def test_step_info(self) -> None:
        """Test step info dictionary."""
        info = _step_info(5, True, False)
        assert info["index"] == "5"
        assert info["in_session"] == "1"
        assert info["auto_square_off"] == "0"
