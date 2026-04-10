"""
Tests for dashboard integration: Zerodha status, exchange status,
scanner matrix, live charts, and SQLite polling.

All external APIs (Zerodha/Kite) are fully mocked. No real network calls.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.enums import Exchange
from iatb.visualization.dashboard import (
    render_exchange_status_panel,
    render_live_chart,
    render_scanner_matrix_from_sqlite,
    render_system_tab,
    render_zerodha_account_status,
)
from iatb.visualization.dashboard_status import (
    ExchangeSessionStatus,
    ScannerInstrumentRow,
    ZerodhaAccountSnapshot,
    initialize_status_tables,
    read_engine_status,
    read_exchange_session_status,
    read_scanner_results,
    read_zerodha_snapshot,
    write_engine_heartbeat,
    write_scanner_results,
    write_zerodha_snapshot,
)


@dataclass
class _FakeStreamlit:
    """Mock Streamlit module with all required functions."""

    headers: list[str] = field(default_factory=list)
    subheaders: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)
    successes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: list[tuple[str, str, str]] = field(default_factory=list)
    dataframes: list[object] = field(default_factory=list)
    charts: list[object] = field(default_factory=list)
    dividers: int = 0

    def header(self, text: str) -> None:
        self.headers.append(text)

    def subheader(self, text: str) -> None:
        self.subheaders.append(text)

    def info(self, text: str) -> None:
        self.infos.append(text)

    def success(self, text: str) -> None:
        self.successes.append(text)

    def warning(self, text: str) -> None:
        self.warnings.append(text)

    def metric(self, label: str, value: str, delta: str = "") -> None:
        self.metrics.append((label, value, delta))

    def dataframe(self, data: object, **kwargs: object) -> None:
        self.dataframes.append(data)

    def plotly_chart(self, fig: object, **kwargs: object) -> None:
        self.charts.append(fig)

    def columns(self, n: int) -> list["_FakeStreamlit"]:
        return [self for _ in range(n)]

    def divider(self) -> None:
        self.dividers += 1


class _FakePlotlyGo:
    """Mock plotly.graph_objects module."""

    def __init__(self) -> None:
        self.figures: list[object] = []

    def Figure(self) -> "_FakeFigure":  # noqa: N802
        fig = _FakeFigure()
        self.figures.append(fig)
        return fig

    def Candlestick(self, **kwargs: object) -> object:  # noqa: N802
        return {"type": "candlestick", **kwargs}

    def Bar(self, **kwargs: object) -> object:  # noqa: N802
        return {"type": "bar", **kwargs}


class _FakeFigure:
    """Mock Plotly Figure class."""

    def __init__(self) -> None:
        self.traces: list[object] = []
        self.layout: dict[str, object] = {}

    def add_trace(self, trace: object) -> None:
        self.traces.append(trace)

    def update_layout(self, **kwargs: object) -> None:
        self.layout.update(kwargs)


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database path."""
    return tmp_path / "test_status.sqlite"


@pytest.fixture()
def initialized_db(tmp_db: Path) -> Path:
    """Create and initialize a temporary SQLite database."""
    initialize_status_tables(tmp_db)
    return tmp_db


@pytest.fixture()
def populated_db(initialized_db: Path) -> Path:
    """Create a fully populated SQLite database."""
    write_engine_heartbeat(
        initialized_db,
        mode="PAPER",
        trades_today=5,
    )
    write_zerodha_snapshot(
        user_id="AB1234",
        user_name="Test User",
        user_email="test@example.com",
        available_balance=Decimal("150000.50"),
        equity_margin=Decimal("120000.00"),
        commodity_margin=Decimal("30000.00"),
        db_path=initialized_db,
    )
    write_scanner_results(
        [
            ScannerInstrumentRow(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                sentiment_score=Decimal("0.85"),
                market_strength_score=Decimal("0.78"),
                drl_score=Decimal("0.72"),
                volume_profile_score=Decimal("0.80"),
                composite_score=Decimal("0.79"),
                is_approved=True,
                scan_timestamp_utc=datetime.now(UTC),
            ),
            ScannerInstrumentRow(
                symbol="TCS",
                exchange=Exchange.NSE,
                sentiment_score=Decimal("0.45"),
                market_strength_score=Decimal("0.50"),
                drl_score=Decimal("0.40"),
                volume_profile_score=Decimal("0.35"),
                composite_score=Decimal("0.42"),
                is_approved=False,
                scan_timestamp_utc=datetime.now(UTC),
            ),
        ],
        db_path=initialized_db,
    )
    return initialized_db


class TestDashboardStatusSQLite:
    """Tests for dashboard_status.py SQLite operations."""

    def test_initialize_creates_tables(self, tmp_db: Path) -> None:
        initialize_status_tables(tmp_db)
        assert tmp_db.exists()

    def test_write_and_read_heartbeat(self, initialized_db: Path) -> None:
        write_engine_heartbeat(initialized_db, mode="PAPER", trades_today=3)
        status = read_engine_status(initialized_db)
        assert status.is_running is True
        assert status.mode == "PAPER"
        assert status.trades_today == 3
        assert status.last_heartbeat_utc is not None

    def test_read_engine_status_no_db(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent.sqlite"
        status = read_engine_status(fake_path)
        assert status.is_running is False
        assert status.mode == "UNKNOWN"

    def test_write_and_read_zerodha_snapshot(self, initialized_db: Path) -> None:
        write_zerodha_snapshot(
            user_id="XY9876",
            user_name="Trader One",
            user_email="trader@example.com",
            available_balance=Decimal("250000.75"),
            equity_margin=Decimal("200000.00"),
            commodity_margin=Decimal("50000.00"),
            db_path=initialized_db,
        )
        snapshot = read_zerodha_snapshot(initialized_db)
        assert snapshot is not None
        assert snapshot.user_id == "XY9876"
        assert snapshot.user_name == "Trader One"
        assert snapshot.user_email == "trader@example.com"
        assert snapshot.available_balance == Decimal("250000.75")
        assert snapshot.equity_margin == Decimal("200000.00")
        assert snapshot.commodity_margin == Decimal("50000.00")
        assert snapshot.snapshot_timestamp_utc is not None

    def test_read_zerodha_snapshot_no_data(self, initialized_db: Path) -> None:
        snapshot = read_zerodha_snapshot(initialized_db)
        assert snapshot is None

    def test_read_zerodha_snapshot_no_db(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent.sqlite"
        snapshot = read_zerodha_snapshot(fake_path)
        assert snapshot is None

    def test_write_and_read_scanner_results(self, initialized_db: Path) -> None:
        now = datetime.now(UTC)
        instruments = [
            ScannerInstrumentRow(
                symbol="INFY",
                exchange=Exchange.NSE,
                sentiment_score=Decimal("0.80"),
                market_strength_score=Decimal("0.75"),
                drl_score=Decimal("0.70"),
                volume_profile_score=Decimal("0.65"),
                composite_score=Decimal("0.73"),
                is_approved=True,
                scan_timestamp_utc=now,
            ),
            ScannerInstrumentRow(
                symbol="WIPRO",
                exchange=Exchange.NSE,
                sentiment_score=Decimal("0.30"),
                market_strength_score=Decimal("0.35"),
                drl_score=Decimal("0.25"),
                volume_profile_score=Decimal("0.20"),
                composite_score=Decimal("0.28"),
                is_approved=False,
                scan_timestamp_utc=now,
            ),
        ]
        write_scanner_results(instruments, initialized_db)
        results = read_scanner_results(initialized_db)
        assert len(results) == 2
        assert results[0].symbol == "INFY"
        assert results[0].is_approved is True
        assert results[1].symbol == "WIPRO"
        assert results[1].is_approved is False

    def test_read_scanner_results_no_db(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent.sqlite"
        results = read_scanner_results(fake_path)
        assert results == []

    def test_scanner_results_overwrite_on_write(self, initialized_db: Path) -> None:
        now = datetime.now(UTC)
        instruments_a = [
            ScannerInstrumentRow(
                symbol="A",
                exchange=Exchange.NSE,
                sentiment_score=Decimal("0.5"),
                market_strength_score=Decimal("0.5"),
                drl_score=Decimal("0.5"),
                volume_profile_score=Decimal("0.5"),
                composite_score=Decimal("0.5"),
                is_approved=False,
                scan_timestamp_utc=now,
            ),
        ]
        write_scanner_results(instruments_a, initialized_db)
        assert len(read_scanner_results(initialized_db)) == 1

        instruments_b = [
            ScannerInstrumentRow(
                symbol="B1",
                exchange=Exchange.NSE,
                sentiment_score=Decimal("0.6"),
                market_strength_score=Decimal("0.6"),
                drl_score=Decimal("0.6"),
                volume_profile_score=Decimal("0.6"),
                composite_score=Decimal("0.6"),
                is_approved=True,
                scan_timestamp_utc=now,
            ),
            ScannerInstrumentRow(
                symbol="B2",
                exchange=Exchange.MCX,
                sentiment_score=Decimal("0.7"),
                market_strength_score=Decimal("0.7"),
                drl_score=Decimal("0.7"),
                volume_profile_score=Decimal("0.7"),
                composite_score=Decimal("0.7"),
                is_approved=True,
                scan_timestamp_utc=now,
            ),
        ]
        write_scanner_results(instruments_b, initialized_db)
        results = read_scanner_results(initialized_db)
        assert len(results) == 2
        symbols = {r.symbol for r in results}
        assert symbols == {"B1", "B2"}


class TestExchangeSessionStatus:
    """Tests for exchange session open/closed detection."""

    @patch("iatb.visualization.dashboard_status.datetime")
    def test_nse_weekday_open(self, mock_dt: MagicMock) -> None:
        mock_now = datetime(2026, 4, 9, 9, 0, tzinfo=UTC)
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)  # noqa: DTZ001
        status = read_exchange_session_status(Exchange.NSE, "09:15", "15:30")
        assert status.exchange == Exchange.NSE
        assert status.is_open is True
        assert status.status_label == "OPEN"

    @patch("iatb.visualization.dashboard_status.datetime")
    def test_nse_weekday_closed_after_hours(self, mock_dt: MagicMock) -> None:
        mock_now = datetime(2026, 4, 9, 16, 0, tzinfo=UTC)
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)  # noqa: DTZ001
        status = read_exchange_session_status(Exchange.NSE, "09:15", "15:30")
        assert status.is_open is False
        assert status.status_label == "CLOSED"

    @patch("iatb.visualization.dashboard_status.datetime")
    def test_nse_weekday_premarket(self, mock_dt: MagicMock) -> None:
        mock_now = datetime(2026, 4, 9, 3, 0, tzinfo=UTC)
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)  # noqa: DTZ001
        status = read_exchange_session_status(Exchange.NSE, "09:15", "15:30")
        assert status.is_open is False
        assert status.status_label == "PRE-MARKET"

    @patch("iatb.visualization.dashboard_status.datetime")
    def test_nse_weekend(self, mock_dt: MagicMock) -> None:
        mock_now = datetime(2026, 4, 11, 10, 0, tzinfo=UTC)
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)  # noqa: DTZ001
        status = read_exchange_session_status(Exchange.NSE, "09:15", "15:30")
        assert status.is_open is False
        assert "Weekend" in status.status_label

    @patch("iatb.visualization.dashboard_status.datetime")
    def test_mcx_evening_session(self, mock_dt: MagicMock) -> None:
        mock_now = datetime(2026, 4, 9, 17, 0, tzinfo=UTC)
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)  # noqa: DTZ001
        status = read_exchange_session_status(Exchange.MCX, "09:00", "23:30")
        assert status.is_open is True
        assert status.status_label == "OPEN"

    def test_exchange_status_invalid_time_format(self) -> None:
        status = read_exchange_session_status(Exchange.CDS, "invalid", "time")
        assert status.status_label == "ERROR"
        assert status.is_open is False

    @patch("iatb.visualization.dashboard_status.datetime")
    def test_cds_session(self, mock_dt: MagicMock) -> None:
        mock_now = datetime(2026, 4, 9, 6, 0, tzinfo=UTC)
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)  # noqa: DTZ001
        status = read_exchange_session_status(Exchange.CDS, "09:00", "17:00")
        assert status.is_open is True
        assert status.status_label == "OPEN"


class TestRenderZerodhaAccountStatus:
    """Tests for render_zerodha_account_status."""

    def test_no_snapshot_shows_warning(self) -> None:
        st = _FakeStreamlit()
        result = render_zerodha_account_status(None, st)
        assert result["rendered"] is False
        assert len(st.warnings) == 1
        assert "Zerodha" in st.warnings[0]

    def test_with_snapshot_renders_metrics(self) -> None:
        snapshot = ZerodhaAccountSnapshot(
            user_id="AB1234",
            user_name="Test Trader",
            user_email="test@test.com",
            available_balance=Decimal("100000.50"),
            equity_margin=Decimal("80000.00"),
            commodity_margin=Decimal("20000.00"),
            snapshot_timestamp_utc=datetime.now(UTC),
        )
        st = _FakeStreamlit()
        result = render_zerodha_account_status(snapshot, st)
        assert result["rendered"] is True
        assert result["user_id"] == "AB1234"
        assert len(st.successes) == 1
        assert "AB1234" in st.successes[0]
        assert len(st.metrics) >= 3
        metric_labels = [m[0] for m in st.metrics]
        assert "User ID" in metric_labels
        assert "Available Balance" in metric_labels
        assert "Email" in metric_labels

    def test_snapshot_without_timestamp(self) -> None:
        snapshot = ZerodhaAccountSnapshot(
            user_id="XY0001",
            user_name="NoTime",
            user_email="n@t.com",
            available_balance=Decimal("50000"),
            equity_margin=Decimal("40000"),
            commodity_margin=Decimal("10000"),
            snapshot_timestamp_utc=None,
        )
        st = _FakeStreamlit()
        result = render_zerodha_account_status(snapshot, st)
        assert result["rendered"] is True
        assert "N/A" in st.successes[0]


class TestRenderExchangeStatusPanel:
    """Tests for render_exchange_status_panel."""

    def test_with_explicit_sessions(self) -> None:
        sessions = [
            ExchangeSessionStatus(
                exchange=Exchange.NSE,
                is_open=True,
                session_open_time="09:15",
                session_close_time="15:30",
                status_label="OPEN",
            ),
            ExchangeSessionStatus(
                exchange=Exchange.CDS,
                is_open=False,
                session_open_time="09:00",
                session_close_time="17:00",
                status_label="CLOSED",
            ),
            ExchangeSessionStatus(
                exchange=Exchange.MCX,
                is_open=True,
                session_open_time="09:00",
                session_close_time="23:30",
                status_label="OPEN",
            ),
        ]
        st = _FakeStreamlit()
        rendered = render_exchange_status_panel(sessions, st)
        assert len(rendered) == 3
        assert rendered[0]["exchange"] == "NSE"
        assert rendered[0]["is_open"] is True
        assert rendered[1]["exchange"] == "CDS"
        assert rendered[1]["is_open"] is False
        assert len(st.metrics) == 3

    def test_default_sessions_generated(self) -> None:
        st = _FakeStreamlit()
        rendered = render_exchange_status_panel(None, st)
        assert len(rendered) == 3
        exchanges = {r["exchange"] for r in rendered}
        assert exchanges == {"NSE", "CDS", "MCX"}


class TestRenderScannerMatrix:
    """Tests for render_scanner_matrix_from_sqlite."""

    def test_empty_instruments(self) -> None:
        st = _FakeStreamlit()
        go = _FakePlotlyGo()
        result = render_scanner_matrix_from_sqlite([], st, go)
        assert result["total"] == 0
        assert result["approved"] == 0
        assert len(st.infos) == 1

    def test_with_approved_and_rejected(self) -> None:
        now = datetime.now(UTC)
        instruments = [
            ScannerInstrumentRow(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                sentiment_score=Decimal("0.85"),
                market_strength_score=Decimal("0.78"),
                drl_score=Decimal("0.72"),
                volume_profile_score=Decimal("0.80"),
                composite_score=Decimal("0.79"),
                is_approved=True,
                scan_timestamp_utc=now,
            ),
            ScannerInstrumentRow(
                symbol="TCS",
                exchange=Exchange.NSE,
                sentiment_score=Decimal("0.45"),
                market_strength_score=Decimal("0.50"),
                drl_score=Decimal("0.40"),
                volume_profile_score=Decimal("0.35"),
                composite_score=Decimal("0.42"),
                is_approved=False,
                scan_timestamp_utc=now,
            ),
        ]
        st = _FakeStreamlit()
        go = _FakePlotlyGo()
        result = render_scanner_matrix_from_sqlite(instruments, st, go)
        assert result["total"] == 2
        assert result["approved"] == 1
        assert len(st.dataframes) == 1
        assert "RELIANCE" in result["symbols"]
        assert "TCS" not in result["symbols"]
        assert len(go.figures) == 1

    def test_reads_from_sqlite(self, populated_db: Path) -> None:
        st = _FakeStreamlit()
        go = _FakePlotlyGo()
        result = render_scanner_matrix_from_sqlite(
            db_path=populated_db,
            streamlit_module=st,
            plotly_module=go,
        )
        assert result["total"] == 2
        assert result["approved"] == 1
        assert "RELIANCE" in result["symbols"]


class TestRenderLiveChart:
    """Tests for render_live_chart."""

    def test_insufficient_data_returns_none(self) -> None:
        st = _FakeStreamlit()
        go = _FakePlotlyGo()
        result = render_live_chart("TEST", [{"close": 100}], go, st)
        assert result is None
        assert len(st.infos) == 1

    def test_with_ohlcv_data(self) -> None:
        ts = datetime.now(UTC)
        data = [
            {
                "timestamp": ts,
                "open": Decimal("100"),
                "high": Decimal("105"),
                "low": Decimal("98"),
                "close": Decimal("103"),
            },
            {
                "timestamp": ts,
                "open": Decimal("103"),
                "high": Decimal("108"),
                "low": Decimal("101"),
                "close": Decimal("106"),
            },
        ]
        st = _FakeStreamlit()
        go = _FakePlotlyGo()
        fig = render_live_chart("RELIANCE", data, go, st)
        assert fig is not None
        assert len(st.charts) == 1


class TestRenderSystemTab:
    """Tests for render_system_tab."""

    def test_with_populated_db(self, populated_db: Path) -> None:
        st = _FakeStreamlit()
        result = render_system_tab(populated_db, st)
        assert result["engine_running"] is True
        assert result["zerodha_connected"] is True
        assert len(result["exchanges"]) == 3
        assert len(st.successes) >= 2
        assert any("Engine Online" in s for s in st.successes)
        assert any("AB1234" in s for s in st.successes)

    def test_with_no_db(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent.sqlite"
        st = _FakeStreamlit()
        result = render_system_tab(fake_path, st)
        assert result["engine_running"] is False
        assert result["zerodha_connected"] is False
        assert any("Offline" in w for w in st.warnings)

    def test_engine_offline_db_exists(self, initialized_db: Path) -> None:
        st = _FakeStreamlit()
        result = render_system_tab(initialized_db, st)
        assert result["engine_running"] is False
        assert any("Offline" in w for w in st.warnings)


class TestZerodhaSnapshotDecimals:
    """Test Decimal precision for financial values."""

    def test_balance_precision(self, initialized_db: Path) -> None:
        write_zerodha_snapshot(
            user_id="P1",
            user_name="Precise",
            user_email="p@p.com",
            available_balance=Decimal("123456.789012"),
            equity_margin=Decimal("99999.999999"),
            commodity_margin=Decimal("0.01"),
            db_path=initialized_db,
        )
        snapshot = read_zerodha_snapshot(initialized_db)
        assert snapshot is not None
        assert snapshot.available_balance == Decimal("123456.789012")
        assert snapshot.equity_margin == Decimal("99999.999999")
        assert snapshot.commodity_margin == Decimal("0.01")

    def test_large_balance(self, initialized_db: Path) -> None:
        write_zerodha_snapshot(
            user_id="P2",
            user_name="Large",
            user_email="l@l.com",
            available_balance=Decimal("999999999.99"),
            equity_margin=Decimal("500000000.00"),
            commodity_margin=Decimal("0.00"),
            db_path=initialized_db,
        )
        snapshot = read_zerodha_snapshot(initialized_db)
        assert snapshot is not None
        assert snapshot.available_balance == Decimal("999999999.99")


class TestTimezoneHandling:
    """Test UTC timezone handling in status data."""

    def test_heartbeat_timestamp_is_utc(self, initialized_db: Path) -> None:
        write_engine_heartbeat(initialized_db)
        status = read_engine_status(initialized_db)
        assert status.last_heartbeat_utc is not None
        assert status.last_heartbeat_utc.tzinfo == UTC

    def test_zerodha_snapshot_timestamp_is_utc(self, initialized_db: Path) -> None:
        write_zerodha_snapshot(
            user_id="TZ1",
            user_name="TZ",
            user_email="tz@tz.com",
            available_balance=Decimal("100"),
            equity_margin=Decimal("100"),
            commodity_margin=Decimal("0"),
            db_path=initialized_db,
        )
        snapshot = read_zerodha_snapshot(initialized_db)
        assert snapshot is not None
        assert snapshot.snapshot_timestamp_utc is not None
        assert snapshot.snapshot_timestamp_utc.tzinfo == UTC

    def test_scanner_result_timestamp_is_utc(self, initialized_db: Path) -> None:
        now = datetime.now(UTC)
        write_scanner_results(
            [
                ScannerInstrumentRow(
                    symbol="X",
                    exchange=Exchange.NSE,
                    sentiment_score=Decimal("0.5"),
                    market_strength_score=Decimal("0.5"),
                    drl_score=Decimal("0.5"),
                    volume_profile_score=Decimal("0.5"),
                    composite_score=Decimal("0.5"),
                    is_approved=False,
                    scan_timestamp_utc=now,
                ),
            ],
            initialized_db,
        )
        results = read_scanner_results(initialized_db)
        assert len(results) == 1
        assert results[0].scan_timestamp_utc is not None
        assert results[0].scan_timestamp_utc.tzinfo == UTC


class TestErrorPaths:
    """Test error handling in status polling."""

    def test_read_engine_status_corrupt_db(self, tmp_path: Path) -> None:
        bad_db = tmp_path / "corrupt.sqlite"
        bad_db.write_text("not a sqlite file")
        status = read_engine_status(bad_db)
        assert status.is_running is False

    def test_read_zerodha_corrupt_db(self, tmp_path: Path) -> None:
        bad_db = tmp_path / "corrupt.sqlite"
        bad_db.write_text("not a sqlite file")
        result = read_zerodha_snapshot(bad_db)
        assert result is None

    def test_read_scanner_corrupt_db(self, tmp_path: Path) -> None:
        bad_db = tmp_path / "corrupt.sqlite"
        bad_db.write_text("not a sqlite file")
        results = read_scanner_results(bad_db)
        assert results == []
