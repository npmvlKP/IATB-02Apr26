"""Coverage tests for iatb.ml.base - PredictionResult and Predictor protocol."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult, Predictor, _as_decimal


class TestAsDecimal:
    """Tests for _as_decimal helper function."""

    def test_converts_integer_to_decimal(self) -> None:
        result = _as_decimal(42, "field")
        assert result == Decimal("42")

    def test_converts_float_string_to_decimal(self) -> None:
        result = _as_decimal("3.14", "field")
        assert result == Decimal("3.14")

    def test_converts_decimal_passthrough(self) -> None:
        result = _as_decimal(Decimal("9.99"), "field")
        assert result == Decimal("9.99")

    def test_raises_config_error_on_invalid_string(self) -> None:
        with pytest.raises(ConfigError, match="decimal-compatible"):
            _as_decimal("not_a_number", "test_field")

    def test_raises_config_error_on_nan(self) -> None:
        with pytest.raises(ConfigError, match="must be finite"):
            _as_decimal("NaN", "test_field")

    def test_raises_config_error_on_infinity(self) -> None:
        with pytest.raises(ConfigError, match="must be finite"):
            _as_decimal("Infinity", "test_field")

    def test_raises_config_error_on_negative_infinity(self) -> None:
        with pytest.raises(ConfigError, match="must be finite"):
            _as_decimal("-Infinity", "field")


class TestPredictionResult:
    """Tests for PredictionResult dataclass."""

    def test_valid_creation_with_all_fields(self) -> None:
        result = PredictionResult(
            symbol="RELIANCE",
            score=Decimal("0.75"),
            confidence=Decimal("0.8"),
            regime_label="BULL",
        )
        assert result.symbol == "RELIANCE"
        assert result.score == Decimal("0.75")
        assert result.confidence == Decimal("0.8")
        assert result.regime_label == "BULL"

    def test_valid_creation_with_metadata(self) -> None:
        result = PredictionResult(
            symbol="TCS",
            score=Decimal("1"),
            confidence=Decimal("0.5"),
            regime_label="SIDEWAYS",
            metadata={"key1": "val1", 2: 3},
        )
        assert result.metadata == {"key1": "val1", "2": "3"}

    def test_default_metadata_is_empty_dict(self) -> None:
        result = PredictionResult(
            symbol="INFY",
            score=Decimal("0"),
            confidence=Decimal("0.1"),
            regime_label="BEAR",
        )
        assert result.metadata == {}

    def test_empty_symbol_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="symbol cannot be empty"):
            PredictionResult(
                symbol=" ",
                score=Decimal("0"),
                confidence=Decimal("0"),
                regime_label="BULL",
            )

    def test_empty_regime_label_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="regime_label cannot be empty"):
            PredictionResult(
                symbol="RELIANCE",
                score=Decimal("0"),
                confidence=Decimal("0"),
                regime_label=" ",
            )

    def test_score_coerced_to_decimal(self) -> None:
        result = PredictionResult(
            symbol="RELIANCE",
            score=0.75,
            confidence=Decimal("0.5"),
            regime_label="BULL",
        )
        assert isinstance(result.score, Decimal)

    def test_confidence_coerced_to_decimal(self) -> None:
        result = PredictionResult(
            symbol="RELIANCE",
            score=Decimal("0"),
            confidence=0.5,
            regime_label="BULL",
        )
        assert isinstance(result.confidence, Decimal)

    def test_confidence_zero_boundary(self) -> None:
        result = PredictionResult(
            symbol="RELIANCE",
            score=Decimal("0"),
            confidence=Decimal("0"),
            regime_label="BEAR",
        )
        assert result.confidence == Decimal("0")

    def test_confidence_one_boundary(self) -> None:
        result = PredictionResult(
            symbol="RELIANCE",
            score=Decimal("0"),
            confidence=Decimal("1"),
            regime_label="BULL",
        )
        assert result.confidence == Decimal("1")

    def test_confidence_above_one_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="confidence must be between 0 and 1"):
            PredictionResult(
                symbol="RELIANCE",
                score=Decimal("0"),
                confidence=Decimal("1.01"),
                regime_label="BULL",
            )

    def test_confidence_below_zero_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="confidence must be between 0 and 1"):
            PredictionResult(
                symbol="RELIANCE",
                score=Decimal("0"),
                confidence=Decimal("-0.01"),
                regime_label="BEAR",
            )

    def test_frozen_dataclass_immutable(self) -> None:
        result = PredictionResult(
            symbol="RELIANCE",
            score=Decimal("0"),
            confidence=Decimal("0.5"),
            regime_label="BULL",
        )
        with pytest.raises(AttributeError):
            result.symbol = "TCS"  # type: ignore[misc]

    def test_invalid_score_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="decimal-compatible"):
            PredictionResult(
                symbol="RELIANCE",
                score="not_decimal",  # type: ignore[arg-type]
                confidence=Decimal("0.5"),
                regime_label="BULL",
            )


class TestPredictorProtocol:
    """Tests for Predictor runtime-checkable protocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        assert isinstance(
            type(
                "ValidPredictor",
                (),
                {"predict": lambda self, features: None},
            ),
            Predictor,
        )

    def test_object_without_predict_is_not_predictor(self) -> None:
        assert not isinstance(type("Invalid", (), {}), Predictor)
