import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.visualization.charts import build_candlestick_chart

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


@dataclass
class _FakeTrace:
    kind: str
    kwargs: dict[str, object]


class _FakeFigure:
    def __init__(self) -> None:
        self.traces: list[_FakeTrace] = []

    def add_trace(self, trace: _FakeTrace) -> None:
        self.traces.append(trace)


def _candlestick(**kwargs: object) -> _FakeTrace:
    return _FakeTrace("candlestick", dict(kwargs))


def _scatter(**kwargs: object) -> _FakeTrace:
    return _FakeTrace("scatter", dict(kwargs))


def _bar(**kwargs: object) -> _FakeTrace:
    return _FakeTrace("bar", dict(kwargs))


def test_build_candlestick_chart_with_fake_plotly(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_go = SimpleNamespace(
        Figure=_FakeFigure, Candlestick=_candlestick, Scatter=_scatter, Bar=_bar
    )
    monkeypatch.setattr("iatb.visualization.charts.importlib.import_module", lambda _: fake_go)
    figure = build_candlestick_chart(_sample_rows())
    assert isinstance(figure, _FakeFigure)
    assert len(figure.traces) == 5
    assert figure.traces[0].kind == "candlestick"
    assert figure.traces[-1].kind == "bar"


def test_build_candlestick_chart_validations() -> None:
    with pytest.raises(ConfigError, match="at least two"):
        build_candlestick_chart([])
    with pytest.raises(ConfigError, match="must include timestamp"):
        build_candlestick_chart([{"close": Decimal("1")}, {"close": Decimal("2")}])
    with pytest.raises(ConfigError, match="must be positive"):
        build_candlestick_chart(_sample_rows(), ema_period=0)
    with pytest.raises(ConfigError, match="must be positive"):
        build_candlestick_chart(_sample_rows(), ema_period=-1)
    with pytest.raises(ConfigError, match="must be positive"):
        build_candlestick_chart(_sample_rows(), bollinger_period=0)
    with pytest.raises(ConfigError, match="must include timestamp/open/high/low/close/volume"):
        build_candlestick_chart(
            [
                {
                    "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                    "open": "1",
                    "high": "2",
                    "low": "1",
                    "close": "1.5",
                },
                {
                    "timestamp": datetime(2026, 1, 2, tzinfo=UTC),
                    "open": "1",
                    "high": "2",
                    "low": "1",
                    "close": "1.5",
                },
            ]
        )


def test_build_candlestick_chart_missing_plotly_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing plotly module raises ConfigError."""
    monkeypatch.setattr(
        "iatb.visualization.charts.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError("No module named 'plotly'")),
    )
    with pytest.raises(ConfigError, match="plotly dependency is required"):
        build_candlestick_chart(_sample_rows())


def test_build_candlestick_chart_invalid_decimal_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that invalid decimal values raise ConfigError."""
    fake_go = SimpleNamespace(
        Figure=_FakeFigure, Candlestick=_candlestick, Scatter=_scatter, Bar=_bar
    )
    monkeypatch.setattr("iatb.visualization.charts.importlib.import_module", lambda _: fake_go)

    # Test with invalid close value
    invalid_rows = [
        {
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "invalid",  # Invalid decimal
            "volume": "1000",
        },
        {
            "timestamp": datetime(2026, 1, 2, tzinfo=UTC),
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100.5",
            "volume": "1000",
        },
    ]

    with pytest.raises(ConfigError, match="close must be decimal-compatible"):  # noqa: E501
        build_candlestick_chart(invalid_rows)


def test_build_candlestick_chart_custom_periods(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test building chart with custom EMA and Bollinger periods."""
    fake_go = SimpleNamespace(
        Figure=_FakeFigure, Candlestick=_candlestick, Scatter=_scatter, Bar=_bar
    )
    monkeypatch.setattr("iatb.visualization.charts.importlib.import_module", lambda _: fake_go)
    figure = build_candlestick_chart(_sample_rows(), ema_period=10, bollinger_period=15)
    assert isinstance(figure, _FakeFigure)
    assert len(figure.traces) == 5


def _sample_rows() -> list[dict[str, object]]:
    start = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    output: list[dict[str, object]] = []
    for idx in range(3):
        output.append(
            {
                "timestamp": start + timedelta(minutes=idx),
                "open": Decimal("100") + Decimal(idx),
                "high": Decimal("101") + Decimal(idx),
                "low": Decimal("99") + Decimal(idx),
                "close": Decimal("100.5") + Decimal(idx),
                "volume": Decimal("1000") + Decimal(idx * 10),
            }
        )
    return output
