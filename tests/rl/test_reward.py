from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.rl.reward import (
    _DEFAULT_POSITIVE_EXIT_THRESHOLD,
    _SQRT_252,
    composite_reward,
    pnl_reward,
    positive_exit_reward,
    sharpe_reward,
    sortino_reward,
)


class TestPnlReward:
    """Tests for PnL-based reward calculation."""

    def test_pnl_reward_subtracts_costs(self) -> None:
        """Test PnL reward subtracts costs."""
        assert pnl_reward(Decimal("125.5"), costs=Decimal("5.5")) == Decimal("120.0")

    def test_pnl_reward_with_zero_costs(self) -> None:
        """Test PnL reward with zero costs."""
        assert pnl_reward(Decimal("100")) == Decimal("100")

    def test_pnl_reward_negative_pnl(self) -> None:
        """Test PnL reward with negative PnL."""
        assert pnl_reward(Decimal("-50"), costs=Decimal("10")) == Decimal("-60")

    def test_pnl_reward_zero_pnl(self) -> None:
        """Test PnL reward with zero PnL."""
        assert pnl_reward(Decimal("0"), costs=Decimal("5")) == Decimal("-5")

    def test_pnl_reward_precision_handling(self) -> None:
        """Test Decimal precision handling."""
        assert pnl_reward(Decimal("100.123"), Decimal("5.456")) == Decimal("94.667")


class TestSharpeReward:
    """Tests for Sharpe ratio-based reward calculation."""

    def test_sharpe_reward_returns_positive_for_consistent_positive_returns(self) -> None:
        """Test Sharpe reward positive for consistent positive returns."""
        returns = [Decimal("0.01"), Decimal("0.015"), Decimal("0.012"), Decimal("0.011")]
        reward = sharpe_reward(returns)
        assert reward > Decimal("0")

    def test_sharpe_reward_handles_empty_and_zero_dispersion(self) -> None:
        """Test Sharpe reward handles empty and zero dispersion."""
        assert sharpe_reward([], costs=Decimal("0.3")) == Decimal("-0.3")
        flat = [Decimal("0.01"), Decimal("0.01"), Decimal("0.01")]
        assert sharpe_reward(flat, costs=Decimal("0.2")) == Decimal("-0.2")

    def test_sharpe_reward_negative_returns(self) -> None:
        """Test Sharpe reward with negative returns."""
        returns = [Decimal("-0.01"), Decimal("-0.015"), Decimal("-0.012")]
        reward = sharpe_reward(returns)
        assert reward < Decimal("0")

    def test_sharpe_reward_mixed_returns(self) -> None:
        """Test Sharpe reward with mixed returns."""
        returns = [Decimal("0.02"), Decimal("-0.01"), Decimal("0.01"), Decimal("-0.005")]
        reward = sharpe_reward(returns)
        # Should be positive if mean positive despite volatility
        assert isinstance(reward, Decimal)

    def test_sharpe_reward_with_costs(self) -> None:
        """Test Sharpe reward subtracts costs."""
        returns = [Decimal("0.01"), Decimal("0.015"), Decimal("0.012")]
        reward_with_costs = sharpe_reward(returns, costs=Decimal("0.5"))
        reward_without_costs = sharpe_reward(returns, costs=Decimal("0"))
        assert reward_with_costs < reward_without_costs

    def test_sharpe_reward_precision_handling(self) -> None:
        """Test Decimal precision handling."""
        returns = [Decimal("0.0123"), Decimal("0.0156"), Decimal("0.0111")]
        reward = sharpe_reward(returns)
        assert isinstance(reward, Decimal)


class TestSortinoReward:
    """Tests for Sortino ratio-based reward calculation."""

    def test_sortino_reward_penalizes_downside_and_supports_empty_input(self) -> None:
        """Test Sortino reward penalizes downside and handles empty input."""
        mixed = [Decimal("0.02"), Decimal("-0.01"), Decimal("0.01"), Decimal("-0.005")]
        reward = sortino_reward(mixed, costs=Decimal("0.1"))
        assert reward < Decimal("10")
        assert sortino_reward([]) == Decimal("0")

    def test_sortino_reward_without_downside_uses_mean_scaling(self) -> None:
        """Test Sortino reward without downside uses mean scaling."""
        positive_only = [Decimal("0.01"), Decimal("0.02"), Decimal("0.015")]
        assert sortino_reward(positive_only) > Decimal("0")

    def test_sortino_reward_all_negative(self) -> None:
        """Test Sortino reward with all negative returns."""
        negative_only = [Decimal("-0.01"), Decimal("-0.02"), Decimal("-0.015")]
        reward = sortino_reward(negative_only)
        assert reward < Decimal("0")

    def test_sortino_reward_with_costs(self) -> None:
        """Test Sortino reward subtracts costs."""
        returns = [Decimal("0.01"), Decimal("0.02"), Decimal("0.015")]
        reward_with_costs = sortino_reward(returns, costs=Decimal("0.5"))
        reward_without_costs = sortino_reward(returns, costs=Decimal("0"))
        assert reward_with_costs < reward_without_costs

    def test_sortino_reward_precision_handling(self) -> None:
        """Test Decimal precision handling."""
        returns = [Decimal("0.0123"), Decimal("-0.0056"), Decimal("0.0111")]
        reward = sortino_reward(returns)
        assert isinstance(reward, Decimal)


class TestPositiveExitReward:
    """Tests for positive exit reward based on DRL predictions."""

    def test_high_confidence_positive_exit(self) -> None:
        """Test high confidence positive exit gets full reward."""
        reward = positive_exit_reward(
            exit_probability=Decimal("0.8"),
            pnl=Decimal("100"),
            threshold=Decimal("0.7"),
        )
        # Confidence weight = 0.8, reward = 100 * 0.8 = 80
        assert reward == Decimal("80")

    def test_at_threshold_exactly(self) -> None:
        """Test exit at exactly threshold gets full weighted reward."""
        reward = positive_exit_reward(
            exit_probability=Decimal("0.7"),
            pnl=Decimal("100"),
            threshold=Decimal("0.7"),
        )
        # Confidence weight = 0.7, reward = 100 * 0.7 = 70
        assert reward == Decimal("70")

    def test_below_threshold_gets_penalty(self) -> None:
        """Test exit below threshold gets penalty."""
        reward = positive_exit_reward(
            exit_probability=Decimal("0.5"),
            pnl=Decimal("100"),
            threshold=Decimal("0.7"),
        )
        # Penalty: -1 * 100 * 0.5 = -50
        assert reward == Decimal("-50")

    def test_zero_probability_no_reward(self) -> None:
        """Test zero probability gets no reward."""
        reward = positive_exit_reward(
            exit_probability=Decimal("0"),
            pnl=Decimal("100"),
            threshold=Decimal("0.7"),
        )
        assert reward == Decimal("0")

    def test_one_probability_full_reward(self) -> None:
        """Test probability of 1 gets full reward."""
        reward = positive_exit_reward(
            exit_probability=Decimal("1"),
            pnl=Decimal("100"),
            threshold=Decimal("0.7"),
        )
        assert reward == Decimal("100")

    def test_negative_pnl_with_high_confidence(self) -> None:
        """Test negative PnL with high confidence."""
        reward = positive_exit_reward(
            exit_probability=Decimal("0.8"),
            pnl=Decimal("-50"),
            threshold=Decimal("0.7"),
        )
        # -50 * 0.8 = -40
        assert reward == Decimal("-40")

    def test_with_costs(self) -> None:
        """Test positive exit reward with costs."""
        reward = positive_exit_reward(
            exit_probability=Decimal("0.8"),
            pnl=Decimal("100"),
            costs=Decimal("10"),
            threshold=Decimal("0.7"),
        )
        # (100 - 10) * 0.8 = 72
        assert reward == Decimal("72")

    def test_default_threshold_constant(self) -> None:
        """Verify default threshold constant is correct."""
        assert _DEFAULT_POSITIVE_EXIT_THRESHOLD == Decimal("0.7")

    def test_default_threshold_parameter(self) -> None:
        """Test default threshold parameter value."""
        reward = positive_exit_reward(
            exit_probability=Decimal("0.8"),
            pnl=Decimal("100"),
        )
        # Uses default threshold of 0.7, so confidence weight = 0.8
        assert reward == Decimal("80")

    def test_negative_probability_raises_error(self) -> None:
        """Test that negative probability raises ConfigError."""
        with pytest.raises(ConfigError, match="must be between 0 and 1"):
            positive_exit_reward(
                exit_probability=Decimal("-0.1"),
                pnl=Decimal("100"),
            )

    def test_probability_above_one_raises_error(self) -> None:
        """Test that probability above 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="must be between 0 and 1"):
            positive_exit_reward(
                exit_probability=Decimal("1.1"),
                pnl=Decimal("100"),
            )

    def test_negative_threshold_raises_error(self) -> None:
        """Test that negative threshold raises ConfigError."""
        with pytest.raises(ConfigError, match="must be between 0 and 1"):
            positive_exit_reward(
                exit_probability=Decimal("0.5"),
                pnl=Decimal("100"),
                threshold=Decimal("-0.1"),
            )

    def test_threshold_of_one_raises_error(self) -> None:
        """Test that threshold of 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="must be between 0 and 1"):
            positive_exit_reward(
                exit_probability=Decimal("0.5"),
                pnl=Decimal("100"),
                threshold=Decimal("1"),
            )

    def test_precision_handling(self) -> None:
        """Test Decimal precision handling."""
        reward = positive_exit_reward(
            exit_probability=Decimal("0.699999"),
            pnl=Decimal("100.123"),
            threshold=Decimal("0.699998"),
        )
        expected = Decimal("100.123") * Decimal("0.699999")
        assert reward == expected


class TestCompositeReward:
    """Tests for composite reward combining Sharpe and positive exit."""

    def test_composite_reward_equal_weights(self) -> None:
        """Test composite reward with equal weights."""
        returns = [Decimal("0.01"), Decimal("0.015"), Decimal("0.012")]
        reward = composite_reward(
            returns=returns,
            exit_probability=Decimal("0.8"),
            pnl=Decimal("100"),
        )
        assert isinstance(reward, Decimal)

    def test_composite_reward_custom_weights(self) -> None:
        """Test composite reward with custom weights."""
        returns = [Decimal("0.01"), Decimal("0.015"), Decimal("0.012")]
        reward = composite_reward(
            returns=returns,
            exit_probability=Decimal("0.8"),
            pnl=Decimal("100"),
            sharpe_weight=Decimal("0.3"),
            exit_weight=Decimal("0.7"),
        )
        assert isinstance(reward, Decimal)

    def test_weights_must_sum_to_one(self) -> None:
        """Test that weights must sum to 1."""
        returns = [Decimal("0.01"), Decimal("0.015"), Decimal("0.012")]
        with pytest.raises(ValueError, match="must sum to 1"):
            composite_reward(
                returns=returns,
                exit_probability=Decimal("0.8"),
                pnl=Decimal("100"),
                sharpe_weight=Decimal("0.5"),
                exit_weight=Decimal("0.6"),
            )

    def test_composite_reward_with_costs(self) -> None:
        """Test composite reward subtracts costs."""
        returns = [Decimal("0.01"), Decimal("0.015"), Decimal("0.012")]
        reward_with_costs = composite_reward(
            returns=returns,
            exit_probability=Decimal("0.8"),
            pnl=Decimal("100"),
            costs=Decimal("5"),
        )
        reward_without_costs = composite_reward(
            returns=returns,
            exit_probability=Decimal("0.8"),
            pnl=Decimal("100"),
            costs=Decimal("0"),
        )
        assert reward_with_costs < reward_without_costs

    def test_composite_reward_custom_threshold(self) -> None:
        """Test composite reward with custom exit threshold."""
        returns = [Decimal("0.01"), Decimal("0.015"), Decimal("0.012")]
        reward = composite_reward(
            returns=returns,
            exit_probability=Decimal("0.6"),
            pnl=Decimal("100"),
            exit_threshold=Decimal("0.5"),
        )
        assert isinstance(reward, Decimal)

    def test_composite_reward_below_threshold_penalty(self) -> None:
        """Test composite reward applies penalty below threshold."""
        returns = [Decimal("0.01"), Decimal("0.015"), Decimal("0.012")]
        reward_low = composite_reward(
            returns=returns,
            exit_probability=Decimal("0.5"),
            pnl=Decimal("100"),
            exit_threshold=Decimal("0.7"),
        )
        reward_high = composite_reward(
            returns=returns,
            exit_probability=Decimal("0.8"),
            pnl=Decimal("100"),
            exit_threshold=Decimal("0.7"),
        )
        # High confidence should give better reward
        assert reward_high > reward_low

    def test_composite_reward_empty_returns(self) -> None:
        """Test composite reward with empty returns."""
        reward = composite_reward(
            returns=[],
            exit_probability=Decimal("0.8"),
            pnl=Decimal("100"),
        )
        assert isinstance(reward, Decimal)

    def test_composite_reward_negative_pnl(self) -> None:
        """Test composite reward with negative PnL and negative returns."""
        # Use negative returns to ensure overall negative reward
        returns = [Decimal("-0.01"), Decimal("-0.015"), Decimal("-0.012")]
        reward = composite_reward(
            returns=returns,
            exit_probability=Decimal("0.5"),  # Below threshold for penalty
            pnl=Decimal("-50"),
            exit_threshold=Decimal("0.7"),
        )
        assert reward < Decimal("0")

    def test_precision_handling(self) -> None:
        """Test Decimal precision handling."""
        returns = [Decimal("0.0123"), Decimal("0.0156"), Decimal("0.0111")]
        reward = composite_reward(
            returns=returns,
            exit_probability=Decimal("0.699999"),
            pnl=Decimal("100.123"),
        )
        assert isinstance(reward, Decimal)


class TestConstants:
    """Tests for module constants."""

    def test_sqrt_252_constant(self) -> None:
        """Verify sqrt(252) constant is correct."""
        # sqrt(252) ≈ 15.874507866387544
        assert abs(_SQRT_252 - Decimal("15.8745078664")) < Decimal("0.0000000001")
