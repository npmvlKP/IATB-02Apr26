"""Coverage tests for scanner.scan_cycle."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from iatb.scanner.scan_cycle import ScanCycleResult, run_scan_cycle


class TestScanCycleResult:
    def test_init_defaults(self) -> None:
        ts = datetime.now(UTC)
        obj = ScanCycleResult(
            scanner_result=None,
            trades_executed=0,
            total_pnl=Decimal("0"),
            errors=[],
            timestamp_utc=ts,
        )
        assert obj.scanner_result is None
        assert obj.trades_executed == 0
        assert obj.total_pnl == Decimal("0")
        assert obj.errors == []
        assert obj.pipeline_id is None

    def test_init_with_values(self) -> None:
        ts = datetime.now(UTC)
        obj = ScanCycleResult(
            scanner_result=None,
            trades_executed=3,
            total_pnl=Decimal("100.50"),
            errors=["err1"],
            timestamp_utc=ts,
            pipeline_id="pipe-1",
        )
        assert obj.trades_executed == 3
        assert obj.total_pnl == Decimal("100.50")
        assert obj.errors == ["err1"]
        assert obj.pipeline_id == "pipe-1"

    def test_init_negative_pnl(self) -> None:
        ts = datetime.now(UTC)
        obj = ScanCycleResult(
            scanner_result=None,
            trades_executed=0,
            total_pnl=Decimal("-50.25"),
            errors=[],
            timestamp_utc=ts,
        )
        assert obj.total_pnl == Decimal("-50.25")


class TestRefreshSymbols:
    @patch(
        "iatb.scanner.scan_cycle._load_symbols_from_config",
        return_value=["RELIANCE", "TCS"],
    )
    def test_refresh_symbols_with_symbols(self, mock_load: MagicMock) -> None:
        from iatb.scanner.scan_cycle import refresh_symbols

        result = refresh_symbols()
        assert result == ["RELIANCE", "TCS"]

    @patch("iatb.scanner.scan_cycle._load_symbols_from_config", return_value=None)
    def test_refresh_symbols_no_symbols(self, mock_load: MagicMock) -> None:
        from iatb.scanner.scan_cycle import refresh_symbols

        result = refresh_symbols()
        assert result is None


class TestRunScanCycle:
    @patch("iatb.scanner.scan_cycle._run_scan_cycle_with_params")
    def test_run_scan_cycle_basic(self, mock_run: MagicMock) -> None:
        ts = datetime.now(UTC)
        mock_run.return_value = ScanCycleResult(
            scanner_result=None,
            trades_executed=0,
            total_pnl=Decimal("0"),
            errors=[],
            timestamp_utc=ts,
        )
        result = run_scan_cycle()
        assert isinstance(result, ScanCycleResult)

    @patch("iatb.scanner.scan_cycle._run_scan_cycle_with_params")
    def test_run_scan_cycle_with_errors(self, mock_run: MagicMock) -> None:
        ts = datetime.now(UTC)
        mock_run.return_value = ScanCycleResult(
            scanner_result=None,
            trades_executed=0,
            total_pnl=Decimal("0"),
            errors=["timeout"],
            timestamp_utc=ts,
        )
        result = run_scan_cycle()
        assert result.errors == ["timeout"]

    @patch("iatb.scanner.scan_cycle._run_scan_cycle_with_params")
    def test_run_scan_cycle_empty_symbols(self, mock_run: MagicMock) -> None:
        ts = datetime.now(UTC)
        mock_run.return_value = ScanCycleResult(
            scanner_result=None,
            trades_executed=0,
            total_pnl=Decimal("0"),
            errors=[],
            timestamp_utc=ts,
        )
        result = run_scan_cycle(symbols=[])
        assert isinstance(result, ScanCycleResult)


class TestPipelineHealthMonitor:
    def test_get_pipeline_health_monitor(self) -> None:
        from iatb.scanner.scan_cycle import get_pipeline_health_monitor

        monitor = get_pipeline_health_monitor()
        assert monitor is not None

    def test_generate_pipeline_id(self) -> None:
        from iatb.scanner.scan_cycle import _generate_pipeline_id

        pid = _generate_pipeline_id()
        assert pid.startswith("scan-")
