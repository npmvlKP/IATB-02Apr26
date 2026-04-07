"""
Unit tests for OpenAlgoExecutor with Zerodha broker integration.

Covers happy path, error paths, precision handling, timezone handling,
and external API mocking.
"""

import os
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus, OrderType
from iatb.core.exceptions import ConfigError
from iatb.execution.base import OrderRequest
from iatb.execution.openalgo_executor import OpenAlgoExecutor


class TestOpenAlgoExecutor:
    """Test suite for OpenAlgoExecutor Zerodha integration."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_place_order = MagicMock(
            return_value={
                "order_id": "ORD123",
                "status": "FILLED",
                "filled_quantity": "10",
                "average_price": "150.25",
            }
        )
        self.mock_cancel_all = MagicMock(return_value=5)
        self.executor = OpenAlgoExecutor(
            place_order=self.mock_place_order,
            cancel_all_orders=self.mock_cancel_all,
            broker="zerodha",
        )

    @pytest.fixture(autouse=True)
    def reset_env(self) -> None:
        """Reset environment variables before each test."""
        original_env = os.environ.copy()
        os.environ.clear()
        yield
        os.environ.clear()
        os.environ.update(original_env)

    # ========================================
    # Happy Path Tests
    # ========================================

    def test_initialization_with_zerodha(self) -> None:
        """Test executor initializes correctly with Zerodha broker."""
        assert self.executor.broker == "zerodha"

    def test_execute_order_success(self) -> None:
        """Test successful order execution with Decimal precision."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
            metadata={"algo_id": "ALGO_001"},
        )

        result = self.executor.execute_order(request)

        assert result.order_id == "ORD123"
        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == Decimal("10")
        assert result.average_price == Decimal("150.25")
        self.mock_place_order.assert_called_once()

    def test_cancel_all_success(self) -> None:
        """Test successful cancellation of all orders."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        cancelled = self.executor.cancel_all()

        assert cancelled == 5
        self.mock_cancel_all.assert_called_once()

    def test_limit_order_with_price(self) -> None:
        """Test limit order execution with specific price."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="INFY",
            side=OrderSide.SELL,
            quantity=Decimal("50"),
            order_type=OrderType.LIMIT,
            price=Decimal("1450.75"),
            metadata={"algo_id": "ALGO_002"},
        )

        self.executor.execute_order(request)

        call_args = self.mock_place_order.call_args[0][0]
        assert call_args["price"] == "1450.75"
        assert call_args["order_type"] == "LIMIT"

    # ========================================
    # Error Path Tests
    # ========================================

    def test_live_trading_disabled_raises_error(self) -> None:
        """Test error when live trading is disabled."""
        os.environ["LIVE_TRADING_ENABLED"] = "false"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001"},
        )

        with pytest.raises(ConfigError, match="live execution blocked"):
            self.executor.execute_order(request)

    def test_oauth_2fa_not_verified_raises_error(self) -> None:
        """Test error when OAuth 2FA is not verified."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "false"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001"},
        )

        with pytest.raises(ConfigError, match="broker access blocked"):
            self.executor.execute_order(request)

    def test_missing_api_key_raises_error(self) -> None:
        """Test error when Zerodha API key is missing."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001"},
        )

        with pytest.raises(ConfigError, match="Zerodha API key missing"):
            self.executor.execute_order(request)

    def test_missing_api_secret_raises_error(self) -> None:
        """Test error when Zerodha API secret is missing."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001"},
        )

        with pytest.raises(ConfigError, match="Zerodha API secret missing"):
            self.executor.execute_order(request)

    def test_missing_algo_id_raises_error(self) -> None:
        """Test error when algo_id is missing from metadata."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={},  # Missing algo_id
        )

        with pytest.raises(ConfigError, match="algo_id metadata is required"):
            self.executor.execute_order(request)

    def test_empty_algo_id_raises_error(self) -> None:
        """Test error when algo_id is empty string."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "   "},  # Empty/whitespace only
        )

        with pytest.raises(ConfigError, match="algo_id metadata is required"):
            self.executor.execute_order(request)

    def test_invalid_broker_raises_error(self) -> None:
        """Test error when unsupported broker is provided."""
        with pytest.raises(ConfigError, match="unsupported broker"):
            OpenAlgoExecutor(
                place_order=self.mock_place_order,
                cancel_all_orders=self.mock_cancel_all,
                broker="invalid_broker",
            )

    def test_response_missing_order_id_raises_error(self) -> None:
        """Test error when API response lacks order_id."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        self.mock_place_order.return_value = {"status": "COMPLETE"}

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001"},
        )

        with pytest.raises(ConfigError, match="response missing order_id"):
            self.executor.execute_order(request)

    # ========================================
    # Precision Handling Tests
    # ========================================

    def test_decimal_precision_in_quantity(self) -> None:
        """Test that Decimal precision is maintained for quantity."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        high_precision_qty = Decimal("10.5")
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=high_precision_qty,
            metadata={"algo_id": "ALGO_001"},
        )

        self.executor.execute_order(request)

        call_args = self.mock_place_order.call_args[0][0]
        assert call_args["quantity"] == "10.5"

    def test_decimal_precision_in_price(self) -> None:
        """Test that Decimal precision is maintained for price."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        high_precision_price = Decimal("1234.5678")
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.LIMIT,
            price=high_precision_price,
            metadata={"algo_id": "ALGO_001"},
        )

        self.executor.execute_order(request)

        call_args = self.mock_place_order.call_args[0][0]
        assert call_args["price"] == "1234.5678"

    def test_response_parsed_with_decimal_precision(self) -> None:
        """Test that API response values are parsed as Decimal."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        self.mock_place_order.return_value = {
            "order_id": "ORD123",
            "status": "COMPLETE",
            "filled_quantity": "10.5",
            "average_price": "1234.5678",
        }

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001"},
        )

        result = self.executor.execute_order(request)

        assert result.filled_quantity == Decimal("10.5")
        assert result.average_price == Decimal("1234.5678")
        assert isinstance(result.filled_quantity, Decimal)
        assert isinstance(result.average_price, Decimal)

    # ========================================
    # Timezone Handling Tests
    # ========================================

    @patch("iatb.execution.openalgo_executor.datetime")
    def test_logging_uses_utc_datetime(self, mock_datetime: MagicMock) -> None:
        """Test that logging uses UTC timezone-aware datetime."""
        mock_now = datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC)
        mock_datetime.now.return_value = mock_now
        mock_datetime.UTC = UTC

        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001"},
        )

        self.executor.execute_order(request)

        # Verify datetime.now(UTC) was called (not datetime.now() without UTC)
        mock_datetime.now.assert_called_with(UTC)

    # ========================================
    # External API Mocking Tests
    # ========================================

    def test_external_place_order_is_mocked(self) -> None:
        """Test that external place_order API is properly mocked."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001"},
        )

        _ = self.executor.execute_order(request)

        # Verify mock was called with correct payload
        assert self.mock_place_order.called
        call_args = self.mock_place_order.call_args[0][0]
        assert call_args["broker"] == "zerodha"
        assert call_args["symbol"] == "TCS"
        assert call_args["side"] == "BUY"

    def test_external_cancel_all_is_mocked(self) -> None:
        """Test that external cancel_all API is properly mocked."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        cancelled = self.executor.cancel_all()

        # Verify mock was called
        assert self.mock_cancel_all.called
        assert cancelled == 5

    # ========================================
    # Broker Configuration Tests
    # ========================================

    def test_broker_case_insensitive(self) -> None:
        """Test that broker name is case-insensitive."""
        executor_upper = OpenAlgoExecutor(
            place_order=self.mock_place_order,
            cancel_all_orders=self.mock_cancel_all,
            broker="ZERODHA",
        )
        assert executor_upper.broker == "zerodha"

        executor_mixed = OpenAlgoExecutor(
            place_order=self.mock_place_order,
            cancel_all_orders=self.mock_cancel_all,
            broker="ZeRoDhA",
        )
        assert executor_mixed.broker == "zerodha"

    def test_supported_brokers_include_zerodha(self) -> None:
        """Test that Zerodha is in the supported brokers list."""
        executor = OpenAlgoExecutor(
            place_order=self.mock_place_order,
            cancel_all_orders=self.mock_cancel_all,
            broker="zerodha",
        )
        assert executor.broker == "zerodha"

    # ========================================
    # Order Status Parsing Tests
    # ========================================

    def test_parse_valid_order_status(self) -> None:
        """Test parsing of valid order status strings."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        test_cases = [
            ("FILLED", OrderStatus.FILLED),
            ("PENDING", OrderStatus.PENDING),
            ("CANCELLED", OrderStatus.CANCELLED),
            ("REJECTED", OrderStatus.REJECTED),
            ("OPEN", OrderStatus.OPEN),
        ]

        for status_str, expected_status in test_cases:
            self.mock_place_order.return_value = {
                "order_id": "ORD123",
                "status": status_str,
                "filled_quantity": "10",
                "average_price": "150.25",
            }

            request = OrderRequest(
                exchange=Exchange.NSE,
                symbol="TCS",
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                metadata={"algo_id": "ALGO_001"},
            )

            result = self.executor.execute_order(request)
            assert result.status == expected_status

    def test_parse_invalid_order_status_defaults_to_pending(
        self,
    ) -> None:
        """Test that invalid order status defaults to PENDING."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        self.mock_place_order.return_value = {
            "order_id": "ORD123",
            "status": "UNKNOWN_STATUS",
            "filled_quantity": "10",
            "average_price": "150.25",
        }

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001"},
        )

        result = self.executor.execute_order(request)
        assert result.status == OrderStatus.PENDING

    # ========================================
    # Payload Building Tests
    # ========================================

    def test_request_payload_includes_required_fields(self) -> None:
        """Test that request payload includes all required fields."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
            metadata={"algo_id": "ALGO_001", "product": "MIS", "validity": "DAY"},
        )

        self.executor.execute_order(request)

        call_args = self.mock_place_order.call_args[0][0]
        required_fields = [
            "broker",
            "exchange",
            "symbol",
            "side",
            "quantity",
            "order_type",
            "algo_id",
        ]
        for field in required_fields:
            assert field in call_args, f"Missing required field: {field}"

    def test_request_payload_preserves_metadata(self) -> None:
        """Test that metadata fields are preserved in payload."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001", "custom_field": "custom_value"},
        )

        self.executor.execute_order(request)

        call_args = self.mock_place_order.call_args[0][0]
        assert call_args["custom_field"] == "custom_value"

    # ========================================
    # Edge Cases
    # ========================================

    def test_non_zerodha_broker_skips_credential_check(self) -> None:
        """Test that non-Zerodha brokers don't require Zerodha credentials."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        # No Zerodha credentials set

        angelone_executor = OpenAlgoExecutor(
            place_order=self.mock_place_order,
            cancel_all_orders=self.mock_cancel_all,
            broker="angelone",  # Different broker
        )

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001"},
        )

        # Should not raise credential error for non-Zerodha broker
        angelone_executor.execute_order(request)

    def test_response_with_message(self) -> None:
        """Test that response message is preserved."""
        os.environ["LIVE_TRADING_ENABLED"] = "true"
        os.environ["BROKER_OAUTH_2FA_VERIFIED"] = "true"
        os.environ["ZERODHA_API_KEY"] = "test_key"
        os.environ["ZERODHA_API_SECRET"] = "test_secret"  # noqa: S105

        self.mock_place_order.return_value = {
            "order_id": "ORD123",
            "status": "FILLED",
            "filled_quantity": "10",
            "average_price": "150.25",
            "message": "Order placed successfully",
        }

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            metadata={"algo_id": "ALGO_001"},
        )

        result = self.executor.execute_order(request)
        assert result.message == "Order placed successfully"
