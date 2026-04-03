from decimal import Decimal

from iatb.rl.reward import pnl_reward, sharpe_reward, sortino_reward


def test_pnl_reward_subtracts_costs() -> None:
    assert pnl_reward(Decimal("125.5"), costs=Decimal("5.5")) == Decimal("120.0")


def test_sharpe_reward_returns_positive_for_consistent_positive_returns() -> None:
    returns = [Decimal("0.01"), Decimal("0.015"), Decimal("0.012"), Decimal("0.011")]
    reward = sharpe_reward(returns)
    assert reward > Decimal("0")


def test_sortino_reward_penalizes_downside_and_supports_empty_input() -> None:
    mixed = [Decimal("0.02"), Decimal("-0.01"), Decimal("0.01"), Decimal("-0.005")]
    reward = sortino_reward(mixed, costs=Decimal("0.1"))
    assert reward < Decimal("10")
    assert sortino_reward([]) == Decimal("0")


def test_sharpe_reward_handles_empty_and_zero_dispersion() -> None:
    assert sharpe_reward([], costs=Decimal("0.3")) == Decimal("-0.3")
    flat = [Decimal("0.01"), Decimal("0.01"), Decimal("0.01")]
    assert sharpe_reward(flat, costs=Decimal("0.2")) == Decimal("-0.2")


def test_sortino_reward_without_downside_uses_mean_scaling() -> None:
    positive_only = [Decimal("0.01"), Decimal("0.02"), Decimal("0.015")]
    assert sortino_reward(positive_only) > Decimal("0")
