from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.feature_engine import FeatureEngineer


def test_feature_engine_builds_deterministic_scaled_vectors() -> None:
    engineer = FeatureEngineer(volatility_window=4)
    ohlcv = _sample_ohlcv()
    sentiments = [Decimal("0.0"), Decimal("0.2"), Decimal("0.1"), Decimal("-0.1"), Decimal("0.3")]
    regimes = ["SIDEWAYS", "BULL", "BEAR", "UNKNOWN", "BULL"]
    stamps = _sample_stamps(len(ohlcv))
    one = engineer.build_features(ohlcv, sentiments, regimes, stamps)
    two = engineer.build_features(ohlcv, sentiments, regimes, stamps)
    assert one == two
    assert len(one) == len(ohlcv) - 1
    assert len(one[0]) == 10


def test_feature_engine_rejects_invalid_inputs() -> None:
    engineer = FeatureEngineer()
    rows = _sample_ohlcv()[:2]
    sentiments = [Decimal("0.1"), Decimal("0.2")]
    regimes = ["BULL", "BEAR"]
    bad_stamps = [datetime(2026, 1, 5, 4, 0), datetime(2026, 1, 5, 4, 1)]  # noqa: DTZ001
    with pytest.raises(ConfigError, match="share equal length"):
        engineer.build_features(rows, sentiments[:1], regimes, _sample_stamps(2))
    with pytest.raises(ConfigError, match="timezone-aware UTC"):
        engineer.build_features(rows, sentiments, regimes, bad_stamps)
    with pytest.raises(ConfigError, match="volatility_window must be >= 2"):
        FeatureEngineer(volatility_window=1)


def _sample_ohlcv() -> list[dict[str, Decimal]]:
    return [
        {
            "open": Decimal("100"),
            "high": Decimal("101"),
            "low": Decimal("99"),
            "close": Decimal("100"),
            "volume": Decimal("1000"),
        },
        {
            "open": Decimal("101"),
            "high": Decimal("102"),
            "low": Decimal("100"),
            "close": Decimal("101"),
            "volume": Decimal("1200"),
        },
        {
            "open": Decimal("100"),
            "high": Decimal("103"),
            "low": Decimal("99"),
            "close": Decimal("102"),
            "volume": Decimal("1100"),
        },
        {
            "open": Decimal("102"),
            "high": Decimal("104"),
            "low": Decimal("101"),
            "close": Decimal("103"),
            "volume": Decimal("1500"),
        },
        {
            "open": Decimal("103"),
            "high": Decimal("105"),
            "low": Decimal("102"),
            "close": Decimal("104"),
            "volume": Decimal("1300"),
        },
    ]


def _sample_stamps(length: int) -> list[datetime]:
    start = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    return [start + timedelta(minutes=idx) for idx in range(length)]
