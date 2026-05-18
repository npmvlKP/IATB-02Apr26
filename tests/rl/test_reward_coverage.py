"""
Comprehensive coverage tests for reward.py.

Tests reward function, Sharpe ratio computation, and error paths.
"""

from decimal import Decimal

import pytest
from iatb.rl.reward import (
    compute_reward,
    compute_sharpe_ratio,
    compute_sortino_ratio,
)


class TestComputeReward:
    """Test compute_reward function."""

    def test_basic_reward_computation(self) -> None:
        """Test basic reward computation."""
        action = "BUY"
        price_change = Decimal("0.05")
        confidence = Decimal("0.8")

        result = compute_reward(action, price_change, confidence)
        assert isinstance(result, Decimal)
        assert result >= Decimal("0")

    def test_profitable_buy_action(self) -> None:
        """Test profitable BUY action."""
        action = "BUY"
        price_change = Decimal("0.10")  # 10% gain
        confidence = Decimal("0.9")

        result = compute_reward(action, price_change, confidence)
        # Should be positive reward
        assert result > Decimal("0")

    def test_loss_buy_action(self) -> None:
        """Test loss BUY action."""
        action = "BUY"
        price_change = Decimal("-0.05")  # 5% loss
        confidence = Decimal("0.9")

        result = compute_reward(action, price_change, confidence)
        # Should be negative reward
        assert result < Decimal("0")

    def test_profitable_sell_action(self) -> None:
        """Test profitable SELL action (short)."""
        action = "SELL"
        price_change = Decimal("-0.05")  # Price dropped, profit on short
        confidence = Decimal("0.8")

        result = compute_reward(action, price_change, confidence)
        # Should be positive reward
        assert result > Decimal("0")

    def test_loss_sell_action(self) -> None:
        """Test loss SELL action."""
        action = "SELL"
        price_change = Decimal("0.05")  # Price rose, loss on short
        confidence = Decimal("0.8")

        result = compute_reward(action, price_change, confidence)
        # Should be negative reward
        assert result < Decimal("0")

    def test_hold_action(self) -> None:
        """Test HOLD action."""
        action = "HOLD"
        price_change = Decimal("0.01")
        confidence = Decimal("0.5")

        result = compute_reward(action, price_change, confidence)
        # HOLD should have minimal or no reward
        assert result == Decimal("0")

    def test_high_confidence_multiplier(self) -> None:
        """Test high confidence increases reward magnitude."""
        action = "BUY"
        price_change = Decimal("0.10")

        low_conf_result = compute_reward(action, price_change, Decimal("0.3"))
        high_conf_result = compute_reward(action, price_change, Decimal("0.9"))

        assert high_conf_result > low_conf_result

    def test_zero_price_change(self) -> None:
        """Test with zero price change."""
        action = "BUY"
        price_change = Decimal("0.0")
        confidence = Decimal("0.8")

        result = compute_reward(action, price_change, confidence)
        assert result == Decimal("0")

    def test_invalid_action(self) -> None:
        """Test with invalid action."""
        action = "INVALID"
        price_change = Decimal("0.05")
        confidence = Decimal("0.8")

        with pytest.raises(ValueError) as exc_info:
            compute_reward(action, price_change, confidence)
        assert "action" in str(exc_info.value).lower()

    def test_invalid_confidence_range_high(self) -> None:
        """Test with confidence above 1.0."""
        action = "BUY"
        price_change = Decimal("0.05")
        confidence = Decimal("1.5")

        with pytest.raises(ValueError) as exc_info:
            compute_reward(action, price_change, confidence)
        assert (
            "confidence" in str(exc_info.value).lower()
            or "range" in str(exc_info.value).lower()
        )

    def test_invalid_confidence_range_negative(self) -> None:
        """Test with negative confidence."""
        action = "BUY"
        price_change = Decimal("0.05")
        confidence = Decimal("-0.1")

        with pytest.raises(ValueError) as exc_info:
            compute_reward(action, price_change, confidence)
        assert "confidence" in str(exc_info.value).lower()


class TestComputeSharpeRatio:
    """Test compute_sharpe_ratio function."""

    def test_positive_sharpe(self) -> None:
        """Test positive Sharpe ratio."""
        returns = [Decimal("0.05"), Decimal("0.03"), Decimal("0.04"), Decimal("0.06")]
        risk_free_rate = Decimal("0.02")

        result = compute_sharpe_ratio(returns, risk_free_rate)
        assert result > Decimal("0")

    def test_negative_sharpe(self) -> None:
        """Test negative Sharpe ratio."""
        returns = [Decimal("-0.02"), Decimal("-0.03"), Decimal("-0.01")]
        risk_free_rate = Decimal("0.02")

        result = compute_sharpe_ratio(returns, risk_free_rate)
        assert result < Decimal("0")

    def test_zero_volatility(self) -> None:
        """Test with zero volatility (constant returns)."""
        returns = [Decimal("0.05"), Decimal("0.05"), Decimal("0.05")]
        risk_free_rate = Decimal("0.02")

        result = compute_sharpe_ratio(returns, risk_free_rate)
        # Should handle division by zero
        assert isinstance(result, Decimal)

    def test_single_return(self) -> None:
        """Test with single return."""
        returns = [Decimal("0.05")]
        risk_free_rate = Decimal("0.02")

        result = compute_sharpe_ratio(returns, risk_free_rate)
        # Should handle single value
        assert isinstance(result, Decimal)

    def test_empty_returns(self) -> None:
        """Test with empty returns."""
        returns: list[Decimal] = []
        risk_free_rate = Decimal("0.02")

        result = compute_sharpe_ratio(returns, risk_free_rate)
        # Should return 0 or handle gracefully
        assert isinstance(result, Decimal)

    def test_high_sharpe(self) -> None:
        """Test high Sharpe ratio (good performance)."""
        returns = [Decimal("0.10"), Decimal("0.12"), Decimal("0.11"), Decimal("0.13")]
        risk_free_rate = Decimal("0.02")

        result = compute_sharpe_ratio(returns, risk_free_rate)
        assert result > Decimal("1.0")

    def test_decimal_precision(self) -> None:
        """Test Decimal precision handling."""
        returns = [Decimal("0.123456789"), Decimal("0.234567890")]
        risk_free_rate = Decimal("0.01")

        result = compute_sharpe_ratio(returns, risk_free_rate)
        # Should maintain precision
        assert isinstance(result, Decimal)


class TestComputeSortinoRatio:
    """Test compute_sortino_ratio function."""

    def test_positive_sortino(self) -> None:
        """Test positive Sortino ratio."""
        returns = [Decimal("0.05"), Decimal("0.03"), Decimal("0.04"), Decimal("0.06")]
        risk_free_rate = Decimal("0.02")

        result = compute_sortino_ratio(returns, risk_free_rate)
        assert result > Decimal("0")

    def test_negative_sortino(self) -> None:
        """Test negative Sortino ratio."""
        returns = [Decimal("-0.02"), Decimal("-0.03"), Decimal("-0.01")]
        risk_free_rate = Decimal("0.02")

        result = compute_sortino_ratio(returns, risk_free_rate)
        assert result < Decimal("0")

    def test_zero_downside_volatility(self) -> None:
        """Test with zero downside volatility (all positive returns)."""
        returns = [Decimal("0.05"), Decimal("0.06"), Decimal("0.07")]
        risk_free_rate = Decimal("0.02")

        result = compute_sortino_ratio(returns, risk_free_rate)
        # Should handle division by zero
        assert isinstance(result, Decimal)

    def test_mixed_returns(self) -> None:
        """Test with mixed positive and negative returns."""
        returns = [Decimal("0.10"), Decimal("-0.02"), Decimal("0.05"), Decimal("-0.01")]
        risk_free_rate = Decimal("0.02")

        result = compute_sortino_ratio(returns, risk_free_rate)
        assert isinstance(result, Decimal)

    def test_empty_returns(self) -> None:
        """Test with empty returns."""
        returns: list[Decimal] = []
        risk_free_rate = Decimal("0.02")

        result = compute_sortino_ratio(returns, risk_free_rate)
        # Should return 0 or handle gracefully
        assert isinstance(result, Decimal)
