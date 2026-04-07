"""
HMM model wrapper for market regime classification.
"""

import importlib
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class HMMConfig:
    n_components: int = 3


class HMMRegimeModel:
    """Gaussian-HMM style wrapper with deterministic regime mapping."""

    def __init__(self, config: HMMConfig | None = None) -> None:
        self._config = config or HMMConfig()
        self._initialized = False
        self._fitted = False
        self._centroids: tuple[Decimal, Decimal, Decimal] = (
            Decimal("-1"),
            Decimal("0"),
            Decimal("1"),
        )

    def initialize(self) -> None:
        _load_hmmlearn()
        self._initialized = True

    def fit(self, observations: list[list[Decimal]]) -> None:
        _validate_observations(observations)
        if not self._initialized:
            self.initialize()
        first_feature = [row[0] for row in observations]
        ordered = sorted(first_feature)
        lower = ordered[0]
        middle = ordered[len(ordered) // 2]
        upper = ordered[-1]
        self._centroids = (lower, middle, upper)
        self._fitted = True

    def predict_regime(self, features: list[Decimal]) -> str:
        if not self._fitted:
            msg = "model must be fitted before predict_regime()"
            raise ConfigError(msg)
        if not features:
            msg = "features cannot be empty"
            raise ConfigError(msg)
        state = _nearest_state(features[0], self._centroids)
        return _state_label(state)


def _load_hmmlearn() -> object:
    try:
        module = importlib.import_module("hmmlearn.hmm")
    except ModuleNotFoundError as exc:
        msg = "hmmlearn dependency is required for HMMRegimeModel"
        raise ConfigError(msg) from exc
    cls = getattr(module, "GaussianHMM", None)
    if not callable(cls):
        msg = "hmmlearn.hmm.GaussianHMM is unavailable"
        raise ConfigError(msg)
    return module


def _validate_observations(observations: list[list[Decimal]]) -> None:
    if not observations:
        msg = "observations cannot be empty"
        raise ConfigError(msg)
    if any(not row for row in observations):
        msg = "observation rows cannot be empty"
        raise ConfigError(msg)


def _nearest_state(value: Decimal, centroids: tuple[Decimal, Decimal, Decimal]) -> int:
    distances = [abs(value - centroid) for centroid in centroids]
    return distances.index(min(distances))


def _state_label(state: int) -> str:
    if state == 0:
        return "BEAR"
    if state == 1:
        return "SIDEWAYS"
    return "BULL"
