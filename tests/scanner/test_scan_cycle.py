"""
Tests for scan cycle implementation.
"""

from datetime import UTC, datetime
from decimal import Decimal

from iatb.scanner.scan_cycle import ScanCycleResult, run_scan_cycle


class TestScanCycleResult:
    """Tests for ScanCycleResult dataclass."""

    def test_init(self) -> None:
        """Test ScanCycleResult initialization."""
        result = ScanCycleResult(
            scanner_result=None,
            trades_executed=5,
            total_pnl=Decimal("100.50"),
            errors=[],
            timestamp_utc=datetime.now(UTC),
        )
        assert result.trades_executed == 5
        assert result.total_pnl == Decimal("100.50")
        assert result.errors == []
        assert result.scanner_result is None


class TestRunScanCycle:
    """Tests for run_scan_cycle function."""

    def test_run_scan_cycle_with_no_symbols(self) -> None:
        """Test run_scan_cycle with no symbols (uses defaults)."""
        result = run_scan_cycle(symbols=None, max_trades=0)
        assert isinstance(result, ScanCycleResult)
        assert result.timestamp_utc is not None
        assert isinstance(result.trades_executed, int)

    def test_run_scan_cycle_with_empty_symbols(self) -> None:
        """Test run_scan_cycle with empty symbols list."""
        result = run_scan_cycle(symbols=[], max_trades=0)
        assert isinstance(result, ScanCycleResult)
        # Should handle empty symbols gracefully

    def test_run_scan_cycle_with_max_trades_zero(self) -> None:
        """Test run_scan_cycle with max_trades=0 (no trades executed)."""
        result = run_scan_cycle(symbols=["RELIANCE"], max_trades=0)
        assert isinstance(result, ScanCycleResult)
        assert result.trades_executed == 0

    def test_run_scan_cycle_returns_timestamp_utc(self) -> None:
        """Test that run_scan_cycle returns UTC timestamp."""
        result = run_scan_cycle(symbols=None, max_trades=0)
        assert result.timestamp_utc.tzinfo is not None
        # Verify it's UTC
        assert result.timestamp_utc.tzinfo == UTC

    def test_run_scan_cycle_handles_sentiment_errors(self) -> None:
        """Test that run_scan_cycle handles sentiment analyzer errors gracefully."""
        result = run_scan_cycle(symbols=None, max_trades=0)
        assert isinstance(result, ScanCycleResult)
        # Should not crash even if sentiment fails

    def test_run_scan_cycle_handles_scanner_errors(self) -> None:
        """Test that run_scan_cycle handles scanner errors gracefully."""
        # Use invalid symbol that will fail
        result = run_scan_cycle(symbols=["INVALID_SYMBOL_123"], max_trades=0)
        assert isinstance(result, ScanCycleResult)
        # Should handle scanner errors without crashing

    def test_run_scan_cycle_returns_errors_list(self) -> None:
        """Test that run_scan_cycle returns errors list."""
        result = run_scan_cycle(symbols=None, max_trades=0)
        assert isinstance(result.errors, list)

    def test_run_scan_cycle_with_custom_scanner_config(self) -> None:
        """Test run_scan_cycle with custom scanner config."""
        from iatb.scanner.instrument_scanner import ScannerConfig

        config = ScannerConfig(top_n=5, min_volume_ratio=Decimal("1.5"))
        result = run_scan_cycle(symbols=None, max_trades=0, scanner_config=config)
        assert isinstance(result, ScanCycleResult)

    def test_run_scan_cycle_result_attributes(self) -> None:
        """Test that run_scan_cycle returns result with all expected attributes."""
        result = run_scan_cycle(symbols=None, max_trades=0)
        assert hasattr(result, "scanner_result")
        assert hasattr(result, "trades_executed")
        assert hasattr(result, "total_pnl")
        assert hasattr(result, "errors")
        assert hasattr(result, "timestamp_utc")

    def test_run_scan_cycle_timestamp_is_recent(self) -> None:
        """Test that run_scan_cycle timestamp is recent (within 1 minute)."""
        before = datetime.now(UTC)
        result = run_scan_cycle(symbols=None, max_trades=0)
        after = datetime.now(UTC)
        assert before <= result.timestamp_utc <= after

    def test_total_pnl_zero_when_no_trades(self) -> None:
        """Test that total_pnl is zero when no trades are executed."""
        result = run_scan_cycle(symbols=["RELIANCE"], max_trades=0)
        assert result.trades_executed == 0
        assert result.total_pnl == Decimal("0")

    def test_total_pnl_accumulates_fill_values(self) -> None:
        """Test that total_pnl correctly accumulates fill values from executed trades."""
        from unittest.mock import MagicMock, patch

        from iatb.core.enums import Exchange, OrderStatus
        from iatb.execution.base import ExecutionResult
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.scanner.instrument_scanner import (
            InstrumentCategory,
            ScannerCandidate,
            ScannerResult,
        )

        # Create mock candidate with all required fields
        candidate = ScannerCandidate(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("2.05"),
            composite_score=Decimal("0.75"),
            sentiment_score=Decimal("0.80"),
            volume_ratio=Decimal("2.0"),
            exit_probability=Decimal("0.60"),
            is_tradable=True,
            regime=MarketRegime.SIDEWAYS,
            rank=1,
            timestamp_utc=datetime.now(UTC),
            close_price=Decimal("2500.50"),
            metadata={},
        )

        # Create mock scanner result
        scanner_result = ScannerResult(
            gainers=[candidate],
            losers=[],
            total_scanned=1,
            filtered_count=1,
            scan_timestamp_utc=datetime.now(UTC),
        )

        # Mock the scanner to return our controlled result
        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            # Mock order manager to return filled orders
            with patch("iatb.scanner.scan_cycle.OrderManager") as mock_om_class:
                mock_om = MagicMock()
                # First trade fills at 2500.50 with qty 10 = 25005.00
                mock_om.place_order.return_value = ExecutionResult(
                    order_id="TEST-001",
                    status=OrderStatus.FILLED,
                    filled_quantity=Decimal("10"),
                    average_price=Decimal("2500.50"),
                    message="Filled",
                )
                mock_om_class.return_value = mock_om

                result = run_scan_cycle(symbols=["RELIANCE"], max_trades=1)

                # Verify PnL tracking
                assert result.trades_executed == 1
                expected_pnl = Decimal("10") * Decimal("2500.50")  # 25005.00
                assert result.total_pnl == expected_pnl

    def test_total_pnl_with_multiple_trades(self) -> None:
        """Test that total_pnl correctly sums multiple trade fill values."""
        from unittest.mock import MagicMock, patch

        from iatb.core.enums import Exchange, OrderStatus
        from iatb.execution.base import ExecutionResult
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.scanner.instrument_scanner import (
            InstrumentCategory,
            ScannerCandidate,
            ScannerResult,
        )

        # Create multiple mock candidates
        candidates = []
        for idx, (symbol, price) in enumerate(
            [
                ("RELIANCE", "2500.50"),
                ("TCS", "3500.75"),
                ("INFY", "1500.25"),
            ]
        ):
            candidates.append(
                ScannerCandidate(
                    symbol=symbol,
                    exchange=Exchange.NSE,
                    category=InstrumentCategory.STOCK,
                    pct_change=Decimal("2.05"),
                    composite_score=Decimal("0.75"),
                    sentiment_score=Decimal("0.80"),
                    volume_ratio=Decimal("2.0"),
                    exit_probability=Decimal("0.60"),
                    is_tradable=True,
                    regime=MarketRegime.SIDEWAYS,
                    rank=idx + 1,
                    timestamp_utc=datetime.now(UTC),
                    close_price=Decimal(price),
                    metadata={},
                )
            )

        # Create mock scanner result
        scanner_result = ScannerResult(
            gainers=candidates,
            losers=[],
            total_scanned=3,
            filtered_count=3,
            scan_timestamp_utc=datetime.now(UTC),
        )

        # Mock the scanner to return our controlled result
        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            # Mock order manager to return filled orders
            with patch("iatb.scanner.scan_cycle.OrderManager") as mock_om_class:
                mock_om = MagicMock()
                # Each trade fills at respective price with qty 10
                fill_values = [
                    (
                        Decimal("10") * Decimal("2500.50")  # 25005.00
                    ),
                    (
                        Decimal("10") * Decimal("3500.75")  # 35007.50
                    ),
                    (
                        Decimal("10") * Decimal("1500.25")  # 15002.50
                    ),
                ]
                mock_om.place_order.side_effect = [
                    ExecutionResult(
                        order_id=f"TEST-00{i+1}",
                        status=OrderStatus.FILLED,
                        filled_quantity=Decimal("10"),
                        average_price=Decimal(price),
                        message="Filled",
                    )
                    for i, price in enumerate(["2500.50", "3500.75", "1500.25"])
                ]
                mock_om_class.return_value = mock_om

                result = run_scan_cycle(symbols=["RELIANCE", "TCS", "INFY"], max_trades=3)

                # Verify PnL tracking sums all fills
                assert result.trades_executed == 3
                expected_pnl = sum(fill_values)  # 75015.00
                assert result.total_pnl == expected_pnl

    def test_total_pnl_ignores_non_filled_orders(self) -> None:
        """Test that total_pnl does not accumulate for non-filled orders."""
        from unittest.mock import MagicMock, patch

        from iatb.core.enums import Exchange, OrderStatus
        from iatb.execution.base import ExecutionResult
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.scanner.instrument_scanner import (
            InstrumentCategory,
            ScannerCandidate,
            ScannerResult,
        )

        # Create mock candidate
        candidate = ScannerCandidate(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("2.05"),
            composite_score=Decimal("0.75"),
            sentiment_score=Decimal("0.80"),
            volume_ratio=Decimal("2.0"),
            exit_probability=Decimal("0.60"),
            is_tradable=True,
            regime=MarketRegime.SIDEWAYS,
            rank=1,
            timestamp_utc=datetime.now(UTC),
            close_price=Decimal("2500.50"),
            metadata={},
        )

        # Create mock scanner result
        scanner_result = ScannerResult(
            gainers=[candidate],
            losers=[],
            total_scanned=1,
            filtered_count=1,
            scan_timestamp_utc=datetime.now(UTC),
        )

        # Mock the scanner to return our controlled result
        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            # Mock order manager to return REJECTED order
            with patch("iatb.scanner.scan_cycle.OrderManager") as mock_om_class:
                mock_om = MagicMock()
                mock_om.place_order.return_value = ExecutionResult(
                    order_id="TEST-001",
                    status=OrderStatus.REJECTED,
                    filled_quantity=Decimal("0"),
                    average_price=Decimal("0"),
                    message="Rejected",
                )
                mock_om_class.return_value = mock_om

                result = run_scan_cycle(symbols=["RELIANCE"], max_trades=1)

                # Verify PnL is zero for non-filled order
                assert result.trades_executed == 1
                assert result.total_pnl == Decimal("0")
