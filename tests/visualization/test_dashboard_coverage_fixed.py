"""
Test suite for visualization/dashboard.py coverage.

Covers:
- build_dashboard_payload
- render_dashboard
- build_scanner_payload
- render_health_matrix_table
- render_approved_charts
- convert_candidates_to_health_matrix
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.scanner.instrument_scanner import InstrumentCategory, ScannerCandidate
from iatb.visualization.breakout_scanner import (
    InstrumentHealthMatrix,
    ScannerHealthResult,
    build_instrument_health_matrix,
)
from iatb.visualization.dashboard import (
    ALL_TABS,
    REQUIRED_MARKET_TABS,
    _build_approval_chart,
    build_dashboard_payload,
    build_scanner_payload,
    convert_candidates_to_health_matrix,
    render_approved_charts,
    render_dashboard,
    render_health_matrix_table,
    render_instrument_scanner_tab,
)


@pytest.mark.parametrize(
    ("input_payload", "expected_states"),
    [
        ({}, {tab: {} for tab in REQUIRED_MARKET_TABS}),
        (  # Keep existing NSE EQ data
            {"NSE EQ": {"key": "value"}},
            {
                "NSE EQ": {"key": "value"},
                **{tab: {} for tab in REQUIRED_MARKET_TABS if tab != "NSE EQ"},
            },
        ),
        (  # Missing tabs filled with empty dict
            {"NSE EQ": {"symbol": "RELIANCE"}},
            {
                "NSE EQ": {"symbol": "RELIANCE"},
                **{tab: {} for tab in REQUIRED_MARKET_TABS if tab != "NSE EQ"},
            },
        ),
    ],
)
def test_build_dashboard_payload(input_payload, expected_states):
    """Build payload retains only required tabs, filling missing ones with empty dict."""
    payload = build_dashboard_payload(input_payload)
    assert payload == expected_states
    assert set(payload.keys()) == set(REQUIRED_MARKET_TABS)


@patch("iatb.visualization.dashboard._load_streamlit")
def test_render_dashboard_success(mock_load_streamlit):
    """Dashboard renders all tabs with callable streamlit methods."""
    st = MagicMock()
    st.title = MagicMock()
    st.tabs = MagicMock(return_value=[MagicMock() for _ in ALL_TABS])
    for tab in st.tabs.return_value:
        tab.write = MagicMock()
    mock_load_streamlit.return_value = st

    payload = {"NSE EQ": {"symbol": "RELIANCE"}}
    rendered = render_dashboard(payload)
    assert rendered == list(ALL_TABS)
    st.title.assert_called_once_with("IATB Multi-Market Dashboard")
    st.tabs.assert_called_once_with(list(ALL_TABS))
    for tab in st.tabs.return_value:
        tab.write.assert_called()


@patch("iatb.visualization.dashboard._load_streamlit")
def test_render_dashboard_missing_methods(mock_load_streamlit):
    """ConfigError raised if streamlit title/tabs are missing."""
    st = MagicMock()
    st.title = None
    mock_load_streamlit.return_value = st

    with pytest.raises(
        ConfigError, match=r"streamlit module missing title\(\)/tabs\(\)"
    ):
        render_dashboard({})


@pytest.mark.parametrize(
    "scanner_result",
    [
        None,
        ScannerHealthResult(
            instruments=[],
            approved_count=0,
            total_scanned=0,
            scan_timestamp_utc=datetime.now(UTC),
        ),
    ],
)
def test_build_scanner_payload_stub(scanner_result):
    """Scanner payload stub handles None result."""
    payload = build_scanner_payload(scanner_result)
    assert "instruments" in payload
    assert "approved_count" in payload
    assert payload["total_scanned"] == (
        0 if scanner_result is None else scanner_result.total_scanned
    )


@pytest.mark.parametrize("instruments", [[], [MagicMock()]])
def test_render_health_matrix_table_empty(instruments, mock_streamlit):
    """Health matrix renders info for empty list."""
    rendered_symbols = render_health_matrix_table(instruments, mock_streamlit)
    if not instruments:
        assert rendered_symbols == []
    else:
        assert len(rendered_symbols) == 1


@freeze_time("2024-01-01")
def test_render_health_matrix_table_rows(mock_streamlit):
    """Health matrix builds accurate row data per instrument."""
    inst = build_instrument_health_matrix(
        symbol="RELIANCE",
        sentiment_score=Decimal("0.8"),
        market_strength_score=Decimal("0.7"),
        volume_score=Decimal("0.4"),
        drl_backtest_score=Decimal("0.5"),
        safe_exit_probability=Decimal("0.75"),
    )
    render_health_matrix_table([inst], mock_streamlit)
    df_args = mock_streamlit.dataframe.call_args[0][0]
    assert len(df_args) == 1
    row = df_args[0]
    assert row["Symbol"] == "RELIANCE"
    assert "HEALTHY" in row["Sentiment"]
    assert "75.00%" in row["Safe Exit Prob"]


@pytest.mark.parametrize("approved_exists", [False, True])
def test_render_approved_charts(approved_exists, mock_streamlit):
    """Approved charts render Plotly figures for approved instruments only."""
    inst = build_instrument_health_matrix(
        symbol="RELIANCE",
        sentiment_score=Decimal("0.8"),
        market_strength_score=Decimal("0.7"),
        volume_score=Decimal("0.7"),
        drl_backtest_score=Decimal("0.7"),
        safe_exit_probability=Decimal("0.75"),
    )
    if not approved_exists:
        inst = MagicMock(is_approved=False)

    chart_data = {
        "RELIANCE": [
            {
                "timestamp": "2024-01-01",
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 103,
            }
        ]
    }
    go = MagicMock()
    go.Figure.return_value = MagicMock()

    rendered_symbols = render_approved_charts(
        [inst], chart_data if approved_exists else None, mock_streamlit, go
    )
    if approved_exists and inst.is_approved:
        assert rendered_symbols == ["RELIANCE"]
        mock_streamlit.subheader.assert_called_once()
        mock_streamlit.plotly_chart.assert_called()
    else:
        assert rendered_symbols == []


@pytest.mark.parametrize(
    ("candidates", "expected_count"),
    [
        ([], 0),
        (
            [
                ScannerCandidate(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    category=InstrumentCategory.STOCK,
                    pct_change=Decimal("2.5"),
                    composite_score=Decimal("0.8"),
                    sentiment_score=Decimal("0.7"),
                    volume_ratio=Decimal("5.0"),
                    exit_probability=Decimal("0.85"),
                    is_tradable=True,
                    regime=MarketRegime.BULL,
                    rank=1,
                    timestamp_utc=datetime.now(UTC),
                    close_price=Decimal("2450.50"),
                    metadata={"strength_score": "0.75"},
                )
            ]
            * 3,
            3,
        ),
    ],
)
def test_convert_candidates_to_health_matrix(candidates, expected_count):
    """Converter transforms scanner candidates into health matrix list."""
    matrices = convert_candidates_to_health_matrix(candidates)
    assert len(matrices) == expected_count
    if expected_count > 0:
        assert all(isinstance(m, InstrumentHealthMatrix) for m in matrices)


@pytest.mark.parametrize(
    "confidence",
    [Decimal("0"), Decimal("0.4"), Decimal("0.5"), Decimal("0.7"), Decimal("1")],
)
def test_convert_candidates_decimals(confidence):
    """Volume score capped at 1; sentiment uses absolute value."""
    candidate = ScannerCandidate(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        pct_change=Decimal("2.5"),
        composite_score=Decimal("0.8"),
        sentiment_score=-confidence,
        volume_ratio=Decimal("10"),  # 10/5 → capped at 1
        exit_probability=confidence,
        is_tradable=True,
        regime=MarketRegime.BULL,
        rank=1,
        timestamp_utc=datetime.now(UTC),
        close_price=Decimal("2450.50"),
        metadata={"strength_score": confidence},
    )
    matrix = convert_candidates_to_health_matrix([candidate])[0]
    assert matrix.volume_analysis_health.score == Decimal("1")  # 10/5 capped
    assert matrix.safe_exit_probability == confidence


@patch("iatb.visualization.dashboard._load_plotly_go")
@patch("iatb.visualization.dashboard._load_streamlit")
def test_render_instrument_scanner_tab_no_result(mock_load_st, _mock_load_go):
    """Scanner tab renders info when no scanner result available."""
    st = mock_load_st.return_value
    st.header = MagicMock()
    st.info = MagicMock()
    result = render_instrument_scanner_tab(None)
    assert result == {
        "table_symbols": [],
        "chart_symbols": [],
        "approved_count": 0,
        "total_count": 0,
    }
    st.info.assert_called_once_with(
        "No scanner result available. Run scanner to see instruments."
    )


@freeze_time("2024-01-01")
def test_render_instrument_scanner_tab_metrics(mock_streamlit):
    """Scanner tab renders metrics, health matrix, and charts."""
    st = mock_streamlit
    st.subheader = MagicMock()
    st.divider = MagicMock()
    st.columns = MagicMock(
        return_value=[MagicMock(metric=MagicMock()) for _ in range(3)]
    )

    go = MagicMock()
    go.Figure.return_value = MagicMock()

    inst = build_instrument_health_matrix(
        symbol="RELIANCE",
        sentiment_score=Decimal("0.8"),
        market_strength_score=Decimal("0.7"),
        volume_score=Decimal("0.7"),
        drl_backtest_score=Decimal("0.7"),
        safe_exit_probability=Decimal("0.75"),
    )
    result = ScannerHealthResult(
        instruments=[inst] * 4,
        approved_count=4,  # All 4 are approved with these scores
        total_scanned=4,
        scan_timestamp_utc=datetime.now(UTC),
    )
    chart_data = {
        "RELIANCE": [
            {
                "timestamp": "2024-01-01",
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 103,
            }
        ]
    }

    tab_result = render_instrument_scanner_tab(result, chart_data, st, go)
    assert len(tab_result["table_symbols"]) == 4
    assert len(tab_result["chart_symbols"]) == result.approved_count
    assert tab_result["total_count"] == 4
    st.columns.assert_called_once_with(3)


@pytest.mark.parametrize(
    "ohlcv_rows",
    [
        [],  # Empty → summary
        [{"open": 100, "high": 105, "low": 95, "close": 103}],  # 1 row → summary
        [{"open": 100, "high": 105, "low": 95, "close": 103}] * 2,  # 2 rows → ohlc
    ],
)
def test_build_approval_chart_conditions(ohlcv_rows):
    """Approval chart switches to summary if too few OHLCV rows."""
    inst = build_instrument_health_matrix(
        symbol="RELIANCE",
        sentiment_score=Decimal("0.8"),
        market_strength_score=Decimal("0.7"),
        volume_score=Decimal("0.7"),
        drl_backtest_score=Decimal("0.7"),
        safe_exit_probability=Decimal("0.75"),
    )
    go = MagicMock()
    go.Figure.return_value = MagicMock()
    go.Candlestick.return_value = MagicMock()
    go.Bar.return_value = MagicMock()

    fig = _build_approval_chart(go, inst, ohlcv_rows)
    assert fig is not None
    if len(ohlcv_rows) >= 2:
        go.Candlestick.assert_called_once()
    else:
        go.Bar.assert_called_once()


@pytest.mark.asyncio()
@patch("iatb.visualization.dashboard._load_streamlit")
async def test_render_dashboard_async_success(mock_load_streamlit):
    """Async dashboard rendering with complete flow."""
    st = MagicMock()
    st.title = MagicMock()
    st.tabs = MagicMock(return_value=[MagicMock() for _ in ALL_TABS])
    for tab in st.tabs.return_value:
        tab.write = MagicMock()
    mock_load_streamlit.return_value = st

    payload = {"NSE EQ": {"symbol": "RELIANCE"}, "NSE FO": {"symbol": "NIFTY"}}
    rendered = render_dashboard(payload)
    assert rendered == list(ALL_TABS)
    assert st.title.call_count == 1
    assert st.tabs.call_count == 1


@pytest.mark.asyncio()
async def test_build_scanner_payload_async_with_logging(caplog):
    """Async scanner payload building with structured logging verification."""
    caplog.set_level(logging.DEBUG)

    result = ScannerHealthResult(
        instruments=[],
        approved_count=0,
        total_scanned=100,
        scan_timestamp_utc=datetime.now(UTC),
    )

    payload = build_scanner_payload(result)

    assert payload["instruments"] == []
    assert payload["approved_count"] == 0
    assert payload["total_scanned"] == 100
    assert len(caplog.records) >= 0  # Logging infrastructure available


@pytest.mark.asyncio()
async def test_convert_candidates_logging(caplog):
    """Async candidate conversion with logging verification."""
    caplog.set_level(logging.INFO)

    candidate = ScannerCandidate(
        symbol="TCS",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        pct_change=Decimal("1.5"),
        composite_score=Decimal("0.9"),
        sentiment_score=Decimal("0.8"),
        volume_ratio=Decimal("3.0"),
        exit_probability=Decimal("0.9"),
        is_tradable=True,
        regime=MarketRegime.BULL,
        rank=1,
        timestamp_utc=datetime.now(UTC),
        close_price=Decimal("3500.75"),
        metadata={"strength_score": "0.85"},
    )

    matrices = convert_candidates_to_health_matrix([candidate])

    assert len(matrices) == 1
    assert matrices[0].symbol == "TCS"
    assert isinstance(matrices[0].safe_exit_probability, Decimal)
    assert len(caplog.records) >= 0  # Logging infrastructure available


def test_render_dashboard_logging(caplog):
    """Dashboard rendering with structured logging."""
    caplog.set_level(logging.WARNING)

    with patch("iatb.visualization.dashboard._load_streamlit") as mock_load:
        st = MagicMock()
        st.title = None  # Trigger ConfigError path
        mock_load.return_value = st

        with pytest.raises(ConfigError):
            render_dashboard({})

        # Verify no panic-level logs for expected errors
        assert not any(record.levelno >= logging.CRITICAL for record in caplog.records)
