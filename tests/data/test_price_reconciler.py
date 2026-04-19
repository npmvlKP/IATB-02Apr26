"""
Comprehensive tests for price reconciliation module.

Tests cover:
- Happy path: Normal price reconciliation within thresholds
- Edge cases: Symbol mapping, timestamp alignment, price deviations
- Error cases: Invalid inputs, large deviations, stale data
- Corporate action detection: Splits, bonuses, dividends
- Type handling: Decimal precision, timezone validation
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.data.price_reconciler import (
    PriceDataPoint,
    PriceReconciler,
    ReconciliationConfig,
)


class TestReconciliationConfig:
    """Test ReconciliationConfig initialization and validation."""

    def test_valid_config_defaults(self) -> None:
        """Test that default config is valid."""
        config = ReconciliationConfig()
        assert config.max_price_deviation_pct == Decimal("0.02")
        assert config.max_timestamp_drift_seconds == 60
        assert config.strict_eod_alignment is True
        assert config.detect_corporate_actions is True
        assert config.validate_symbol_mapping is True
        assert config.max_price_jump_pct == Decimal("0.20")

    def test_valid_config_custom(self) -> None:
        """Test custom valid configuration."""
        config = ReconciliationConfig(
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

    def test_invalid_config_zero_deviation(self) -> None:
        """Test that zero max_price_deviation_pct raises error."""
        with pytest.raises(ConfigError, match="max_price_deviation_pct must be positive"):
            ReconciliationConfig(max_price_deviation_pct=Decimal("0"))

    def test_invalid_config_negative_deviation(self) -> None:
        """Test that negative max_price_deviation_pct raises error."""
        with pytest.raises(ConfigError, match="max_price_deviation_pct must be positive"):
            ReconciliationConfig(max_price_deviation_pct=Decimal("-0.01"))

    def test_invalid_config_zero_drift(self) -> None:
        """Test that zero max_timestamp_drift_seconds raises error."""
        with pytest.raises(ConfigError, match="max_timestamp_drift_seconds must be positive"):
            ReconciliationConfig(max_timestamp_drift_seconds=0)

    def test_invalid_config_negative_drift(self) -> None:
        """Test that negative max_timestamp_drift_seconds raises error."""
        with pytest.raises(ConfigError, match="max_timestamp_drift_seconds must be positive"):
            ReconciliationConfig(max_timestamp_drift_seconds=-10)

    def test_invalid_config_zero_jump(self) -> None:
        """Test that zero max_price_jump_pct raises error."""
        with pytest.raises(ConfigError, match="max_price_jump_pct must be positive"):
            ReconciliationConfig(max_price_jump_pct=Decimal("0"))


class TestPriceDataPoint:
    """Test PriceDataPoint initialization and validation."""

    def test_valid_price_data_point(self) -> None:
        """Test valid PriceDataPoint creation."""
        now = datetime.now(UTC)
        point = PriceDataPoint(
            price=Decimal("100.50"),
            timestamp=now,
            source="jugaad",
            symbol="RELIANCE",
            data_type="day",
        )
        assert point.price == Decimal("100.50")
        assert point.timestamp == now
        assert point.source == "jugaad"
        assert point.symbol == "RELIANCE"
        assert point.data_type == "day"

    def test_invalid_price_data_point_non_utc_timestamp(self) -> None:
        """Test that non-UTC timestamp raises error."""
        # Create naive datetime (intentionally for this test)
        naive_dt = datetime(2026, 4, 19, 12, 0, 0, tzinfo=None)  # noqa: DTZ001
        with pytest.raises(ConfigError, match="timestamp must be UTC-aware"):
            PriceDataPoint(
                price=Decimal("100.50"),
                timestamp=naive_dt,
                source="jugaad",
                symbol="RELIANCE",
                data_type="day",
            )


class TestPriceReconciler:
    """Test PriceReconciler main functionality."""

    @pytest.fixture
    def config(self) -> ReconciliationConfig:
        """Default config for testing."""
        return ReconciliationConfig(
            max_price_deviation_pct=Decimal("0.02"),
            max_timestamp_drift_seconds=60,
            strict_eod_alignment=True,
            detect_corporate_actions=True,
            validate_symbol_mapping=True,
            max_price_jump_pct=Decimal("0.20"),
        )

    @pytest.fixture
    def scanner_price(self) -> PriceDataPoint:
        """Scanner price point (EOD data)."""
        return PriceDataPoint(
            price=Decimal("1000.00"),
            timestamp=datetime.now(UTC).replace(hour=15, minute=30, second=0, microsecond=0),
            source="jugaad",
            symbol="RELIANCE",
            data_type="day",
        )

    @pytest.fixture
    def execution_price(self) -> PriceDataPoint:
        """Execution price point (real-time tick)."""
        return PriceDataPoint(
            price=Decimal("1010.00"),  # 1% deviation from scanner
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

    def test_reconcile_prices_happy_path(self, config, scanner_price, execution_price) -> None:
        """Test successful reconciliation with prices within threshold."""
        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_price, execution_price)

        assert result.passed is True
        assert result.deviation_pct == Decimal("0.01")  # 1% deviation
        assert result.severity == "info"

    def test_reconcile_prices_high_deviation(self, config, scanner_price) -> None:
        """Test reconciliation fails when deviation exceeds threshold."""
        # Create execution price with 5% deviation (exceeds 2% threshold)
        high_dev_price = PriceDataPoint(
            price=Decimal("1050.00"),  # 5% deviation
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_price, high_dev_price)

        assert result.passed is False
        assert result.deviation_pct == Decimal("0.05")
        # 5% deviation is at the threshold for "critical" (>= 5%)
        assert result.severity == "critical"
        assert "exceeds max" in result.reason

    def test_reconcile_prices_symbol_mismatch(self, config, scanner_price, execution_price) -> None:
        """Test reconciliation fails with symbol mismatch."""
        # Change execution symbol
        wrong_symbol_price = PriceDataPoint(
            price=Decimal("1010.00"),
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="TCS",  # Different symbol
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_price, wrong_symbol_price)

        assert result.passed is False
        assert result.severity == "critical"
        assert "Symbol mismatch" in result.reason

    def test_reconcile_prices_symbol_mapping_normalization(self, config, scanner_price) -> None:
        """Test that symbol mapping normalization works (RELIANCE vs RELIANCE-EQ)."""
        # Scanner uses RELIANCE-EQ, execution uses RELIANCE
        scanner_with_suffix = PriceDataPoint(
            price=Decimal("1000.00"),
            timestamp=datetime.now(UTC).replace(hour=15, minute=30),
            source="jugaad",
            symbol="RELIANCE-EQ",  # With suffix
            data_type="day",
        )

        execution_price = PriceDataPoint(
            price=Decimal("1010.00"),
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",  # Without suffix
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_with_suffix, execution_price)

        # Should pass because symbols normalize to same value
        assert result.passed is True

    def test_reconcile_prices_stale_execution_price(self, config, scanner_price) -> None:
        """Test reconciliation fails with stale execution price."""
        # Create execution price 2 minutes old (exceeds 60s threshold)
        stale_price = PriceDataPoint(
            price=Decimal("1010.00"),
            timestamp=datetime.now(UTC) - timedelta(minutes=2),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_price, stale_price)

        assert result.passed is False
        assert result.severity == "error"
        assert "timestamp drift too high" in result.reason

    def test_reconcile_prices_old_scanner_eod(self, config) -> None:
        """Test reconciliation fails when scanner EOD is too old (>1 day)."""
        old_scanner = PriceDataPoint(
            price=Decimal("1000.00"),
            timestamp=datetime.now(UTC) - timedelta(days=2),  # 2 days old
            source="jugaad",
            symbol="RELIANCE",
            data_type="day",
        )

        execution_price = PriceDataPoint(
            price=Decimal("1010.00"),
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(old_scanner, execution_price)

        assert result.passed is False
        assert result.severity == "error"
        assert "too old" in result.reason

    def test_reconcile_prices_zero_price(self, config, scanner_price, execution_price) -> None:
        """Test reconciliation fails with zero price."""
        zero_price = PriceDataPoint(
            price=Decimal("0"),
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_price, zero_price)

        assert result.passed is False
        assert result.severity == "critical"
        assert "Invalid price" in result.reason

    def test_reconcile_prices_negative_price(self, config, scanner_price, execution_price) -> None:
        """Test reconciliation fails with negative price."""
        negative_price = PriceDataPoint(
            price=Decimal("-10.00"),
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_price, negative_price)

        assert result.passed is False
        assert result.severity == "critical"
        assert "Invalid price" in result.reason

    def test_reconcile_prices_corporate_action_split(self, config) -> None:
        """Test corporate action detection for stock split."""
        # Scanner shows previous day's close (before split)
        scanner_price = PriceDataPoint(
            price=Decimal("2000.00"),  # Pre-split price
            timestamp=datetime.now(UTC).replace(hour=15, minute=30),
            source="jugaad",
            symbol="RELIANCE",
            data_type="day",
        )

        # Execution shows post-split price (50% drop due to 2:1 split)
        execution_price = PriceDataPoint(
            price=Decimal("1000.00"),  # Post-split price
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        # Previous close matches scanner price
        prev_close = Decimal("2000.00")

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(
            scanner_price,
            execution_price,
            prev_close_price=prev_close,
        )

        # Should detect corporate action and pass (with warning)
        assert result.passed is True
        assert result.severity == "warning"
        assert "Corporate action detected" in result.reason
        assert "DOWN" in result.reason  # Price moved down

    def test_reconcile_prices_corporate_action_bonus(self, config) -> None:
        """Test corporate action detection for bonus issue (25% drop)."""
        # Scanner shows previous day's close
        scanner_price = PriceDataPoint(
            price=Decimal("1000.00"),
            timestamp=datetime.now(UTC).replace(hour=15, minute=30),
            source="jugaad",
            symbol="RELIANCE",
            data_type="day",
        )

        # Execution shows adjusted price (25% drop - above 20% CA threshold)
        execution_price = PriceDataPoint(
            price=Decimal("750.00"),  # 25% adjusted price
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        # Previous close matches scanner price
        prev_close = Decimal("1000.00")

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(
            scanner_price,
            execution_price,
            prev_close_price=prev_close,
        )

        # Should detect corporate action and pass (with warning)
        assert result.passed is True
        assert result.severity == "warning"
        assert "Corporate action detected" in result.reason

    def test_reconcile_prices_market_movement_not_ca(self, config) -> None:
        """Test that normal market movement within threshold passes."""
        # Both prices show similar deviation from prev_close (market movement)
        scanner_price = PriceDataPoint(
            price=Decimal("1050.00"),  # 5% up from prev_close
            timestamp=datetime.now(UTC).replace(hour=15, minute=30),
            source="jugaad",
            symbol="RELIANCE",
            data_type="day",
        )

        execution_price = PriceDataPoint(
            price=Decimal("1060.00"),  # Similar deviation (0.95% from scanner)
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        prev_close = Decimal("1000.00")

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(
            scanner_price,
            execution_price,
            prev_close_price=prev_close,
        )

        # Should pass as prices are within 2% threshold
        assert result.passed is True
        assert "within threshold" in result.reason.lower()

    def test_reconcile_prices_inconclusive_ca_status(self, config) -> None:
        """Test when price deviation exceeds threshold before CA detection can conclude."""
        # Scanner price close to prev_close
        scanner_price = PriceDataPoint(
            price=Decimal("1005.00"),  # Close to prev_close
            timestamp=datetime.now(UTC).replace(hour=15, minute=30),
            source="jugaad",
            symbol="RELIANCE",
            data_type="day",
        )

        # Execution price shows large jump (9.45% deviation, >5% threshold for critical)
        # This is so high that it fails price check before CA detection can complete
        execution_price = PriceDataPoint(
            price=Decimal("1100.00"),  # 9.45% jump from scanner
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        prev_close = Decimal("1000.00")

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(
            scanner_price,
            execution_price,
            prev_close_price=prev_close,
        )

        # Should fail - price deviation too high for CA detection to conclude
        assert result.passed is False
        # 9.45% deviation is >=5%, so severity is "critical"
        assert result.severity == "critical"
        # The high deviation fails the price check before reaching CA detection
        assert "exceeds max" in result.reason

    def test_reconcile_prices_disable_symbol_validation(self, config, scanner_price) -> None:
        """Test reconciliation with symbol validation disabled."""
        # Disable symbol validation
        config_disabled = ReconciliationConfig(
            validate_symbol_mapping=False,
            max_price_deviation_pct=Decimal("0.02"),
        )

        # Create wrong symbol
        wrong_symbol_price = PriceDataPoint(
            price=Decimal("1010.00"),
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="TCS",  # Different symbol
            data_type="tick",
        )

        reconciler = PriceReconciler(config_disabled)
        result = reconciler.reconcile_prices(scanner_price, wrong_symbol_price)

        # Should pass price check (symbol validation disabled)
        assert result.passed is True

    def test_reconcile_prices_disable_strict_eod_alignment(self, config) -> None:
        """Test reconciliation with strict EOD alignment disabled."""
        # Disable strict EOD alignment
        config_disabled = ReconciliationConfig(
            strict_eod_alignment=False,
            max_price_deviation_pct=Decimal("0.02"),
        )

        # Create old scanner price (would normally fail)
        old_scanner = PriceDataPoint(
            price=Decimal("1000.00"),
            timestamp=datetime.now(UTC) - timedelta(days=2),
            source="jugaad",
            symbol="RELIANCE",
            data_type="day",
        )

        execution_price = PriceDataPoint(
            price=Decimal("1010.00"),
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        reconciler = PriceReconciler(config_disabled)
        result = reconciler.reconcile_prices(old_scanner, execution_price)

        # Should pass price check (EOD alignment disabled)
        assert result.passed is True

    def test_reconcile_prices_without_prev_close(
        self, config, scanner_price, execution_price
    ) -> None:
        """Test reconciliation without previous close price."""
        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(
            scanner_price,
            execution_price,
            prev_close_price=None,  # No prev_close
        )

        # Should still perform basic checks without CA detection
        assert result.passed is True

    def test_reconcile_prices_disable_ca_detection(self, config, scanner_price) -> None:
        """Test reconciliation with CA detection disabled."""
        # Disable CA detection
        config_disabled = ReconciliationConfig(
            detect_corporate_actions=False,
            max_price_deviation_pct=Decimal("0.02"),
        )

        # Create high deviation price (would normally trigger CA check)
        high_dev_price = PriceDataPoint(
            price=Decimal("1200.00"),  # 20% deviation
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        prev_close = Decimal("1000.00")

        reconciler = PriceReconciler(config_disabled)
        result = reconciler.reconcile_prices(
            scanner_price,
            high_dev_price,
            prev_close_price=prev_close,
        )

        # Should fail without attempting CA detection
        assert result.passed is False
        assert result.severity == "critical"


class TestReconcilerEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def config(self) -> ReconciliationConfig:
        """Default config for testing."""
        return ReconciliationConfig()

    def test_exact_threshold_deviation(self, config) -> None:
        """Test behavior at exact deviation threshold (2%)."""
        scanner_price = PriceDataPoint(
            price=Decimal("1000.00"),
            timestamp=datetime.now(UTC).replace(hour=15, minute=30),
            source="jugaad",
            symbol="RELIANCE",
            data_type="day",
        )

        # Exactly 2% deviation
        execution_price = PriceDataPoint(
            price=Decimal("1020.00"),  # 2% deviation
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_price, execution_price)

        # Should pass (exactly at threshold)
        assert result.passed is True

    def test_just_above_threshold_deviation(self, config) -> None:
        """Test behavior just above deviation threshold (2.01%)."""
        scanner_price = PriceDataPoint(
            price=Decimal("1000.00"),
            timestamp=datetime.now(UTC).replace(hour=15, minute=30),
            source="jugaad",
            symbol="RELIANCE",
            data_type="day",
        )

        # Just above 2% deviation
        execution_price = PriceDataPoint(
            price=Decimal("1020.10"),  # 2.01% deviation
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_price, execution_price)

        # Should fail (above threshold)
        assert result.passed is False

    def test_exact_timestamp_drift(self, config) -> None:
        """Test behavior at exact timestamp drift threshold (60s)."""
        scanner_price = PriceDataPoint(
            price=Decimal("1000.00"),
            timestamp=datetime.now(UTC).replace(hour=15, minute=30),
            source="jugaad",
            symbol="RELIANCE",
            data_type="day",
        )

        # Exactly 60 seconds old
        execution_price = PriceDataPoint(
            price=Decimal("1010.00"),
            timestamp=datetime.now(UTC) - timedelta(seconds=60),
            source="kite",
            symbol="RELIANCE",
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_price, execution_price)

        # Should pass (exactly at threshold)
        assert result.passed is True

    def test_symbol_case_normalization(self, config) -> None:
        """Test that symbol case is normalized."""
        scanner_price = PriceDataPoint(
            price=Decimal("1000.00"),
            timestamp=datetime.now(UTC).replace(hour=15, minute=30),
            source="jugaad",
            symbol="reliance",  # lowercase
            data_type="day",
        )

        execution_price = PriceDataPoint(
            price=Decimal("1010.00"),
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",  # uppercase
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_price, execution_price)

        # Should pass (case normalized)
        assert result.passed is True

    def test_symbol_whitespace_normalization(self, config) -> None:
        """Test that symbol whitespace is normalized."""
        scanner_price = PriceDataPoint(
            price=Decimal("1000.00"),
            timestamp=datetime.now(UTC).replace(hour=15, minute=30),
            source="jugaad",
            symbol="  RELIANCE  ",  # with whitespace
            data_type="day",
        )

        execution_price = PriceDataPoint(
            price=Decimal("1010.00"),
            timestamp=datetime.now(UTC),
            source="kite",
            symbol="RELIANCE",  # no whitespace
            data_type="tick",
        )

        reconciler = PriceReconciler(config)
        result = reconciler.reconcile_prices(scanner_price, execution_price)

        # Should pass (whitespace stripped)
        assert result.passed is True
