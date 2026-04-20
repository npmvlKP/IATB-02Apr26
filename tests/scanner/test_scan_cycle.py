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

    def test_run_scan_cycle_with_max_trades_zero(self) -> None:
        """Test run_scan_cycle with max_trades=0 (no trades executed)."""
        result = run_scan_cycle(symbols=["RELIANCE"], max_trades=0)
        assert isinstance(result, ScanCycleResult)
        assert result.trades_executed == 0

    def test_run_scan_cycle_returns_timestamp_utc(self) -> None:
        """Test that run_scan_cycle returns UTC timestamp."""
        result = run_scan_cycle(symbols=None, max_trades=0)
        assert result.timestamp_utc.tzinfo is not None
        assert result.timestamp_utc.tzinfo == UTC

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

    def test_total_pnl_zero_when_no_trades(self) -> None:
        """Test that total_pnl is zero when no trades are executed."""
        result = run_scan_cycle(symbols=["RELIANCE"], max_trades=0)
        assert result.trades_executed == 0
        assert result.total_pnl == Decimal("0")

    def test_gainers_only_bought_with_positive_sentiment(self) -> None:
        """
        Regression test: Ensure gainers are only BUYed when sentiment is positive.
        Previously, the code would flip to SELL for gainers with negative sentiment,
        which incorrectly shorts top gainers instead of processing losers separately.
        """
        from unittest.mock import MagicMock, patch

        from iatb.core.enums import Exchange, OrderSide, OrderStatus
        from iatb.execution.base import ExecutionResult, OrderRequest
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.scanner.instrument_scanner import (
            InstrumentCategory,
            ScannerCandidate,
            ScannerResult,
        )

        # Create a gainer with NEGATIVE sentiment - should be SKIPPED, not shorted
        negative_sentiment_gainer = ScannerCandidate(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("2.05"),
            composite_score=Decimal("0.75"),
            sentiment_score=Decimal("-0.80"),  # Negative sentiment
            volume_ratio=Decimal("2.0"),
            exit_probability=Decimal("0.60"),
            is_tradable=True,
            regime=MarketRegime.SIDEWAYS,
            rank=1,
            timestamp_utc=datetime.now(UTC),
            close_price=Decimal("2500.50"),
            metadata={},
        )

        # Create a gainer with POSITIVE sentiment - should be BUYed
        positive_sentiment_gainer = ScannerCandidate(
            symbol="TCS",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("1.50"),
            composite_score=Decimal("0.70"),
            sentiment_score=Decimal("0.75"),  # Positive sentiment
            volume_ratio=Decimal("2.5"),
            exit_probability=Decimal("0.65"),
            is_tradable=True,
            regime=MarketRegime.SIDEWAYS,
            rank=2,
            timestamp_utc=datetime.now(UTC),
            close_price=Decimal("3500.00"),
            metadata={},
        )

        scanner_result = ScannerResult(
            gainers=[negative_sentiment_gainer, positive_sentiment_gainer],
            losers=[],
            total_scanned=2,
            filtered_count=2,
            scan_timestamp_utc=datetime.now(UTC),
        )

        captured_orders: list[OrderRequest] = []

        def capture_order(request: OrderRequest, strategy_id: str) -> ExecutionResult:
            captured_orders.append(request)
            return ExecutionResult(
                order_id=f"TEST-{len(captured_orders)}",
                status=OrderStatus.FILLED,
                filled_quantity=Decimal("10"),
                average_price=request.price or Decimal("0"),
                message="Filled",
            )

        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            with patch("iatb.scanner.scan_cycle.OrderManager") as mock_om_class:
                mock_om = MagicMock()
                mock_om.place_order = capture_order
                mock_om_class.return_value = mock_om

                result = run_scan_cycle(symbols=["RELIANCE", "TCS"], max_trades=3)

                # Only TCS should be traded (positive sentiment gainer)
                assert result.trades_executed == 1
                assert len(captured_orders) == 1
                assert captured_orders[0].symbol == "TCS"
                assert captured_orders[0].side == OrderSide.BUY

    def test_losers_only_sold_with_negative_sentiment(self) -> None:
        """
        Regression test: Ensure losers are only SELLed when sentiment is negative.
        Losers with positive sentiment should be skipped.
        """
        from unittest.mock import MagicMock, patch

        from iatb.core.enums import Exchange, OrderSide, OrderStatus
        from iatb.execution.base import ExecutionResult, OrderRequest
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.scanner.instrument_scanner import (
            InstrumentCategory,
            ScannerCandidate,
            ScannerResult,
        )

        # Create a loser with NEGATIVE sentiment - should be SELLed
        negative_sentiment_loser = ScannerCandidate(
            symbol="INFY",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("-1.50"),
            composite_score=Decimal("0.75"),
            sentiment_score=Decimal("-0.85"),  # Negative sentiment
            volume_ratio=Decimal("2.0"),
            exit_probability=Decimal("0.60"),
            is_tradable=True,
            regime=MarketRegime.SIDEWAYS,
            rank=1,
            timestamp_utc=datetime.now(UTC),
            close_price=Decimal("1500.00"),
            metadata={},
        )

        # Create a loser with POSITIVE sentiment - should be SKIPPED
        positive_sentiment_loser = ScannerCandidate(
            symbol="HDFCBANK",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("-0.80"),
            composite_score=Decimal("0.70"),
            sentiment_score=Decimal("0.70"),  # Positive sentiment
            volume_ratio=Decimal("2.5"),
            exit_probability=Decimal("0.65"),
            is_tradable=True,
            regime=MarketRegime.SIDEWAYS,
            rank=2,
            timestamp_utc=datetime.now(UTC),
            close_price=Decimal("1600.00"),
            metadata={},
        )

        scanner_result = ScannerResult(
            gainers=[],
            losers=[negative_sentiment_loser, positive_sentiment_loser],
            total_scanned=2,
            filtered_count=2,
            scan_timestamp_utc=datetime.now(UTC),
        )

        captured_orders: list[OrderRequest] = []

        def capture_order(request: OrderRequest, strategy_id: str) -> ExecutionResult:
            captured_orders.append(request)
            return ExecutionResult(
                order_id=f"TEST-{len(captured_orders)}",
                status=OrderStatus.FILLED,
                filled_quantity=Decimal("10"),
                average_price=request.price or Decimal("0"),
                message="Filled",
            )

        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            with patch("iatb.scanner.scan_cycle.OrderManager") as mock_om_class:
                mock_om = MagicMock()
                mock_om.place_order = capture_order
                mock_om_class.return_value = mock_om

                result = run_scan_cycle(symbols=["INFY", "HDFCBANK"], max_trades=3)

                # Only INFY should be traded (negative sentiment loser)
                assert result.trades_executed == 1
                assert len(captured_orders) == 1
                assert captured_orders[0].symbol == "INFY"
                assert captured_orders[0].side == OrderSide.SELL

    def test_trades_allocated_proportionally_between_gainers_and_losers(self) -> None:
        """
        Test that max_trades is allocated proportionally between gainers and losers.
        For max_trades=5, gainers get 3 trades and losers get 2 trades.
        """
        from unittest.mock import MagicMock, patch

        from iatb.core.enums import Exchange, OrderSide, OrderStatus
        from iatb.execution.base import ExecutionResult, OrderRequest
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.scanner.instrument_scanner import (
            InstrumentCategory,
            ScannerCandidate,
            ScannerResult,
        )

        # Create 5 gainers with positive sentiment
        gainers = [
            ScannerCandidate(
                symbol=f"GAINER{i}",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                pct_change=Decimal("2.0"),
                composite_score=Decimal("0.75"),
                sentiment_score=Decimal("0.80"),
                volume_ratio=Decimal("2.0"),
                exit_probability=Decimal("0.60"),
                is_tradable=True,
                regime=MarketRegime.SIDEWAYS,
                rank=i,
                timestamp_utc=datetime.now(UTC),
                close_price=Decimal(str(2000 + i * 100)),
                metadata={},
            )
            for i in range(1, 6)
        ]

        # Create 5 losers with negative sentiment
        losers = [
            ScannerCandidate(
                symbol=f"LOSER{i}",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                pct_change=Decimal("-2.0"),
                composite_score=Decimal("0.75"),
                sentiment_score=Decimal("-0.80"),
                volume_ratio=Decimal("2.0"),
                exit_probability=Decimal("0.60"),
                is_tradable=True,
                regime=MarketRegime.SIDEWAYS,
                rank=i,
                timestamp_utc=datetime.now(UTC),
                close_price=Decimal(str(1000 + i * 100)),
                metadata={},
            )
            for i in range(1, 6)
        ]

        scanner_result = ScannerResult(
            gainers=gainers,
            losers=losers,
            total_scanned=10,
            filtered_count=10,
            scan_timestamp_utc=datetime.now(UTC),
        )

        captured_orders: list[OrderRequest] = []

        def capture_order(request: OrderRequest, strategy_id: str) -> ExecutionResult:
            captured_orders.append(request)
            return ExecutionResult(
                order_id=f"TEST-{len(captured_orders)}",
                status=OrderStatus.FILLED,
                filled_quantity=Decimal("10"),
                average_price=request.price or Decimal("0"),
                message="Filled",
            )

        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            with patch("iatb.scanner.scan_cycle.OrderManager") as mock_om_class:
                mock_om = MagicMock()
                mock_om.place_order = capture_order
                mock_om_class.return_value = mock_om

                result = run_scan_cycle(symbols=[], max_trades=5)

                # For max_trades=5: gainers get 3, losers get 2
                assert result.trades_executed == 5
                assert len(captured_orders) == 5

                # Count BUY and SELL orders
                buy_orders = [o for o in captured_orders if o.side == OrderSide.BUY]
                sell_orders = [o for o in captured_orders if o.side == OrderSide.SELL]

                assert len(buy_orders) == 3  # (5 + 1) // 2 = 3
                assert len(sell_orders) == 2  # 5 // 2 = 2

                # Verify all BUY orders are for gainers
                for order in buy_orders:
                    assert order.symbol.startswith("GAINER")

                # Verify all SELL orders are for losers
                for order in sell_orders:
                    assert order.symbol.startswith("LOSER")

    def test_candidate_uses_close_price_attribute_not_market_data(self) -> None:
        """
        Regression test: Ensure ScannerCandidate.close_price is used directly,
        not via candidate.market_data.close_price (which doesn't exist).

        This test verifies that paper trades execute at the correct price
        from ScannerCandidate.close_price attribute.
        """
        from unittest.mock import MagicMock, patch

        from iatb.core.enums import Exchange, OrderSide, OrderStatus
        from iatb.execution.base import ExecutionResult, OrderRequest
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.scanner.instrument_scanner import (
            InstrumentCategory,
            ScannerCandidate,
            ScannerResult,
        )

        # Create candidate with explicit close_price
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

        # Create scanner result
        scanner_result = ScannerResult(
            gainers=[candidate],
            losers=[],
            total_scanned=1,
            filtered_count=1,
            scan_timestamp_utc=datetime.now(UTC),
        )

        # Mock scanner
        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            # Mock order manager to capture the OrderRequest
            with patch("iatb.scanner.scan_cycle.OrderManager") as mock_om_class:
                mock_om = MagicMock()

                # Capture the order request
                captured_request: OrderRequest | None = None

                def capture_order(request: OrderRequest, strategy_id: str) -> ExecutionResult:
                    nonlocal captured_request
                    captured_request = request
                    return ExecutionResult(
                        order_id="TEST-001",
                        status=OrderStatus.FILLED,
                        filled_quantity=Decimal("10"),
                        average_price=Decimal("2500.50"),
                        message="Filled",
                    )

                mock_om.place_order = capture_order
                mock_om_class.return_value = mock_om

                # Run scan cycle
                result = run_scan_cycle(symbols=["RELIANCE"], max_trades=1)

                # Verify order was placed
                assert result.trades_executed == 1
                assert captured_request is not None

                # Critical: Verify price comes from candidate.close_price
                assert captured_request.price == candidate.close_price
                assert captured_request.price == Decimal("2500.50")
                assert captured_request.symbol == "RELIANCE"
                assert captured_request.quantity == Decimal("10")
                assert captured_request.side == OrderSide.BUY  # Positive sentiment

    def test_scanner_failure_returns_early_with_error(self) -> None:
        """
        Test that scanner failure returns early with error.
        This covers lines 262-266 in scan_cycle.py.
        """
        from unittest.mock import patch

        # Mock scanner to raise exception
        with patch(
            "iatb.scanner.instrument_scanner.InstrumentScanner",
            side_effect=Exception("Scanner failed"),
        ):
            result = run_scan_cycle(symbols=["RELIANCE"], max_trades=0)

            # Verify early return with error
            assert result.scanner_result is None
            assert result.trades_executed == 0
            assert result.total_pnl == Decimal("0")
            assert len(result.errors) > 0
            assert any("Scanner" in error for error in result.errors)

    def test_paper_executor_init_failure_returns_early_with_error(self) -> None:
        """
        Test that PaperExecutor initialization failure returns early with error.
        This covers lines 220-230 in scan_cycle.py.
        """
        from unittest.mock import MagicMock, patch

        # Mock scanner to succeed
        from iatb.scanner.instrument_scanner import ScannerResult

        scanner_result = ScannerResult(
            gainers=[],
            losers=[],
            total_scanned=0,
            filtered_count=0,
            scan_timestamp_utc=datetime.now(UTC),
        )

        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            # Mock PaperExecutor to fail during OrderManager init
            with patch(
                "iatb.scanner.scan_cycle.PaperExecutor",
                side_effect=Exception("Executor init failed"),
            ):
                result = run_scan_cycle(symbols=["RELIANCE"], max_trades=0)

                # Verify early return with error
                assert result.scanner_result is None
                assert result.trades_executed == 0
                assert result.total_pnl == Decimal("0")
                assert len(result.errors) > 0
                assert any("order manager" in error.lower() for error in result.errors)

    def test_trade_exception_continues_with_next_candidate(self) -> None:
        """
        Test that trade execution exception continues to next candidate.
        This covers lines 333-337 in scan_cycle.py.
        """
        from unittest.mock import MagicMock, patch

        from iatb.core.enums import Exchange, OrderStatus
        from iatb.execution.base import ExecutionResult, OrderRequest
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.scanner.instrument_scanner import (
            InstrumentCategory,
            ScannerCandidate,
            ScannerResult,
        )

        # Create 3 gainers with positive sentiment
        gainers = [
            ScannerCandidate(
                symbol=f"GAINER{i}",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                pct_change=Decimal("2.0"),
                composite_score=Decimal("0.75"),
                sentiment_score=Decimal("0.80"),
                volume_ratio=Decimal("2.0"),
                exit_probability=Decimal("0.60"),
                is_tradable=True,
                regime=MarketRegime.SIDEWAYS,
                rank=i,
                timestamp_utc=datetime.now(UTC),
                close_price=Decimal(str(2000 + i * 100)),
                metadata={},
            )
            for i in range(1, 4)
        ]

        scanner_result = ScannerResult(
            gainers=gainers,
            losers=[],
            total_scanned=3,
            filtered_count=3,
            scan_timestamp_utc=datetime.now(UTC),
        )

        trade_count = [0]

        def failing_order(request: OrderRequest, strategy_id: str) -> ExecutionResult:
            trade_count[0] += 1
            # Fail on second trade
            if trade_count[0] == 2:
                raise Exception("Trade execution failed")
            return ExecutionResult(
                order_id=f"TEST-{trade_count[0]}",
                status=OrderStatus.FILLED,
                filled_quantity=Decimal("10"),
                average_price=request.price or Decimal("0"),
                message="Filled",
            )

        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            with patch("iatb.scanner.scan_cycle.OrderManager") as mock_om_class:
                mock_om = MagicMock()
                mock_om.place_order = failing_order
                mock_om_class.return_value = mock_om

                result = run_scan_cycle(symbols=[], max_trades=5)

                # Should continue after exception and execute 2 trades (skip the failing one)
                assert result.trades_executed == 2
                # Check for at least one trade error (may also have KiteProvider init error)
                assert any("Trade failed" in error for error in result.errors)

    def test_trade_exception_in_losers_continues_with_next_candidate(self) -> None:
        """
        Test that trade execution exception in losers continues to next candidate.
        This covers lines 388-392 in scan_cycle.py.
        """
        from unittest.mock import MagicMock, patch

        from iatb.core.enums import Exchange, OrderStatus
        from iatb.execution.base import ExecutionResult, OrderRequest
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.scanner.instrument_scanner import (
            InstrumentCategory,
            ScannerCandidate,
            ScannerResult,
        )

        # Create 2 losers with negative sentiment
        losers = [
            ScannerCandidate(
                symbol=f"LOSER{i}",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                pct_change=Decimal("-2.0"),
                composite_score=Decimal("0.75"),
                sentiment_score=Decimal("-0.80"),
                volume_ratio=Decimal("2.0"),
                exit_probability=Decimal("0.60"),
                is_tradable=True,
                regime=MarketRegime.SIDEWAYS,
                rank=i,
                timestamp_utc=datetime.now(UTC),
                close_price=Decimal(str(1000 + i * 100)),
                metadata={},
            )
            for i in range(1, 3)
        ]

        scanner_result = ScannerResult(
            gainers=[],
            losers=losers,
            total_scanned=2,
            filtered_count=2,
            scan_timestamp_utc=datetime.now(UTC),
        )

        trade_count = [0]

        def failing_order(request: OrderRequest, strategy_id: str) -> ExecutionResult:
            trade_count[0] += 1
            # Fail on first trade
            if trade_count[0] == 1:
                raise Exception("Sell trade execution failed")
            return ExecutionResult(
                order_id=f"TEST-{trade_count[0]}",
                status=OrderStatus.FILLED,
                filled_quantity=Decimal("10"),
                average_price=request.price or Decimal("0"),
                message="Filled",
            )

        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            with patch("iatb.scanner.scan_cycle.OrderManager") as mock_om_class:
                mock_om = MagicMock()
                mock_om.place_order = failing_order
                mock_om_class.return_value = mock_om

                result = run_scan_cycle(symbols=[], max_trades=5)

                # Should continue after exception and execute 1 trade (skip the failing one)
                assert result.trades_executed == 1
                # Check for at least one trade error (may also have KiteProvider init error)
                assert any("Sell trade" in error for error in result.errors)
