"""Tests for dashboard Plotly chart generation and API endpoints."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from iatb.core.enums import Exchange
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    ScannerCandidate,
)


def test_generate_plotly_chart_with_empty_candidates() -> None:
    """Test chart generation with empty candidate list."""
    from scripts.dashboard import _generate_plotly_chart

    chart = _generate_plotly_chart([], "Test Chart")
    assert chart == {"data": [], "layout": {"title": {"text": "Test Chart"}}}


def test_generate_plotly_chart_with_candidates() -> None:
    """Test chart generation with valid candidates."""
    from scripts.dashboard import _generate_plotly_chart

    candidates = [
        {
            "symbol": "RELIANCE",
            "pct_change": Decimal("5.25"),
            "composite_score": Decimal("0.85"),
            "volume_ratio": Decimal("3.5"),
        },
        {
            "symbol": "INFY",
            "pct_change": Decimal("3.10"),
            "composite_score": Decimal("0.75"),
            "volume_ratio": Decimal("2.8"),
        },
    ]

    chart = _generate_plotly_chart(candidates, "Test Chart")

    # Verify structure
    assert "data" in chart
    assert "layout" in chart
    assert len(chart["data"]) == 3  # bar, scatter, scatter

    # Verify data series
    symbols = chart["data"][0]["x"]
    assert symbols == ["RELIANCE", "INFY"]

    # Verify values are floats (for Plotly)
    assert isinstance(chart["data"][0]["y"][0], float)
    assert chart["data"][0]["y"][0] == 5.25

    # Verify layout
    assert chart["layout"]["title"]["text"] == "Test Chart"
    assert chart["layout"]["plot_bgcolor"] == "#0d1117"
    assert "yaxis2" in chart["layout"]


def test_generate_plotly_chart_decimal_conversion() -> None:
    """Test that Decimal values are properly converted to float."""
    from scripts.dashboard import _generate_plotly_chart

    candidates = [
        {
            "symbol": "TCS",
            "pct_change": Decimal("2.50"),
            "composite_score": Decimal("0.90"),
            "volume_ratio": Decimal("4.0"),
        }
    ]

    chart = _generate_plotly_chart(candidates, "Decimal Test")

    # All y values should be floats, not Decimals
    for series in chart["data"]:
        assert all(isinstance(y, float) for y in series["y"])

    # Verify exact values
    assert chart["data"][0]["y"][0] == 2.50
    assert chart["data"][1]["y"][0] == 0.90
    assert chart["data"][2]["y"][0] == 4.0


def test_update_scanner_data() -> None:
    """Test updating global scanner data."""
    from scripts.dashboard import _SCANNER_DATA, _update_scanner_data

    gainers = [
        {
            "symbol": "RELIANCE",
            "pct_change": Decimal("5.25"),
            "composite_score": Decimal("0.85"),
            "volume_ratio": Decimal("3.5"),
        }
    ]
    losers = [
        {
            "symbol": "TATASTEEL",
            "pct_change": Decimal("-2.10"),
            "composite_score": Decimal("0.60"),
            "volume_ratio": Decimal("2.1"),
        }
    ]

    _update_scanner_data(gainers, losers)

    assert _SCANNER_DATA["gainers"] == gainers
    assert _SCANNER_DATA["losers"] == losers
    assert "timestamp" in _SCANNER_DATA
    assert _SCANNER_DATA["timestamp"] != ""


def test_dashboard_charts_gainers_endpoint_logic() -> None:
    """Test gainers chart endpoint logic generates valid JSON."""
    from scripts.dashboard import _SCANNER_DATA, _generate_plotly_chart

    # Setup mock data
    _SCANNER_DATA["gainers"] = [
        {
            "symbol": "RELIANCE",
            "pct_change": Decimal("5.25"),
            "composite_score": Decimal("0.85"),
            "volume_ratio": Decimal("3.5"),
        }
    ]

    gainers = _SCANNER_DATA.get("gainers", [])
    chart = _generate_plotly_chart(gainers, "Top Gainers - Live Scanner")
    body = json.dumps(chart, default=str).encode()

    # Verify response
    assert b"data" in body
    assert b"layout" in body
    assert b"RELIANCE" in body
    assert b"Top Gainers" in body


def test_dashboard_handler_charts_losers_endpoint() -> None:
    """Test /api/charts/losers endpoint returns valid chart data."""
    from scripts.dashboard import _SCANNER_DATA

    # Setup mock data
    _SCANNER_DATA["losers"] = [
        {
            "symbol": "TATASTEEL",
            "pct_change": Decimal("-2.10"),
            "composite_score": Decimal("0.60"),
            "volume_ratio": Decimal("2.1"),
        }
    ]

    from scripts.dashboard import _generate_plotly_chart

    losers = _SCANNER_DATA.get("losers", [])
    chart = _generate_plotly_chart(losers, "Top Losers - Live Scanner")

    # Verify chart structure
    assert "data" in chart
    assert "layout" in chart
    assert len(chart["data"]) == 3
    assert chart["layout"]["title"]["text"] == "Top Losers - Live Scanner"


def test_scanner_candidate_to_dict_compatibility() -> None:
    """Test that ScannerCandidate objects can be converted to dict for charts."""
    from scripts.dashboard import _generate_plotly_chart

    candidate = ScannerCandidate(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        pct_change=Decimal("5.25"),
        composite_score=Decimal("0.85"),
        sentiment_score=Decimal("0.80"),
        volume_ratio=Decimal("3.5"),
        exit_probability=Decimal("0.75"),
        is_tradable=True,
        regime="uptrend",  # type: ignore[arg-type]
        rank=1,
        timestamp_utc=datetime(2026, 1, 5, 10, 30, tzinfo=UTC),
        metadata={"adx": "45.5", "atr_pct": "2.1", "strength_score": "0.9"},
    )

    # Convert to dict
    candidate_dict = {
        "symbol": candidate.symbol,
        "pct_change": candidate.pct_change,
        "composite_score": candidate.composite_score,
        "volume_ratio": candidate.volume_ratio,
    }

    chart = _generate_plotly_chart([candidate_dict], "Scanner Candidate Test")

    assert len(chart["data"]) == 3
    assert chart["data"][0]["x"] == ["RELIANCE"]
    assert chart["data"][0]["y"][0] == 5.25


def test_chart_layout_consistency() -> None:
    """Test that chart layout maintains consistent styling."""
    from scripts.dashboard import _generate_plotly_chart

    candidates = [
        {
            "symbol": "TEST",
            "pct_change": Decimal("1.0"),
            "composite_score": Decimal("0.5"),
            "volume_ratio": Decimal("1.5"),
        }
    ]

    chart = _generate_plotly_chart(candidates, "Layout Test")
    layout = chart["layout"]

    # Verify dark theme colors
    assert layout["plot_bgcolor"] == "#0d1117"
    assert layout["paper_bgcolor"] == "#161b22"
    assert layout["font"]["color"] == "#8b949e"
    assert layout["xaxis"]["gridcolor"] == "#30363d"
    assert layout["yaxis"]["gridcolor"] == "#30363d"

    # Verify dual y-axis setup
    assert "yaxis2" in layout
    assert layout["yaxis2"]["side"] == "right"
    assert layout["yaxis2"]["overlaying"] == "y"


def test_chart_data_series_types() -> None:
    """Test that chart data series have correct types and names."""
    from scripts.dashboard import _generate_plotly_chart

    candidates = [
        {
            "symbol": "TEST",
            "pct_change": Decimal("1.0"),
            "composite_score": Decimal("0.5"),
            "volume_ratio": Decimal("1.5"),
        }
    ]

    chart = _generate_plotly_chart(candidates, "Series Test")
    data = chart["data"]

    # Verify series 0: bar chart for % change
    assert data[0]["type"] == "bar"
    assert data[0]["name"] == "% Change"
    assert data[0]["marker"]["color"] == "#58a6ff"
    assert data[0]["yaxis"] == "y"

    # Verify series 1: scatter line for composite score
    assert data[1]["type"] == "scatter"
    assert data[1]["mode"] == "lines+markers"
    assert data[1]["name"] == "Composite Score"
    assert data[1]["line"]["color"] == "#3fb950"
    assert data[1]["yaxis"] == "y2"

    # Verify series 2: scatter markers for volume ratio
    assert data[2]["type"] == "scatter"
    assert data[2]["mode"] == "markers"
    assert data[2]["name"] == "Volume Ratio"
    assert data[2]["marker"]["color"] == "#d29922"
    assert data[2]["marker"]["size"] == 10
    assert data[2]["yaxis"] == "y2"


def test_chart_handles_missing_fields() -> None:
    """Test that chart generation handles missing candidate fields gracefully."""
    from scripts.dashboard import _generate_plotly_chart

    # Candidate with missing fields
    candidates = [
        {
            "symbol": "TEST",
            # pct_change missing
            "composite_score": Decimal("0.5"),
            "volume_ratio": Decimal("1.5"),
        }
    ]

    chart = _generate_plotly_chart(candidates, "Missing Fields Test")

    # Should still generate chart with defaults
    assert "data" in chart
    assert len(chart["data"]) == 3
    # Missing values should default to 0
    assert chart["data"][0]["y"][0] == 0.0
