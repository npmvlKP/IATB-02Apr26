import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    ScannerCandidate,
)
from iatb.visualization.breakout_scanner import (
    HealthStatus,
    build_instrument_health_matrix,
    build_scanner_health_result,
)
from iatb.visualization.dashboard import (
    INSTRUMENT_SCANNER_TAB,
    REQUIRED_MARKET_TABS,
    build_dashboard_payload,
    build_scanner_payload,
    convert_candidates_to_health_matrix,
    render_approved_charts,
    render_dashboard,
    render_health_matrix_table,
    render_instrument_scanner_tab,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


@dataclass
class _FakeTab:
    writes: list[object] = field(default_factory=list)

    def write(self, value: object) -> None:
        self.writes.append(value)


class _FakeStreamlit:
    def __init__(self) -> None:
        self.titles: list[str] = []
        self._tabs = [_FakeTab() for _ in REQUIRED_MARKET_TABS + (INSTRUMENT_SCANNER_TAB,)]

    def title(self, text: str) -> None:
        self.titles.append(text)

    def tabs(self, names: list[str]) -> list[_FakeTab]:
        _ = names
        return self._tabs


def test_dashboard_payload_and_render() -> None:
    payload = build_dashboard_payload({"NSE EQ": {"signals": 3}, "Crypto": {"signals": 5}})
    assert set(payload.keys()) == set(REQUIRED_MARKET_TABS)
    streamlit = _FakeStreamlit()
    rendered = render_dashboard(payload, streamlit)
    assert rendered == list(REQUIRED_MARKET_TABS) + [INSTRUMENT_SCANNER_TAB]
    assert streamlit.titles == ["IATB Multi-Market Dashboard"]


def test_dashboard_missing_streamlit_api_raises() -> None:
    with pytest.raises(ConfigError, match="missing title\\(\\)/tabs\\(\\)"):
        render_dashboard({}, streamlit_module=object())


@dataclass
class _FakeStreamlitWithFunctions:
    """Mock Streamlit module with all required functions."""

    headers: list[str] = field(default_factory=list)
    subheaders: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)
    metrics: list[tuple[str, str]] = field(default_factory=list)
    dataframes: list[object] = field(default_factory=list)
    charts: list[object] = field(default_factory=list)
    dividers: int = 0

    def header(self, text: str) -> None:
        self.headers.append(text)

    def subheader(self, text: str) -> None:
        self.subheaders.append(text)

    def info(self, text: str) -> None:
        self.infos.append(text)

    def metric(self, label: str, value: str) -> None:
        self.metrics.append((label, value))

    def dataframe(self, data: object, **kwargs: object) -> None:  # noqa: ARG002
        self.dataframes.append(data)

    def plotly_chart(self, fig: object, **kwargs: object) -> None:  # noqa: ARG002
        self.charts.append(fig)

    def columns(self, n: int) -> list["_FakeStreamlitWithFunctions"]:
        return [self for _ in range(n)]

    def divider(self) -> None:
        self.dividers += 1


@dataclass
class _FakePlotlyGo:
    """Mock plotly.graph_objects module."""

    figures: list[object] = field(default_factory=list)

    def Figure(self) -> "_FakePlotlyFigure":  # noqa: N802 (mimics plotly.graph_objects)
        fig = _FakePlotlyFigure()
        self.figures.append(fig)
        return fig

    def Candlestick(self, **kwargs: object) -> object:  # noqa: N802 (mimics plotly.graph_objects)
        return {"type": "candlestick", **kwargs}

    def Bar(self, **kwargs: object) -> object:  # noqa: N802 (mimics plotly.graph_objects)
        return {"type": "bar", **kwargs}


class _FakePlotlyFigure:
    """Mock Plotly Figure class."""

    def __init__(self) -> None:
        self.traces: list[object] = []
        self.layout: dict[str, object] = {}

    def add_trace(self, trace: object) -> None:
        self.traces.append(trace)

    def update_layout(self, **kwargs: object) -> None:
        self.layout.update(kwargs)


def test_build_scanner_payload_with_result() -> None:
    """Test building scanner payload with valid result."""
    timestamp = datetime.now(UTC)
    matrix = build_instrument_health_matrix(
        symbol="RELIANCE",
        sentiment_score=Decimal("0.8"),
        market_strength_score=Decimal("0.75"),
        volume_score=Decimal("0.85"),
        drl_backtest_score=Decimal("0.7"),
        safe_exit_probability=Decimal("0.65"),
        timestamp_utc=timestamp,
    )
    result = build_scanner_health_result([matrix])

    payload = build_scanner_payload(result)

    assert payload["approved_count"] == 1
    assert payload["total_scanned"] == 1
    assert payload["scan_timestamp_utc"] == result.scan_timestamp_utc
    assert len(payload["instruments"]) == 1


def test_build_scanner_payload_without_result() -> None:
    """Test building scanner payload without result (empty state)."""
    payload = build_scanner_payload(None)

    assert payload["approved_count"] == 0
    assert payload["total_scanned"] == 0
    assert payload["scan_timestamp_utc"] is None
    assert payload["instruments"] == []


def test_render_health_matrix_table_empty() -> None:
    """Test rendering health matrix table with no instruments."""
    st = _FakeStreamlitWithFunctions()
    rendered = render_health_matrix_table([], st)

    assert rendered == []
    assert len(st.infos) == 1
    assert "No instruments" in st.infos[0]


def test_render_health_matrix_table_with_instruments() -> None:
    """Test rendering health matrix table with instruments."""
    timestamp = datetime.now(UTC)
    matrix1 = build_instrument_health_matrix(
        symbol="RELIANCE",
        sentiment_score=Decimal("0.8"),
        market_strength_score=Decimal("0.75"),
        volume_score=Decimal("0.85"),
        drl_backtest_score=Decimal("0.7"),
        safe_exit_probability=Decimal("0.65"),
        timestamp_utc=timestamp,
    )
    matrix2 = build_instrument_health_matrix(
        symbol="TCS",
        sentiment_score=Decimal("0.4"),
        market_strength_score=Decimal("0.5"),
        volume_score=Decimal("0.3"),
        drl_backtest_score=Decimal("0.4"),
        safe_exit_probability=Decimal("0.4"),
        timestamp_utc=timestamp,
    )

    st = _FakeStreamlitWithFunctions()
    rendered = render_health_matrix_table([matrix1, matrix2], st)

    assert len(rendered) == 2
    assert "RELIANCE" in rendered
    assert "TCS" in rendered
    assert len(st.dataframes) == 1
    df = st.dataframes[0]
    assert len(df) == 2
    assert df[0]["Symbol"] == "RELIANCE"
    assert df[1]["Symbol"] == "TCS"
    # Check badges are present
    assert "✅" in df[0]["Sentiment"] or "❌" in df[0]["Sentiment"]
    assert "✅" in df[0]["Overall"] or "❌" in df[0]["Overall"]


def test_render_approved_charts_empty() -> None:
    """Test rendering approved charts with no approved instruments."""
    timestamp = datetime.now(UTC)
    matrix = build_instrument_health_matrix(
        symbol="RELIANCE",
        sentiment_score=Decimal("0.4"),
        market_strength_score=Decimal("0.5"),
        volume_score=Decimal("0.3"),
        drl_backtest_score=Decimal("0.4"),
        safe_exit_probability=Decimal("0.4"),
        timestamp_utc=timestamp,
    )

    st = _FakeStreamlitWithFunctions()
    go = _FakePlotlyGo()
    rendered = render_approved_charts([matrix], None, st, go)

    assert rendered == []
    assert len(st.charts) == 0


def test_render_approved_charts_with_approved() -> None:
    """Test rendering approved charts with approved instruments."""
    timestamp = datetime.now(UTC)
    matrix = build_instrument_health_matrix(
        symbol="RELIANCE",
        sentiment_score=Decimal("0.8"),
        market_strength_score=Decimal("0.75"),
        volume_score=Decimal("0.85"),
        drl_backtest_score=Decimal("0.7"),
        safe_exit_probability=Decimal("0.65"),
        timestamp_utc=timestamp,
    )

    st = _FakeStreamlitWithFunctions()
    go = _FakePlotlyGo()
    rendered = render_approved_charts([matrix], None, st, go)

    assert len(rendered) == 1
    assert "RELIANCE" in rendered
    assert len(st.subheaders) == 1
    assert "RELIANCE" in st.subheaders[0]
    assert len(st.charts) == 1
    # Verify chart type is bar (summary chart when no chart_data)
    assert go.figures[0].traces[0]["type"] == "bar"


def test_render_approved_charts_with_chart_data() -> None:
    """Test rendering approved charts with OHLCV data."""
    timestamp = datetime.now(UTC)
    matrix = build_instrument_health_matrix(
        symbol="RELIANCE",
        sentiment_score=Decimal("0.8"),
        market_strength_score=Decimal("0.75"),
        volume_score=Decimal("0.85"),
        drl_backtest_score=Decimal("0.7"),
        safe_exit_probability=Decimal("0.65"),
        timestamp_utc=timestamp,
    )

    chart_data = {
        "RELIANCE": [
            {
                "timestamp": timestamp,
                "open": Decimal("2500"),
                "high": Decimal("2550"),
                "low": Decimal("2480"),
                "close": Decimal("2530"),
            },
            {
                "timestamp": timestamp,
                "open": Decimal("2530"),
                "high": Decimal("2580"),
                "low": Decimal("2520"),
                "close": Decimal("2560"),
            },
        ]
    }

    st = _FakeStreamlitWithFunctions()
    go = _FakePlotlyGo()
    rendered = render_approved_charts([matrix], chart_data, st, go)

    assert len(rendered) == 1
    assert len(st.charts) == 1
    # Verify chart type is candlestick when chart_data provided
    assert go.figures[0].traces[0]["type"] == "candlestick"


def test_render_instrument_scanner_tab_no_result() -> None:
    """Test rendering instrument scanner tab without result."""
    st = _FakeStreamlitWithFunctions()
    go = _FakePlotlyGo()

    result = render_instrument_scanner_tab(None, None, st, go)

    assert result["table_symbols"] == []
    assert result["chart_symbols"] == []
    assert result["approved_count"] == 0
    assert result["total_count"] == 0
    assert len(st.headers) == 1
    assert "Instrument Scanner" in st.headers[0]
    assert len(st.infos) == 1
    assert "No scanner result available" in st.infos[0]


def test_render_instrument_scanner_tab_with_result() -> None:
    """Test rendering complete instrument scanner tab."""
    timestamp = datetime.now(UTC)
    matrix1 = build_instrument_health_matrix(
        symbol="RELIANCE",
        sentiment_score=Decimal("0.8"),
        market_strength_score=Decimal("0.75"),
        volume_score=Decimal("0.85"),
        drl_backtest_score=Decimal("0.7"),
        safe_exit_probability=Decimal("0.65"),
        timestamp_utc=timestamp,
    )
    matrix2 = build_instrument_health_matrix(
        symbol="TCS",
        sentiment_score=Decimal("0.4"),
        market_strength_score=Decimal("0.5"),
        volume_score=Decimal("0.3"),
        drl_backtest_score=Decimal("0.4"),
        safe_exit_probability=Decimal("0.4"),
        timestamp_utc=timestamp,
    )
    result = build_scanner_health_result([matrix1, matrix2])

    st = _FakeStreamlitWithFunctions()
    go = _FakePlotlyGo()

    output = render_instrument_scanner_tab(result, None, st, go)

    assert output["total_count"] == 2
    assert output["approved_count"] == 1
    assert len(output["table_symbols"]) == 2
    assert len(output["chart_symbols"]) == 1
    assert "RELIANCE" in output["chart_symbols"]
    # Verify metrics
    assert len(st.metrics) == 3
    assert any(m[0] == "Total Scanned" for m in st.metrics)
    assert any(m[0] == "Approved" for m in st.metrics)
    assert any(m[0] == "Approval Rate" for m in st.metrics)
    # Verify sections (Health Matrix + Approved Instruments Charts + 1 approved instrument header)
    assert len(st.subheaders) == 3
    assert "Health Matrix" in st.subheaders[0]
    assert "Approved Instruments Charts" in st.subheaders[1]
    assert "RELIANCE" in st.subheaders[2]
    assert st.dividers == 2


def test_convert_candidates_to_health_matrix() -> None:
    """Test converting ScannerCandidate list to InstrumentHealthMatrix."""
    timestamp = datetime.now(UTC)
    candidates = [
        ScannerCandidate(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("5.2"),
            composite_score=Decimal("0.75"),
            sentiment_score=Decimal("0.8"),
            volume_ratio=Decimal("3.5"),
            exit_probability=Decimal("0.65"),
            is_tradable=True,
            regime="SIDEWAYS",  # type: ignore[arg-type]
            rank=1,
            timestamp_utc=timestamp,
            metadata={"strength_score": "0.75"},
        ),
        ScannerCandidate(
            symbol="TCS",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("-2.1"),
            composite_score=Decimal("0.45"),
            sentiment_score=Decimal("0.4"),
            volume_ratio=Decimal("1.8"),
            exit_probability=Decimal("0.4"),
            is_tradable=False,
            regime="SIDEWAYS",  # type: ignore[arg-type]
            rank=2,
            timestamp_utc=timestamp,
            metadata={"strength_score": "0.5"},
        ),
    ]

    matrices = convert_candidates_to_health_matrix(candidates)

    assert len(matrices) == 2
    assert matrices[0].symbol == "RELIANCE"
    assert matrices[1].symbol == "TCS"
    # Check RELIANCE (should be approved)
    assert matrices[0].sentiment_health.score == Decimal("0.8")
    assert matrices[0].market_strength_health.score == Decimal("0.75")
    # Volume score should be min(1, volume_ratio / 5)
    assert matrices[0].volume_analysis_health.score == Decimal("0.7")
    assert matrices[0].drl_backtest_health.score == Decimal("0.65")
    assert matrices[0].safe_exit_probability == Decimal("0.65")
    # Overall health should be HEALTHY
    assert matrices[0].overall_health == HealthStatus.HEALTHY
    assert matrices[0].is_approved is True


def test_convert_candidates_with_custom_thresholds() -> None:
    """Test converting candidates with custom thresholds."""
    timestamp = datetime.now(UTC)
    candidates = [
        ScannerCandidate(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("5.2"),
            composite_score=Decimal("0.75"),
            sentiment_score=Decimal("0.8"),
            volume_ratio=Decimal("3.5"),
            exit_probability=Decimal("0.65"),
            is_tradable=True,
            regime="SIDEWAYS",  # type: ignore[arg-type]
            rank=1,
            timestamp_utc=timestamp,
            metadata={"strength_score": "0.75"},
        ),
    ]

    # Higher thresholds - should NOT be approved
    matrices = convert_candidates_to_health_matrix(
        candidates,
        sentiment_threshold=Decimal("0.9"),
        strength_threshold=Decimal("0.9"),
        volume_threshold=Decimal("0.9"),
        drl_threshold=Decimal("0.9"),
    )

    assert len(matrices) == 1
    # With score 0.8 and threshold 0.9, it's NEUTRAL (not HEALTHY, not NOT_HEALTHY)
    assert matrices[0].sentiment_health.status == HealthStatus.NEUTRAL
    assert matrices[0].market_strength_health.status == HealthStatus.NEUTRAL
    assert matrices[0].is_approved is False


def test_health_matrix_utc_timestamp_validation() -> None:
    """Test that health matrix requires UTC timestamps."""
    non_utc_ts = datetime.now()  # noqa: DTZ005 (intentionally non-UTC for test)
    with pytest.raises(ConfigError, match="must be UTC"):
        build_instrument_health_matrix(
            symbol="RELIANCE",
            sentiment_score=Decimal("0.8"),
            market_strength_score=Decimal("0.75"),
            volume_score=Decimal("0.85"),
            drl_backtest_score=Decimal("0.7"),
            safe_exit_probability=Decimal("0.65"),
            timestamp_utc=non_utc_ts,
        )


def test_render_approved_charts_multiple_instruments() -> None:
    """Test rendering charts for multiple approved instruments."""
    timestamp = datetime.now(UTC)
    matrix1 = build_instrument_health_matrix(
        symbol="RELIANCE",
        sentiment_score=Decimal("0.8"),
        market_strength_score=Decimal("0.75"),
        volume_score=Decimal("0.85"),
        drl_backtest_score=Decimal("0.7"),
        safe_exit_probability=Decimal("0.65"),
        timestamp_utc=timestamp,
    )
    matrix2 = build_instrument_health_matrix(
        symbol="TCS",
        sentiment_score=Decimal("0.9"),
        market_strength_score=Decimal("0.85"),
        volume_score=Decimal("0.9"),
        drl_backtest_score=Decimal("0.8"),
        safe_exit_probability=Decimal("0.7"),
        timestamp_utc=timestamp,
    )

    st = _FakeStreamlitWithFunctions()
    go = _FakePlotlyGo()
    rendered = render_approved_charts([matrix1, matrix2], None, st, go)

    assert len(rendered) == 2
    assert "RELIANCE" in rendered
    assert "TCS" in rendered
    assert len(st.charts) == 2


def test_render_dashboard_with_empty_data() -> None:
    """Test rendering dashboard with no market data."""
    payload = build_dashboard_payload({})
    streamlit = _FakeStreamlit()
    rendered = render_dashboard(payload, streamlit)

    assert rendered == list(REQUIRED_MARKET_TABS) + [INSTRUMENT_SCANNER_TAB]
    assert streamlit.titles == ["IATB Multi-Market Dashboard"]
