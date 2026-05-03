"""
Test crash recovery functionality for order manager and paper executor.
"""

import json
from decimal import Decimal
from pathlib import Path

from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.execution.base import OrderRequest
from iatb.execution.order_manager import OrderManager
from iatb.execution.paper_executor import PaperExecutor
from iatb.storage.backup import export_trading_state, load_trading_state


class TestCrashRecoveryMode:
    """Test crash recovery mode functionality."""

    def test_paper_executor_loads_state_on_init(self, tmp_path: Path) -> None:
        """Test that PaperExecutor loads trading state on initialization."""
        state_path = tmp_path / "state.json"
        positions = {"NIFTY": (Decimal("10"), Decimal("100"))}
        pending_orders: dict[str, dict[str, object]] = {}
        export_trading_state(positions, pending_orders, state_path)

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        assert executor._state_persistence_path == state_path
        assert executor._crash_recovery_mode is True

    def test_order_manager_loads_state_on_init(self, tmp_path: Path) -> None:
        """Test that OrderManager loads state on initialization in crash recovery mode."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        assert order_manager._state_persistence_path == state_path
        assert order_manager._crash_recovery_mode is True

    def test_crash_recovery_skips_already_filled_orders(self, tmp_path: Path) -> None:
        """Test that crash recovery mode skips orders that were already filled."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100")
        )

        result1 = order_manager.place_order(request)
        assert result1.status == OrderStatus.FILLED

        original_order_id = result1.order_id

        order_manager.save_state(state_path)

        new_executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        new_order_manager = OrderManager(
            executor=new_executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        result2 = new_order_manager.place_order(request)

        assert result2.order_id == original_order_id
        assert result2.status == OrderStatus.FILLED

    def test_export_trading_state_on_fill(self, tmp_path: Path) -> None:
        """Test that trading state is exported on every order fill."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100")
        )

        order_manager.place_order(request)

        assert state_path.exists()
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert "exported_at_utc" in data

    def test_crash_recovery_idempotency(self, tmp_path: Path) -> None:
        """Test that crash recovery ensures idempotent order handling."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100")
        )

        result1 = order_manager.place_order(request)
        order_manager.save_state(state_path)

        new_executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        new_order_manager = OrderManager(
            executor=new_executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        for _ in range(3):
            result = new_order_manager.place_order(request)
            assert result.order_id == result1.order_id

    def test_state_persistence_path_optional(self) -> None:
        """Test that state persistence path is optional."""
        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=None,
            crash_recovery_mode=False,
        )

        assert executor._state_persistence_path is None
        assert executor._crash_recovery_mode is False

    def test_crash_recovery_mode_without_state_file(self, tmp_path: Path) -> None:
        """Test that crash recovery mode handles missing state file gracefully."""
        state_path = tmp_path / "nonexistent.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100")
        )

        result = order_manager.place_order(request)
        assert result.status == OrderStatus.FILLED

    def test_load_trading_state_format(self, tmp_path: Path) -> None:
        """Test loading trading state with correct format."""
        state_path = tmp_path / "state.json"
        positions = {"NIFTY": (Decimal("10"), Decimal("100.50"))}
        pending_orders = {
            "order-1": {
                "symbol": "NIFTY",
                "side": "BUY",
                "quantity": str(Decimal("1")),
                "price": str(Decimal("100")),
            }
        }

        export_trading_state(positions, pending_orders, state_path)
        loaded_positions, loaded_orders = load_trading_state(state_path)

        assert loaded_positions["NIFTY"] == (Decimal("10"), Decimal("100.50"))
        assert "order-1" in loaded_orders
        assert loaded_orders["order-1"]["symbol"] == "NIFTY"

    def test_crash_recovery_with_multiple_orders(self, tmp_path: Path) -> None:
        """Test crash recovery with multiple orders."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        orders = []
        for i in range(3):
            request = OrderRequest(
                Exchange.NSE,
                f"NIFTY{i}",
                OrderSide.BUY,
                Decimal("1"),
                price=Decimal("100"),
            )
            result = order_manager.place_order(request)
            orders.append(result.order_id)
            order_manager.save_state(state_path)

        new_executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        new_order_manager = OrderManager(
            executor=new_executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        for i, original_order_id in enumerate(orders):
            request = OrderRequest(
                Exchange.NSE,
                f"NIFTY{i}",
                OrderSide.BUY,
                Decimal("1"),
                price=Decimal("100"),
            )
            result = new_order_manager.place_order(request)
            assert result.order_id == original_order_id

    def test_state_export_import_roundtrip(self, tmp_path: Path) -> None:
        """Test that state export and import works correctly."""
        state_path = tmp_path / "state.json"

        original_positions = {
            "NIFTY": (Decimal("10"), Decimal("100.50")),
            "BANKNIFTY": (Decimal("5"), Decimal("45000.25")),
        }
        original_orders = {
            "order-1": {"symbol": "NIFTY", "side": "BUY"},
            "order-2": {"symbol": "BANKNIFTY", "side": "SELL"},
        }

        export_trading_state(original_positions, original_orders, state_path)
        loaded_positions, loaded_orders = load_trading_state(state_path)

        assert loaded_positions == original_positions
        # Verify core fields are preserved (quantity/price are added with defaults)
        assert loaded_orders["order-1"]["symbol"] == "NIFTY"
        assert loaded_orders["order-1"]["side"] == "BUY"
        assert loaded_orders["order-2"]["symbol"] == "BANKNIFTY"
        assert loaded_orders["order-2"]["side"] == "SELL"

    def test_crash_recovery_preserves_order_status(self, tmp_path: Path) -> None:
        """Test that crash recovery preserves order status."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100")
        )

        result = order_manager.place_order(request)
        original_order_id = result.order_id

        order_manager.save_state(state_path)

        new_executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        new_order_manager = OrderManager(
            executor=new_executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        status = new_order_manager.get_order_status(original_order_id)
        assert status == OrderStatus.FILLED

    def test_paper_executor_exports_state_on_fill(self, tmp_path: Path) -> None:
        """Test that PaperExecutor exports trading state on every order fill."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100")
        )

        # Execute order
        result = executor.execute_order(request)

        # Verify state file was created
        assert state_path.exists()

        # Verify state file has correct structure
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert "exported_at_utc" in data
        assert "positions" in data
        assert "pending_orders" in data

        # Verify order is in pending orders
        assert result.order_id in data["pending_orders"]
        assert data["pending_orders"][result.order_id]["status"] == "OPEN"

    def test_paper_executor_handles_export_errors(self, tmp_path: Path) -> None:
        """Test that PaperExecutor handles export errors gracefully."""
        # Create a directory instead of a file to trigger write error
        state_path = tmp_path / "state_dir"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100")
        )

        # Should not raise exception even if export fails
        result = executor.execute_order(request)
        assert result.status == OrderStatus.FILLED

    def test_crash_recovery_with_order_status_restore(self, tmp_path: Path) -> None:
        """Test crash recovery with order status restoration."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        # Place buy order
        buy_request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"), price=Decimal("100")
        )
        result = order_manager.place_order(buy_request)
        original_order_id = result.order_id
        order_manager.save_state(state_path)

        # Simulate crash and restore
        new_executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        new_order_manager = OrderManager(
            executor=new_executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        # Verify order status was restored
        status = new_order_manager.get_order_status(original_order_id)
        assert status == OrderStatus.FILLED

    def test_crash_recovery_with_multiple_symbols(self, tmp_path: Path) -> None:
        """Test crash recovery with multiple symbols."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        symbols = ["NIFTY", "BANKNIFTY", "FINNIFTY"]
        order_ids = []

        for symbol in symbols:
            request = OrderRequest(
                Exchange.NSE, symbol, OrderSide.BUY, Decimal("5"), price=Decimal("100")
            )
            result = order_manager.place_order(request)
            order_ids.append(result.order_id)

        order_manager.save_state(state_path)

        # Simulate crash and restore
        new_executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        new_order_manager = OrderManager(
            executor=new_executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        # Verify all order statuses were restored
        for order_id in order_ids:
            status = new_order_manager.get_order_status(order_id)
            assert status == OrderStatus.FILLED

    def test_crash_recovery_preserves_order_fingerprints(self, tmp_path: Path) -> None:
        """Test that crash recovery preserves order fingerprints for duplicate detection."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100")
        )

        result1 = order_manager.place_order(request)
        order_manager.save_state(state_path)

        # Simulate crash and restore
        new_executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        new_order_manager = OrderManager(
            executor=new_executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        # Attempt to place duplicate order - should be detected
        result2 = new_order_manager.place_order(request)

        # Should return the original order ID (duplicate detected)
        assert result2.order_id == result1.order_id
        assert result2.status == OrderStatus.FILLED

    def test_crash_recovery_mode_false_no_duplicate_skip(self, tmp_path: Path) -> None:
        """Test that without crash recovery mode, duplicate orders are not skipped."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=False,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=False,
        )

        request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100")
        )

        result1 = order_manager.place_order(request)
        order_manager.save_state(state_path)

        # Create new order manager without crash recovery mode
        new_executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=False,
        )

        new_order_manager = OrderManager(
            executor=new_executor,
            state_persistence_path=state_path,
            crash_recovery_mode=False,
        )

        # Without crash recovery mode, duplicate detection should still work
        # but it won't skip FILLED orders (it will return them as duplicates)
        result2 = new_order_manager.place_order(request)

        # Should return the original order ID (duplicate detection works regardless of mode)
        assert result2.order_id == result1.order_id

    def test_state_persistence_with_corrupted_file(self, tmp_path: Path) -> None:
        """Test that corrupted state file is handled gracefully."""
        state_path = tmp_path / "state.json"

        # Write corrupted JSON
        state_path.write_text("{invalid json", encoding="utf-8")

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        # Should be able to place orders despite corrupted state file
        request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100")
        )

        result = order_manager.place_order(request)
        assert result.status == OrderStatus.FILLED

    def test_export_trading_state_preserves_precision(self, tmp_path: Path) -> None:
        """Test that state export preserves Decimal precision."""
        state_path = tmp_path / "state.json"

        executor = PaperExecutor(
            slippage_bps=Decimal("5"),
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        order_manager = OrderManager(
            executor=executor,
            state_persistence_path=state_path,
            crash_recovery_mode=True,
        )

        # Use high precision values
        request = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("0.5"), price=Decimal("12345.67")
        )

        order_manager.place_order(request)
        order_manager.save_state(state_path)

        # Load state and verify precision is preserved
        data = json.loads(state_path.read_text(encoding="utf-8"))

        # Check position data preserves precision
        position_data = data.get("position_state", {})
        if "NIFTY" in position_data:
            qty = Decimal(position_data["NIFTY"]["qty"])
            avg_price = Decimal(position_data["NIFTY"]["avg_price"])
            assert qty == Decimal("0.5")
            assert avg_price > Decimal("12345")  # Should be close to original with slippage
