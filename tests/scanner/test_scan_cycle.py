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
        """
        Test that total_pnl correctly sums multiple trade fill values.
        With max_trades=3 and 3 gainers, only 2 gainers are traded due to
        proportional allocation (gainers get ceil(3/2) = 2 trades).
        """
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
                    Decimal("10") * Decimal("2500.50"),  # 25005.00
                    Decimal("10") * Decimal("3500.75"),  # 35007.50
                ]
                mock_om.place_order.side_effect = [
                    ExecutionResult(
                        order_id=f"TEST-00{i+1}",
                        status=OrderStatus.FILLED,
                        filled_quantity=Decimal("10"),
                        average_price=Decimal(price),
                        message="Filled",
                    )
                    for i, price in enumerate(["2500.50", "3500.75"])
                ]
                mock_om_class.return_value = mock_om

                result = run_scan_cycle(symbols=["RELIANCE", "TCS", "INFY"], max_trades=3)

                # Verify PnL tracking sums all fills (only 2 trades due to allocation)
                assert result.trades_executed == 2
                expected_pnl = sum(fill_values)  # 60012.50
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
                # This would fail if code used getattr(
                # candidate.market_data, "close_price", Decimal("0")
                # )
                assert captured_request.price == candidate.close_price
                assert captured_request.price == Decimal("2500.50")
                assert captured_request.symbol == "RELIANCE"
                assert captured_request.quantity == Decimal("10")
                assert captured_request.side == OrderSide.BUY  # Positive sentiment

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
                average_price=request.price,
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
                average_price=request.price,
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
                average_price=request.price,
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

    def test_no_trades_when_gainers_have_non_positive_sentiment(self) -> None:
        """
        Test that no trades are executed when all gainers have non-positive sentiment.
        """
        from unittest.mock import MagicMock, patch

        from iatb.core.enums import Exchange, OrderStatus
        from iatb.execution.base import ExecutionResult
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.scanner.instrument_scanner import (
            InstrumentCategory,
            ScannerCandidate,
            ScannerResult,
        )

        # Create gainers with non-positive sentiment
        gainers = [
            ScannerCandidate(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                pct_change=Decimal("2.0"),
                composite_score=Decimal("0.75"),
                sentiment_score=Decimal("-0.50"),  # Negative
                volume_ratio=Decimal("2.0"),
                exit_probability=Decimal("0.60"),
                is_tradable=True,
                regime=MarketRegime.SIDEWAYS,
                rank=1,
                timestamp_utc=datetime.now(UTC),
                close_price=Decimal("2500.00"),
                metadata={},
            ),
            ScannerCandidate(
                symbol="TCS",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                pct_change=Decimal("1.5"),
                composite_score=Decimal("0.70"),
                sentiment_score=Decimal("0.00"),  # Zero
                volume_ratio=Decimal("2.0"),
                exit_probability=Decimal("0.60"),
                is_tradable=True,
                regime=MarketRegime.SIDEWAYS,
                rank=2,
                timestamp_utc=datetime.now(UTC),
                close_price=Decimal("3500.00"),
                metadata={},
            ),
        ]

        scanner_result = ScannerResult(
            gainers=gainers,
            losers=[],
            total_scanned=2,
            filtered_count=2,
            scan_timestamp_utc=datetime.now(UTC),
        )

        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            with patch("iatb.scanner.scan_cycle.OrderManager") as mock_om_class:
                mock_om = MagicMock()
                mock_om.place_order.return_value = ExecutionResult(
                    order_id="TEST-001",
                    status=OrderStatus.FILLED,
                    filled_quantity=Decimal("10"),
                    average_price=Decimal("2500.00"),
                    message="Filled",
                )
                mock_om_class.return_value = mock_om

                result = run_scan_cycle(symbols=["RELIANCE", "TCS"], max_trades=2)

                # No trades should be executed
                assert result.trades_executed == 0
                assert result.total_pnl == Decimal("0")

    def test_no_trades_when_losers_have_non_negative_sentiment(self) -> None:
        """
        Test that no trades are executed when all losers have non-negative sentiment.
        """
        from unittest.mock import MagicMock, patch

        from iatb.core.enums import Exchange, OrderStatus
        from iatb.execution.base import ExecutionResult
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.scanner.instrument_scanner import (
            InstrumentCategory,
            ScannerCandidate,
            ScannerResult,
        )

        # Create losers with non-negative sentiment
        losers = [
            ScannerCandidate(
                symbol="INFY",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                pct_change=Decimal("-2.0"),
                composite_score=Decimal("0.75"),
                sentiment_score=Decimal("0.50"),  # Positive
                volume_ratio=Decimal("2.0"),
                exit_probability=Decimal("0.60"),
                is_tradable=True,
                regime=MarketRegime.SIDEWAYS,
                rank=1,
                timestamp_utc=datetime.now(UTC),
                close_price=Decimal("1500.00"),
                metadata={},
            ),
            ScannerCandidate(
                symbol="HDFCBANK",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                pct_change=Decimal("-1.5"),
                composite_score=Decimal("0.70"),
                sentiment_score=Decimal("0.00"),  # Zero
                volume_ratio=Decimal("2.0"),
                exit_probability=Decimal("0.60"),
                is_tradable=True,
                regime=MarketRegime.SIDEWAYS,
                rank=2,
                timestamp_utc=datetime.now(UTC),
                close_price=Decimal("1600.00"),
                metadata={},
            ),
        ]

        scanner_result = ScannerResult(
            gainers=[],
            losers=losers,
            total_scanned=2,
            filtered_count=2,
            scan_timestamp_utc=datetime.now(UTC),
        )

        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_scanner_class:
            mock_scanner = MagicMock()
            mock_scanner.scan.return_value = scanner_result
            mock_scanner_class.return_value = mock_scanner

            with patch("iatb.scanner.scan_cycle.OrderManager") as mock_om_class:
                mock_om = MagicMock()
                mock_om.place_order.return_value = ExecutionResult(
                    order_id="TEST-001",
                    status=OrderStatus.FILLED,
                    filled_quantity=Decimal("10"),
                    average_price=Decimal("1500.00"),
                    message="Filled",
                )
                mock_om_class.return_value = mock_om

                result = run_scan_cycle(symbols=["INFY", "HDFCBANK"], max_trades=2)

                # No trades should be executed
                assert result.trades_executed == 0
                assert result.total_pnl == Decimal("0")
