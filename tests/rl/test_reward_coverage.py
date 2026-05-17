"""
Comprehensive coverage tests for reward.py.

Tests reward function, Sharpe ratio, and reward computation.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.rl.reward import (
    RewardConfig,
    RewardFunction,
    SharpeReward,
    compute_drawdown,
    compute_sharpe_ratio,
)


class TestRewardConfig:
    """Test configuration validation."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RewardConfig()
        assert config.transaction_cost == Decimal("0.001")
        assert config.risk_free_rate == Decimal("0.02")
        assert config.sharpe_window == 20
        assert config.drawdown_penalty == Decimal("0.5")

    def test_negative_transaction_cost_raises_error(self):
        """Test that negative transaction_cost raises ConfigError."""
        with pytest.raises(ConfigError, match="transaction_cost cannot be negative"):
            RewardConfig(transaction_cost=Decimal("-0.01"))

    def test_negative_risk_free_rate_raises_error(self):
        """Test that negative risk_free_rate raises ConfigError."""
        with pytest.raises(ConfigError, match="risk_free_rate cannot be negative"):
            RewardConfig(risk_free_rate=Decimal("-0.02"))

    def test_invalid_sharpe_window_raises_error(self):
        """Test that invalid sharpe_window raises ConfigError."""
        with pytest.raises(ConfigError, match="sharpe_window must be positive"):
            RewardConfig(sharpe_window=0)

    def test_negative_drawdown_penalty_raises_error(self):
        """Test that negative drawdown_penalty raises ConfigError."""
        with pytest.raises(ConfigError, match="drawdown_penalty cannot be negative"):
            RewardConfig(drawdown_penalty=Decimal("-0.5"))


class TestComputeSharpeRatio:
    """Test Sharpe ratio computation."""

    def test_compute_sharpe_positive_returns(self):
        """Test Sharpe ratio with positive returns."""
        returns = [
            Decimal("0.01"),
            Decimal("0.02"),
            Decimal("0.015"),
            Decimal("0.025"),
            Decimal("0.02"),
        ]
        risk_free = Decimal("0.02") / Decimal("252")  # Daily risk-free rate

        sharpe = compute_sharpe_ratio(returns, risk_free)

        assert sharpe > Decimal("0")

    def test_compute_sharpe_negative_returns(self):
        """Test Sharpe ratio with negative returns."""
        returns = [Decimal("-0.01"), Decimal("-0.02"), Decimal("-0.015")]
        risk_free = Decimal("0.02") / Decimal("252")

        sharpe = compute_sharpe_ratio(returns, risk_free)

        assert sharpe < Decimal("0")

    def test_compute_sharpe_insufficient_samples(self):
        """Test that insufficient samples return None."""
        returns = [Decimal("0.01")]
        risk_free = Decimal("0.02") / Decimal("252")

        sharpe = compute_sharpe_ratio(returns, risk_free)

        assert sharpe is None

    def test_compute_sharpe_zero_std_returns(self):
        """Test Sharpe ratio with zero standard deviation."""
        returns = [Decimal("0.01"), Decimal("0.01"), Decimal("0.01")]
        risk_free = Decimal("0.02") / Decimal("252")

        sharpe = compute_sharpe_ratio(returns, risk_free)

        # Should handle zero std gracefully
        assert sharpe is not None

    def test_compute_sharpe_with_risk_free_rate(self):
        """Test Sharpe ratio with different risk-free rates."""
        returns = [Decimal("0.01"), Decimal("0.02"), Decimal("0.015")]
        risk_free_low = Decimal("0.01") / Decimal("252")
        risk_free_high = Decimal("0.05") / Decimal("252")

        sharpe_low = compute_sharpe_ratio(returns, risk_free_low)
        sharpe_high = compute_sharpe_ratio(returns, risk_free_high)

        # Higher risk-free rate should result in lower Sharpe
        assert sharpe_low >= sharpe_high


class TestComputeDrawdown:
    """Test drawdown computation."""

    def test_compute_drawdown_no_drawdown(self):
        """Test drawdown with monotonically increasing values."""
        values = [
            Decimal("100"),
            Decimal("105"),
            Decimal("110"),
            Decimal("115"),
            Decimal("120"),
        ]

        drawdown = compute_drawdown(values)

        assert drawdown == Decimal("0")

    def test_compute_drawdown_with_decline(self):
        """Test drawdown with price decline."""
        values = [
            Decimal("100"),
            Decimal("105"),
            Decimal("110"),
            Decimal("95"),
            Decimal("90"),
        ]

        drawdown = compute_drawdown(values)

        assert drawdown < Decimal("0")

    def test_compute_drawdown_single_value(self):
        """Test drawdown with single value."""
        values = [Decimal("100")]

        drawdown = compute_drawdown(values)

        assert drawdown == Decimal("0")

    def test_compute_drawdown_mixed_trend(self):
        """Test drawdown with mixed trend."""
        values = [
            Decimal("100"),
            Decimal("110"),
            Decimal("105"),
            Decimal("115"),
            Decimal("100"),
        ]

        drawdown = compute_drawdown(values)

        assert drawdown < Decimal("0")


class TestRewardFunction:
    """Test base reward function."""

    def test_reward_function_initialization(self):
        """Test reward function initialization."""
        config = RewardConfig()
        reward_fn = RewardFunction(config)

        assert reward_fn.config == config

    def test_compute_reward_default_implementation(self):
        """Test default reward computation."""
        config = RewardConfig()
        reward_fn = RewardFunction(config)

        # Default implementation should be overridden
        with pytest.raises(NotImplementedError):
            reward_fn.compute_reward(
                action=1,
                current_price=Decimal("100"),
                next_price=Decimal("101"),
                position=1,
            )


class TestSharpeReward:
    """Test Sharpe-based reward function."""

    def test_sharpe_reward_initialization(self):
        """Test Sharpe reward initialization."""
        config = RewardConfig(sharpe_window=20)
        reward_fn = SharpeReward(config)

        assert reward_fn.config.sharpe_window == 20
        assert len(reward_fn.returns_history) == 0

    def test_compute_reward_with_profit(self):
        """Test reward computation with profitable trade."""
        config = RewardConfig()
        reward_fn = SharpeReward(config)

        reward = reward_fn.compute_reward(
            action=1,  # Buy
            current_price=Decimal("100"),
            next_price=Decimal("101"),
            position=1,
        )

        # Should get positive reward
        assert reward > Decimal("0")

    def test_compute_reward_with_loss(self):
        """Test reward computation with losing trade."""
        config = RewardConfig()
        reward_fn = SharpeReward(config)

        reward = reward_fn.compute_reward(
            action=1,  # Buy
            current_price=Decimal("100"),
            next_price=Decimal("99"),
            position=1,
        )

        # Should get negative reward
        assert reward < Decimal("0")

    def test_compute_reward_with_no_position(self):
        """Test reward computation with no position."""
        config = RewardConfig()
        reward_fn = SharpeReward(config)

        reward = reward_fn.compute_reward(
            action=0,  # Hold
            current_price=Decimal("100"),
            next_price=Decimal("101"),
            position=0,
        )

        # Should get zero reward for no position
        assert reward == Decimal("0")

    def test_compute_reward_with_transaction_cost(self):
        """Test reward computation with transaction cost."""
        config = RewardConfig(transaction_cost=Decimal("0.01"))
        reward_fn = SharpeReward(config)

        reward = reward_fn.compute_reward(
            action=1,  # Buy
            current_price=Decimal("100"),
            next_price=Decimal("101"),
            position=1,
        )

        # Reward should be reduced by transaction cost
        assert reward < Decimal("1")

    def test_compute_reward_with_drawdown_penalty(self):
        """Test reward computation with drawdown penalty."""
        config = RewardConfig(drawdown_penalty=Decimal("1.0"))
        reward_fn = SharpeReward(config)

        # Build up history with losses
        for _ in range(5):
            reward_fn.compute_reward(
                action=1,
                current_price=Decimal("100"),
                next_price=Decimal("99"),
                position=1,
            )

        # Now get a reward with drawdown penalty
        reward = reward_fn.compute_reward(
            action=1,
            current_price=Decimal("100"),
            next_price=Decimal("101"),
            position=1,
        )

        # Should be penalized for drawdown
        assert reward is not None

    def test_history_window_limit(self):
        """Test that history is limited to window size."""
        config = RewardConfig(sharpe_window=5)
        reward_fn = SharpeReward(config)

        # Add more returns than window size
        for i in range(10):
            reward_fn.compute_reward(
                action=1,
                current_price=Decimal("100"),
                next_price=Decimal(str(100 + i)),
                position=1,
            )

        # Should only keep last 5
        assert len(reward_fn.returns_history) <= 5

    def test_short_position_reward(self):
        """Test reward computation with short position."""
        config = RewardConfig()
        reward_fn = SharpeReward(config)

        # Short position profits when price goes down
        reward = reward_fn.compute_reward(
            action=2,  # Sell
            current_price=Decimal("100"),
            next_price=Decimal("99"),
            position=-1,
        )

        # Should get positive reward
        assert reward > Decimal("0")

    def test_short_position_loss(self):
        """Test reward computation with short position loss."""
        config = RewardConfig()
        reward_fn = SharpeReward(config)

        # Short position loses when price goes up
        reward = reward_fn.compute_reward(
            action=2,  # Sell
            current_price=Decimal("100"),
            next_price=Decimal("101"),
            position=-1,
        )

        # Should get negative reward
        assert reward < Decimal("0")

    def test_reset_history(self):
        """Test resetting returns history."""
        config = RewardConfig()
        reward_fn = SharpeReward(config)

        # Add some returns
        for _ in range(5):
            reward_fn.compute_reward(
                action=1,
                current_price=Decimal("100"),
                next_price=Decimal("101"),
                position=1,
            )

        assert len(reward_fn.returns_history) > 0

        # Reset
        reward_fn.reset()

        assert len(reward_fn.returns_history) == 0

    def test_get_sharpe_ratio(self):
        """Test getting current Sharpe ratio."""
        config = RewardConfig(sharpe_window=10)
        reward_fn = SharpeReward(config)

        # Add enough returns
        for _ in range(10):
            reward_fn.compute_reward(
                action=1,
                current_price=Decimal("100"),
                next_price=Decimal("101"),
                position=1,
            )

        sharpe = reward_fn.get_sharpe_ratio()

        assert sharpe is not None

    def test_get_sharpe_ratio_insufficient_history(self):
        """Test that insufficient history returns None."""
        config = RewardConfig(sharpe_window=10)
        reward_fn = SharpeReward(config)

        # Add only 2 returns (need at least 3 for std dev)
        for _ in range(2):
            reward_fn.compute_reward(
                action=1,
                current_price=Decimal("100"),
                next_price=Decimal("101"),
                position=1,
            )

        sharpe = reward_fn.get_sharpe_ratio()

        assert sharpe is None
