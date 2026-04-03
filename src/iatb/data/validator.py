"""
Fail-closed runtime validation for normalized data models.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from iatb.core.exceptions import ValidationError
from iatb.data.base import OHLCVBar, TickerSnapshot

_MAX_FUTURE_SKEW = timedelta(minutes=2)


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not value.strip():
        msg = f"{field_name} cannot be empty"
        raise ValidationError(msg)


def _validate_non_negative(value: Decimal, field_name: str) -> None:
    if value < Decimal("0"):
        msg = f"{field_name} cannot be negative: {value}"
        raise ValidationError(msg)


def _validate_timestamp_not_far_future(timestamp: datetime) -> None:
    if timestamp > datetime.now(UTC) + _MAX_FUTURE_SKEW:
        msg = "timestamp cannot be in the future beyond allowed skew"
        raise ValidationError(msg)


def validate_ohlcv_bar(bar: OHLCVBar) -> None:
    """Validate one OHLCV bar under strict financial and temporal constraints."""
    _require_non_empty_text(bar.symbol, "symbol")
    _require_non_empty_text(bar.source, "source")
    _validate_non_negative(bar.open, "open")
    _validate_non_negative(bar.high, "high")
    _validate_non_negative(bar.low, "low")
    _validate_non_negative(bar.close, "close")
    _validate_non_negative(bar.volume, "volume")
    _validate_timestamp_not_far_future(bar.timestamp)

    max_traded = max(bar.open, bar.close, bar.low)
    min_traded = min(bar.open, bar.close, bar.high)
    if bar.high < max_traded:
        msg = "high price cannot be lower than open/close/low"
        raise ValidationError(msg)
    if bar.low > min_traded:
        msg = "low price cannot be greater than open/close/high"
        raise ValidationError(msg)


def validate_ohlcv_series(bars: Sequence[OHLCVBar]) -> None:
    """Validate consistency and strict timestamp ordering across an OHLCV series."""
    if not bars:
        return

    first = bars[0]
    previous_timestamp: datetime | None = None
    for bar in bars:
        validate_ohlcv_bar(bar)
        if bar.symbol != first.symbol:
            msg = "OHLCV series must contain only one symbol"
            raise ValidationError(msg)
        if bar.exchange != first.exchange:
            msg = "OHLCV series must contain only one exchange"
            raise ValidationError(msg)
        if previous_timestamp is not None and bar.timestamp <= previous_timestamp:
            msg = "OHLCV timestamps must be strictly increasing"
            raise ValidationError(msg)
        previous_timestamp = bar.timestamp


def validate_ticker_snapshot(snapshot: TickerSnapshot) -> None:
    """Validate one ticker snapshot with spread and temporal checks."""
    _require_non_empty_text(snapshot.symbol, "symbol")
    _require_non_empty_text(snapshot.source, "source")
    _validate_non_negative(snapshot.bid, "bid")
    _validate_non_negative(snapshot.ask, "ask")
    _validate_non_negative(snapshot.last, "last")
    _validate_non_negative(snapshot.volume_24h, "volume_24h")
    _validate_timestamp_not_far_future(snapshot.timestamp)

    if snapshot.bid > snapshot.ask:
        msg = "bid cannot exceed ask"
        raise ValidationError(msg)
    if snapshot.last < snapshot.bid or snapshot.last > snapshot.ask:
        msg = "last must be within bid/ask spread"
        raise ValidationError(msg)
