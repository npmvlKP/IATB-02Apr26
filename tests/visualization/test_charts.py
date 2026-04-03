from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from iatb.core.exceptions import ConfigError
from iatb.visualization.charts import build_candlestick_chart


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
