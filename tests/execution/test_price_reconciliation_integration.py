"""
Integration tests for price reconciliation in pre-trade validation.

Tests cover:
- validate_with_price_reconciliation function
- create_reconciliation_config helper function
- Integration with existing pre-trade validation
- Error handling and edge cases
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.data.price_reconciler import (
    ReconciliationConfig,
)
from iatb.execution.pre_trade_validator import (
    create_reconciliation_config,
    validate_with_price_reconciliation,
)


class TestValidateWithPriceReconciliation:
    """Test validate_with_price_reconciliation function."""

    def test_happy_path_within_threshold(self) -> None:
        """Test successful validation with prices within threshold."""
        scanner_price = Decimal("1000.00")
        execution_price = Decimal("1010.00")  # 1% deviation
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC)
        symbol = "RELIANCE"

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
        )

        assert result.passed is True
        assert result.deviation_pct == Decimal("0.01")
        assert result.severity == "info"

    def test_high_deviation_fails(self) -> None:
        """Test validation fails with high price deviation."""
        scanner_price = Decimal("1000.00")
        execution_price = Decimal("1050.00")  # 5% deviation (exceeds 2%)
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC)
        symbol = "RELIANCE"

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
        )

        assert result.passed is False
        assert result.deviation_pct == Decimal("0.05")
        # 5% deviation is at threshold for "critical" (>= 5%)
        assert result.severity == "critical"

    def test_with_custom_config(self) -> None:
        """Test validation with custom reconciliation config."""
        custom_config = ReconciliationConfig(
            max_price_deviation_pct=Decimal("0.05"),  # 5% threshold
        )

        scanner_price = Decimal("1000.00")
        execution_price = Decimal("1030.00")  # 3% deviation (within 5%)
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC)
        symbol = "RELIANCE"

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
            reconciler_config=custom_config,
        )

        assert result.passed is True
        assert result.deviation_pct == Decimal("0.03")

    def test_with_corporate_action_detection(self) -> None:
        """Test validation with corporate action detection."""
        scanner_price = Decimal("2000.00")
        execution_price = Decimal("1000.00")  # 50% drop (potential split)
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC)
        symbol = "RELIANCE"
        prev_close = Decimal("2000.00")

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
            prev_close_price=prev_close,
        )

        # Should detect corporate action and pass with warning
        assert result.passed is True
        assert result.severity == "warning"
        assert "Corporate action detected" in result.reason

    def test_non_utc_timestamp_raises_error(self) -> None:
        """Test that non-UTC timestamp raises ConfigError."""
        # Create naive datetime (intentionally for this test)
        naive_ts = datetime(2026, 4, 19, 12, 0, 0, tzinfo=None)  # noqa: DTZ001

        with pytest.raises(ConfigError, match="timestamp must be UTC-aware"):
            validate_with_price_reconciliation(
                scanner_price=Decimal("1000.00"),
                execution_price=Decimal("1010.00"),
                scanner_timestamp=naive_ts,  # Non-UTC
                execution_timestamp=datetime.now(UTC),
                symbol="RELIANCE",
            )

    def test_stale_execution_price_fails(self) -> None:
        """Test that stale execution price fails validation."""
        scanner_price = Decimal("1000.00")
        execution_price = Decimal("1010.00")
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC) - timedelta(minutes=2)  # 2 minutes old
        symbol = "RELIANCE"

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
        )

        assert result.passed is False
        assert "timestamp drift too high" in result.reason
        assert result.severity == "error"

    def test_old_scanner_eod_fails(self) -> None:
        """Test that old scanner EOD data fails validation."""
        scanner_price = Decimal("1000.00")
        execution_price = Decimal("1010.00")
        scanner_ts = datetime.now(UTC) - timedelta(days=2)  # 2 days old
        execution_ts = datetime.now(UTC)
        symbol = "RELIANCE"

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
        )

        assert result.passed is False
        assert "too old" in result.reason
        assert result.severity == "error"

    def test_zero_price_fails(self) -> None:
        """Test that zero price fails validation."""
        scanner_price = Decimal("1000.00")
        execution_price = Decimal("0")  # Zero price
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC)
        symbol = "RELIANCE"

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
        )

        assert result.passed is False
        assert "Invalid price" in result.reason
        assert result.severity == "critical"

    def test_negative_price_fails(self) -> None:
        """Test that negative price fails validation."""
        scanner_price = Decimal("1000.00")
        execution_price = Decimal("-10.00")  # Negative price
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC)
        symbol = "RELIANCE"

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
        )

        assert result.passed is False
        assert "Invalid price" in result.reason
        assert result.severity == "critical"

    def test_symbol_mapping_normalization(self) -> None:
        """Test that symbol mapping normalization works."""
        scanner_price = Decimal("1000.00")
        execution_price = Decimal("1010.00")
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC)

        # Different symbol representations
        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol="RELIANCE-EQ",  # Scanner uses suffix
        )

        # Should pass because symbol is normalized internally
        assert result.passed is True


class TestCreateReconciliationConfig:
    """Test create_reconciliation_config helper function."""

    def test_default_config(self) -> None:
        """Test creating config with all defaults."""
        config = create_reconciliation_config()

        assert config.max_price_deviation_pct == Decimal("0.02")
        assert config.max_timestamp_drift_seconds == 60
        assert config.strict_eod_alignment is True
        assert config.detect_corporate_actions is True
        assert config.validate_symbol_mapping is True
        assert config.max_price_jump_pct == Decimal("0.20")

    def test_custom_config(self) -> None:
        """Test creating config with custom parameters."""
        config = create_reconciliation_config(
            max_price_deviation_pct=Decimal("0.05"),
            max_timestamp_drift_seconds=120,
            strict_eod_alignment=False,
            detect_corporate_actions=False,
            validate_symbol_mapping=False,
            max_price_jump_pct=Decimal("0.30"),
        )

        assert config.max_price_deviation_pct == Decimal("0.05")
        assert config.max_timestamp_drift_seconds == 120
        assert config.strict_eod_alignment is False
        assert config.detect_corporate_actions is False
        assert config.validate_symbol_mapping is False
        assert config.max_price_jump_pct == Decimal("0.30")

    def test_partial_custom_config(self) -> None:
        """Test creating config with some custom parameters."""
        config = create_reconciliation_config(
            max_price_deviation_pct=Decimal("0.03"),
            max_timestamp_drift_seconds=90,
        )

        assert config.max_price_deviation_pct == Decimal("0.03")
        assert config.max_timestamp_drift_seconds == 90
        # Other parameters should use defaults
        assert config.strict_eod_alignment is True
        assert config.detect_corporate_actions is True
        assert config.validate_symbol_mapping is True
        assert config.max_price_jump_pct == Decimal("0.20")

    def test_returns_reconciliation_config_type(self) -> None:
        """Test that function returns ReconciliationConfig instance."""
        config = create_reconciliation_config()
        assert isinstance(config, ReconciliationConfig)


class TestIntegrationScenarios:
    """Test real-world integration scenarios."""

    def test_normal_trading_day_scenario(self) -> None:
        """Test normal trading day with small price movements."""
        # Scenario: Scanner analyzed EOD data yesterday, executing today
        scanner_price = Decimal("2450.75")
        execution_price = Decimal("2462.50")  # ~0.5% movement
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30) - timedelta(days=1)
        execution_ts = datetime.now(UTC)
        symbol = "INFY"
        prev_close = Decimal("2450.75")

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
            prev_close_price=prev_close,
        )

        assert result.passed is True
        assert result.severity == "info"

    def test_stock_split_scenario(self) -> None:
        """Test scenario with 2:1 stock split."""
        # Scenario: Company announced 2:1 split, price adjusted
        scanner_price = Decimal("3000.00")  # Pre-split EOD
        execution_price = Decimal("1500.00")  # Post-split price
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC)
        symbol = "HDFCBANK"
        prev_close = Decimal("3000.00")

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
            prev_close_price=prev_close,
        )

        # Should detect corporate action and allow with warning
        assert result.passed is True
        assert result.severity == "warning"
        assert "Corporate action detected" in result.reason
        assert "DOWN" in result.reason

    def test_bonus_issue_scenario(self) -> None:
        """Test scenario with bonus issue (1:1)."""
        # Scenario: 1:1 bonus issue, price adjusted
        scanner_price = Decimal("2000.00")
        execution_price = Decimal("1000.00")  # Post-bonus price
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC)
        symbol = "TCS"
        prev_close = Decimal("2000.00")

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
            prev_close_price=prev_close,
        )

        # Should detect corporate action and allow with warning
        assert result.passed is True
        assert result.severity == "warning"

    def test_high_volatility_scenario(self) -> None:
        """Test scenario with high market volatility."""
        # Scenario: Market down 4% due to news
        scanner_price = Decimal("1000.00")
        execution_price = Decimal("960.00")  # 4% drop
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC)
        symbol = "NIFTY50"
        prev_close = Decimal("1000.00")

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
            prev_close_price=prev_close,
        )

        # Should fail - 4% exceeds 2% threshold
        assert result.passed is False
        # 4% deviation is <5% so severity is "error", not "critical"
        assert result.severity == "error"

    def test_data_feed_lag_scenario(self) -> None:
        """Test scenario with data feed lag."""
        # Scenario: Kite WebSocket lagged by 90 seconds
        scanner_price = Decimal("1000.00")
        execution_price = Decimal("1005.00")
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC) - timedelta(seconds=90)  # Lagged
        symbol = "RELIANCE"

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
        )

        # Should fail due to stale execution price
        assert result.passed is False
        assert "timestamp drift too high" in result.reason

    def test_symbol_suffix_mismatch_scenario(self) -> None:
        """Test scenario with symbol suffix variations."""
        # Scenario: Scanner uses RELIANCE-EQ, execution uses RELIANCE
        scanner_price = Decimal("2500.00")
        execution_price = Decimal("2525.00")
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30)
        execution_ts = datetime.now(UTC)
        symbol = "RELIANCE-EQ"  # Scanner suffix

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
        )

        # Should pass - symbol normalization handles suffix
        assert result.passed is True

    def test_weekend_gap_scenario(self) -> None:
        """Test scenario with weekend price gap."""
        # Scenario: Trading on Monday, scanner from Friday
        scanner_price = Decimal("1000.00")
        execution_price = Decimal("1015.00")  # 1.5% gap
        scanner_ts = datetime.now(UTC).replace(hour=15, minute=30) - timedelta(days=3)  # Friday
        execution_ts = datetime.now(UTC)  # Monday
        symbol = "WIPRO"
        prev_close = Decimal("1000.00")

        result = validate_with_price_reconciliation(
            scanner_price=scanner_price,
            execution_price=execution_price,
            scanner_timestamp=scanner_ts,
            execution_timestamp=execution_ts,
            symbol=symbol,
            prev_close_price=prev_close,
        )

        # Should fail - scanner data too old (>1 day)
        assert result.passed is False
        assert "too old" in result.reason
