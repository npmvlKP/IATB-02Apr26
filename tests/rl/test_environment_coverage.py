"""
Comprehensive coverage tests for environment.py.

Tests trading environment step/reset, Gymnasium interface, and state management.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.rl.environment import (
    TradingEnvConfig,
    TradingEnvironment,
    _action_to_order_side,
    _compute_reward_sharpe,
    _discrete_action_space,
    _get_observation,
    _reset_state,
    _validate_environment,
)


class TestValidateEnvironment:
    """Test environment validation."""

    def test_valid_environment(self):
        """Test valid environment."""
        mock_env = MagicMock()
        mock_env.observation_space = MagicMock()
        mock_env.action_space = MagicMock()
        mock_env.spec = MagicMock()

        _validate_environment(mock_env)  # Should not raise

    def test_missing_observation_space_raises_error(self):
        """Test that missing observation_space raises ConfigError."""
        mock_env = MagicMock()
        mock_env.observation_space = None

        with pytest.raises(ConfigError, match="environment missing observation_space"):
            _validate_environment(mock_env)

    def test_missing_action_space_raises_error(self):
        """Test that missing action_space raises ConfigError."""
        mock_env = MagicMock()
        mock_env.observation_space = MagicMock()
        mock_env.action_space = None

        with pytest.raises(ConfigError, match="environment missing action_space"):
            _validate_environment(mock_env)


class TestDiscreteActionSpace:
    """Test discrete action space."""

    def test_discrete_action_space(self):
        """Test creating discrete action space."""
        space = _discrete_action_space(3)
        assert space is not None

    def test_invalid_action_count_raises_error(self):
        """Test that invalid action count raises ConfigError."""
        with pytest.raises(ConfigError, match="n_actions must be positive"):
            _discrete_action_space(0)


class TestActionToOrderSide:
    """Test action to order side conversion."""

    def test_action_0_to_sell(self):
        """Test action 0 converts to sell."""
        with patch("iatb.rl.environment.OrderSide") as mock_order_side:
            _action_to_order_side(0)
            mock_order_side.SELL.assert_called_once()

    def test_action_1_to_hold(self):
        """Test action 1 converts to hold."""
        result = _action_to_order_side(1)
        assert result is None

    def test_action_2_to_buy(self):
        """Test action 2 converts to buy."""
        with patch("iatb.rl.environment.OrderSide") as mock_order_side:
            _action_to_order_side(2)
            mock_order_side.BUY.assert_called_once()

    def test_invalid_action_raises_error(self):
        """Test that invalid action raises ConfigError."""
        with pytest.raises(ConfigError, match="invalid discrete action"):
            _action_to_order_side(5)


class TestResetState:
    """Test state reset."""

    def test_reset_state(self):
        """Test resetting state."""
        config = TradingEnvConfig()
        state = _reset_state(config)

        assert state.position == 0
        assert state.entry_price is None
        assert state.unrealized_pnl == Decimal("0")
        assert state.step_count == 0


class TestComputeRewardSharpe:
    """Test Sharpe-based reward computation."""

    def test_compute_reward_sharpe(self):
        """Test Sharpe reward computation."""
        returns = [Decimal("0.01"), Decimal("0.02"), Decimal("0.015")]
        risk_free = Decimal("0.02") / Decimal("252")

        reward = _compute_reward_sharpe(returns, risk_free)

        assert reward is not None

    def test_compute_reward_sharpe_insufficient_returns(self):
        """Test that insufficient returns return zero."""
        returns = [Decimal("0.01")]
        risk_free = Decimal("0.02") / Decimal("252")

        reward = _compute_reward_sharpe(returns, risk_free)

        assert reward == Decimal("0")


class TestGetObservation:
    """Test observation extraction."""

    def test_get_observation_with_position(self):
        """Test observation with open position."""
        mock_state = MagicMock()
        mock_state.position = 1
        mock_state.entry_price = Decimal("100")
        mock_state.unrealized_pnl = Decimal("5")
        mock_state.step_count = 10

        mock_obs = MagicMock()
        mock_obs.price = Decimal("105")

        obs = _get_observation(mock_state, mock_obs)

        assert obs is not None

    def test_get_observation_without_position(self):
        """Test observation without open position."""
        mock_state = MagicMock()
        mock_state.position = 0
        mock_state.entry_price = None
        mock_state.unrealized_pnl = Decimal("0")
        mock_state.step_count = 5

        mock_obs = MagicMock()
        mock_obs.price = Decimal("100")

        obs = _get_observation(mock_state, mock_obs)

        assert obs is not None


class TestTradingEnvConfig:
    """Test trading environment configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = TradingEnvConfig()
        assert config.max_steps == 1000
        assert config.transaction_cost == Decimal("0.001")
        assert config.sharpe_window == 20


class TestTradingEnvironment:
    """Test trading environment functionality."""

    def test_environment_initialization(self):
        """Test environment initialization."""
        config = TradingEnvConfig()
        mock_data_source = MagicMock()

        env = TradingEnvironment(mock_data_source, config)

        assert env._config == config
        assert env._data_source == mock_data_source

    def test_environment_invalid_raises_error(self):
        """Test that invalid environment raises ConfigError."""
        config = TradingEnvConfig()
        mock_data_source = MagicMock()
        mock_data_source.observation_space = None

        with pytest.raises(ConfigError, match="environment missing observation_space"):
            TradingEnvironment(mock_data_source, config)

    def test_reset(self):
        """Test environment reset."""
        config = TradingEnvConfig()
        mock_data_source = MagicMock()
        mock_data_source.observation_space = MagicMock()
        mock_data_source.action_space = MagicMock()
        mock_data_source.reset.return_value = MagicMock(price=Decimal("100"))

        env = TradingEnvironment(mock_data_source, config)

        obs, info = env.reset(seed=42)

        assert obs is not None
        assert info is not None
        assert env.state.position == 0

    def test_step_buy(self):
        """Test step with buy action."""
        config = TradingEnvConfig()
        mock_data_source = MagicMock()
        mock_data_source.observation_space = MagicMock()
        mock_data_source.action_space = MagicMock()
        mock_data_source.reset.return_value = MagicMock(price=Decimal("100"))
        mock_data_source.step.return_value = (
            MagicMock(price=Decimal("105")),
            {},
            False,
            False,
            {},
        )

        env = TradingEnvironment(mock_data_source, config)
        env.reset()

        obs, reward, terminated, truncated, info = env.step(2)  # Buy

        assert obs is not None
        assert env.state.position == 1

    def test_step_sell(self):
        """Test step with sell action."""
        config = TradingEnvConfig()
        mock_data_source = MagicMock()
        mock_data_source.observation_space = MagicMock()
        mock_data_source.action_space = MagicMock()
        mock_data_source.reset.return_value = MagicMock(price=Decimal("100"))
        mock_data_source.step.return_value = (
            MagicMock(price=Decimal("105")),
            {},
            False,
            False,
            {},
        )

        env = TradingEnvironment(mock_data_source, config)
        env.reset()

        obs, reward, terminated, truncated, info = env.step(0)  # Sell

        assert obs is not None
        assert env.state.position == -1

    def test_step_hold(self):
        """Test step with hold action."""
        config = TradingEnvConfig()
        mock_data_source = MagicMock()
        mock_data_source.observation_space = MagicMock()
        mock_data_source.action_space = MagicMock()
        mock_data_source.reset.return_value = MagicMock(price=Decimal("100"))
        mock_data_source.step.return_value = (
            MagicMock(price=Decimal("105")),
            {},
            False,
            False,
            {},
        )

        env = TradingEnvironment(mock_data_source, config)
        env.reset()

        obs, reward, terminated, truncated, info = env.step(1)  # Hold

        assert obs is not None
        assert env.state.position == 0

    def test_step_terminated_at_max_steps(self):
        """Test that environment terminates at max_steps."""
        config = TradingEnvConfig(max_steps=2)
        mock_data_source = MagicMock()
        mock_data_source.observation_space = MagicMock()
        mock_data_source.action_space = MagicMock()
        mock_data_source.reset.return_value = MagicMock(price=Decimal("100"))
        mock_data_source.step.return_value = (
            MagicMock(price=Decimal("105")),
            {},
            False,
            False,
            {},
        )

        env = TradingEnvironment(mock_data_source, config)
        env.reset()

        env.step(1)  # Step 1
        obs, reward, terminated, truncated, info = env.step(1)  # Step 2

        assert terminated is True or truncated is True

    def test_compute_pnl_long_position(self):
        """Test PnL computation for long position."""
        config = TradingEnvConfig()
        mock_data_source = MagicMock()
        mock_data_source.observation_space = MagicMock()
        mock_data_source.action_space = MagicMock()
        mock_data_source.reset.return_value = MagicMock(price=Decimal("100"))
        mock_data_source.step.return_value = (
            MagicMock(price=Decimal("105")),
            {},
            False,
            False,
            {},
        )

        env = TradingEnvironment(mock_data_source, config)
        env.reset()

        # Buy at 100
        env.step(2)

        # Step to 105
        obs, reward, terminated, truncated, info = env.step(1)

        assert env.state.unrealized_pnl > Decimal("0")

    def test_compute_pnl_short_position(self):
        """Test PnL computation for short position."""
        config = TradingEnvConfig()
        mock_data_source = MagicMock()
        mock_data_source.observation_space = MagicMock()
        mock_data_source.action_space = MagicMock()
        mock_data_source.reset.return_value = MagicMock(price=Decimal("100"))
        mock_data_source.step.return_value = (
            MagicMock(price=Decimal("95")),
            {},
            False,
            False,
            {},
        )

        env = TradingEnvironment(mock_data_source, config)
        env.reset()

        # Sell at 100
        env.step(0)

        # Step to 95
        obs, reward, terminated, truncated, info = env.step(1)

        assert env.state.unrealized_pnl > Decimal("0")

    def test_close_position(self):
        """Test closing position."""
        config = TradingEnvConfig()
        mock_data_source = MagicMock()
        mock_data_source.observation_space = MagicMock()
        mock_data_source.action_space = MagicMock()
        mock_data_source.reset.return_value = MagicMock(price=Decimal("100"))
        mock_data_source.step.return_value = (
            MagicMock(price=Decimal("105")),
            {},
            False,
            False,
            {},
        )

        env = TradingEnvironment(mock_data_source, config)
        env.reset()

        # Buy
        env.step(2)
        assert env.state.position == 1

        # Close position (sell)
        env.step(0)
        assert env.state.position == -1

    def test_observation_space(self):
        """Test observation space property."""
        config = TradingEnvConfig()
        mock_data_source = MagicMock()
        mock_data_source.observation_space = MagicMock()
        mock_data_source.action_space = MagicMock()
        mock_data_source.spec = MagicMock()

        env = TradingEnvironment(mock_data_source, config)

        assert env.observation_space is not None

    def test_action_space(self):
        """Test action space property."""
        config = TradingEnvConfig()
        mock_data_source = MagicMock()
        mock_data_source.observation_space = MagicMock()
        mock_data_source.action_space = MagicMock()
        mock_data_source.spec = MagicMock()

        env = TradingEnvironment(mock_data_source, config)

        assert env.action_space is not None
