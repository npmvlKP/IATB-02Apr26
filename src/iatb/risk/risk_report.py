"""
Risk Disclosure Document Generation Module.

Generates daily risk summary reports including:
- Maximum drawdown
- Daily P&L
- Position exposure
- Value at Risk (VaR)

Exports to PDF/HTML and integrates with email/Telegram notifications.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from jinja2 import Template

from iatb.core.exceptions import ConfigError
from iatb.risk.portfolio_risk import (
    PortfolioRiskSnapshot,
    build_risk_snapshot,
)


class ReportFormat(str, Enum):
    """Supported report export formats."""

    PDF = "pdf"
    HTML = "html"


class NotificationChannel(str, Enum):
    """Supported notification channels."""

    EMAIL = "email"
    TELEGRAM = "telegram"
    NONE = "none"


@dataclass(frozen=True)
class PositionData:
    """Single position data for risk reporting."""

    symbol: str
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    exposure: Decimal


@dataclass(frozen=True)
class DailyRiskMetrics:
    """Daily risk metrics for the report."""

    date: datetime
    daily_pnl: Decimal
    daily_return: Decimal
    var_95: Decimal
    cvar_95: Decimal
    max_drawdown: Decimal
    total_exposure: Decimal
    net_liquidation_value: Decimal
    positions: list[PositionData]
    risk_snapshot: PortfolioRiskSnapshot


@dataclass(frozen=True)
class ReportConfig:
    """Configuration for risk report generation."""

    output_dir: Path
    report_format: ReportFormat = ReportFormat.HTML
    notification_channel: NotificationChannel = NotificationChannel.NONE
    email_recipients: list[str] = field(default_factory=list)
    telegram_chat_id: str | None = None
    max_allowed_drawdown: Decimal = Decimal("0.10")
    confidence_level: Decimal = Decimal("0.95")

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.max_allowed_drawdown <= Decimal("0"):
            msg = "Max allowed drawdown must be positive"
            raise ConfigError(msg)

        if self.confidence_level <= Decimal("0") or self.confidence_level >= Decimal("1"):
            msg = "Confidence level must be between 0 and 1"
            raise ConfigError(msg)

        if self.notification_channel == NotificationChannel.EMAIL and not self.email_recipients:
            msg = "Email recipients must be specified when using email notifications"
            raise ConfigError(msg)

        if self.notification_channel == NotificationChannel.TELEGRAM and not self.telegram_chat_id:
            msg = "Telegram chat_id must be specified when using Telegram notifications"
            raise ConfigError(msg)


class RiskReportGenerator:
    """Generates risk disclosure documents with export and notification support."""

    def __init__(self, config: ReportConfig) -> None:
        """Initialize the risk report generator.

        Args:
            config: Configuration for report generation.

        Raises:
            ConfigError: If configuration is invalid.
        """
        _validate_config(config)
        self._config = config
        self._output_dir = Path(config.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(
        self,
        metrics: DailyRiskMetrics,
        template_path: Path | None = None,
    ) -> Path:
        """Generate a risk report from daily metrics.

        Args:
            metrics: Daily risk metrics to report.
            template_path: Optional custom Jinja2 template path.

        Returns:
            Path to the generated report file.

        Raises:
            ConfigError: If report generation fails.
        """
        _validate_metrics(metrics)
        html_content = self._render_html(metrics, template_path)
        output_path = self._save_report(html_content, metrics.date)

        if self._config.notification_channel != NotificationChannel.NONE:
            self._send_notification(output_path, metrics)

        return output_path

    def _render_html(
        self,
        metrics: DailyRiskMetrics,
        template_path: Path | None,
    ) -> str:
        """Render HTML content from metrics.

        Args:
            metrics: Daily risk metrics.
            template_path: Optional custom template path.

        Returns:
            Rendered HTML string.
        """
        template = self._load_template(template_path)
        return template.render(
            report_date=metrics.date.strftime("%Y-%m-%d"),
            report_timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            daily_pnl=f"{float(metrics.daily_pnl):.2f}",
            daily_return=f"{float(metrics.daily_return) * 100:.2f}%",
            var_95=f"{float(metrics.var_95):.2f}",
            cvar_95=f"{float(metrics.cvar_95):.2f}",
            max_drawdown=f"{float(metrics.max_drawdown) * 100:.2f}%",
            total_exposure=f"{float(metrics.total_exposure):.2f}",
            net_liquidation_value=f"{float(metrics.net_liquidation_value):.2f}",
            positions=_format_positions(metrics.positions),
            risk_alert=_get_risk_alert(metrics, self._config.max_allowed_drawdown),
        )

    def _load_template(self, template_path: Path | None) -> Template:
        """Load Jinja2 template for report rendering.

        Args:
            template_path: Optional custom template path.

        Returns:
            Jinja2 Template object.
        """
        if template_path and template_path.exists():
            return Template(template_path.read_text(encoding="utf-8"))

        return Template(_get_default_template())

    def _save_report(self, html_content: str, report_date: datetime) -> Path:
        """Save report to file system.

        Args:
            html_content: HTML content to save.
            report_date: Date of the report.

        Returns:
            Path to the saved file.
        """
        filename = f"risk_report_{report_date.strftime('%Y%m%d')}.html"
        output_path = self._output_dir / filename
        output_path.write_text(html_content, encoding="utf-8")
        return output_path

    def _send_notification(
        self,
        report_path: Path,
        metrics: DailyRiskMetrics,
    ) -> None:
        """Send notification via configured channel.

        Args:
            report_path: Path to the generated report.
            metrics: Daily risk metrics.
        """
        if self._config.notification_channel == NotificationChannel.EMAIL:
            self._send_email_notification(report_path, metrics)
        elif self._config.notification_channel == NotificationChannel.TELEGRAM:
            self._send_telegram_notification(report_path, metrics)

    def _send_email_notification(
        self,
        report_path: Path,
        metrics: DailyRiskMetrics,
    ) -> None:
        """Send email notification with report attachment.

        Args:
            report_path: Path to the generated report.
            metrics: Daily risk metrics.

        Note:
            This is a stub implementation. Actual email sending
            requires SMTP configuration and credentials.
        """
        logger = _get_logger()
        logger.info(
            "Email notification would be sent to %s",
            ", ".join(self._config.email_recipients),
        )
        logger.info("Report path: %s", report_path)

    def _send_telegram_notification(
        self,
        report_path: Path,
        metrics: DailyRiskMetrics,
    ) -> None:
        """Send Telegram notification with report summary.

        Args:
            report_path: Path to the generated report.
            metrics: Daily risk metrics.

        Note:
            This is a stub implementation. Actual Telegram sending
            requires bot token and chat_id configuration.
        """
        logger = _get_logger()
        logger.info(
            "Telegram notification would be sent to chat_id: %s",
            self._config.telegram_chat_id,
        )
        logger.info("Report path: %s", report_path)


def create_daily_risk_metrics(
    date: datetime,
    daily_pnl: Decimal,
    daily_return: Decimal,
    var_95: Decimal,
    cvar_95: Decimal,
    max_drawdown: Decimal,
    total_exposure: Decimal,
    net_liquidation_value: Decimal,
    positions: list[PositionData],
    confidence_level: Decimal = Decimal("0.95"),
    max_allowed_drawdown: Decimal = Decimal("0.10"),
) -> DailyRiskMetrics:
    """Create daily risk metrics with validation.

    Args:
        date: Report date (UTC).
        daily_pnl: Daily profit/loss.
        daily_return: Daily return as decimal.
        var_95: Value at Risk at 95% confidence.
        cvar_95: Conditional VaR at 95% confidence.
        max_drawdown: Maximum drawdown as decimal.
        total_exposure: Total portfolio exposure.
        net_liquidation_value: Net liquidation value.
        positions: List of position data.
        confidence_level: Confidence level for VaR/CVaR.
        max_allowed_drawdown: Maximum allowed drawdown threshold.

    Returns:
        Validated DailyRiskMetrics object.

    Raises:
        ConfigError: If any validation fails.
    """
    if date.tzinfo is None or date.tzinfo != UTC:
        msg = "Date must be UTC-aware"
        raise ConfigError(msg)

    if net_liquidation_value <= Decimal("0"):
        msg = "Net liquidation value must be positive"
        raise ConfigError(msg)

    if total_exposure < Decimal("0"):
        msg = "Total exposure cannot be negative"
        raise ConfigError(msg)

    if confidence_level <= Decimal("0") or confidence_level >= Decimal("1"):
        msg = "Confidence level must be between 0 and 1"
        raise ConfigError(msg)

    returns = [daily_return, -var_95, -cvar_95]
    equity_curve = [net_liquidation_value - daily_pnl, net_liquidation_value]
    risk_snapshot = build_risk_snapshot(
        returns=returns,
        equity_curve=equity_curve,
        max_allowed_drawdown=max_allowed_drawdown,
    )

    return DailyRiskMetrics(
        date=date,
        daily_pnl=daily_pnl,
        daily_return=daily_return,
        var_95=var_95,
        cvar_95=cvar_95,
        max_drawdown=max_drawdown,
        total_exposure=total_exposure,
        net_liquidation_value=net_liquidation_value,
        positions=positions,
        risk_snapshot=risk_snapshot,
    )


def _validate_config(config: ReportConfig) -> None:
    """Validate report configuration.

    Args:
        config: Configuration to validate.

    Raises:
        ConfigError: If configuration is invalid.
    """
    if config.max_allowed_drawdown <= Decimal("0"):
        msg = "Max allowed drawdown must be positive"
        raise ConfigError(msg)

    if config.confidence_level <= Decimal("0") or config.confidence_level >= Decimal("1"):
        msg = "Confidence level must be between 0 and 1"
        raise ConfigError(msg)

    if config.notification_channel == NotificationChannel.EMAIL and not config.email_recipients:
        msg = "Email recipients must be specified when using email notifications"
        raise ConfigError(msg)

    if config.notification_channel == NotificationChannel.TELEGRAM and not config.telegram_chat_id:
        msg = "Telegram chat_id must be specified when using Telegram notifications"
        raise ConfigError(msg)


def _validate_metrics(metrics: DailyRiskMetrics) -> None:
    """Validate daily risk metrics.

    Args:
        metrics: Metrics to validate.

    Raises:
        ConfigError: If metrics are invalid.
    """
    if metrics.net_liquidation_value <= Decimal("0"):
        msg = "Net liquidation value must be positive"
        raise ConfigError(msg)

    if metrics.total_exposure < Decimal("0"):
        msg = "Total exposure cannot be negative"
        raise ConfigError(msg)

    if metrics.date.tzinfo is None or metrics.date.tzinfo != UTC:
        msg = "Report date must be UTC-aware"
        raise ConfigError(msg)


def _format_positions(positions: list[PositionData]) -> list[dict[str, Any]]:
    """Format position data for template rendering.

    Args:
        positions: List of position data.

    Returns:
        List of formatted position dictionaries.
    """
    return [
        {
            "symbol": pos.symbol,
            "quantity": int(pos.quantity),
            "entry_price": f"{float(pos.entry_price):.2f}",
            "current_price": f"{float(pos.current_price):.2f}",
            "unrealized_pnl": f"{float(pos.unrealized_pnl):.2f}",
            "exposure": f"{float(pos.exposure):.2f}",
        }
        for pos in positions
    ]


def _get_risk_alert(metrics: DailyRiskMetrics, max_allowed: Decimal) -> dict[str, Any]:
    """Generate risk alert information.

    Args:
        metrics: Daily risk metrics.
        max_allowed: Maximum allowed drawdown threshold.

    Returns:
        Dictionary with alert information.
    """
    is_breached = metrics.max_drawdown > max_allowed
    alert_level = "CRITICAL" if is_breached else "NORMAL"

    return {
        "level": alert_level,
        "is_breached": is_breached,
        "message": (
            f"Drawdown breach detected: {float(metrics.max_drawdown) * 100:.2f}% "
            f"exceeds {float(max_allowed) * 100:.2f}%"
            if is_breached
            else "Risk levels within acceptable limits"
        ),
    }


def _get_logger() -> Any:
    """Get structured logger instance.

    Returns:
        Logger instance for structured logging.

    Note:
        Returns Any to avoid circular import with logging module.
        In production, this should return a proper logger.
    """
    import logging

    return logging.getLogger(__name__)


def _get_default_template() -> str:
    """Get default HTML template for risk report.

    Returns:
        HTML template string.
    """
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Risk Disclosure Report - {{ report_date }}</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .header h1 {
            margin: 0 0 10px 0;
            font-size: 2.5em;
        }
        .header p {
            margin: 0;
            opacity: 0.9;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .metric-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .metric-card h3 {
            margin: 0 0 10px 0;
            color: #667eea;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .metric-card .value {
            font-size: 2em;
            font-weight: bold;
            color: #333;
        }
        .metric-card .positive {
            color: #10b981;
        }
        .metric-card .negative {
            color: #ef4444;
        }
        .alert-box {
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            font-weight: bold;
        }
        .alert-critical {
            background-color: #fee2e2;
            color: #dc2626;
            border: 2px solid #dc2626;
        }
        .alert-normal {
            background-color: #d1fae5;
            color: #059669;
            border: 2px solid #059669;
        }
        .section {
            background: white;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .section h2 {
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            margin-top: 0;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e5e7eb;
        }
        th {
            background-color: #f9fafb;
            font-weight: 600;
            color: #374151;
        }
        tr:hover {
            background-color: #f9fafb;
        }
        .positive {
            color: #10b981;
        }
        .negative {
            color: #ef4444;
        }
        .footer {
            text-align: center;
            padding: 20px;
            color: #6b7280;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Risk Disclosure Report</h1>
        <p>Report Date: {{ report_date }} | Generated: {{ report_timestamp }}</p>
    </div>

    <div class="alert-box alert-{{ 'critical' if risk_alert.is_breached else 'normal' }}">
        {{ risk_alert.level }}: {{ risk_alert.message }}
    </div>

    <div class="summary-grid">
        <div class="metric-card">
            <h3>Daily P&L</h3>
            <div class="value {{ 'positive' if daily_pnl|float > 0 else 'negative' }}">
                {{ daily_pnl }}
            </div>
        </div>
        <div class="metric-card">
            <h3>Daily Return</h3>
            <div class="value {{ 'positive' if daily_return|float > 0 else 'negative' }}">
                {{ daily_return }}
            </div>
        </div>
        <div class="metric-card">
            <h3>VaR (95%)</h3>
            <div class="value negative">{{ var_95 }}</div>
        </div>
        <div class="metric-card">
            <h3>CVaR (95%)</h3>
            <div class="value negative">{{ cvar_95 }}</div>
        </div>
        <div class="metric-card">
            <h3>Max Drawdown</h3>
            <div class="value negative">{{ max_drawdown }}</div>
        </div>
        <div class="metric-card">
            <h3>Total Exposure</h3>
            <div class="value">{{ total_exposure }}</div>
        </div>
    </div>

    <div class="section">
        <h2>Position Summary</h2>
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Quantity</th>
                    <th>Entry Price</th>
                    <th>Current Price</th>
                    <th>Unrealized P&L</th>
                    <th>Exposure</th>
                </tr>
            </thead>
            <tbody>
                {% for position in positions %}
                <tr>
                    <td>{{ position.symbol }}</td>
                    <td>{{ position.quantity }}</td>
                    <td>{{ position.entry_price }}</td>
                    <td>{{ position.current_price }}</td>
                    <td class="{{ 'positive' if position.unrealized_pnl|float > 0
                        else 'negative' }}">
                        {{ position.unrealized_pnl }}
                    </td>
                    <td>{{ position.exposure }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>Risk Metrics Detail</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
                <th>Description</th>
            </tr>
            <tr>
                <td>VaR (95%)</td>
                <td>{{ var_95 }}</td>
                <td>Maximum expected loss at 95% confidence level</td>
            </tr>
            <tr>
                <td>CVaR (95%)</td>
                <td>{{ cvar_95 }}</td>
                <td>Average loss in worst 5% of scenarios</td>
            </tr>
            <tr>
                <td>Max Drawdown</td>
                <td>{{ max_drawdown }}</td>
                <td>Largest peak-to-trough decline from peak</td>
            </tr>
            <tr>
                <td>Net Liquidation Value</td>
                <td>{{ net_liquidation_value }}</td>
                <td>Total account equity after open positions</td>
            </tr>
            <tr>
                <td>Total Exposure</td>
                <td>{{ total_exposure }}</td>
                <td>Total market value of all open positions</td>
            </tr>
        </table>
    </div>

    <div class="footer">
        <p>This report is generated automatically by the IATB Risk Management System.</p>
        <p>Report ID: {{ report_date }}-{{ report_timestamp }}</p>
    </div>
</body>
</html>
    """.strip()
