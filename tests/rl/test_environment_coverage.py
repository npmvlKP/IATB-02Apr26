"""
Comprehensive coverage tests for environment.py.

Tests trading environment step/reset, reward calculation, and error paths.
"""

from decimal import Decimal

import pytest
from iatb.rl.environment import (
    TradingEnvironment,
    compute_step_reward,
)


class TestComputeStepReward:
    """Test compute_step_reward function."""

    def test_profitable_step(self) -> None:
        """Test profitable step reward."""
        action = "BUY"
        current_price = Decimal("105")
        previous_price = Decimal("100")

        result = compute_step_reward(action, current_price, previous_price)
        assert result > Decimal("0")

    def test_loss_step(self) -> None:
        """Test loss step reward."""
        action = "BUY"
        current_price = Decimal("95")
        previous_price = Decimal("100")

        result = compute_step_reward(action, current_price, previous_price)
        assert result < Decimal("0")

    def test_hold_action(self) -> None:
        """Test HOLD action reward."""
        action = "HOLD"
        current_price = Decimal("105")
        previous_price = Decimal("100")

        result = compute_step_reward(action, current_price, previous_price)
        assert result == Decimal("0")

    def test_sell_profit(self) -> None:
        """Test SELL action with profit (short position)."""
        action = "SELL"
        current_price = Decimal("95")
        previous_price = Decimal("100")

        result = compute_step_reward(action, current_price, previous_price)
        assert result > Decimal("0")

    def test_sell_loss(self) -> None:
        """Test SELL action with loss."""
        action = "SELL"
        current_price = Decimal("105")
        previous_price = Decimal("100")

        result = compute_step_reward(action, current_price, previous_price)
        assert result < Decimal("0")

    def test_invalid_action(self) -> None:
        """Test with invalid action."""
        action = "INVALID"
        current_price = Decimal("105")
        previous_price = Decimal("100")

        with pytest.raises(ValueError) as exc_info:
            compute_step_reward(action, current_price, previous_price)
        assert "action" in str(exc_info.value).lower()

    def test_zero_price_change(self) -> None:
        """Test with zero price change."""
        action = "BUY"
        current_price = Decimal("100")
        previous_price = Decimal("100")

        result = compute_step_reward(action, current_price, previous_price)
        assert result == Decimal("0")


class TestTradingEnvironment:
    """Test TradingEnvironment class."""

    def test_environment_initialization(self) -> None:
        """Test environment initialization."""
        env = TradingEnvironment()
        assert env is not None

    def test_environment_reset(self) -> None:
        """Test environment reset."""
        env = TradingEnvironment()
        initial_state = env.reset()
        assert initial_state is not None

    def test_environment_step(self) -> None:
        """Test environment step."""
        env = TradingEnvironment()
        env.reset()

        state, reward, done, info = env.step("BUY")
        assert state is not None
        assert isinstance(reward, Decimal)
        assert isinstance(done, bool)
        assert isinstance(info, dict)

    def test_environment_episode_complete(self) -> None:
        """Test episode completion."""
        env = TradingEnvironment(max_steps=5)
        env.reset()

        for _ in range(5):
            state, reward, done, info = env.step("BUY")

        assert done is True

    def test_environment_with_custom_params(self) -> None:
        """Test environment with custom parameters."""
        env = TradingEnvironment(
            initial_balance=Decimal("100000"),
            max_steps=100,
            transaction_cost=Decimal("0.001"),
        )
        assert env.initial_balance == Decimal("100000")
