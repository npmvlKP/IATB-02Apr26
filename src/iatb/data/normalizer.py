"""
Normalization helpers for provider-specific OHLCV payloads.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from iatb.core.enums import Exchange
from iatb.core.exceptions import ValidationError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.base import OHLCVBar
from iatb.data.validator import validate_ohlcv_bar, validate_ohlcv_series

logger = logging.getLogger(__name__)

_REQUIRED_OHLCV_KEYS = ("timestamp", "open", "high", "low", "close", "volume")


def _required_field(raw_record: Mapping[str, object], field_name: str) -> object:
    if field_name not in raw_record:
        msg = f"OHLCV field missing: {field_name}"
        raise ValidationError(msg)
    return raw_record[field_name]


def _to_decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool):
        msg = f"{field_name} cannot be boolean"
        raise ValidationError(msg)
    if not isinstance(value, Decimal | int | float | str):
        msg = f"{field_name} must be Decimal, int, float, or str"
        raise ValidationError(msg)
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        msg = f"{field_name} is not Decimal-compatible: {value!r}"
        raise ValidationError(msg) from exc
    if not decimal_value.is_finite():
        msg = f"{field_name} must be finite, got: {decimal_value}"
        raise ValidationError(msg)
    return decimal_value


def _parse_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            msg = "timestamp must be timezone-aware"
            raise ValidationError(msg)
        return value.astimezone(UTC)
    if isinstance(value, int):
        timestamp_seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(timestamp_seconds, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            msg = f"invalid unix timestamp: {value}"
            raise ValidationError(msg) from exc
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            msg = "timestamp cannot be empty"
            raise ValidationError(msg)
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            msg = f"invalid ISO timestamp string: {value!r}"
            raise ValidationError(msg) from exc
        if parsed.tzinfo is None:
            msg = "timestamp string must include timezone information"
            raise ValidationError(msg)
        return parsed.astimezone(UTC)
    msg = f"Unsupported timestamp type: {type(value).__name__}"
    raise ValidationError(msg)


def normalize_ohlcv_record(
    raw_record: Mapping[str, object],
    *,
    symbol: str,
    exchange: Exchange,
    source: str,
    validate: bool = True,
) -> OHLCVBar:
    """Normalize one provider OHLCV payload into strict internal form."""
    for key in _REQUIRED_OHLCV_KEYS:
        _required_field(raw_record, key)

    normalized = OHLCVBar(
        timestamp=create_timestamp(_parse_timestamp(raw_record["timestamp"])),
        exchange=exchange,
        symbol=symbol,
        open=create_price(_to_decimal(raw_record["open"], "open")),
        high=create_price(_to_decimal(raw_record["high"], "high")),
        low=create_price(_to_decimal(raw_record["low"], "low")),
        close=create_price(_to_decimal(raw_record["close"], "close")),
        volume=create_quantity(_to_decimal(raw_record["volume"], "volume")),
        source=source,
    )
    if validate:
        validate_ohlcv_bar(normalized)
    logger.debug("Normalized OHLCV record for %s on %s", symbol, exchange.value)
    return normalized


def normalize_ohlcv_batch(
    raw_records: Sequence[Mapping[str, object]],
    *,
    symbol: str,
    exchange: Exchange,
    source: str,
    validate_series: bool = True,
) -> list[OHLCVBar]:
    """Normalize a batch of OHLCV payloads with index-aware error context."""
    normalized_records: list[OHLCVBar] = []
    for index, raw_record in enumerate(raw_records):
        try:
            normalized_records.append(
                normalize_ohlcv_record(
                    raw_record,
                    symbol=symbol,
                    exchange=exchange,
                    source=source,
                    validate=False,
                )
            )
        except ValidationError as exc:
            msg = f"Invalid OHLCV record at index {index}: {exc}"
            raise ValidationError(msg) from exc

    if validate_series:
        validate_ohlcv_series(normalized_records)
    return normalized_records
