from __future__ import annotations

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.volume_filter import MIN_VOLUME_RATIO, has_volume_confirmation


class TestHasVolumeConfirmationHappyPath:
    def test_volume_ratio_exceeds_threshold_returns_true(self) -> None:
        result = has_volume_confirmation(Decimal("2.5"), threshold=Decimal("1.5"))
        assert result is True

    def test_volume_ratio_equals_threshold_returns_true(self) -> None:
        result = has_volume_confirmation(Decimal("1.5"), threshold=Decimal("1.5"))
        assert result is True

    def test_volume_ratio_slightly_above_threshold_returns_true(self) -> None:
        result = has_volume_confirmation(
            Decimal("1.50000000000000001"), threshold=Decimal("1.5")
        )
        assert result is True

    def test_volume_ratio_below_threshold_returns_false(self) -> None:
        result = has_volume_confirmation(Decimal("1.0"), threshold=Decimal("1.5"))
        assert result is False

    def test_volume_ratio_zero_with_positive_threshold_returns_false(self) -> None:
        result = has_volume_confirmation(Decimal("0"), threshold=Decimal("1.5"))
        assert result is False

    def test_default_threshold_uses_module_constant(self) -> None:
        result = has_volume_confirmation(Decimal("1.5"))
        assert result is True

    def test_custom_threshold_exceeding_default(self) -> None:
        result = has_volume_confirmation(Decimal("4.0"), threshold=Decimal("3.5"))
        assert result is True

    def test_custom_threshold_below_value_returns_false(self) -> None:
        result = has_volume_confirmation(Decimal("2.0"), threshold=Decimal("3.5"))
        assert result is False

    def test_high_precision_decimal_values(self) -> None:
        result = has_volume_confirmation(
            Decimal("3.141592653589793238462643383279"),
            threshold=Decimal("3.141592653589793238462643383278"),
        )
        assert result is True

    def test_very_large_decimal_values(self) -> None:
        result = has_volume_confirmation(
            Decimal("999999999999999999999999999999"),
            threshold=Decimal("500000000000000000000000000000"),
        )
        assert result is True

    def test_volume_ratio_less_than_one_returns_false(self) -> None:
        result = has_volume_confirmation(Decimal("0.5"))
        assert result is False


class TestHasVolumeConfirmationErrors:
    def test_negative_volume_ratio_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="volume_ratio cannot be negative"):
            has_volume_confirmation(Decimal("-0.1"))

    def test_very_negative_volume_ratio_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="volume_ratio cannot be negative"):
            has_volume_confirmation(Decimal("-999.99"))

    def test_zero_threshold_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="threshold must be positive"):
            has_volume_confirmation(Decimal("1.5"), threshold=Decimal("0"))

    def test_negative_threshold_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="threshold must be positive"):
            has_volume_confirmation(Decimal("1.5"), threshold=Decimal("-1.5"))

    def test_threshold_validated_before_volume_ratio(self) -> None:
        with pytest.raises(ConfigError, match="threshold must be positive"):
            has_volume_confirmation(Decimal("-5.0"), threshold=Decimal("0"))


class TestHasVolumeConfirmationEdgeCases:
    def test_volume_ratio_zero_with_default_threshold(self) -> None:
        result = has_volume_confirmation(Decimal("0"))
        assert result is False

    def test_volume_ratio_exactly_at_default_boundary(self) -> None:
        result = has_volume_confirmation(MIN_VOLUME_RATIO)
        assert result is True

    def test_volume_ratio_just_below_default_boundary(self) -> None:
        result = has_volume_confirmation(Decimal("1.4999999999999999999999999999"))
        assert result is False

    def test_volume_ratio_very_small_positive_returns_false(self) -> None:
        result = has_volume_confirmation(Decimal("0.0000000000000000000000000001"))
        assert result is False

    def test_high_precision_equals_threshold_is_true(self) -> None:
        threshold = Decimal("1.234567890123456789012345678901")
        result = has_volume_confirmation(threshold, threshold=threshold)
        assert result is True

    def test_high_precision_below_threshold_is_false(self) -> None:
        threshold = Decimal("1.234567890123456789012345678901")
        below = Decimal("1.234567890123456789012345678900")
        result = has_volume_confirmation(below, threshold=threshold)
        assert result is False


class TestVolumeFilterReturnType:
    def test_result_is_bool(self) -> None:
        result = has_volume_confirmation(Decimal("2.0"), threshold=Decimal("1.0"))
        assert isinstance(result, bool)

    def test_error_paths_never_return_bool(self) -> None:
        with pytest.raises(ConfigError):
            has_volume_confirmation(Decimal("-1.0"))


class TestMinVolumeRatioConstant:
    def test_constant_is_decimal(self) -> None:
        assert isinstance(MIN_VOLUME_RATIO, Decimal)

    def test_constant_is_positive(self) -> None:
        assert Decimal("0") < MIN_VOLUME_RATIO

    def test_constant_value(self) -> None:
        assert Decimal("1.5") == MIN_VOLUME_RATIO
