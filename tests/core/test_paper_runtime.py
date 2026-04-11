"""
Tests for PaperTradingRuntime.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.paper_runtime import (
    PaperTradingRuntime,
    ScannerSettings,
    _register_signal_handlers,
)
from iatb.market_strength.regime_detector import MarketRegime
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    InstrumentScanner,
    MarketData,
    ScannerCandidate,
    ScannerResult,
)
from iatb.storage.sqlite_store import TradeAuditRecord


@pytest.fixture
def tmp_path(tmp_path: Path) -> Path:
    """Create a temporary path for test databases."""
    return tmp_path


@pytest.fixture
def mock_scanner_settings():
    """Create mock scanner settings."""
    return ScannerSettings(
        watchlist=["RELIANCE", "TCS"],
        scan_interval_seconds=60,
        max_candidates=3,
    )


@pytest.fixture
def mock_market_data():
    """Create mock market data."""
    return {
        "RELIANCE": MarketData(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("2500"),
            prev_close_price=Decimal("2400"),
            volume=Decimal("2000000"),
            avg_volume=Decimal("1000000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("2550"),
            low_price=Decimal("2450"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        ),
        "TCS": MarketData(
            symbol="TCS",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("3500"),
            prev_close_price=Decimal("3400"),
            volume=Decimal("1500000"),
            avg_volume=Decimal("750000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("3550"),
            low_price=Decimal("3450"),
            adx=Decimal("28"),
            atr_pct=Decimal("0.018"),
            breadth_ratio=Decimal("1.6"),
        ),
    }


@pytest.mark.asyncio
async def test_scanner_settings_load_success(tmp_path):
    """Test loading scanner settings from TOML file."""
    config_path = tmp_path / "settings.toml"
    config_path.write_text(
        """
[scanner]
watchlist = ["RELIANCE", "TCS", "INFY"]
scan_interval_seconds = 30
max_candidates = 10
"""
    )

    settings = ScannerSettings.load(config_path)
    assert settings.watchlist == ["RELIANCE", "TCS", "INFY"]
    assert settings.scan_interval_seconds == 30
    assert settings.max_candidates == 10


@pytest.mark.asyncio
async def test_scanner_settings_load_fallback():
    """Test fallback to defaults when config file not found."""
    settings = ScannerSettings.load(Path("nonexistent.toml"))
    assert settings.watchlist == ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    assert settings.scan_interval_seconds == 60
    assert settings.max_candidates == 5


@pytest.mark.asyncio
async def test_start_and_stop(tmp_path, mock_scanner_settings):
    """Test starting and stopping the runtime."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    await runtime.start()
    assert runtime._running is True
    await runtime.stop()
    assert runtime._running is False


@pytest.mark.asyncio
async def test_check_readiness_engine_not_running(tmp_path, mock_scanner_settings):
    """Test _check_readiness returns False when engine not running."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    # Don't start the engine
    assert runtime._check_readiness() is False


@pytest.mark.asyncio
async def test_check_readiness_success(tmp_path, mock_scanner_settings):
    """Test _check_readiness returns True when engine is running."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    await runtime.start()
    assert runtime._check_readiness() is True
    await runtime.stop()


@pytest.mark.asyncio
async def test_fetch_market_data(tmp_path, mock_scanner_settings):
    """Test _fetch_market_data fetches data from scanner."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )

    with patch.object(InstrumentScanner, "scan") as mock_scan:
        mock_scan.return_value = ScannerResult(
            gainers=[],
            losers=[],
            total_scanned=2,
            filtered_count=0,
            scan_timestamp_utc=datetime.now(UTC),
        )

        data = runtime._fetch_market_data()
        assert isinstance(data, dict)
        mock_scan.assert_called_once()


@pytest.mark.asyncio
async def test_run_sentiment(tmp_path, mock_scanner_settings, mock_market_data):
    """Test _run_sentiment returns sentiment scores."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    scores = runtime._run_sentiment(mock_market_data)
    assert isinstance(scores, dict)
    assert "RELIANCE" in scores
    assert "TCS" in scores
    # Default is neutral (0)
    assert scores["RELIANCE"] == Decimal("0")


@pytest.mark.asyncio
async def test_calculate_strength(tmp_path, mock_scanner_settings, mock_market_data):
    """Test _calculate_strength computes strength scores."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    scores = runtime._calculate_strength(mock_market_data)
    assert isinstance(scores, dict)
    assert "RELIANCE" in scores
    assert "TCS" in scores
    # Strength scores should be between 0 and 1
    for score in scores.values():
        assert Decimal("0") <= score <= Decimal("1")


@pytest.mark.asyncio
async def test_run_scanner(tmp_path, mock_scanner_settings, mock_market_data):
    """Test _run_scanner filters and ranks candidates."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )

    # Set up sentiment scores that pass the VERY_STRONG threshold
    sentiment_scores = {"RELIANCE": Decimal("0.8"), "TCS": Decimal("0.85")}
    strength_scores = {"RELIANCE": Decimal("0.7"), "TCS": Decimal("0.75")}

    result = runtime._run_scanner(mock_market_data, sentiment_scores, strength_scores)

    assert isinstance(result, ScannerResult)
    assert result.total_scanned == 2
    # Both should pass filters: |sentiment| >= 0.75, is_tradable, volume_ratio >= 2.0
    assert len(result.gainers) == 2


@pytest.mark.asyncio
async def test_run_scanner_filters_out_weak_sentiment(
    tmp_path, mock_scanner_settings, mock_market_data
):
    """Test _run_scanner filters out candidates with weak sentiment."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )

    # Set up weak sentiment scores (below 0.75 threshold)
    sentiment_scores = {"RELIANCE": Decimal("0.5"), "TCS": Decimal("0.6")}
    strength_scores = {"RELIANCE": Decimal("0.7"), "TCS": Decimal("0.75")}

    result = runtime._run_scanner(mock_market_data, sentiment_scores, strength_scores)

    # None should pass the VERY_STRONG filter
    assert len(result.gainers) == 0
    assert len(result.losers) == 0


@pytest.mark.asyncio
async def test_execute_paper_orders(tmp_path, mock_scanner_settings):
    """Test _execute_paper_orders creates and executes orders."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    timestamp = datetime.now(UTC)

    # Create mock scanner result
    scanner_result = ScannerResult(
        gainers=[
            ScannerCandidate(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                pct_change=Decimal("2.5"),
                composite_score=Decimal("0.8"),
                sentiment_score=Decimal("0.8"),
                volume_ratio=Decimal("2.5"),
                exit_probability=Decimal("0.6"),
                is_tradable=True,
                regime=MarketRegime.SIDEWAYS,
                rank=1,
                timestamp_utc=timestamp,
                metadata={},
            )
        ],
        losers=[],
        total_scanned=1,
        filtered_count=0,
        scan_timestamp_utc=timestamp,
    )

    executed_orders = runtime._execute_paper_orders(scanner_result, timestamp)

    assert len(executed_orders) == 1
    assert executed_orders[0].symbol == "RELIANCE"
    assert executed_orders[0].side == OrderSide.BUY


@pytest.mark.asyncio
async def test_execute_paper_orders_idempotency(tmp_path, mock_scanner_settings):
    """Test _execute_paper_orders prevents duplicate orders."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    timestamp = datetime.now(UTC)

    scanner_result = ScannerResult(
        gainers=[
            ScannerCandidate(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                pct_change=Decimal("2.5"),
                composite_score=Decimal("0.8"),
                sentiment_score=Decimal("0.8"),
                volume_ratio=Decimal("2.5"),
                exit_probability=Decimal("0.6"),
                is_tradable=True,
                regime=MarketRegime.SIDEWAYS,
                rank=1,
                timestamp_utc=timestamp,
                metadata={},
            )
        ],
        losers=[],
        total_scanned=1,
        filtered_count=0,
        scan_timestamp_utc=timestamp,
    )

    # Execute first time
    orders1 = runtime._execute_paper_orders(scanner_result, timestamp)
    assert len(orders1) == 1

    # Execute second time with same timestamp (should be skipped)
    orders2 = runtime._execute_paper_orders(scanner_result, timestamp)
    assert len(orders2) == 0


@pytest.mark.asyncio
async def test_persist_audit(tmp_path, mock_scanner_settings):
    """Test _persist_audit saves trades to database."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )

    audit_record = TradeAuditRecord(
        trade_id="TEST-001",
        timestamp=datetime.now(UTC),
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        price=Decimal("2500"),
        status=OrderStatus.FILLED,
        strategy_id="test-strategy",
        metadata={},
    )

    # Should not raise
    runtime._persist_audit([audit_record])

    # Verify it was saved
    retrieved = runtime._audit_logger.get_trade("TEST-001")
    assert retrieved is not None
    assert retrieved.trade_id == "TEST-001"
    assert retrieved.symbol == "RELIANCE"


@pytest.mark.asyncio
async def test_publish_results(tmp_path, mock_scanner_settings):
    """Test _publish_results publishes to event bus."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    await runtime.start()

    timestamp = datetime.now(UTC)
    scanner_result = ScannerResult(
        gainers=[],
        losers=[],
        total_scanned=0,
        filtered_count=0,
        scan_timestamp_utc=timestamp,
    )

    # Should not raise
    runtime._publish_results(scanner_result, [], timestamp)

    await runtime.stop()


@pytest.mark.asyncio
async def test_run_scan_cycle_integration(tmp_path, mock_scanner_settings, mock_market_data):
    """Test full scan cycle integration with mocked components."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    await runtime.start()

    with patch.object(runtime, "_fetch_market_data", return_value=mock_market_data):
        with patch.object(runtime, "_run_sentiment", return_value={"RELIANCE": Decimal("0.8")}):
            with patch.object(
                runtime, "_calculate_strength", return_value={"RELIANCE": Decimal("0.7")}
            ):
                with patch.object(runtime, "_persist_audit"):
                    with patch.object(runtime, "_publish_results"):
                        # Should not raise
                        await runtime.run_scan_cycle()

    await runtime.stop()


@pytest.mark.asyncio
async def test_run_scan_cycle_not_ready(tmp_path, mock_scanner_settings):
    """Test scan cycle skips when system not ready."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    # Don't start the runtime
    await runtime.run_scan_cycle()  # Should not raise, just log warning


@pytest.mark.asyncio
async def test_run_scan_cycle_no_market_data(tmp_path, mock_scanner_settings):
    """Test scan cycle skips when no market data available."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    await runtime.start()

    with patch.object(runtime, "_fetch_market_data", return_value={}):
        await runtime.run_scan_cycle()  # Should not raise, just log info

    await runtime.stop()


@pytest.mark.asyncio
async def test_run_scan_cycle_exception_handling(tmp_path, mock_scanner_settings):
    """Test scan cycle handles exceptions gracefully."""
    runtime = PaperTradingRuntime(
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    await runtime.start()

    with patch.object(runtime, "_fetch_market_data", side_effect=Exception("Test error")):
        await runtime.run_scan_cycle()  # Should not raise, just log error

    await runtime.stop()


@pytest.mark.asyncio
async def test_run_continuous_stops_on_flag(tmp_path, mock_scanner_settings):
    """Test continuous loop stops on stop event."""
    runtime = PaperTradingRuntime(
        scan_interval_seconds=0.01,
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    await runtime.start()
    task = asyncio.create_task(runtime.run_continuous())
    await asyncio.sleep(0.05)
    runtime._stop_event.set()
    await task


@pytest.mark.asyncio
async def test_run_full_lifecycle(tmp_path, mock_scanner_settings):
    """Test full runtime lifecycle."""
    runtime = PaperTradingRuntime(
        scan_interval_seconds=0.01,
        audit_db_path=tmp_path / "audit.sqlite",
        scanner_settings=mock_scanner_settings,
    )
    task = asyncio.create_task(runtime.run())
    await asyncio.sleep(0.05)
    runtime._stop_event.set()
    await task


@pytest.mark.asyncio
async def test_register_signal_handlers_windows_fallback():
    """Test signal handler registration falls back gracefully on Windows."""
    stop_event = asyncio.Event()
    _register_signal_handlers(stop_event)
    assert not stop_event.is_set()


@pytest.mark.asyncio
async def test_main_entrypoint(monkeypatch):
    """Test main entry point."""
    from iatb.core import paper_runtime

    called: list[str] = []

    def _fake_run(coro: object) -> None:
        called.append("asyncio.run")
        if hasattr(coro, "close"):
            coro.close()  # type: ignore[union-attr]

    monkeypatch.setattr(asyncio, "run", _fake_run)
    import logging as stdlib_logging

    monkeypatch.setattr(stdlib_logging, "basicConfig", lambda **kw: None)
    paper_runtime.main()
    assert "asyncio.run" in called
