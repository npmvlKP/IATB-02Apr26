"""
Unit tests for src/iatb/visualization/dashboard.py.

Tests cover: happy path, edge cases, errors, type handling,
precision handling, timezone handling.
All external calls are mocked (streamlit, plotly, scanner).
"""

import random
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    InstrumentScanner,
    MarketData,
    MarketRegime,
    ScannerCandidate,
    create_mock_rl_predictor,
    create_mock_sentiment_analyzer,
)
from iatb.visualization.breakout_scanner import (
    FactorHealth,
    HealthStatus,
    build_instrument_health_matrix,
    build_scanner_health_result,
    compute_overall_health,
    evaluate_factor_health,
    health_status_to_badge,
    health_status_to_color,
)
from iatb.visualization.dashboard import (
    ALL_TABS,
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

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def utc_timestamp():
    """UTC timestamp for testing."""
    return datetime(2026, 1, 5, 10, 30, 0, tzinfo=UTC)


@pytest.fixture
def mock_streamlit():
    """Mock streamlit module."""
    mock = MagicMock()
    mock.title = MagicMock()
    mock.tabs = MagicMock()
    mock.info = MagicMock()
    mock.dataframe = MagicMock()
    mock.header = MagicMock()
    mock.subheader = MagicMock()
    mock.metric = MagicMock()
    mock.divider = MagicMock()
    mock.columns = MagicMock()
    mock.plotly_chart = MagicMock()
    # Setup columns to return mocks with metric
    col_mock = MagicMock()
    col_mock.metric = MagicMock()
    mock.columns.return_value = [col_mock, col_mock, col_mock]
    return mock


@pytest.fixture
def mock_plotly_go():
    """Mock plotly graph_objects module."""
    mock = MagicMock()
    mock.Figure = MagicMock()
    mock.Candlestick = MagicMock()
    mock.Bar = MagicMock()
    mock.Scatter = MagicMock()
    return mock


@pytest.fixture
def mock_tab():
    """Mock tab object for streamlit tabs."""
    mock = MagicMock()
    mock.write = MagicMock()
    return mock


@pytest.fixture
def valid_market_data(utc_timestamp):
    """Valid market data for testing."""
    return MarketData(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        close_price=Decimal("2500.00"),
        prev_close_price=Decimal("2400.00"),
        volume=Decimal("10000000"),
        avg_volume=Decimal("4000000"),
        timestamp_utc=utc_timestamp,
        high_price=Decimal("2520.00"),
        low_price=Decimal("2390.00"),
        adx=Decimal("25.0"),
        atr_pct=Decimal("0.025"),
        breadth_ratio=Decimal("1.5"),
    )


@pytest.fixture
def gainer_market_data(utc_timestamp):
    """Market data for a gainer stock."""
    return MarketData(
        symbol="TATAMOTORS",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        close_price=Decimal("500.00"),
        prev_close_price=Decimal("450.00"),
        volume=Decimal("15000000"),
        avg_volume=Decimal("5000000"),
        timestamp_utc=utc_timestamp,
        high_price=Decimal("510.00"),
        low_price=Decimal("445.00"),
        adx=Decimal("30.0"),
        atr_pct=Decimal("0.020"),
        breadth_ratio=Decimal("2.0"),
    )


@pytest.fixture
def loser_market_data(utc_timestamp):
    """Market data for a loser stock."""
    return MarketData(
        symbol="INFY",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        close_price=Decimal("1400.00"),
        prev_close_price=Decimal("1500.00"),
        volume=Decimal("8000000"),
        avg_volume=Decimal("3000000"),
        timestamp_utc=utc_timestamp,
        high_price=Decimal("1490.00"),
        low_price=Decimal("1395.00"),
        adx=Decimal("20.0"),
        atr_pct=Decimal("0.030"),
        breadth_ratio=Decimal("0.8"),
    )


@pytest.fixture
def mock_sentiment_strong():
    """Mock sentiment analyzer returning VERY_STRONG."""
    return create_mock_sentiment_analyzer(
        {
            "RELIANCE": (Decimal("0.80"), True),
            "TATAMOTORS": (Decimal("0.85"), True),
            "INFY": (Decimal("-0.78"), True),
            "APPROVED": (Decimal("0.90"), True),
        }
    )


@pytest.fixture
def mock_sentiment_weak():
    """Mock sentiment analyzer returning weak sentiment."""
    return create_mock_sentiment_analyzer(
        {
            "RELIANCE": (Decimal("0.50"), False),
            "TATAMOTORS": (Decimal("0.60"), False),
        }
    )


@pytest.fixture
def mock_rl_positive():
    """Mock RL predictor returning positive exit probability."""
    return create_mock_rl_predictor(Decimal("0.65"))


@pytest.fixture
def mock_rl_negative():
    """Mock RL predictor returning negative exit probability."""
    return create_mock_rl_predictor(Decimal("0.30"))


@pytest.fixture
def scanner_with_mocks(mock_sentiment_strong, mock_rl_positive):
    """Scanner with all mocks configured."""
    return InstrumentScanner(
        sentiment_analyzer=mock_sentiment_strong,
        rl_predictor=mock_rl_positive,
    )


@pytest.fixture
def sample_health_matrix(utc_timestamp):
    """Sample health matrix for testing."""
    return build_instrument_health_matrix(
        symbol="TESTSTOCK",
        sentiment_score=Decimal("0.75"),
        market_strength_score=Decimal("0.80"),
        volume_score=Decimal("0.70"),
        drl_backtest_score=Decimal("0.65"),
        safe_exit_probability=Decimal("0.70"),
        timestamp_utc=utc_timestamp,
    )


@pytest.fixture
def sample_ohlcv_data(utc_timestamp):
    """Sample OHLCV data for chart testing."""
    return [
        {
            "timestamp": utc_timestamp,
            "open": Decimal("100"),
            "high": Decimal("105"),
            "low": Decimal("98"),
            "close": Decimal("103"),
            "volume": Decimal("1000000"),
        },
        {
            "timestamp": datetime(2026, 1, 5, 10, 31, 0, tzinfo=UTC),
            "open": Decimal("103"),
            "high": Decimal("108"),
            "low": Decimal("101"),
            "close": Decimal("106"),
            "volume": Decimal("1200000"),
        },
    ]


# =============================================================================
# HealthStatus Tests
# =============================================================================


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_health_status_values(self):
        """Test HealthStatus enum values."""
        assert HealthStatus.HEALTHY.value == "HEALTHY"
        assert HealthStatus.NOT_HEALTHY.value == "NOT_HEALTHY"
        assert HealthStatus.NEUTRAL.value == "NEUTRAL"


# =============================================================================
# FactorHealth Tests
# =============================================================================


class TestFactorHealth:
    """Tests for FactorHealth dataclass."""

    def test_factor_health_creation(self):
        """Test FactorHealth creation."""
        health = FactorHealth(
            factor_name="Sentiment",
            status=HealthStatus.HEALTHY,
            score=Decimal("0.75"),
            details="Test details",
        )
        assert health.factor_name == "Sentiment"
        assert health.status == HealthStatus.HEALTHY
        assert health.score == Decimal("0.75")
        assert health.details == "Test details"

    def test_factor_health_validation_empty_name(self):
        """Test empty factor name raises ConfigError."""
        with pytest.raises(ConfigError, match="factor_name"):
            FactorHealth(
                factor_name="",
                status=HealthStatus.HEALTHY,
                score=Decimal("0.75"),
                details="Test",
            )

    def test_factor_health_validation_score_range(self):
        """Test invalid score raises ConfigError."""
        with pytest.raises(ConfigError, match="score"):
            FactorHealth(
                factor_name="Test",
                status=HealthStatus.HEALTHY,
                score=Decimal("1.5"),
                details="Test",
            )
        with pytest.raises(ConfigError, match="score"):
            FactorHealth(
                factor_name="Test",
                status=HealthStatus.HEALTHY,
                score=Decimal("-0.1"),
                details="Test",
            )


# =============================================================================
# InstrumentHealthMatrix Tests
# =============================================================================


class TestInstrumentHealthMatrix:
    """Tests for InstrumentHealthMatrix dataclass."""

    def test_matrix_creation(self, sample_health_matrix):
        """Test InstrumentHealthMatrix creation."""
        matrix = sample_health_matrix
        assert matrix.symbol == "TESTSTOCK"
        assert matrix.sentiment_health.status == HealthStatus.HEALTHY
        assert matrix.market_strength_health.status == HealthStatus.HEALTHY
        assert matrix.volume_analysis_health.status == HealthStatus.HEALTHY
        assert matrix.drl_backtest_health.status == HealthStatus.HEALTHY
        assert matrix.overall_health == HealthStatus.HEALTHY
        assert matrix.is_approved is True
        assert matrix.timestamp_utc.tzinfo == UTC

    def test_matrix_validation_empty_symbol(self, utc_timestamp):
        """Test empty symbol raises ConfigError."""
        with pytest.raises(ConfigError, match="symbol"):
            build_instrument_health_matrix(
                symbol="",
                sentiment_score=Decimal("0.75"),
                market_strength_score=Decimal("0.80"),
                volume_score=Decimal("0.70"),
                drl_backtest_score=Decimal("0.65"),
                safe_exit_probability=Decimal("0.70"),
                timestamp_utc=utc_timestamp,
            )

    def test_matrix_validation_exit_prob_range(self, utc_timestamp):
        """Test invalid exit probability raises ConfigError."""
        with pytest.raises(ConfigError, match="safe_exit_probability"):
            build_instrument_health_matrix(
                symbol="TEST",
                sentiment_score=Decimal("0.75"),
                market_strength_score=Decimal("0.80"),
                volume_score=Decimal("0.70"),
                drl_backtest_score=Decimal("0.65"),
                safe_exit_probability=Decimal("1.5"),
                timestamp_utc=utc_timestamp,
            )
        with pytest.raises(ConfigError, match="safe_exit_probability"):
            build_instrument_health_matrix(
                symbol="TEST",
                sentiment_score=Decimal("0.75"),
                market_strength_score=Decimal("0.80"),
                volume_score=Decimal("0.70"),
                drl_backtest_score=Decimal("0.65"),
                safe_exit_probability=Decimal("-0.1"),
                timestamp_utc=utc_timestamp,
            )

    def test_matrix_validation_non_utc_timestamp(self):
        """Test non-UTC timestamp raises ConfigError."""
        naive_ts = datetime(2026, 1, 5, 10, 30, 0)  # noqa: DTZ001
        with pytest.raises(ConfigError, match="timestamp_utc"):
            build_instrument_health_matrix(
                symbol="TEST",
                sentiment_score=Decimal("0.75"),
                market_strength_score=Decimal("0.80"),
                volume_score=Decimal("0.70"),
                drl_backtest_score=Decimal("0.65"),
                safe_exit_probability=Decimal("0.70"),
                timestamp_utc=naive_ts,
            )

    def test_matrix_not_approved_when_unhealthy(self, utc_timestamp):
        """Test matrix is not approved when overall is not healthy."""
        matrix = build_instrument_health_matrix(
            symbol="BADSTOCK",
            sentiment_score=Decimal("0.30"),
            market_strength_score=Decimal("0.35"),
            volume_score=Decimal("0.40"),
            drl_backtest_score=Decimal("0.30"),
            safe_exit_probability=Decimal("0.25"),
            timestamp_utc=utc_timestamp,
        )
        assert matrix.overall_health == HealthStatus.NOT_HEALTHY
        assert matrix.is_approved is False


# =============================================================================
# ScannerHealthResult Tests
# =============================================================================


class TestScannerHealthResult:
    """Tests for ScannerHealthResult dataclass."""

    def test_result_creation(self, sample_health_matrix):
        """Test ScannerHealthResult creation."""
        result = build_scanner_health_result([sample_health_matrix])
        assert result.total_scanned == 1
        assert result.approved_count == 1
        assert result.scan_timestamp_utc.tzinfo == UTC
        assert len(result.instruments) == 1

    def test_result_empty_instruments(self):
        """Test result with empty instruments."""
        result = build_scanner_health_result([])
        assert result.total_scanned == 0
        assert result.approved_count == 0
        assert result.instruments == []

    def test_result_multiple_instruments(self, utc_timestamp):
        """Test result with multiple instruments."""
        matrices = [
            build_instrument_health_matrix(
                symbol=f"STOCK{i}",
                sentiment_score=Decimal("0.75"),
                market_strength_score=Decimal("0.80"),
                volume_score=Decimal("0.70"),
                drl_backtest_score=Decimal("0.65"),
                safe_exit_probability=Decimal("0.70"),
                timestamp_utc=utc_timestamp,
            )
            for i in range(3)
        ]
        result = build_scanner_health_result(matrices)
        assert result.total_scanned == 3
        assert result.approved_count == 3


# =============================================================================
# evaluate_factor_health Tests
# =============================================================================


class TestEvaluateFactorHealth:
    """Tests for evaluate_factor_health function."""

    def test_healthy_score(self):
        """Test healthy score returns HEALTHY."""
        health = evaluate_factor_health("Test", Decimal("0.75"))
        assert health.status == HealthStatus.HEALTHY
        assert health.score == Decimal("0.75")

    def test_unhealthy_score(self):
        """Test unhealthy score returns NOT_HEALTHY."""
        health = evaluate_factor_health("Test", Decimal("0.30"))
        assert health.status == HealthStatus.NOT_HEALTHY
        assert health.score == Decimal("0.30")

    def test_neutral_score(self):
        """Test neutral score returns NEUTRAL."""
        health = evaluate_factor_health("Test", Decimal("0.50"))
        assert health.status == HealthStatus.NEUTRAL
        assert health.score == Decimal("0.50")

    def test_custom_thresholds(self):
        """Test custom thresholds."""
        health = evaluate_factor_health(
            "Test",
            Decimal("0.55"),
            healthy_threshold=Decimal("0.5"),
            unhealthy_threshold=Decimal("0.3"),
        )
        assert health.status == HealthStatus.HEALTHY
        assert health.score == Decimal("0.55")

    def test_invalid_thresholds_raises(self):
        """Test invalid thresholds raise ConfigError."""
        with pytest.raises(ConfigError, match="healthy_threshold"):
            evaluate_factor_health(
                "Test",
                Decimal("0.75"),
                healthy_threshold=Decimal("0.3"),
                unhealthy_threshold=Decimal("0.5"),
            )


# =============================================================================
# compute_overall_health Tests
# =============================================================================


class TestComputeOverallHealth:
    """Tests for compute_overall_health function."""

    @pytest.fixture
    def healthy_factors(self):
        """Create healthy factor health objects."""
        return (
            FactorHealth("Sentiment", HealthStatus.HEALTHY, Decimal("0.75"), ""),
            FactorHealth("Market Strength", HealthStatus.HEALTHY, Decimal("0.80"), ""),
            FactorHealth("Volume", HealthStatus.HEALTHY, Decimal("0.70"), ""),
            FactorHealth("DRL", HealthStatus.HEALTHY, Decimal("0.65"), ""),
        )

    @pytest.fixture
    def unhealthy_factors(self):
        """Create unhealthy factor health objects."""
        return (
            FactorHealth("Sentiment", HealthStatus.NOT_HEALTHY, Decimal("0.30"), ""),
            FactorHealth(
                "Market Strength",
                HealthStatus.NOT_HEALTHY,
                Decimal("0.35"),
                "",
            ),
            FactorHealth("Volume", HealthStatus.HEALTHY, Decimal("0.70"), ""),
            FactorHealth("DRL", HealthStatus.HEALTHY, Decimal("0.65"), ""),
        )

    @pytest.fixture
    def mixed_factors(self):
        """Create mixed factor health objects."""
        return (
            FactorHealth("Sentiment", HealthStatus.HEALTHY, Decimal("0.75"), ""),
            FactorHealth("Market Strength", HealthStatus.HEALTHY, Decimal("0.80"), ""),
            FactorHealth("Volume", HealthStatus.NEUTRAL, Decimal("0.50"), ""),
            FactorHealth("DRL", HealthStatus.HEALTHY, Decimal("0.65"), ""),
        )

    def test_all_healthy_with_good_exit_prob(self, healthy_factors):
        """Test all healthy factors with good exit prob returns HEALTHY."""
        result = compute_overall_health(
            healthy_factors[0],
            healthy_factors[1],
            healthy_factors[2],
            healthy_factors[3],
            Decimal("0.70"),
        )
        assert result == HealthStatus.HEALTHY

    def test_two_unhealthy_returns_not_healthy(self, unhealthy_factors):
        """Test two unhealthy factors returns NOT_HEALTHY."""
        result = compute_overall_health(
            unhealthy_factors[0],
            unhealthy_factors[1],
            unhealthy_factors[2],
            unhealthy_factors[3],
            Decimal("0.70"),
        )
        assert result == HealthStatus.NOT_HEALTHY

    def test_mixed_factors_with_neutral(self, mixed_factors):
        """Test mixed factors with neutral returns HEALTHY (3 healthy, 1 neutral)."""
        result = compute_overall_health(
            mixed_factors[0],
            mixed_factors[1],
            mixed_factors[2],
            mixed_factors[3],
            Decimal("0.70"),
        )
        # 3 healthy + 1 neutral = HEALTHY overall
        assert result == HealthStatus.HEALTHY

    def test_low_exit_prob_returns_not_healthy(self, healthy_factors):
        """Test low exit prob returns NOT_HEALTHY."""
        result = compute_overall_health(
            healthy_factors[0],
            healthy_factors[1],
            healthy_factors[2],
            healthy_factors[3],
            Decimal("0.30"),
        )
        assert result == HealthStatus.NOT_HEALTHY


# =============================================================================
# health_status_to_* Tests
# =============================================================================


class TestHealthStatusHelpers:
    """Tests for health status helper functions."""

    def test_health_status_to_color(self):
        """Test health status to color conversion."""
        assert health_status_to_color(HealthStatus.HEALTHY) == "green"
        assert health_status_to_color(HealthStatus.NOT_HEALTHY) == "red"
        assert health_status_to_color(HealthStatus.NEUTRAL) == "gray"

    def test_health_status_to_badge(self):
        """Test health status to badge conversion."""
        assert health_status_to_badge(HealthStatus.HEALTHY) == "✅"
        assert health_status_to_badge(HealthStatus.NOT_HEALTHY) == "❌"
        assert health_status_to_badge(HealthStatus.NEUTRAL) == "⚪"


# =============================================================================
# build_dashboard_payload Tests
# =============================================================================


class TestBuildDashboardPayload:
    """Tests for build_dashboard_payload function."""

    def test_empty_payload_returns_all_tabs(self):
        """Test empty payload returns dict with all required tabs."""
        result = build_dashboard_payload({})
        # Function returns all required market tabs even with empty input
        for tab in REQUIRED_MARKET_TABS:
            assert tab in result
            assert result[tab] == {}

    def test_payload_with_data(self):
        """Test payload with market data."""
        market_data = {
            "NSE EQ": {"symbols": ["RELIANCE", "TCS"]},
            "NSE F&O": {"expiry": "26-Jan-2026"},
        }
        result = build_dashboard_payload(market_data)
        assert "NSE EQ" in result
        assert result["NSE EQ"]["symbols"] == ["RELIANCE", "TCS"]
        assert result["NSE F&O"]["expiry"] == "26-Jan-2026"
        assert result["BSE"] == {}
        assert result["MCX"] == {}

    def test_all_tabs_present(self):
        """Test all required tabs are present in result."""
        full_data = {tab: {"data": f"value_{tab}"} for tab in REQUIRED_MARKET_TABS}
        result = build_dashboard_payload(full_data)
        for tab in REQUIRED_MARKET_TABS:
            assert tab in result
            assert result[tab]["data"] == f"value_{tab}"


# =============================================================================
# build_scanner_payload Tests
# =============================================================================


class TestBuildScannerPayload:
    """Tests for build_scanner_payload function."""

    def test_none_result(self):
        """Test None result returns empty payload."""
        result = build_scanner_payload(None)
        assert result["instruments"] == []
        assert result["approved_count"] == 0
        assert result["total_scanned"] == 0
        assert result["scan_timestamp_utc"] is None

    def test_with_result(self, sample_health_matrix):
        """Test with valid result."""
        scanner_result = build_scanner_health_result([sample_health_matrix])
        result = build_scanner_payload(scanner_result)
        assert len(result["instruments"]) == 1
        assert result["approved_count"] == 1
        assert result["total_scanned"] == 1
        assert result["scan_timestamp_utc"] is not None


# =============================================================================
# render_dashboard Tests
# =============================================================================


class TestRenderDashboard:
    """Tests for render_dashboard function."""

    def test_render_calls_title_and_tabs(self, mock_streamlit):
        """Test render_dashboard calls title and tabs."""
        payload = {"NSE EQ": {"test": "data"}}
        render_dashboard(payload, mock_streamlit)
        mock_streamlit.title.assert_called_once_with("IATB Multi-Market Dashboard")
        mock_streamlit.tabs.assert_called_once()
        called_tabs = mock_streamlit.tabs.call_args[0][0]
        assert INSTRUMENT_SCANNER_TAB in called_tabs
        for tab in REQUIRED_MARKET_TABS:
            assert tab in called_tabs

    def test_render_missing_title_raises(self, mock_streamlit):
        """Test missing title function raises ConfigError."""
        del mock_streamlit.title
        with pytest.raises(ConfigError, match="title"):
            render_dashboard({}, mock_streamlit)

    def test_render_missing_tabs_raises(self, mock_streamlit):
        """Test missing tabs function raises ConfigError."""
        del mock_streamlit.tabs
        with pytest.raises(ConfigError, match="tabs"):
            render_dashboard({}, mock_streamlit)

    def test_render_returns_rendered_tabs(self, mock_streamlit):
        """Test render_dashboard returns list of rendered tabs."""
        payload = {"NSE EQ": {"test": "data"}}
        result = render_dashboard(payload, mock_streamlit)
        assert len(result) == len(ALL_TABS)
        for tab in ALL_TABS:
            assert tab in result


# =============================================================================
# render_health_matrix_table Tests
# =============================================================================


class TestRenderHealthMatrixTable:
    """Tests for render_health_matrix_table function."""

    def test_empty_instruments_shows_info(self, mock_streamlit):
        """Test empty instruments shows info message."""
        result = render_health_matrix_table([], mock_streamlit)
        assert result == []
        mock_streamlit.info.assert_called_once_with("No instruments to display.")

    def test_single_instrument(self, mock_streamlit, sample_health_matrix):
        """Test single instrument renders correctly."""
        result = render_health_matrix_table([sample_health_matrix], mock_streamlit)
        assert len(result) == 1
        assert result[0] == "TESTSTOCK"
        mock_streamlit.dataframe.assert_called_once()
        call_args = mock_streamlit.dataframe.call_args[0]
        rows = call_args[0]
        assert len(rows) == 1
        row = rows[0]
        assert "Symbol" in row
        assert "Sentiment" in row
        assert "Market Strength" in row
        assert "Volume Analysis" in row
        assert "DRL/Backtest" in row
        assert "Safe Exit Prob" in row
        assert "Overall" in row

    def test_multiple_instruments(self, utc_timestamp):
        """Test multiple instruments render correctly."""
        matrices = [
            build_instrument_health_matrix(
                symbol=f"STOCK{i}",
                sentiment_score=Decimal("0.75"),
                market_strength_score=Decimal("0.80"),
                volume_score=Decimal("0.70"),
                drl_backtest_score=Decimal("0.65"),
                safe_exit_probability=Decimal("0.70"),
                timestamp_utc=utc_timestamp,
            )
            for i in range(3)
        ]
        result = render_health_matrix_table(matrices, None)
        assert len(result) == 3


# =============================================================================
# render_approved_charts Tests
# =============================================================================


class TestRenderApprovedCharts:
    """Tests for render_approved_charts function."""

    def test_no_approved_returns_empty(self, mock_streamlit, mock_plotly_go, utc_timestamp):
        """Test no approved instruments returns empty list."""
        matrix = build_instrument_health_matrix(
            symbol="BADSTOCK",
            sentiment_score=Decimal("0.30"),
            market_strength_score=Decimal("0.35"),
            volume_score=Decimal("0.40"),
            drl_backtest_score=Decimal("0.30"),
            safe_exit_probability=Decimal("0.25"),
            timestamp_utc=utc_timestamp,
        )
        result = render_approved_charts([matrix], None, mock_streamlit, mock_plotly_go)
        assert result == []

    def test_approved_renders_summary_chart(
        self, mock_streamlit, mock_plotly_go, sample_health_matrix
    ):
        """Test approved instrument renders summary chart when no OHLCV."""
        result = render_approved_charts(
            [sample_health_matrix], None, mock_streamlit, mock_plotly_go
        )
        assert len(result) == 1
        assert result[0] == "TESTSTOCK"
        mock_streamlit.subheader.assert_called()
        mock_plotly_go.Figure.assert_called()
        mock_streamlit.plotly_chart.assert_called()

    def test_approved_renders_ohlcv_chart(
        self,
        mock_streamlit,
        mock_plotly_go,
        sample_health_matrix,
        sample_ohlcv_data,
    ):
        """Test approved instrument renders OHLCV chart when data provided."""
        result = render_approved_charts(
            [sample_health_matrix],
            {"TESTSTOCK": sample_ohlcv_data},
            mock_streamlit,
            mock_plotly_go,
        )
        assert len(result) == 1
        assert result[0] == "TESTSTOCK"
        mock_plotly_go.Figure.assert_called()
        mock_plotly_go.Candlestick.assert_called()


# =============================================================================
# render_instrument_scanner_tab Tests
# =============================================================================


class TestRenderInstrumentScannerTab:
    """Tests for render_instrument_scanner_tab function."""

    def test_none_result_shows_info(self, mock_streamlit):
        """Test None result shows info message."""
        result = render_instrument_scanner_tab(None, None, mock_streamlit, None)
        assert result["table_symbols"] == []
        assert result["chart_symbols"] == []
        mock_streamlit.info.assert_called_once()
        mock_streamlit.header.assert_called_once_with("🔍 Instrument Scanner")

    def test_with_result_renders_all(self, mock_streamlit, mock_plotly_go, sample_health_matrix):
        """Test with valid result renders all components."""
        scanner_result = build_scanner_health_result([sample_health_matrix])
        result = render_instrument_scanner_tab(scanner_result, None, mock_streamlit, mock_plotly_go)
        assert result["total_count"] == 1
        assert result["approved_count"] == 1
        assert len(result["table_symbols"]) == 1
        assert len(result["chart_symbols"]) == 1
        mock_streamlit.header.assert_called_once()
        mock_streamlit.subheader.assert_called()

    def test_with_chart_data(
        self,
        mock_streamlit,
        mock_plotly_go,
        sample_health_matrix,
        sample_ohlcv_data,
    ):
        """Test with chart data renders charts for approved instruments."""
        scanner_result = build_scanner_health_result([sample_health_matrix])
        result = render_instrument_scanner_tab(
            scanner_result,
            {"TESTSTOCK": sample_ohlcv_data},
            mock_streamlit,
            mock_plotly_go,
        )
        assert len(result["chart_symbols"]) == 1
        mock_plotly_go.Candlestick.assert_called()


# =============================================================================
# convert_candidates_to_health_matrix Tests
# =============================================================================


class TestConvertCandidatesToHealthMatrix:
    """Tests for convert_candidates_to_health_matrix function."""

    @pytest.fixture
    def scanner_candidate(self, utc_timestamp):
        """Create a scanner candidate for testing."""
        return ScannerCandidate(
            symbol="TESTSTOCK",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("5.0"),
            composite_score=Decimal("0.75"),
            sentiment_score=Decimal("0.80"),
            volume_ratio=Decimal("2.5"),
            exit_probability=Decimal("0.70"),
            is_tradable=True,
            regime=MarketRegime.BULL,
            rank=1,
            close_price=Decimal("100.00"),
            timestamp_utc=utc_timestamp,
            metadata={"strength_score": "0.80", "adx": "25.0"},
        )

    def test_single_candidate_conversion(self, scanner_candidate):
        """Test single candidate is converted correctly."""
        result = convert_candidates_to_health_matrix([scanner_candidate])
        assert len(result) == 1
        assert result[0].symbol == "TESTSTOCK"
        assert isinstance(result[0].sentiment_health, FactorHealth)
        assert isinstance(result[0].market_strength_health, FactorHealth)
        assert isinstance(result[0].volume_analysis_health, FactorHealth)
        assert isinstance(result[0].drl_backtest_health, FactorHealth)
        assert result[0].timestamp_utc.tzinfo == UTC

    def test_multiple_candidates_conversion(self, utc_timestamp):
        """Test multiple candidates are converted correctly."""
        candidates = [
            ScannerCandidate(
                symbol=f"STOCK{i}",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                pct_change=Decimal("5.0"),
                composite_score=Decimal("0.75"),
                sentiment_score=Decimal("0.80"),
                volume_ratio=Decimal("2.5"),
                exit_probability=Decimal("0.70"),
                is_tradable=True,
                regime=MarketRegime.BULL,
                rank=i,
                close_price=Decimal("100.00"),
                timestamp_utc=utc_timestamp,
                metadata={"strength_score": "0.80"},
            )
            for i in range(3)
        ]
        result = convert_candidates_to_health_matrix(candidates)
        assert len(result) == 3
        for i in range(3):
            assert result[i].symbol == f"STOCK{i}"

    def test_candidate_with_low_volume(self, utc_timestamp):
        """Test candidate with low volume gets correct score."""
        candidate = ScannerCandidate(
            symbol="LOWVOL",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("5.0"),
            composite_score=Decimal("0.50"),
            sentiment_score=Decimal("0.80"),
            volume_ratio=Decimal("0.3"),
            exit_probability=Decimal("0.70"),
            is_tradable=True,
            regime=MarketRegime.BULL,
            rank=1,
            close_price=Decimal("100.00"),
            timestamp_utc=utc_timestamp,
            metadata={"strength_score": "0.80"},
        )
        result = convert_candidates_to_health_matrix([candidate])
        assert result[0].volume_analysis_health.score <= Decimal("1.0")

    def test_custom_thresholds(self, scanner_candidate):
        """Test custom thresholds work correctly."""
        result = convert_candidates_to_health_matrix(
            [scanner_candidate],
            sentiment_threshold=Decimal("0.5"),
            strength_threshold=Decimal("0.5"),
            volume_threshold=Decimal("0.5"),
            drl_threshold=Decimal("0.5"),
        )
        assert len(result) == 1
