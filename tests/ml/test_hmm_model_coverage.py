"""Coverage tests for iatb.ml.hmm_model - HMMRegimeModel and helpers."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.hmm_model import (
    HMMConfig,
    HMMRegimeModel,
    _nearest_state,
    _state_label,
    _validate_observations,
)


class TestHMMConfig:
    def test_defaults(self) -> None:
        config = HMMConfig()
        assert config.n_components == 3

    def test_custom_n_components(self) -> None:
        config = HMMConfig(n_components=5)
        assert config.n_components == 5


class TestNearestState:
    def test_first_centroid(self) -> None:
        centroids = (Decimal("-1"), Decimal("0"), Decimal("1"))
        assert _nearest_state(Decimal("-0.9"), centroids) == 0

    def test_second_centroid(self) -> None:
        centroids = (Decimal("-1"), Decimal("0"), Decimal("1"))
        assert _nearest_state(Decimal("0.1"), centroids) == 1

    def test_third_centroid(self) -> None:
        centroids = (Decimal("-1"), Decimal("0"), Decimal("1"))
        assert _nearest_state(Decimal("0.9"), centroids) == 2

    def test_exact_centroid_match(self) -> None:
        centroids = (Decimal("-1"), Decimal("0"), Decimal("1"))
        assert _nearest_state(Decimal("0"), centroids) == 1


class TestStateLabel:
    def test_state_zero_is_bear(self) -> None:
        assert _state_label(0) == "BEAR"

    def test_state_one_is_sideways(self) -> None:
        assert _state_label(1) == "SIDEWAYS"

    def test_state_two_is_bull(self) -> None:
        assert _state_label(2) == "BULL"

    def test_state_three_is_bull(self) -> None:
        assert _state_label(3) == "BULL"


class TestValidateObservations:
    def test_empty_observations_raises(self) -> None:
        with pytest.raises(ConfigError, match="observations cannot be empty"):
            _validate_observations([])

    def test_empty_row_raises(self) -> None:
        with pytest.raises(ConfigError, match="observation rows cannot be empty"):
            _validate_observations([[Decimal("1")], []])

    def test_valid_observations_pass(self) -> None:
        _validate_observations([[Decimal("1"), Decimal("2")]])


class TestHMMRegimeModel:
    def test_init_defaults(self) -> None:
        model = HMMRegimeModel()
        assert model._config.n_components == 3
        assert model._initialized is False
        assert model._fitted is False

    def test_predict_regime_before_fit_raises(self) -> None:
        model = HMMRegimeModel()
        model._fitted = False
        with pytest.raises(ConfigError, match="fitted before predict_regime"):
            model.predict_regime([Decimal("1")])

    def test_predict_regime_empty_features_raises(self) -> None:
        model = HMMRegimeModel()
        model._fitted = True
        with pytest.raises(ConfigError, match="features cannot be empty"):
            model.predict_regime([])

    def test_predict_regime_returns_valid_label(self) -> None:
        model = HMMRegimeModel()
        model._fitted = True
        model._centroids = (Decimal("-1"), Decimal("0"), Decimal("1"))
        label = model.predict_regime([Decimal("0.5")])
        assert label in {"BEAR", "SIDEWAYS", "BULL"}

    def test_predict_regime_bear_label(self) -> None:
        model = HMMRegimeModel()
        model._fitted = True
        model._centroids = (Decimal("-10"), Decimal("0"), Decimal("10"))
        label = model.predict_regime([Decimal("-9")])
        assert label == "BEAR"

    def test_predict_regime_bull_label(self) -> None:
        model = HMMRegimeModel()
        model._fitted = True
        model._centroids = (Decimal("-10"), Decimal("0"), Decimal("10"))
        label = model.predict_regime([Decimal("9")])
        assert label == "BULL"

    def test_load_hmmlearn_missing_raises(self) -> None:
        import iatb.ml.hmm_model as hmm_mod

        original = hmm_mod.importlib.import_module

        def _fake_import(name: str) -> object:
            raise ModuleNotFoundError(name)

        hmm_mod.importlib.import_module = _fake_import
        try:
            with pytest.raises(ConfigError, match="hmmlearn dependency"):
                hmm_mod._load_hmmlearn()
        finally:
            hmm_mod.importlib.import_module = original
