"""
Feature engineering utilities for predictive models.
"""

from datetime import UTC, datetime
from decimal import Decimal

from iatb.core.exceptions import ConfigError


class FeatureEngineer:
    """Builds normalized feature vectors from OHLCV, sentiment, regime, and time context."""

    def __init__(self, volatility_window: int = 14) -> None:
        if volatility_window < 2:
            msg = "volatility_window must be >= 2"
            raise ConfigError(msg)
        self._volatility_window = volatility_window

    def build_features(
        self,
        ohlcv_rows: list[dict[str, Decimal]],
        sentiment_scores: list[Decimal],
        regime_labels: list[str],
        timestamps_utc: list[datetime],
    ) -> list[list[Decimal]]:
        _validate_lengths(ohlcv_rows, sentiment_scores, regime_labels, timestamps_utc)
        raw_vectors = _build_raw_vectors(
            ohlcv_rows,
            sentiment_scores,
            regime_labels,
            timestamps_utc,
            self._volatility_window,
        )
        return _robust_scale(raw_vectors)


def _validate_lengths(
    ohlcv_rows: list[dict[str, Decimal]],
    sentiment_scores: list[Decimal],
    regime_labels: list[str],
    timestamps_utc: list[datetime],
) -> None:
    sizes = {len(ohlcv_rows), len(sentiment_scores), len(regime_labels), len(timestamps_utc)}
    if len(sizes) != 1:
        msg = "ohlcv_rows, sentiment_scores, regime_labels, timestamps_utc must share equal length"
        raise ConfigError(msg)
    if len(ohlcv_rows) < 2:
        msg = "at least two rows are required for return features"
        raise ConfigError(msg)
    if any(stamp.tzinfo != UTC for stamp in timestamps_utc):
        msg = "timestamps_utc must be timezone-aware UTC datetimes"
        raise ConfigError(msg)


def _build_raw_vectors(
    ohlcv_rows: list[dict[str, Decimal]],
    sentiment_scores: list[Decimal],
    regime_labels: list[str],
    timestamps_utc: list[datetime],
    window: int,
) -> list[list[Decimal]]:
    vectors: list[list[Decimal]] = []
    returns: list[Decimal] = []
    for index in range(1, len(ohlcv_rows)):
        close_prev = _field(ohlcv_rows[index - 1], "close")
        close_now = _field(ohlcv_rows[index], "close")
        volume_prev = _field(ohlcv_rows[index - 1], "volume")
        volume_now = _field(ohlcv_rows[index], "volume")
        ret = (close_now - close_prev) / max(close_prev, Decimal("1"))
        returns.append(ret)
        vol = _rolling_dispersion(returns, window)
        ma = _moving_average(ohlcv_rows, index, "close", window)
        trend = (close_now - ma) / max(abs(ma), Decimal("1"))
        volume_ratio = volume_now / max(volume_prev, Decimal("1"))
        regime = _regime_one_hot(regime_labels[index])
        hour_feature, minute_feature = _time_features(timestamps_utc[index])
        vectors.append(
            [
                ret,
                vol,
                trend,
                sentiment_scores[index],
                volume_ratio,
                *regime,
                hour_feature,
                minute_feature,
            ]
        )
    return vectors


def _field(row: dict[str, Decimal], key: str) -> Decimal:
    value = row.get(key)
    if value is None:
        msg = f"missing OHLCV key: {key}"
        raise ConfigError(msg)
    return Decimal(value)


def _moving_average(rows: list[dict[str, Decimal]], index: int, key: str, window: int) -> Decimal:
    start = max(0, index - window + 1)
    values = [_field(row, key) for row in rows[start : index + 1]]
    return _mean(values)


def _rolling_dispersion(values: list[Decimal], window: int) -> Decimal:
    start = max(0, len(values) - window)
    subset = values[start:]
    center = _mean(subset)
    return _mean([abs(value - center) for value in subset])


def _regime_one_hot(label: str) -> tuple[Decimal, Decimal, Decimal]:
    normalized = label.strip().upper()
    if normalized == "BULL":
        return Decimal("1"), Decimal("0"), Decimal("0")
    if normalized == "BEAR":
        return Decimal("0"), Decimal("1"), Decimal("0")
    return Decimal("0"), Decimal("0"), Decimal("1")


def _time_features(stamp_utc: datetime) -> tuple[Decimal, Decimal]:
    hour = Decimal(stamp_utc.hour) / Decimal("23")
    minute = Decimal(stamp_utc.minute) / Decimal("59")
    return hour, minute


def _robust_scale(vectors: list[list[Decimal]]) -> list[list[Decimal]]:
    columns = list(zip(*vectors, strict=True))
    medians = [_median(list(column)) for column in columns]
    iqrs = [_iqr(list(column)) for column in columns]
    scaled: list[list[Decimal]] = []
    for row in vectors:
        scaled_row: list[Decimal] = []
        for idx, value in enumerate(row):
            divisor = iqrs[idx] if iqrs[idx] != Decimal("0") else Decimal("1")
            scaled_row.append((value - medians[idx]) / divisor)
        scaled.append(scaled_row)
    return scaled


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def _iqr(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    quarter = len(ordered) // 4
    lower = ordered[quarter]
    upper = ordered[-(quarter + 1)]
    return upper - lower


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))
