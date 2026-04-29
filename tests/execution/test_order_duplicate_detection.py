"""
Tests for order duplicate detection and idempotent order placement.
"""

from decimal import Decimal
from pathlib import Path

from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.order_manager import OrderManager


class _StubExecutor(Executor):
    def __init__(self) -> None:
        self.cancel_count = 0
        self.order_count = 0

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        self.order_count += 1
        return ExecutionResult(
            f"OID-{self.order_count}",
            OrderStatus.OPEN,
            Decimal("0"),
            Decimal("0"),
        )

    def cancel_all(self) -> int:
        self.cancel_count += 1
        return 1


class TestOrderDuplicateDetection:
    """Test order duplicate detection."""

    def test_duplicate_order_detection_enabled(self) -> None:
        """Test duplicate order detection when enabled."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("1000"),
        )

        result1 = manager.place_order(request)
        result2 = manager.place_order(request)

        assert result1.order_id == result2.order_id
        assert executor.order_count == 1

    def test_duplicate_order_detection_disabled(self) -> None:
        """Test duplicate order detection when disabled."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=False,
        )

        request = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("1000"),
        )

        result1 = manager.place_order(request)
        result2 = manager.place_order(request)

        assert result1.order_id != result2.order_id
        assert executor.order_count == 2

    def test_different_orders_not_detected_as_duplicates(self) -> None:
        """Test different orders are not detected as duplicates."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request1 = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("1000"),
        )

        request2 = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.SELL,
            Decimal("10"),
            Decimal("1000"),
        )

        result1 = manager.place_order(request1)
        result2 = manager.place_order(request2)

        assert result1.order_id != result2.order_id
        assert executor.order_count == 2

    def test_order_fingerprint_generation(self) -> None:
        """Test order fingerprint generation."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("1000"),
        )

        fingerprint = manager._generate_order_fingerprint(request)

        assert "NSE" in fingerprint
        assert "RELIANCE" in fingerprint
        assert "BUY" in fingerprint
        assert "10" in fingerprint
        assert "MARKET" in fingerprint

    def test_order_fingerprint_for_market_order(self) -> None:
        """Test order fingerprint for market orders."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
        )

        fingerprint = manager._generate_order_fingerprint(request)

        assert "MARKET" in fingerprint

    def test_duplicate_order_returns_existing_status(self) -> None:
        """Test duplicate order returns existing order status."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("1000"),
        )

        result1 = manager.place_order(request)
        manager._order_status[result1.order_id] = OrderStatus.OPEN

        result2 = manager.place_order(request)

        assert result2.order_id == result1.order_id
        assert result2.status == OrderStatus.OPEN

    def test_order_fingerprint_recording(self) -> None:
        """Test order fingerprint is recorded after placement."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("1000"),
        )

        result = manager.place_order(request)

        fingerprint = manager._generate_order_fingerprint(request)
        assert fingerprint in manager._order_fingerprints
        assert manager._order_id_mapping[fingerprint] == result.order_id

    def test_multiple_different_orders_recorded(self) -> None:
        """Test multiple different orders are recorded."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request1 = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("1000"),
        )

        request2 = OrderRequest(
            Exchange.NSE,
            "TCS",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("3000"),
        )

        manager.place_order(request1)
        manager.place_order(request2)

        assert len(manager._order_fingerprints) == 2
        assert len(manager._order_id_mapping) == 2


class TestOrderStatePersistence:
    """Test order state persistence."""

    def test_save_state_includes_fingerprints(self) -> None:
        """Test save state includes order fingerprints."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("1000"),
        )

        manager.place_order(request)

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            manager.save_state(state_path)

            assert state_path.exists()

            import json

            with state_path.open() as f:
                data = json.load(f)

            assert "order_fingerprints" in data
            assert "order_id_mapping" in data
            assert len(data["order_fingerprints"]) == 1

    def test_load_state_restores_fingerprints(self) -> None:
        """Test load state restores order fingerprints."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("1000"),
        )

        manager.place_order(request)

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            manager.save_state(state_path)

            new_manager = OrderManager(
                _StubExecutor(),
                heartbeat_timeout_seconds=30,
                enable_duplicate_detection=True,
            )

            new_manager.load_state(state_path)

            assert len(new_manager._order_fingerprints) == 1
            assert len(new_manager._order_id_mapping) == 1

    def test_load_state_handles_missing_file(self) -> None:
        """Test load state handles missing file gracefully."""
        manager = OrderManager(
            _StubExecutor(),
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "nonexistent.json"

            manager.load_state(state_path)

            assert len(manager._order_fingerprints) == 0

    def test_load_state_handles_invalid_json(self) -> None:
        """Test load state handles invalid JSON gracefully."""
        manager = OrderManager(
            _StubExecutor(),
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "invalid.json"
            state_path.write_text("invalid json")

            manager.load_state(state_path)

            assert len(manager._order_fingerprints) == 0

    def test_auto_save_on_order_placement(self) -> None:
        """Test state is auto-saved on order placement when path is set."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            manager._state_persistence_path = state_path

        request = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            price=Decimal("1000"),
        )

        manager.place_order(request)

        assert state_path.exists()


class TestIdempotentOrderPlacement:
    """Test idempotent order placement."""

    def test_idempotent_order_placement(self) -> None:
        """Test idempotent order placement returns same result."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("1000"),
        )

        result1 = manager.place_order(request)
        result2 = manager.place_order(request)
        result3 = manager.place_order(request)

        assert result1.order_id == result2.order_id == result3.order_id
        assert executor.order_count == 1

    def test_idempotent_order_with_different_quantities(self) -> None:
        """Test idempotent order with different quantities creates new order."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request1 = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            Decimal("1000"),
        )

        request2 = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("20"),
            Decimal("1000"),
        )

        result1 = manager.place_order(request1)
        result2 = manager.place_order(request2)

        assert result1.order_id != result2.order_id
        assert executor.order_count == 2

    def test_idempotent_order_with_different_prices(self) -> None:
        """Test idempotent order with different prices creates new order."""
        executor = _StubExecutor()
        manager = OrderManager(
            executor,
            heartbeat_timeout_seconds=30,
            enable_duplicate_detection=True,
        )

        request1 = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            price=Decimal("1000"),
        )

        request2 = OrderRequest(
            Exchange.NSE,
            "RELIANCE",
            OrderSide.BUY,
            Decimal("10"),
            price=Decimal("1100"),
        )

        result1 = manager.place_order(request1)
        result2 = manager.place_order(request2)

        assert result1.order_id != result2.order_id
        assert executor.order_count == 2
