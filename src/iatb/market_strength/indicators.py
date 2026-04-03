"""
pandas-ta wrapper for technical indicators.
"""

import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from iatb.core.exceptions import ConfigError


def _to_decimal(value: object, field_name: str) -> Decimal:
    if value is None:
        msg = f"{field_name} cannot be None"
        raise ConfigError(msg)
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        msg = f"{field_name} is not decimal-compatible: {value!r}"
        raise ConfigError(msg) from exc
    if not decimal_value.is_finite():
        msg = f"{field_name} must be finite"
        raise ConfigError(msg)
    return decimal_value


def _last_decimal(values: object, field_name: str) -> Decimal:
    if isinstance(values, Sequence) and not isinstance(values, str):
        if not values:
            msg = f"{field_name} returned empty sequence"
            raise ConfigError(msg)
        return _to_decimal(values[-1], field_name)
    msg = f"{field_name} returned unsupported output type: {type(values).__name__}"
    raise ConfigError(msg)


@dataclass(frozen=True)
class IndicatorSnapshot:
    rsi: Decimal
    adx: Decimal
    atr: Decimal
    macd_histogram: Decimal
    bollinger_upper: Decimal
    bollinger_middle: Decimal
    bollinger_lower: Decimal


class PandasTaIndicators:
    """Thin abstraction around pandas-ta indicator functions."""

    def __init__(self, backend_loader: Callable[[], object] | None = None) -> None:
        self._backend_loader = backend_loader or self._default_backend_loader
        self._backend = self._backend_loader()

    @staticmethod
    def _default_backend_loader() -> object:
        try:
            return importlib.import_module("pandas_ta")
        except ModuleNotFoundError as exc:
            msg = "pandas-ta dependency is required for market strength indicators"
            raise ConfigError(msg) from exc

    def snapshot(
        self,
        *,
        close: Sequence[Decimal],
        high: Sequence[Decimal],
        low: Sequence[Decimal],
    ) -> IndicatorSnapshot:
        if not close or not high or not low:
            msg = "close/high/low sequences cannot be empty"
            raise ConfigError(msg)
        if not (len(close) == len(high) == len(low)):
            msg = "close/high/low sequences must have equal length"
            raise ConfigError(msg)
        rsi = _last_decimal(self._call("rsi", close=close, length=14), "rsi")
        adx_payload = self._call("adx", high=high, low=low, close=close, length=14)
        adx = _last_decimal(self._extract_named(adx_payload, "ADX_14"), "adx")
        atr = _last_decimal(
            self._call("atr", high=high, low=low, close=close, length=14),
            "atr",
        )
        macd_payload = self._call("macd", close=close, fast=12, slow=26, signal=9)
        macd_hist = _last_decimal(
            self._extract_named(macd_payload, "MACDh_12_26_9"),
            "macd",
        )
        bb_payload = self._call("bbands", close=close, length=20, std=2.0)
        return IndicatorSnapshot(
            rsi=rsi,
            adx=adx,
            atr=atr,
            macd_histogram=macd_hist,
            bollinger_upper=_last_decimal(
                self._extract_named(bb_payload, "BBU_20_2.0"),
                "bb_upper",
            ),
            bollinger_middle=_last_decimal(
                self._extract_named(bb_payload, "BBM_20_2.0"),
                "bb_middle",
            ),
            bollinger_lower=_last_decimal(
                self._extract_named(bb_payload, "BBL_20_2.0"),
                "bb_lower",
            ),
        )

    def _call(self, function_name: str, **kwargs: object) -> object:
        function = getattr(self._backend, function_name, None)
        if not callable(function):
            msg = f"pandas-ta backend is missing function: {function_name}"
            raise ConfigError(msg)
        return function(**kwargs)

    @staticmethod
    def _extract_named(payload: object, column_name: str) -> object:
        if isinstance(payload, dict):
            if column_name not in payload:
                msg = f"indicator payload missing column: {column_name}"
                raise ConfigError(msg)
            return payload[column_name]
        if hasattr(payload, "__getitem__"):
            try:
                return payload[column_name]
            except Exception as exc:
                msg = f"indicator payload missing column: {column_name}"
                raise ConfigError(msg) from exc
        msg = "indicator payload must support named column access"
        raise ConfigError(msg)
