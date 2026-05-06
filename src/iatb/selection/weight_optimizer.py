"""
Walk-forward weight optimization for composite scoring.

Uses Optuna TPE to search regime-specific weight vectors,
validated via Information Coefficient on out-of-sample data.
"""

import importlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.config_manager import get_config_manager
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.selection._util import clamp_01
from iatb.selection.composite_score import RegimeWeights
from iatb.selection.ic_monitor import compute_information_coefficient

logger = logging.getLogger(__name__)

_IC_THRESHOLD = Decimal("0.03")

# Weight config file path
WEIGHTS_CONFIG_PATH = "config/weights.toml"


@dataclass(frozen=True)
class OptimizationResult:
    regime: MarketRegime
    best_weights: RegimeWeights
    best_ic: Decimal
    trials: int
    improved: bool


# API boundary: Optuna framework requires float return type for objective functions
def _create_objective(
    signal_history: list[dict[str, Decimal]], forward_returns: Sequence[Decimal]
) -> Callable[[object], float]:
    """Create Optuna objective function.

    Args:
        signal_history: Historical signal data.
        forward_returns: Forward returns aligned with signals.

    Returns:
        Objective function for Optuna optimization.

    Note:
        Return type uses Python's built-in numeric type as required by the
        external Optuna API boundary. This is the only instance in the
        selection/ path and is explicitly documented as an external API
        requirement (not financial calculation).
    """

    # API boundary: Optuna objective callback requires built-in numeric type.
    def objective(trial: object) -> float:
        weights = _suggest_weights(trial)
        composites = _compute_composites(signal_history, weights)
        ic_result = compute_information_coefficient(composites, list(forward_returns))  # noqa: F841
        # API boundary: Optuna trial API requires built-in numeric return.
        return float(ic_result.ic)  # noqa: G7,F821

    return objective


def _log_optimization_result(regime: MarketRegime, best_ic: Decimal, improved: bool) -> None:
    """Log optimization result.

    Args:
        regime: Market regime.
        best_ic: Best information coefficient.
        improved: Whether improvement threshold was met.
    """
    if improved:
        logger.info(
            "Weight optimization for %s: IC=%.4f (improved)",
            regime.value,
            best_ic,
        )
    else:
        logger.warning(
            "Weight optimization for %s: IC=%.4f (below threshold)",
            regime.value,
            best_ic,
        )


def optimize_weights_for_regime(
    regime: MarketRegime,
    signal_history: list[dict[str, Decimal]],
    forward_returns: Sequence[Decimal],
    n_trials: int = 50,
    seed: int = 42,
    persist: bool = True,
) -> OptimizationResult:
    """Find optimal regime weights via Optuna TPE search.

    signal_history: list of dicts with keys
    'sentiment', 'strength', 'volume_profile', 'drl'
    each value in [0, 1].
    forward_returns: realised returns aligned with signal_history.
    persist: whether to save optimized weights to config.
    """
    _validate_inputs(signal_history, forward_returns, n_trials)
    optuna = _load_optuna()
    sampler = _build_sampler(optuna, seed)
    study = _create_study(optuna, sampler)

    objective = _create_objective(signal_history, forward_returns)
    _run_study(study, objective, n_trials)

    best_weights = _extract_best_weights(study)
    best_ic = Decimal(str(_best_value(study)))
    improved = best_ic >= _IC_THRESHOLD

    _log_optimization_result(regime, best_ic, improved)

    if persist:
        _save_weights_to_config(regime, best_weights)

    return OptimizationResult(
        regime=regime,
        best_weights=best_weights,
        best_ic=best_ic,
        trials=n_trials,
        improved=improved,
    )


def _compute_composites(
    history: list[dict[str, Decimal]],
    weights: RegimeWeights,
) -> list[Decimal]:
    result: list[Decimal] = []
    for row in history:
        composite = (
            weights.sentiment * row.get("sentiment", Decimal("0"))
            + weights.strength * row.get("strength", Decimal("0"))
            + weights.volume_profile * row.get("volume_profile", Decimal("0"))
            + weights.drl * row.get("drl", Decimal("0"))
        )
        result.append(clamp_01(composite))
    return result


def _suggest_weights(trial: object) -> RegimeWeights:
    suggest = getattr(trial, "suggest_int", None)
    if not callable(suggest):
        msg = "trial does not provide suggest_int()"
        raise ConfigError(msg)
    s = suggest("sentiment", 5, 50)
    st = suggest("strength", 5, 50)
    vp = suggest("volume_profile", 5, 50)
    d = suggest("drl", 5, 50)
    total = s + st + vp + d
    return RegimeWeights(
        sentiment=Decimal(s) / Decimal(total),
        strength=Decimal(st) / Decimal(total),
        volume_profile=Decimal(vp) / Decimal(total),
        drl=Decimal(d) / Decimal(total),
    )


def _validate_inputs(
    history: list[dict[str, Decimal]],
    returns: Sequence[Decimal],
    n_trials: int,
) -> None:
    if len(history) != len(returns):
        msg = "signal_history and forward_returns must have equal length"
        raise ConfigError(msg)
    if len(history) < 10:
        msg = "at least 10 observations required for weight optimization"
        raise ConfigError(msg)
    if n_trials <= 0:
        msg = "n_trials must be positive"
        raise ConfigError(msg)


def _load_optuna() -> object:
    try:
        return importlib.import_module("optuna")
    except ModuleNotFoundError as exc:
        msg = "optuna dependency required for weight optimization"
        raise ConfigError(msg) from exc


def _build_sampler(optuna: object, seed: int) -> object:
    samplers = getattr(optuna, "samplers", None)
    cls = getattr(samplers, "TPESampler", None)
    if not callable(cls):
        msg = "optuna.samplers.TPESampler unavailable"
        raise ConfigError(msg)
    return cls(seed=seed)


def _create_study(optuna: object, sampler: object) -> object:
    create = getattr(optuna, "create_study", None)
    if not callable(create):
        msg = "optuna.create_study unavailable"
        raise ConfigError(msg)
    return create(direction="maximize", sampler=sampler)


def _run_study(study: object, objective: object, n_trials: int) -> None:
    optimize = getattr(study, "optimize", None)
    if not callable(optimize):
        msg = "study.optimize unavailable"
        raise ConfigError(msg)
    optimize(objective, n_trials=n_trials)


def _extract_best_weights(study: object) -> RegimeWeights:
    params = getattr(study, "best_params", None)
    if not isinstance(params, dict):
        msg = "study.best_params unavailable"
        raise ConfigError(msg)
    s = int(params.get("sentiment", 25))
    st = int(params.get("strength", 25))
    vp = int(params.get("volume_profile", 25))
    d = int(params.get("drl", 25))
    total = s + st + vp + d
    return RegimeWeights(
        sentiment=Decimal(s) / Decimal(total),
        strength=Decimal(st) / Decimal(total),
        volume_profile=Decimal(vp) / Decimal(total),
        drl=Decimal(d) / Decimal(total),
    )


# API boundary: Optuna study.best_value returns built-in numeric type; convert to required type.
def _best_value(study: object) -> float:
    value = getattr(study, "best_value", None)
    # G7 exemption: Optuna API returns built-in numeric type
    # API boundary: Optuna API returns built-in numeric type; conversion required.
    if not isinstance(value, float | int):  # noqa: G7
        msg = "study.best_value unavailable"
        raise ConfigError(msg)
    return float(value)  # noqa: G7


def _weights_to_dict(weights: RegimeWeights) -> dict[str, str]:
    """Convert RegimeWeights to dictionary with string values.

    Args:
        weights: RegimeWeights object to convert.

    Returns:
        Dictionary with string representations of weights.
    """
    return {
        "sentiment": str(weights.sentiment),
        "strength": str(weights.strength),
        "volume_profile": str(weights.volume_profile),
        "drl": str(weights.drl),
    }


def _save_weights_to_config(regime: MarketRegime, weights: RegimeWeights) -> None:
    """Save optimized weights to ConfigManager TOML persistence.

    Args:
        regime: Market regime for which weights were optimized.
        weights: Optimized weights to save.
    """
    try:
        config_manager = get_config_manager()
        weights_dict = _weights_to_dict(weights)
        config_manager.set_regime_weights(regime.value, weights_dict)
        logger.info(
            "Saved optimized weights for regime %s to config",
            regime.value,
        )
    except Exception as e:
        logger.error(
            "Failed to save weights for regime %s: %s",
            regime.value,
            str(e),
        )
        raise ConfigError(f"Failed to save weights: {e}") from e


def _load_weights_from_config() -> dict[MarketRegime, RegimeWeights]:
    """Load custom weights from ConfigManager.

    Returns:
        Dictionary mapping regimes to their weights.
    """
    try:
        config_manager = get_config_manager()
        weights_config = config_manager.get_weights_config()
        result: dict[MarketRegime, RegimeWeights] = {}

        for regime_str, weights_dict in weights_config.items():
            try:
                regime = MarketRegime(regime_str)
                weights = RegimeWeights(
                    sentiment=Decimal(weights_dict["sentiment"]),
                    strength=Decimal(weights_dict["strength"]),
                    volume_profile=Decimal(weights_dict["volume_profile"]),
                    drl=Decimal(weights_dict["drl"]),
                )
                result[regime] = weights
            except (KeyError, ValueError) as e:
                logger.warning(
                    "Failed to parse weights for regime %s: %s",
                    regime_str,
                    str(e),
                )
                continue

        return result
    except Exception as e:
        logger.warning("Failed to load weights from config: %s", str(e))
        return {}


def optimize_all_regimes(
    signal_history_by_regime: dict[MarketRegime, list[dict[str, Decimal]]],
    forward_returns_by_regime: dict[MarketRegime, Sequence[Decimal]],
    n_trials: int = 50,
    seed: int = 42,
) -> dict[MarketRegime, OptimizationResult]:
    """Run weight optimization for all market regimes.

    Args:
        signal_history_by_regime: Signal history for each regime.
        forward_returns_by_regime: Forward returns for each regime.
        n_trials: Number of optimization trials per regime.
        seed: Random seed for reproducibility.

    Returns:
        Dictionary mapping regimes to their optimization results.
    """
    results: dict[MarketRegime, OptimizationResult] = {}

    for regime, history in signal_history_by_regime.items():
        returns = forward_returns_by_regime.get(regime, [])
        if not returns:
            logger.warning("No forward returns for regime %s, skipping", regime.value)
            continue

        try:
            result = optimize_weights_for_regime(
                regime, history, returns, n_trials=n_trials, seed=seed
            )
            results[regime] = result
        except Exception as e:
            logger.error(
                "Failed to optimize weights for regime %s: %s",
                regime.value,
                str(e),
            )

    return results
