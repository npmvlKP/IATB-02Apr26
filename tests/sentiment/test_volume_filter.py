from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.volume_filter import has_volume_confirmation


def test_volume_filter_passes_threshold() -> None:
    assert has_volume_confirmation(Decimal("1.5"))
    assert has_volume_confirmation(Decimal("2.2"))


def test_volume_filter_rejects_invalid_inputs() -> None:
    with pytest.raises(ConfigError, match="cannot be negative"):
        has_volume_confirmation(Decimal("-0.1"))
    with pytest.raises(ConfigError, match="must be positive"):
        has_volume_confirmation(Decimal("1.5"), threshold=Decimal("0"))
