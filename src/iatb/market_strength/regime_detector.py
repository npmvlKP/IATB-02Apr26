"""
HMM-based market regime detector (bull/bear/sideways).
"""

import importlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from iatb.core.events import RegimeChangeEvent
from iatb.core.exceptions import ConfigError

logger = logging.getLogger(__name__)


class MarketRegime(StrEnum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"


@dataclass(frozen=True)
class RegimeResult:
    regime: MarketRegime
    confidence: Decimal
    transition_event: RegimeChangeEvent | None


class RegimeDetector:
    """Detect market regime from feature matrix using a 3-state HMM."""

    def __init__(self, model_factory: Callable[[], object] | None = None) -> None:
        self._model_factory = model_factory or self._default_model_factory
        self._last_regime: MarketRegime | None = None

    @staticmethod
    def _default_model_factory() -> object:
        try:
            module = importlib.import_module("hmmlearn.hmm")
        except ModuleNotFoundError as exc:
            msg = "hmmlearn dependency is required for RegimeDetector"
            raise ConfigError(msg) from exc
        return module.GaussianHMM(
            n_components=3,
            covariance_type="diag",
            n_iter=100,
            random_state=42,
        )

    def detect(self, features: Sequence[Sequence[Decimal]]) -> RegimeResult:
        logger.debug(
            "Detecting regime from features",
            extra={"feature_rows": len(features)},
        )
        if len(features) < 3:
            msg = "at least three feature rows are required for regime detection"
            raise ConfigError(msg)
        if any(not row for row in features):
            msg = "feature rows cannot be empty"
            raise ConfigError(msg)
        model = self._model_factory()
        # API boundary: hmmlearn requires float inputs (G7 exception)
        feature_matrix = [[float(value) for value in row] for row in features]
        self._fit_model(model, feature_matrix)
        states = self._predict_states(model, feature_matrix)
        regime = self._map_state_to_regime(features, states[-1], states)
        event = self._create_transition_event(regime)
        confidence = self._estimate_confidence(states)
        self._last_regime = regime
        logger.info(
            "Regime detected",
            extra={
                "regime": regime.value,
                "confidence": str(confidence),
                "transition": event is not None,
            },
        )
        return RegimeResult(regime=regime, confidence=confidence, transition_event=event)

    @staticmethod
    def _fit_model(
        model: object, feature_matrix: Sequence[Sequence[float]]
    ) -> None:  # API boundary type (G7)
        if not hasattr(model, "fit"):
            msg = "HMM model must expose fit()"
            raise ConfigError(msg)
        model.fit(feature_matrix)
        logger.debug("HMM model fitted")

    @staticmethod
    def _predict_states(
        model: object, feature_matrix: Sequence[Sequence[float]]
    ) -> list[int]:  # API boundary type (G7)
        if not hasattr(model, "predict"):
            msg = "HMM model must expose predict()"
            raise ConfigError(msg)
        raw_states = model.predict(feature_matrix)
        states = [int(state) for state in raw_states]
        if not states:
            msg = "HMM predict() returned no states"
            raise ConfigError(msg)
        logger.debug("States predicted", extra={"num_states": len(states)})
        return states

    @staticmethod
    def _map_state_to_regime(
        features: Sequence[Sequence[Decimal]],
        current_state: int,
        states: Sequence[int],
    ) -> MarketRegime:
        state_returns: dict[int, list[Decimal]] = {}
        for state, row in zip(states, features, strict=True):
            state_returns.setdefault(state, []).append(row[0])
        mean_returns = {
            state: sum(values, Decimal("0")) / Decimal(len(values))
            for state, values in state_returns.items()
        }
        bull_state = max(mean_returns, key=lambda state: mean_returns[state])
        bear_state = min(mean_returns, key=lambda state: mean_returns[state])
        if current_state == bull_state:
            return MarketRegime.BULL
        if current_state == bear_state:
            return MarketRegime.BEAR
        return MarketRegime.SIDEWAYS

    def _create_transition_event(self, regime: MarketRegime) -> RegimeChangeEvent | None:
        if self._last_regime is None or self._last_regime == regime:
            return None
        logger.info(
            "Regime transition detected",
            extra={
                "from_regime": self._last_regime.value,
                "to_regime": regime.value,
            },
        )
        return RegimeChangeEvent(
            regime_type=regime.value,
            description=f"Regime transition {self._last_regime.value} -> {regime.value}",
            confidence=Decimal("1.0"),
            metadata={"previous": self._last_regime.value, "current": regime.value},
        )

    @staticmethod
    def _estimate_confidence(states: Sequence[int]) -> Decimal:
        current_state = states[-1]
        matching = sum(1 for state in states if state == current_state)
        confidence = Decimal(matching) / Decimal(len(states))
        return min(Decimal("1"), max(Decimal("0"), confidence))
