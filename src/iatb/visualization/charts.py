"""
Plotly chart helpers for OHLCV visualization.
"""

import importlib
from decimal import Decimal
from typing import Any

from iatb.core.exceptions import ConfigError


def build_candlestick_chart(
    rows: list[dict[str, object]],
    ema_period: int = 20,
    bollinger_period: int = 20,
) -> object:
    _validate_rows(rows, ema_period, bollinger_period)
    go = _load_plotly_go()
    closes = [_as_decimal(row["close"], "close") for row in rows]
    ema = _ema_series(closes, ema_period)
    sma = _sma_series(closes, bollinger_period)
    std = _rolling_mean_abs_dev(closes, bollinger_period)
    upper = [sma[idx] + (std[idx] * Decimal("2")) for idx in range(len(sma))]
    lower = [sma[idx] - (std[idx] * Decimal("2")) for idx in range(len(sma))]
    figure = go.Figure()
    _add_candle_trace(figure, go, rows)
    _add_line_trace(figure, go, "EMA", ema)
    _add_line_trace(figure, go, "Bollinger Upper", upper)
    _add_line_trace(figure, go, "Bollinger Lower", lower)
    _add_volume_trace(figure, go, rows)
    return figure


def _validate_rows(rows: list[dict[str, object]], ema_period: int, bollinger_period: int) -> None:
    if len(rows) < 2:
        msg = "rows must include at least two OHLCV points"
        raise ConfigError(msg)
    if ema_period <= 0 or bollinger_period <= 0:
        msg = "ema_period and bollinger_period must be positive"
        raise ConfigError(msg)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    for row in rows:
        if not required.issubset(set(row.keys())):
            msg = "each row must include timestamp/open/high/low/close/volume"
            raise ConfigError(msg)


def _load_plotly_go() -> Any:
    try:
        return importlib.import_module("plotly.graph_objects")
    except ModuleNotFoundError as exc:
        msg = "plotly dependency is required for chart rendering"
        raise ConfigError(msg) from exc


def _add_candle_trace(figure: Any, go: Any, rows: list[dict[str, object]]) -> None:
    figure.add_trace(
        go.Candlestick(
            x=[row["timestamp"] for row in rows],
            open=[_as_float(row["open"], "open") for row in rows],
            high=[_as_float(row["high"], "high") for row in rows],
            low=[_as_float(row["low"], "low") for row in rows],
            close=[_as_float(row["close"], "close") for row in rows],
            name="Candlestick",
        )
    )


def _add_line_trace(figure: Any, go: Any, name: str, values: list[Decimal]) -> None:
    # G7 exemption: Plotly API requires float for chart rendering
    figure.add_trace(go.Scatter(y=[float(value) for value in values], name=name))  # noqa: G7


def _add_volume_trace(figure: Any, go: Any, rows: list[dict[str, object]]) -> None:
    figure.add_trace(go.Bar(y=[_as_float(row["volume"], "volume") for row in rows], name="Volume"))


def _as_decimal(value: object, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:  # noqa: BLE001
        msg = f"{field_name} must be decimal-compatible"
        raise ConfigError(msg) from exc


def _as_float(value: object, field_name: str) -> float:
    # G7 exemption: Plotly API requires float for chart rendering
    return float(_as_decimal(value, field_name))  # noqa: G7


def _ema_series(values: list[Decimal], period: int) -> list[Decimal]:
    multiplier = Decimal("2") / Decimal(period + 1)
    series: list[Decimal] = [values[0]]
    for idx in range(1, len(values)):
        previous = series[idx - 1]
        series.append((values[idx] - previous) * multiplier + previous)
    return series


def _sma_series(values: list[Decimal], period: int) -> list[Decimal]:
    series: list[Decimal] = []
    for idx in range(len(values)):
        start = max(0, idx - period + 1)
        window = values[start : idx + 1]
        series.append(sum(window, Decimal("0")) / Decimal(len(window)))
    return series


def _rolling_mean_abs_dev(values: list[Decimal], period: int) -> list[Decimal]:
    output: list[Decimal] = []
    for idx in range(len(values)):
        start = max(0, idx - period + 1)
        window = values[start : idx + 1]
        center = sum(window, Decimal("0")) / Decimal(len(window))
        output.append(
            sum([abs(item - center) for item in window], Decimal("0")) / Decimal(len(window))
        )
    return output
