"""
Unit tests for OpenAlgo executor with Zerodha-specific integration.

All external API calls are mocked. Tests cover:
- Happy path (successful order execution)
- Error paths (missing credentials, invalid broker, API failures)
- Precision handling (Decimal for financial values)
- Timezone handling (UTC-aware timestamps)
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus, OrderType
from iatb.core.exceptions import ConfigError
from iatb.execution.base import OrderRequest
from iatb.execution.openalgo_executor import (
    OpenAlgoExecutor,
    _assert_zerodha_credentials,
    _parse_response,
    _parse_status,
    _request_payload,
    _validate_broker,
)
from iatb.risk.sebi_compliance import (
    assert_static_ip_allowed,
    validate_static_ip_format,
    validate_static_ips_config,
)

# ===========================================
# Fixtures
# ===========================================


@pytest.fixture
def mock_place_order() -> MagicMock:
    """Mock place_order callable."""
    return MagicMock(
        return_value={
            "order_id": "OA-TEST-123",
            "status": "FILLED",
            "filled_quantity": "10",
            "average_price": "100.50",
            "message": "Order executed successfully",
        }
    )


@pytest.fixture
def mock_cancel_all() -> MagicMock:
    """Mock cancel_all_orders callable."""
    return MagicMock(return_value=5)


@pytest.fixture
def env_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable live trading and OAuth 2FA gates."""
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("BROKER_OAUTH_2FA_VERIFIED", "true")
    monkeypatch.setenv("ZERODHA_API_KEY", "test_api_key_123")
    monkeypatch.setenv("ZERODHA_API_SECRET", "test_api_secret_456")


@pytest.fixture
def sample_order_request() -> OrderRequest:
    """Sample order request for testing."""
    return OrderRequest(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        order_type=OrderType.LIMIT,
        price=Decimal("2500.75"),
        metadata={"algo_id": "ALGO-001", "product": "MIS"},
    )


# ===========================================
# Happy Path Tests
# ===========================================


def test_executor_initialization_with_zerodha(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
) -> None:
    """Test executor initializes correctly with Zerodha broker."""
    executor = OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="zerodha",
    )
    assert executor.broker == "zerodha"


def test_execute_order_happy_path(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
    env_enabled: None,
    sample_order_request: OrderRequest,
) -> None:
    """Test successful order execution with all gates enabled."""
    executor = OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="zerodha",
    )
    result = executor.execute_order(sample_order_request)

    assert result.order_id == "OA-TEST-123"
    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == Decimal("10")
    assert result.average_price == Decimal("100.50")
    assert result.message == "Order executed successfully"
    mock_place_order.assert_called_once()


def test_cancel_all_happy_path(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
    env_enabled: None,
) -> None:
    """Test successful cancellation of all orders."""
    executor = OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="zerodha",
    )
    cancelled_count = executor.cancel_all()

    assert cancelled_count == 5
    mock_cancel_all.assert_called_once()


def test_request_payload_includes_broker(
    env_enabled: None,
    sample_order_request: OrderRequest,
) -> None:
    """Test request payload includes broker field for OpenAlgo."""
    payload = _request_payload(sample_order_request, broker="zerodha")

    assert payload["broker"] == "zerodha"
    assert payload["exchange"] == "NSE"
    assert payload["symbol"] == "RELIANCE"
    assert payload["side"] == "BUY"
    assert payload["quantity"] == "10"
    assert payload["order_type"] == "LIMIT"
    assert payload["price"] == "2500.75"
    assert payload["algo_id"] == "ALGO-001"
    assert payload["product"] == "MIS"


def test_parse_response_decimal_precision() -> None:
    """Test response parsing preserves Decimal precision."""
    response = {
        "order_id": "OA-DECIMAL-TEST",
        "status": "FILLED",
        "filled_quantity": "10.123456",
        "average_price": "2500.987654",
        "message": "Precision test",
    }
    result = _parse_response(response)

    assert result.filled_quantity == Decimal("10.123456")
    assert result.average_price == Decimal("2500.987654")


def test_parse_status_all_valid_statuses() -> None:
    """Test parsing all valid order statuses."""
    assert _parse_status("PENDING") == OrderStatus.PENDING
    assert _parse_status("OPEN") == OrderStatus.OPEN
    assert _parse_status("FILLED") == OrderStatus.FILLED
    assert _parse_status("CANCELLED") == OrderStatus.CANCELLED
    assert _parse_status("REJECTED") == OrderStatus.REJECTED


def test_parse_status_unknown_returns_pending() -> None:
    """Test unknown status defaults to PENDING."""
    assert _parse_status("UNKNOWN_STATUS") == OrderStatus.PENDING
    assert _parse_status("") == OrderStatus.PENDING


# ===========================================
# Error Path Tests
# ===========================================


def test_executor_rejects_unsupported_broker(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
) -> None:
    """Test executor rejects unsupported broker."""
    with pytest.raises(ConfigError, match="unsupported broker"):
        OpenAlgoExecutor(
            place_order=mock_place_order,
            cancel_all_orders=mock_cancel_all,
            broker="invalid_broker",
        )


def test_execute_order_blocked_without_live_gate(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    sample_order_request: OrderRequest,
) -> None:
    """Test execution blocked when LIVE_TRADING_ENABLED is not set."""
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.setenv("BROKER_OAUTH_2FA_VERIFIED", "true")
    monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
    monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

    executor = OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="zerodha",
    )

    with pytest.raises(ConfigError, match="LIVE_TRADING_ENABLED=true"):
        executor.execute_order(sample_order_request)


def test_execute_order_blocked_without_oauth_2fa(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    sample_order_request: OrderRequest,
) -> None:
    """Test execution blocked when BROKER_OAUTH_2FA_VERIFIED is not set."""
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.delenv("BROKER_OAUTH_2FA_VERIFIED", raising=False)
    monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
    monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

    executor = OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="zerodha",
    )

    with pytest.raises(ConfigError, match="BROKER_OAUTH_2FA_VERIFIED=true"):
        executor.execute_order(sample_order_request)


def test_execute_order_blocked_without_zerodha_api_key(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    sample_order_request: OrderRequest,
) -> None:
    """Test execution blocked when ZERODHA_API_KEY is missing."""
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("BROKER_OAUTH_2FA_VERIFIED", "true")
    monkeypatch.delenv("ZERODHA_API_KEY", raising=False)
    monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")

    executor = OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="zerodha",
    )

    with pytest.raises(ConfigError, match="Zerodha API key missing"):
        executor.execute_order(sample_order_request)


def test_execute_order_blocked_without_zerodha_api_secret(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    sample_order_request: OrderRequest,
) -> None:
    """Test execution blocked when ZERODHA_API_SECRET is missing."""
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("BROKER_OAUTH_2FA_VERIFIED", "true")
    monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
    monkeypatch.delenv("ZERODHA_API_SECRET", raising=False)

    executor = OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="zerodha",
    )

    with pytest.raises(ConfigError, match="Zerodha API secret missing"):
        executor.execute_order(sample_order_request)


def test_execute_order_blocked_without_algo_id(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
    env_enabled: None,
) -> None:
    """Test execution blocked when algo_id is missing from metadata."""
    request = OrderRequest(
        exchange=Exchange.NSE,
        symbol="NIFTY",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
    )
    executor = OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="zerodha",
    )

    with pytest.raises(ConfigError, match="algo_id metadata is required"):
        executor.execute_order(request)


def test_parse_response_missing_order_id() -> None:
    """Test parsing response with missing order_id raises error."""
    response = {"status": "FILLED", "filled_quantity": "10"}

    with pytest.raises(ConfigError, match="missing order_id"):
        _parse_response(response)


def test_validate_broker_rejects_empty() -> None:
    """Test broker validation rejects empty string."""
    with pytest.raises(ConfigError, match="unsupported broker"):
        _validate_broker("")


# ===========================================
# Precision Handling Tests
# ===========================================


def test_decimal_precision_in_order_quantity(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
    env_enabled: None,
) -> None:
    """Test Decimal precision is preserved in order quantity."""
    request = OrderRequest(
        exchange=Exchange.NSE,
        symbol="NIFTY",
        side=OrderSide.BUY,
        quantity=Decimal("10.123456789"),
        order_type=OrderType.MARKET,
        metadata={"algo_id": "ALGO-PRECISION"},
    )
    executor = OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="zerodha",
    )
    executor.execute_order(request)

    call_args = mock_place_order.call_args[0][0]
    assert call_args["quantity"] == "10.123456789"


def test_decimal_precision_in_price(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
    env_enabled: None,
) -> None:
    """Test Decimal precision is preserved in limit price."""
    request = OrderRequest(
        exchange=Exchange.NSE,
        symbol="NIFTY",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        order_type=OrderType.LIMIT,
        price=Decimal("2500.0001"),
        metadata={"algo_id": "ALGO-PRECISION"},
    )
    executor = OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="zerodha",
    )
    executor.execute_order(request)

    call_args = mock_place_order.call_args[0][0]
    assert call_args["price"] == "2500.0001"


# ===========================================
# Timezone Handling Tests
# ===========================================


def test_executor_logs_utc_timestamps(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
    env_enabled: None,
    sample_order_request: OrderRequest,
) -> None:
    """Test executor uses UTC timestamps in logging."""
    with patch("iatb.execution.openalgo_executor._LOGGER") as mock_logger:
        executor = OpenAlgoExecutor(
            place_order=mock_place_order,
            cancel_all_orders=mock_cancel_all,
            broker="zerodha",
        )
        executor.execute_order(sample_order_request)

        # Check that info was called with UTC timestamps
        for call in mock_logger.info.call_args_list:
            extra = call.kwargs.get("extra", {})
            if "timestamp_utc" in extra:
                timestamp = extra["timestamp_utc"]
                # ISO format should contain 'Z' or '+00:00' for UTC
                assert "Z" in timestamp or "+00:00" in timestamp


# ===========================================
# Static IP Validation Tests
# ===========================================


def test_validate_static_ip_format_valid() -> None:
    """Test validation accepts valid IPv4 addresses."""
    assert validate_static_ip_format("192.168.1.1") is True
    assert validate_static_ip_format("10.0.0.1") is True
    assert validate_static_ip_format("255.255.255.255") is True
    # Note: 0.0.0.0 is valid IPv4 format (used in tests)
    assert validate_static_ip_format("127.0.0.1") is True


def test_validate_static_ip_format_invalid() -> None:
    """Test validation rejects invalid IPv4 addresses."""
    assert validate_static_ip_format("256.1.1.1") is False
    assert validate_static_ip_format("192.168.1") is False
    assert validate_static_ip_format("192.168.1.1.1") is False
    assert validate_static_ip_format("not.an.ip") is False
    assert validate_static_ip_format("") is False
    assert validate_static_ip_format("192.168.1.1 ") is True  # Trims whitespace


def test_validate_static_ips_config_valid() -> None:
    """Test config validation accepts valid IP tuple."""
    # Should not raise
    validate_static_ips_config(("192.168.1.1", "10.0.0.1"))


def test_validate_static_ips_config_invalid() -> None:
    """Test config validation rejects invalid IPs."""
    with pytest.raises(ConfigError, match="invalid static IP addresses"):
        validate_static_ips_config(("192.168.1.1", "invalid.ip"))


def test_assert_static_ip_allowed_happy_path() -> None:
    """Test static IP assertion passes for allowed IP."""
    # Should not raise
    assert_static_ip_allowed(
        "192.168.1.1",
        ("192.168.1.1", "10.0.0.1"),
        broker="zerodha",
    )


def test_assert_static_ip_allowed_blocked() -> None:
    """Test static IP assertion blocks non-allowed IP."""
    with pytest.raises(ConfigError, match="not in allowed static IPs"):
        assert_static_ip_allowed(
            "192.168.1.100",
            ("192.168.1.1", "10.0.0.1"),
            broker="zerodha",
        )


def test_assert_static_ip_allowed_empty() -> None:
    """Test static IP assertion blocks empty IP."""
    with pytest.raises(ConfigError, match="source IP address cannot be empty"):
        assert_static_ip_allowed(
            "",
            ("192.168.1.1",),
            broker="zerodha",
        )


def test_assert_static_ip_allowed_invalid_format() -> None:
    """Test static IP assertion blocks invalid IP format."""
    with pytest.raises(ConfigError, match="invalid format"):
        assert_static_ip_allowed(
            "not.an.ip.address",
            ("192.168.1.1",),
            broker="zerodha",
        )


# ===========================================
# Supported Broker Tests
# ===========================================


def test_supported_brokers_accepted(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
) -> None:
    """Test all supported brokers are accepted."""
    supported_brokers = ["zerodha", "angelone", "upstox", "icici"]
    for broker in supported_brokers:
        executor = OpenAlgoExecutor(
            place_order=mock_place_order,
            cancel_all_orders=mock_cancel_all,
            broker=broker,
        )
        assert executor.broker == broker


def test_broker_case_insensitive(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
) -> None:
    """Test broker name is case insensitive."""
    executor = OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="ZERODHA",
    )
    assert executor.broker == "zerodha"


def test_non_zerodha_broker_skips_credential_check(
    mock_place_order: MagicMock,
    mock_cancel_all: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test non-Zerodha brokers skip Zerodha credential check."""
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("BROKER_OAUTH_2FA_VERIFIED", "true")
    # No Zerodha credentials set
    monkeypatch.delenv("ZERODHA_API_KEY", raising=False)
    monkeypatch.delenv("ZERODHA_API_SECRET", raising=False)

    OpenAlgoExecutor(
        place_order=mock_place_order,
        cancel_all_orders=mock_cancel_all,
        broker="angelone",
    )
    # Should not raise because broker is not zerodha
    _assert_zerodha_credentials("angelone")


# ===========================================
# Default Values Tests
# ===========================================


def test_request_payload_default_values(env_enabled: None) -> None:
    """Test request payload uses correct default values."""
    request = OrderRequest(
        exchange=Exchange.NSE,
        symbol="NIFTY",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        metadata={"algo_id": "ALGO-DEFAULTS"},
    )
    payload = _request_payload(request, broker="zerodha")

    assert payload["product"] == "MIS"  # Default product
    assert payload["validity"] == "DAY"  # Default validity


def test_request_payload_custom_values(env_enabled: None) -> None:
    """Test request payload respects custom metadata values."""
    request = OrderRequest(
        exchange=Exchange.NSE,
        symbol="NIFTY",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        metadata={
            "algo_id": "ALGO-CUSTOM",
            "product": "CNC",
            "validity": "IOC",
        },
    )
    payload = _request_payload(request, broker="zerodha")

    assert payload["product"] == "CNC"
    assert payload["validity"] == "IOC"
