"""
Comprehensive tests for risk_report module.

Covers:
- Happy path: Normal report generation
- Edge cases: Empty positions, boundary values
- Error paths: Invalid config, invalid metrics
- Type handling: Decimal precision, datetime UTC
- Precision handling: Financial calculations
- Timezone handling: UTC-aware datetimes
"""

import random
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.risk.risk_report import (
    DailyRiskMetrics,
    NotificationChannel,
    PositionData,
    ReportConfig,
    ReportFormat,
    RiskReportGenerator,
    create_daily_risk_metrics,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


@pytest.fixture
def temp_output_dir() -> TemporaryDirectory:
    """Create temporary directory for report output."""
    return TemporaryDirectory()


@pytest.fixture
def sample_positions() -> list[PositionData]:
    """Create sample position data for testing."""
    return [
        PositionData(
            symbol="NIFTY-FUT",
            quantity=Decimal("50"),
            entry_price=Decimal("22500.50"),
            current_price=Decimal("22600.75"),
            unrealized_pnl=Decimal("5012.50"),
            exposure=Decimal("1130037.50"),
        ),
        PositionData(
            symbol="BANKNIFTY-FUT",
            quantity=Decimal("25"),
            entry_price=Decimal("47500.00"),
            current_price=Decimal("47350.00"),
            unrealized_pnl=Decimal("-3750.00"),
            exposure=Decimal("1183750.00"),
        ),
    ]


@pytest.fixture
def sample_metrics(sample_positions: list[PositionData]) -> DailyRiskMetrics:
    """Create sample daily risk metrics for testing."""
    return create_daily_risk_metrics(
        date=datetime.now(UTC),
        daily_pnl=Decimal("1262.50"),
        daily_return=Decimal("0.0005"),
        var_95=Decimal("2500.00"),
        cvar_95=Decimal("3000.00"),
        max_drawdown=Decimal("0.05"),
        total_exposure=Decimal("2313787.50"),
        net_liquidation_value=Decimal("2525000.00"),
        positions=sample_positions,
        confidence_level=Decimal("0.95"),
        max_allowed_drawdown=Decimal("0.10"),
    )


class TestPositionData:
    """Test PositionData dataclass."""

    def test_position_data_creation(self) -> None:
        """Test creating valid position data."""
        position = PositionData(
            symbol="TEST",
            quantity=Decimal("100"),
            entry_price=Decimal("100.00"),
            current_price=Decimal("105.00"),
            unrealized_pnl=Decimal("500.00"),
            exposure=Decimal("10500.00"),
        )
        assert position.symbol == "TEST"
        assert position.quantity == Decimal("100")
        assert position.entry_price == Decimal("100.00")


class TestReportConfig:
    """Test ReportConfig validation."""

    def test_valid_config(self, temp_output_dir: TemporaryDirectory) -> None:
        """Test creating valid report configuration."""
        config = ReportConfig(
            output_dir=Path(temp_output_dir.name),
            report_format=ReportFormat.HTML,
            notification_channel=NotificationChannel.NONE,
        )
        assert config.output_dir == Path(temp_output_dir.name)
        assert config.report_format == ReportFormat.HTML

    def test_config_with_email(self, temp_output_dir: TemporaryDirectory) -> None:
        """Test config with email notification."""
        config = ReportConfig(
            output_dir=Path(temp_output_dir.name),
            notification_channel=NotificationChannel.EMAIL,
            email_recipients=["test@example.com", "admin@example.com"],
        )
        assert len(config.email_recipients) == 2

    def test_config_with_telegram(self, temp_output_dir: TemporaryDirectory) -> None:
        """Test config with Telegram notification."""
        config = ReportConfig(
            output_dir=Path(temp_output_dir.name),
            notification_channel=NotificationChannel.TELEGRAM,
            telegram_chat_id="123456789",
        )
        assert config.telegram_chat_id == "123456789"

    def test_invalid_config_zero_drawdown(self, temp_output_dir: TemporaryDirectory) -> None:
        """Test config validation fails with zero drawdown."""
        with pytest.raises(ConfigError, match="must be positive"):
            ReportConfig(
                output_dir=Path(temp_output_dir.name),
                max_allowed_drawdown=Decimal("0"),
            )

    def test_invalid_config_negative_drawdown(self, temp_output_dir: TemporaryDirectory) -> None:
        """Test config validation fails with negative drawdown."""
        with pytest.raises(ConfigError, match="must be positive"):
            ReportConfig(
                output_dir=Path(temp_output_dir.name),
                max_allowed_drawdown=Decimal("-0.10"),
            )

    def test_invalid_config_confidence_too_low(self, temp_output_dir: TemporaryDirectory) -> None:
        """Test config validation fails with confidence <= 0."""
        with pytest.raises(ConfigError, match="between 0 and 1"):
            ReportConfig(
                output_dir=Path(temp_output_dir.name),
                confidence_level=Decimal("0"),
            )

    def test_invalid_config_confidence_too_high(self, temp_output_dir: TemporaryDirectory) -> None:
        """Test config validation fails with confidence >= 1."""
        with pytest.raises(ConfigError, match="between 0 and 1"):
            ReportConfig(
                output_dir=Path(temp_output_dir.name),
                confidence_level=Decimal("1"),
            )

    def test_invalid_config_email_no_recipients(self, temp_output_dir: TemporaryDirectory) -> None:
        """Test config validation fails with email but no recipients."""
        with pytest.raises(ConfigError, match="Email recipients must be specified"):
            ReportConfig(
                output_dir=Path(temp_output_dir.name),
                notification_channel=NotificationChannel.EMAIL,
                email_recipients=[],
            )

    def test_invalid_config_telegram_no_chat_id(self, temp_output_dir: TemporaryDirectory) -> None:
        """Test config validation fails with Telegram but no chat_id."""
        with pytest.raises(ConfigError, match="Telegram chat_id must be specified"):
            ReportConfig(
                output_dir=Path(temp_output_dir.name),
                notification_channel=NotificationChannel.TELEGRAM,
                telegram_chat_id=None,
            )


class TestCreateDailyRiskMetrics:
    """Test create_daily_risk_metrics function."""

    def test_valid_metrics_creation(self, sample_positions: list[PositionData]) -> None:
        """Test creating valid daily risk metrics."""
        metrics = create_daily_risk_metrics(
            date=datetime.now(UTC),
            daily_pnl=Decimal("1000.00"),
            daily_return=Decimal("0.01"),
            var_95=Decimal("500.00"),
            cvar_95=Decimal("600.00"),
            max_drawdown=Decimal("0.05"),
            total_exposure=Decimal("100000.00"),
            net_liquidation_value=Decimal("200000.00"),
            positions=sample_positions,
        )
        assert metrics.daily_pnl == Decimal("1000.00")
        assert metrics.daily_return == Decimal("0.01")
        assert len(metrics.positions) == 2

    def test_invalid_metrics_naive_datetime(self, sample_positions: list[PositionData]) -> None:
        """Test metrics validation fails with naive datetime."""
        # noqa: DTZ005 - Intentionally using naive datetime for validation test
        naive_datetime = datetime.now()
        with pytest.raises(ConfigError, match="must be UTC-aware"):
            create_daily_risk_metrics(
                date=naive_datetime,
                daily_pnl=Decimal("1000.00"),
                daily_return=Decimal("0.01"),
                var_95=Decimal("500.00"),
                cvar_95=Decimal("600.00"),
                max_drawdown=Decimal("0.05"),
                total_exposure=Decimal("100000.00"),
                net_liquidation_value=Decimal("200000.00"),
                positions=sample_positions,
            )

    def test_invalid_metrics_wrong_timezone(self, sample_positions: list[PositionData]) -> None:
        """Test metrics validation fails with non-UTC timezone."""
        wrong_tz_datetime = datetime.now(tz=timezone(timedelta(hours=5, minutes=30)))
        with pytest.raises(ConfigError, match="must be UTC-aware"):
            create_daily_risk_metrics(
                date=wrong_tz_datetime,
                daily_pnl=Decimal("1000.00"),
                daily_return=Decimal("0.01"),
                var_95=Decimal("500.00"),
                cvar_95=Decimal("600.00"),
                max_drawdown=Decimal("0.05"),
                total_exposure=Decimal("100000.00"),
                net_liquidation_value=Decimal("200000.00"),
                positions=sample_positions,
            )

    def test_invalid_metrics_negative_liquidation(
        self,
        sample_positions: list[PositionData],
    ) -> None:
        """Test metrics validation fails with negative liquidation value."""
        with pytest.raises(ConfigError, match="must be positive"):
            create_daily_risk_metrics(
                date=datetime.now(UTC),
                daily_pnl=Decimal("1000.00"),
                daily_return=Decimal("0.01"),
                var_95=Decimal("500.00"),
                cvar_95=Decimal("600.00"),
                max_drawdown=Decimal("0.05"),
                total_exposure=Decimal("100000.00"),
                net_liquidation_value=Decimal("-100.00"),
                positions=sample_positions,
            )

    def test_invalid_metrics_zero_liquidation(
        self,
        sample_positions: list[PositionData],
    ) -> None:
        """Test metrics validation fails with zero liquidation value."""
        with pytest.raises(ConfigError, match="must be positive"):
            create_daily_risk_metrics(
                date=datetime.now(UTC),
                daily_pnl=Decimal("1000.00"),
                daily_return=Decimal("0.01"),
                var_95=Decimal("500.00"),
                cvar_95=Decimal("600.00"),
                max_drawdown=Decimal("0.05"),
                total_exposure=Decimal("100000.00"),
                net_liquidation_value=Decimal("0"),
                positions=sample_positions,
            )

    def test_invalid_metrics_negative_exposure(
        self,
        sample_positions: list[PositionData],
    ) -> None:
        """Test metrics validation fails with negative exposure."""
        with pytest.raises(ConfigError, match="cannot be negative"):
            create_daily_risk_metrics(
                date=datetime.now(UTC),
                daily_pnl=Decimal("1000.00"),
                daily_return=Decimal("0.01"),
                var_95=Decimal("500.00"),
                cvar_95=Decimal("600.00"),
                max_drawdown=Decimal("0.05"),
                total_exposure=Decimal("-1000.00"),
                net_liquidation_value=Decimal("200000.00"),
                positions=sample_positions,
            )

    def test_metrics_with_empty_positions(self) -> None:
        """Test creating metrics with empty position list."""
        metrics = create_daily_risk_metrics(
            date=datetime.now(UTC),
            daily_pnl=Decimal("1000.00"),
            daily_return=Decimal("0.01"),
            var_95=Decimal("500.00"),
            cvar_95=Decimal("600.00"),
            max_drawdown=Decimal("0.05"),
            total_exposure=Decimal("0"),
            net_liquidation_value=Decimal("200000.00"),
            positions=[],
        )
        assert len(metrics.positions) == 0


class TestRiskReportGenerator:
    """Test RiskReportGenerator class."""

    def test_generator_initialization(self, temp_output_dir: TemporaryDirectory) -> None:
        """Test initializing report generator."""
        config = ReportConfig(output_dir=Path(temp_output_dir.name))
        generator = RiskReportGenerator(config)
        assert generator._output_dir == Path(temp_output_dir.name)

    def test_generate_html_report(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_metrics: DailyRiskMetrics,
    ) -> None:
        """Test generating HTML report."""
        config = ReportConfig(output_dir=Path(temp_output_dir.name))
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(sample_metrics)

        assert report_path.exists()
        assert report_path.suffix == ".html"
        content = report_path.read_text(encoding="utf-8")
        assert "Risk Disclosure Report" in content
        assert "NIFTY-FUT" in content
        assert "BANKNIFTY-FUT" in content

    def test_generate_report_with_custom_template(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_metrics: DailyRiskMetrics,
    ) -> None:
        """Test generating report with custom template."""
        template_path = Path(temp_output_dir.name) / "custom_template.html"
        template_path.write_text(
            "<html><body>Custom: {{ daily_pnl }}</body></html>",
            encoding="utf-8",
        )

        config = ReportConfig(output_dir=Path(temp_output_dir.name))
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(sample_metrics, template_path)

        content = report_path.read_text(encoding="utf-8")
        assert "Custom:" in content
        assert "1262.50" in content

    def test_generate_report_creates_directory(
        self,
        sample_metrics: DailyRiskMetrics,
    ) -> None:
        """Test that generator creates output directory if it doesn't exist."""
        with TemporaryDirectory() as temp_dir:
            nested_dir = Path(temp_dir) / "reports" / "daily"
            config = ReportConfig(output_dir=nested_dir)
            generator = RiskReportGenerator(config)
            report_path = generator.generate_report(sample_metrics)

            assert nested_dir.exists()
            assert report_path.exists()

    def test_report_filename_format(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_metrics: DailyRiskMetrics,
    ) -> None:
        """Test that report filename follows expected format."""
        config = ReportConfig(output_dir=Path(temp_output_dir.name))
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(sample_metrics)

        date_str = sample_metrics.date.strftime("%Y%m%d")
        expected_filename = f"risk_report_{date_str}.html"
        assert report_path.name == expected_filename

    def test_report_contains_all_metrics(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_metrics: DailyRiskMetrics,
    ) -> None:
        """Test that generated report contains all risk metrics."""
        config = ReportConfig(output_dir=Path(temp_output_dir.name))
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(sample_metrics)
        content = report_path.read_text(encoding="utf-8")

        assert "1262.50" in content  # daily_pnl
        assert "0.05%" in content  # daily_return
        assert "2500.00" in content  # var_95
        assert "3000.00" in content  # cvar_95
        assert "5.00%" in content  # max_drawdown
        assert "2313787.50" in content  # total_exposure
        assert "2525000.00" in content  # net_liquidation_value

    def test_report_with_no_notification(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_metrics: DailyRiskMetrics,
    ) -> None:
        """Test report generation with no notification channel."""
        config = ReportConfig(
            output_dir=Path(temp_output_dir.name),
            notification_channel=NotificationChannel.NONE,
        )
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(sample_metrics)

        assert report_path.exists()

    def test_report_with_email_notification(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_metrics: DailyRiskMetrics,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test report generation with email notification stub."""
        config = ReportConfig(
            output_dir=Path(temp_output_dir.name),
            notification_channel=NotificationChannel.EMAIL,
            email_recipients=["test@example.com"],
        )
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(sample_metrics)

        assert report_path.exists()
        assert any("Email notification would be sent" in message for message in caplog.messages)

    def test_report_with_telegram_notification(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_metrics: DailyRiskMetrics,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test report generation with Telegram notification stub."""
        config = ReportConfig(
            output_dir=Path(temp_output_dir.name),
            notification_channel=NotificationChannel.TELEGRAM,
            telegram_chat_id="123456789",
        )
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(sample_metrics)

        assert report_path.exists()
        assert any("Telegram notification would be sent" in message for message in caplog.messages)

    def test_report_contains_risk_alert_normal(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_metrics: DailyRiskMetrics,
    ) -> None:
        """Test report contains normal risk alert when drawdown is within limits."""
        config = ReportConfig(
            output_dir=Path(temp_output_dir.name),
            max_allowed_drawdown=Decimal("0.10"),
        )
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(sample_metrics)
        content = report_path.read_text(encoding="utf-8")

        assert "NORMAL" in content
        assert "Risk levels within acceptable limits" in content

    def test_report_contains_risk_alert_critical(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_positions: list[PositionData],
    ) -> None:
        """Test report contains critical alert when drawdown exceeds limits."""
        metrics = create_daily_risk_metrics(
            date=datetime.now(UTC),
            daily_pnl=Decimal("-50000.00"),
            daily_return=Decimal("-0.05"),
            var_95=Decimal("6000.00"),
            cvar_95=Decimal("7000.00"),
            max_drawdown=Decimal("0.15"),  # Exceeds 0.10 threshold
            total_exposure=Decimal("2313787.50"),
            net_liquidation_value=Decimal("2525000.00"),
            positions=sample_positions,
            max_allowed_drawdown=Decimal("0.10"),
        )

        config = ReportConfig(
            output_dir=Path(temp_output_dir.name),
            max_allowed_drawdown=Decimal("0.10"),
        )
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(metrics)
        content = report_path.read_text(encoding="utf-8")

        assert "CRITICAL" in content
        assert "Drawdown breach detected" in content
        assert "15.00%" in content
        assert "exceeds 10.00%" in content

    def test_report_position_table_content(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_metrics: DailyRiskMetrics,
    ) -> None:
        """Test report position table contains correct data."""
        config = ReportConfig(output_dir=Path(temp_output_dir.name))
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(sample_metrics)
        content = report_path.read_text(encoding="utf-8")

        # Check position data is present
        assert "NIFTY-FUT" in content
        assert "50" in content  # quantity
        assert "22500.50" in content  # entry_price
        assert "22600.75" in content  # current_price
        assert "5012.50" in content  # unrealized_pnl
        assert "BANKNIFTY-FUT" in content
        assert "25" in content  # quantity
        assert "-3750.00" in content  # unrealized_pnl

    def test_report_html_structure(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_metrics: DailyRiskMetrics,
    ) -> None:
        """Test report has proper HTML structure."""
        config = ReportConfig(output_dir=Path(temp_output_dir.name))
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(sample_metrics)
        content = report_path.read_text(encoding="utf-8")

        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content
        assert "<head>" in content
        assert "</head>" in content
        assert "<body>" in content
        assert "</body>" in content

    def test_decimal_precision_handling(
        self,
        temp_output_dir: TemporaryDirectory,
        sample_positions: list[PositionData],
    ) -> None:
        """Test that decimal precision is preserved in report."""
        metrics = create_daily_risk_metrics(
            date=datetime.now(UTC),
            daily_pnl=Decimal("1234.56789"),
            daily_return=Decimal("0.01234567"),
            var_95=Decimal("5678.90123"),
            cvar_95=Decimal("6789.01234"),
            max_drawdown=Decimal("0.0789"),
            total_exposure=Decimal("1234567.89012"),
            net_liquidation_value=Decimal("2345678.90123"),
            positions=sample_positions,
        )

        config = ReportConfig(output_dir=Path(temp_output_dir.name))
        generator = RiskReportGenerator(config)
        report_path = generator.generate_report(metrics)
        content = report_path.read_text(encoding="utf-8")

        # Check that values are formatted with 2 decimal places
        assert "1234.57" in content
        assert "5678.90" in content
        assert "6789.01" in content
