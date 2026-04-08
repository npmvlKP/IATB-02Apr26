"""
Reward functions for RL training objectives with DRL-predicted
positive exit probability threshold integration.
"""

import logging
from decimal import Decimal

from iatb.core.exceptions import ConfigError

# Optional MLflow tracking integration
try:
    from iatb.ml.tracking import ExperimentTracker, ExperimentMetrics
    _MLFLOW_AVAILABLE = True
except ImportError:
    _MLFLOW_AVAILABLE = False
    _LOGGER.debug("MLflow tracking not available for RL rewards")

_LOGGER = logging.getLogger(__name__)

_SQRT_252 = Decimal("15.8745078664")
_DEFAULT_POSITIVE_EXIT_THRESHOLD = Decimal("0.7")


def pnl_reward(pnl: Decimal, costs: Decimal = Decimal("0")) -> Decimal:
    """Calculate PnL-based reward.

    Args:
        pnl: Profit and loss value.
        costs: Transaction costs (default: 0).

    Returns:
        Reward value (PnL minus costs).
    """
    reward = pnl - costs
    _LOGGER.debug(
        "PnL reward calculated",
        extra={"pnl": str(pnl), "costs": str(costs), "reward": str(reward)},
    )
    return reward


def sharpe_reward(returns: list[Decimal], costs: Decimal = Decimal("0")) -> Decimal:
    """Calculate Sharpe ratio-based reward.

    Args:
        returns: List of return values.
        costs: Transaction costs (default: 0).

    Returns:
        Reward value (annualized Sharpe ratio minus costs).
    """
    if not returns:
        _LOGGER.debug("Empty returns list, returning negative costs")
        return -costs
    mean_return = _mean(returns)
    dispersion = _mean([abs(value - mean_return) for value in returns])
    if dispersion == Decimal("0"):
        _LOGGER.debug("Zero dispersion, returning negative costs")
        return -costs
    reward = (mean_return / dispersion) * _SQRT_252 - costs
    _LOGGER.debug(
        "Sharpe reward calculated",
        extra={
            "num_returns": len(returns),
            "mean_return": str(mean_return),
            "dispersion": str(dispersion),
            "costs": str(costs),
            "reward": str(reward),
        },
    )
    return reward


def sortino_reward(returns: list[Decimal], costs: Decimal = Decimal("0")) -> Decimal:
    """Calculate Sortino ratio-based reward (downside risk only).

    Args:
        returns: List of return values.
        costs: Transaction costs (default: 0).

    Returns:
        Reward value (annualized Sortino ratio minus costs).
    """
    if not returns:
        _LOGGER.debug("Empty returns list, returning negative costs")
        return -costs
    mean_return = _mean(returns)
    downside = [abs(value) for value in returns if value < Decimal("0")]
    downside_risk = _mean(downside) if downside else Decimal("0")
    if downside_risk == Decimal("0"):
        reward = mean_return * _SQRT_252 - costs
        _LOGGER.debug(
            "Zero downside risk, using mean return reward",
            extra={"mean_return": str(mean_return), "reward": str(reward)},
        )
        return reward
    reward = (mean_return / downside_risk) * _SQRT_252 - costs
    _LOGGER.debug(
        "Sortino reward calculated",
        extra={
            "num_returns": len(returns),
            "mean_return": str(mean_return),
            "downside_risk": str(downside_risk),
            "costs": str(costs),
            "reward": str(reward),
        },
    )
    return reward


def _validate_probability_input(exit_probability: Decimal, threshold: Decimal) -> None:
    """Validate probability and threshold inputs.

    Args:
        exit_probability: Predicted probability of positive exit (0-1).
        threshold: Minimum probability threshold.

    Raises:
        ConfigError: If any input is invalid.
    """
    if exit_probability < Decimal("0") or exit_probability > Decimal("1"):
        msg = "exit_probability must be between 0 and 1"
        _LOGGER.error(
            "Invalid exit_probability",
            extra={"exit_probability": str(exit_probability)},
        )
        raise ConfigError(msg)
    if threshold <= Decimal("0") or threshold >= Decimal("1"):
        msg = "threshold must be between 0 and 1 (exclusive of 1)"
        _LOGGER.error(
            "Invalid threshold",
            extra={"threshold": str(threshold)},
        )
        raise ConfigError(msg)


def _apply_low_confidence_penalty(
    base_reward: Decimal,
    exit_probability: Decimal,
    threshold: Decimal,
) -> Decimal:
    """Apply penalty for low-confidence exit signals.

    Args:
        base_reward: Base reward value before penalty.
        exit_probability: Predicted probability of positive exit.
        threshold: Minimum probability threshold.

    Returns:
        Penalized reward value.
    """
    penalty_factor = Decimal("0.5")  # 50% penalty for low confidence
    reward = base_reward * Decimal("-1") * penalty_factor
    _LOGGER.debug(
        "Low-confidence exit penalty applied",
        extra={
            "exit_probability": str(exit_probability),
            "threshold": str(threshold),
            "penalty_factor": str(penalty_factor),
            "reward": str(reward),
        },
    )
    return reward


def positive_exit_reward(
    exit_probability: Decimal,
    pnl: Decimal,
    threshold: Decimal = _DEFAULT_POSITIVE_EXIT_THRESHOLD,
    costs: Decimal = Decimal("0"),
) -> Decimal:
    """Calculate reward based on DRL-predicted positive exit probability.

    Rewards high-confidence positive exits while penalizing low-confidence exits.

    Args:
        exit_probability: Predicted probability of positive exit (0-1).
        pnl: Actual profit and loss value.
        threshold: Minimum probability threshold for positive signal (default: 0.7).
        costs: Transaction costs (default: 0).

    Returns:
        Reward value weighted by exit probability confidence.

    Raises:
        ConfigError: If any input is invalid.
    """
    _validate_probability_input(exit_probability, threshold)

    # Weight PnL by confidence (exit probability)
    confidence_weight = exit_probability if exit_probability >= threshold else Decimal("0")
    base_reward = pnl - costs
    reward = base_reward * confidence_weight

    # Apply penalty for low-confidence exits (below threshold but > 0)
    if Decimal("0") < exit_probability < threshold:
        reward = _apply_low_confidence_penalty(base_reward, exit_probability, threshold)

    _LOGGER.debug(
        "Positive exit reward calculated",
        extra={
            "exit_probability": str(exit_probability),
            "pnl": str(pnl),
            "threshold": str(threshold),
            "costs": str(costs),
            "confidence_weight": str(confidence_weight),
            "reward": str(reward),
        },
    )
    return reward


def _validate_composite_weights(sharpe_weight: Decimal, exit_weight: Decimal) -> None:
    """Validate that reward weights sum to 1.

    Args:
        sharpe_weight: Weight for Sharpe reward.
        exit_weight: Weight for positive exit reward.

    Raises:
        ValueError: If weights don't sum to 1.
    """
    if sharpe_weight + exit_weight != Decimal("1"):
        msg = "sharpe_weight and exit_weight must sum to 1"
        _LOGGER.error(
            "Invalid reward weights",
            extra={"sharpe_weight": str(sharpe_weight), "exit_weight": str(exit_weight)},
        )
        raise ValueError(msg)


def _log_composite_reward_details(
    returns: list[Decimal],
    exit_probability: Decimal,
    pnl: Decimal,
    exit_threshold: Decimal,
    sharpe_weight: Decimal,
    exit_weight: Decimal,
    sharpe: Decimal,
    exit_reward: Decimal,
    costs: Decimal,
    total_reward: Decimal,
) -> None:
    """Log composite reward calculation details.

    Args:
        returns: List of return values.
        exit_probability: Predicted probability of positive exit.
        pnl: Actual profit and loss value.
        exit_threshold: Minimum probability threshold.
        sharpe_weight: Weight for Sharpe reward.
        exit_weight: Weight for positive exit reward.
        sharpe: Calculated Sharpe reward.
        exit_reward: Calculated exit reward.
        costs: Transaction costs.
        total_reward: Final composite reward.
    """
    _LOGGER.info(
        "Composite reward calculated",
        extra={
            "num_returns": len(returns),
            "exit_probability": str(exit_probability),
            "pnl": str(pnl),
            "exit_threshold": str(exit_threshold),
            "sharpe_weight": str(sharpe_weight),
            "exit_weight": str(exit_weight),
            "sharpe": str(sharpe),
            "exit_reward": str(exit_reward),
            "costs": str(costs),
            "total_reward": str(total_reward),
        },
    )


def composite_reward(
    returns: list[Decimal],
    exit_probability: Decimal,
    pnl: Decimal,
    exit_threshold: Decimal = _DEFAULT_POSITIVE_EXIT_THRESHOLD,
    sharpe_weight: Decimal = Decimal("0.5"),
    exit_weight: Decimal = Decimal("0.5"),
    costs: Decimal = Decimal("0"),
) -> Decimal:
    """Calculate composite reward combining Sharpe ratio and positive exit signal.

    Args:
        returns: List of return values for Sharpe calculation.
        exit_probability: Predicted probability of positive exit (0-1).
        pnl: Actual profit and loss value.
        exit_threshold: Minimum probability threshold for positive signal (default: 0.7).
        sharpe_weight: Weight for Sharpe reward (default: 0.5).
        exit_weight: Weight for positive exit reward (default: 0.5).
        costs: Transaction costs (default: 0).

    Returns:
        Weighted composite reward value.

    Raises:
        ConfigError: If any input is invalid.
    """
    _validate_composite_weights(sharpe_weight, exit_weight)

    sharpe = sharpe_reward(returns, Decimal("0"))  # Costs handled at composite level
    exit_reward = positive_exit_reward(exit_probability, pnl, exit_threshold, Decimal("0"))

    # Apply costs once at composite level
    total_reward = (sharpe * sharpe_weight + exit_reward * exit_weight) - costs

    _log_composite_reward_details(
        returns,
        exit_probability,
        pnl,
        exit_threshold,
        sharpe_weight,
        exit_weight,
        sharpe,
        exit_reward,
        costs,
        total_reward,
    )
    return total_reward


def _mean(values: list[Decimal]) -> Decimal:
    """Calculate mean of decimal values.

    Args:
        values: List of decimal values.

    Returns:
        Mean value, or 0 if list is empty.
    """
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))
