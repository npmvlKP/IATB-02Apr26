"""Comprehensive coverage tests for iatb.risk.risk_report."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.portfolio_risk import PortfolioRiskSnapshot
from iatb.risk.risk_report import (
    DailyRiskMetrics,
    NotificationChannel,
    PositionData,
    ReportConfig,
    ReportFormat,
    RiskMetricsInputs,
    RiskReportGenerator,
    _build_daily_risk_snapshot,
    _create_daily_risk_metrics_obj,
    _create_validated_risk_metrics,
    _format_positions,
    _get_risk_alert,
    _validate_config,
    _validate_metrics,
    _validate_risk_metrics_inputs,
    create_daily_risk_metrics,
)

_NOW = datetime(2026, 5, 25, 10, 0, tzinfo=UTC)


def _make_snapshot(**overrides: object) -> PortfolioRiskSnapshot:
    defaults = {
        "var_95": Decimal("0.05"),
        "cvar_95": Decimal("0.07"),
        "max_drawdown": Decimal("0.05"),
        "drawdown_breached": False,
    }
    defaults.update(overrides)
    return PortfolioRiskSnapshot(**defaults)


def _make_metrics(**overrides: object) -> DailyRiskMetrics:
    snap = _make_snapshot()
    defaults = {
        "date": _NOW,
        "daily_pnl": Decimal("1000"),
        "daily_return": Decimal("0.01"),
        "var_95": Decimal("0.05"),
        "cvar_95": Decimal("0.07"),
        "max_drawdown": Decimal("0.05"),
        "total_exposure": Decimal("500000"),
        "net_liquidation_value": Decimal("1000000"),
        "positions": [],
        "risk_snapshot": snap,
    }
    defaults.update(overrides)
    return DailyRiskMetrics(**defaults)


class TestReportFormat:
    def test_values(self) -> None:
        assert ReportFormat.PDF.value == "pdf"
        assert ReportFormat.HTML.value == "html"


class TestNotificationChannel:
    def test_values(self) -> None:
        assert NotificationChannel.EMAIL.value == "email"
        assert NotificationChannel.TELEGRAM.value == "telegram"
        assert NotificationChannel.NONE.value == "none"


class TestPositionData:
    def test_fields(self) -> None:
        pd = PositionData(
            symbol="RELIANCE",
            quantity=Decimal("10"),
            entry_price=Decimal("2500"),
            current_price=Decimal("2550"),
            unrealized_pnl=Decimal("500"),
            exposure=Decimal("25500"),
        )
        assert pd.symbol == "RELIANCE"

    def test_frozen(self) -> None:
        pd = PositionData(
            symbol="RELIANCE",
            quantity=Decimal("10"),
            entry_price=Decimal("2500"),
            current_price=Decimal("2550"),
            unrealized_pnl=Decimal("500"),
            exposure=Decimal("25500"),
        )
        with pytest.raises(AttributeError):
            pd.symbol = "TCS"


class TestReportConfig:
    def test_valid_config(self, tmp_path: Path) -> None:
        cfg = ReportConfig(output_dir=tmp_path)
        assert cfg.output_dir == tmp_path

    def test_zero_drawdown_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="positive"):
            ReportConfig(output_dir=tmp_path, max_allowed_drawdown=Decimal("0"))

    def test_negative_drawdown_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="positive"):
            ReportConfig(output_dir=tmp_path, max_allowed_drawdown=Decimal("-0.1"))

    def test_zero_confidence_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            ReportConfig(output_dir=tmp_path, confidence_level=Decimal("0"))

    def test_one_confidence_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            ReportConfig(output_dir=tmp_path, confidence_level=Decimal("1"))

    def test_email_without_recipients_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="Email recipients"):
            ReportConfig(
                output_dir=tmp_path,
                notification_channel=NotificationChannel.EMAIL,
                email_recipients=[],
            )

    def test_telegram_without_chat_id_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="Telegram"):
            ReportConfig(
                output_dir=tmp_path,
                notification_channel=NotificationChannel.TELEGRAM,
                telegram_chat_id=None,
            )

    def test_telegram_with_chat_id(self, tmp_path: Path) -> None:
        cfg = ReportConfig(
            output_dir=tmp_path,
            notification_channel=NotificationChannel.TELEGRAM,
            telegram_chat_id="chat123",
        )
        assert cfg.telegram_chat_id == "chat123"


class TestValidateConfig:
    def test_valid_passes(self, tmp_path: Path) -> None:
        cfg = ReportConfig(output_dir=tmp_path)
        _validate_config(cfg)

    def test_zero_drawdown_raises(self, tmp_path: Path) -> None:
        cfg = ReportConfig(output_dir=tmp_path)
        object.__setattr__(cfg, "max_allowed_drawdown", Decimal("0"))
        with pytest.raises(ConfigError, match="positive"):
            _validate_config(cfg)

    def test_zero_confidence_raises(self, tmp_path: Path) -> None:
        cfg = ReportConfig(output_dir=tmp_path)
        object.__setattr__(cfg, "confidence_level", Decimal("0"))
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_config(cfg)

    def test_one_confidence_raises(self, tmp_path: Path) -> None:
        cfg = ReportConfig(output_dir=tmp_path)
        object.__setattr__(cfg, "confidence_level", Decimal("1"))
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_config(cfg)

    def test_email_without_recipients_raises(self, tmp_path: Path) -> None:
        cfg = ReportConfig(output_dir=tmp_path)
        object.__setattr__(cfg, "notification_channel", NotificationChannel.EMAIL)
        object.__setattr__(cfg, "email_recipients", [])
        with pytest.raises(ConfigError, match="Email recipients"):
            _validate_config(cfg)

    def test_telegram_without_chat_id_raises(self, tmp_path: Path) -> None:
        cfg = ReportConfig(output_dir=tmp_path)
        object.__setattr__(cfg, "notification_channel", NotificationChannel.TELEGRAM)
        object.__setattr__(cfg, "telegram_chat_id", None)
        with pytest.raises(ConfigError, match="Telegram chat_id"):
            _validate_config(cfg)


class TestValidateMetrics:
    def test_valid_metrics(self) -> None:
        metrics = _make_metrics()
        _validate_metrics(metrics)

    def test_zero_nlv_raises(self) -> None:
        metrics = _make_metrics(net_liquidation_value=Decimal("0"))
        with pytest.raises(ConfigError, match="positive"):
            _validate_metrics(metrics)

    def test_negative_nlv_raises(self) -> None:
        metrics = _make_metrics(net_liquidation_value=Decimal("-1"))
        with pytest.raises(ConfigError, match="positive"):
            _validate_metrics(metrics)

    def test_negative_exposure_raises(self) -> None:
        metrics = _make_metrics(total_exposure=Decimal("-1"))
        with pytest.raises(ConfigError, match="negative"):
            _validate_metrics(metrics)

    def test_naive_date_raises(self) -> None:
        metrics = _make_metrics(date=datetime(2026, 5, 25, 10, 0))
        with pytest.raises(ConfigError, match="UTC"):
            _validate_metrics(metrics)


class TestValidateRiskMetricsInputs:
    def test_valid_inputs(self) -> None:
        _validate_risk_metrics_inputs(
            _NOW, Decimal("1000"), Decimal("500"), Decimal("0.95")
        )

    def test_naive_date_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            _validate_risk_metrics_inputs(
                datetime(2026, 5, 25), Decimal("1000"), Decimal("500"), Decimal("0.95")
            )

    def test_zero_nlv_raises(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            _validate_risk_metrics_inputs(
                _NOW, Decimal("0"), Decimal("500"), Decimal("0.95")
            )

    def test_negative_exposure_raises(self) -> None:
        with pytest.raises(ConfigError, match="negative"):
            _validate_risk_metrics_inputs(
                _NOW, Decimal("1000"), Decimal("-1"), Decimal("0.95")
            )

    def test_zero_confidence_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_risk_metrics_inputs(
                _NOW, Decimal("1000"), Decimal("500"), Decimal("0")
            )

    def test_one_confidence_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_risk_metrics_inputs(
                _NOW, Decimal("1000"), Decimal("500"), Decimal("1")
            )

    def test_non_utc_timezone_raises(self) -> None:
        ist = timezone(timedelta(hours=5, minutes=30))
        with pytest.raises(ConfigError, match="UTC"):
            _validate_risk_metrics_inputs(
                datetime(2026, 5, 25, 10, 0, tzinfo=ist),
                Decimal("1000"),
                Decimal("500"),
                Decimal("0.95"),
            )


class TestFormatPositions:
    def test_empty_positions(self) -> None:
        result = _format_positions([])
        assert result == []

    def test_single_position(self) -> None:
        pd = PositionData(
            symbol="RELIANCE",
            quantity=Decimal("10"),
            entry_price=Decimal("2500"),
            current_price=Decimal("2550"),
            unrealized_pnl=Decimal("500"),
            exposure=Decimal("25500"),
        )
        result = _format_positions([pd])
        assert len(result) == 1
        assert result[0]["symbol"] == "RELIANCE"
        assert result[0]["quantity"] == 10


class TestGetRiskAlert:
    def test_no_breach(self) -> None:
        metrics = _make_metrics(max_drawdown=Decimal("0.05"))
        alert = _get_risk_alert(metrics, Decimal("0.10"))
        assert alert["level"] == "NORMAL"
        assert alert["is_breached"] is False

    def test_breach(self) -> None:
        metrics = _make_metrics(max_drawdown=Decimal("0.15"))
        alert = _get_risk_alert(metrics, Decimal("0.10"))
        assert alert["level"] == "CRITICAL"
        assert alert["is_breached"] is True

    def test_exact_boundary_not_breached(self) -> None:
        metrics = _make_metrics(max_drawdown=Decimal("0.10"))
        alert = _get_risk_alert(metrics, Decimal("0.10"))
        assert alert["is_breached"] is False


class TestBuildDailyRiskSnapshot:
    def test_builds_snapshot(self) -> None:
        snap = _build_daily_risk_snapshot(
            daily_return=Decimal("0.01"),
            var_95=Decimal("0.05"),
            cvar_95=Decimal("0.07"),
            net_liquidation_value=Decimal("1000000"),
            daily_pnl=Decimal("1000"),
            max_allowed_drawdown=Decimal("0.10"),
        )
        assert isinstance(snap, PortfolioRiskSnapshot)


class TestCreateDailyRiskMetricsObj:
    def test_creates_metrics(self) -> None:
        snap = _make_snapshot()
        metrics = _create_daily_risk_metrics_obj(
            date=_NOW,
            daily_pnl=Decimal("1000"),
            daily_return=Decimal("0.01"),
            var_95=Decimal("0.05"),
            cvar_95=Decimal("0.07"),
            max_drawdown=Decimal("0.05"),
            total_exposure=Decimal("500000"),
            net_liquidation_value=Decimal("1000000"),
            positions=[],
            risk_snapshot=snap,
        )
        assert isinstance(metrics, DailyRiskMetrics)


class TestCreateValidatedRiskMetrics:
    def test_valid_inputs(self) -> None:
        inputs = RiskMetricsInputs(
            date=_NOW,
            daily_pnl=Decimal("1000"),
            daily_return=Decimal("0.01"),
            var_95=Decimal("0.05"),
            cvar_95=Decimal("0.07"),
            max_drawdown=Decimal("0.05"),
            total_exposure=Decimal("500000"),
            net_liquidation_value=Decimal("1000000"),
            positions=[],
            confidence_level=Decimal("0.95"),
            max_allowed_drawdown=Decimal("0.10"),
        )
        result = _create_validated_risk_metrics(inputs)
        assert isinstance(result, DailyRiskMetrics)

    def test_invalid_nlv_raises(self) -> None:
        inputs = RiskMetricsInputs(
            date=_NOW,
            daily_pnl=Decimal("1000"),
            daily_return=Decimal("0.01"),
            var_95=Decimal("0.05"),
            cvar_95=Decimal("0.07"),
            max_drawdown=Decimal("0.05"),
            total_exposure=Decimal("500000"),
            net_liquidation_value=Decimal("0"),
            positions=[],
            confidence_level=Decimal("0.95"),
            max_allowed_drawdown=Decimal("0.10"),
        )
        with pytest.raises(ConfigError):
            _create_validated_risk_metrics(inputs)


class TestCreateDailyRiskMetrics:
    def test_valid(self) -> None:
        result = create_daily_risk_metrics(
            date=_NOW,
            daily_pnl=Decimal("1000"),
            daily_return=Decimal("0.01"),
            var_95=Decimal("0.05"),
            cvar_95=Decimal("0.07"),
            max_drawdown=Decimal("0.05"),
            total_exposure=Decimal("500000"),
            net_liquidation_value=Decimal("1000000"),
            positions=[],
        )
        assert isinstance(result, DailyRiskMetrics)

    def test_invalid_raises(self) -> None:
        with pytest.raises(ConfigError):
            create_daily_risk_metrics(
                date=_NOW,
                daily_pnl=Decimal("1000"),
                daily_return=Decimal("0.01"),
                var_95=Decimal("0.05"),
                cvar_95=Decimal("0.07"),
                max_drawdown=Decimal("0.05"),
                total_exposure=Decimal("500000"),
                net_liquidation_value=Decimal("0"),
                positions=[],
            )


class TestRiskReportGenerator:
    def test_init(self, tmp_path: Path) -> None:
        gen = RiskReportGenerator(ReportConfig(output_dir=tmp_path))
        assert gen._config.output_dir == tmp_path

    def test_generate_report(self, tmp_path: Path) -> None:
        gen = RiskReportGenerator(ReportConfig(output_dir=tmp_path))
        metrics = _make_metrics()
        path = gen.generate_report(metrics)
        assert path.exists()
        assert path.suffix == ".html"

    def test_generate_report_with_custom_template(self, tmp_path: Path) -> None:
        gen = RiskReportGenerator(ReportConfig(output_dir=tmp_path))
        template_path = tmp_path / "custom.html"
        template_path.write_text("Custom: {{ daily_pnl }}", encoding="utf-8")
        metrics = _make_metrics()
        path = gen.generate_report(metrics, template_path=template_path)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Custom:" in content

    def test_generate_report_with_none_template(self, tmp_path: Path) -> None:
        gen = RiskReportGenerator(ReportConfig(output_dir=tmp_path))
        metrics = _make_metrics()
        path = gen.generate_report(metrics, template_path=None)
        assert path.exists()

    def test_invalid_metrics_raises(self, tmp_path: Path) -> None:
        gen = RiskReportGenerator(ReportConfig(output_dir=tmp_path))
        metrics = _make_metrics(net_liquidation_value=Decimal("0"))
        with pytest.raises(ConfigError, match="positive"):
            gen.generate_report(metrics)

    def test_email_notification(self, tmp_path: Path) -> None:
        cfg = ReportConfig(
            output_dir=tmp_path,
            notification_channel=NotificationChannel.EMAIL,
            email_recipients=["test@example.com"],
        )
        gen = RiskReportGenerator(cfg)
        metrics = _make_metrics()
        path = gen.generate_report(metrics)
        assert path.exists()

    def test_telegram_notification(self, tmp_path: Path) -> None:
        cfg = ReportConfig(
            output_dir=tmp_path,
            notification_channel=NotificationChannel.TELEGRAM,
            telegram_chat_id="chat123",
        )
        gen = RiskReportGenerator(cfg)
        metrics = _make_metrics()
        path = gen.generate_report(metrics)
        assert path.exists()

    def test_no_notification(self, tmp_path: Path) -> None:
        gen = RiskReportGenerator(ReportConfig(output_dir=tmp_path))
        metrics = _make_metrics()
        path = gen.generate_report(metrics)
        assert path.exists()
