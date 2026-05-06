"""Multi-channel alerting system with rules, throttling, and acknowledgment."""

from __future__ import annotations

import asyncio
import os
import smtplib
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from email.mime.text import MIMEText
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

import aiohttp
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from iatb.core.observability.logging_config import get_logger

_LOGGER = get_logger(__name__)


class AlertLevel(StrEnum):
    """Standardized alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AlertType(StrEnum):
    """Alert type categories."""

    BREAKOUT = "breakout"
    REGIME_CHANGE = "regime_change"
    KILL_SWITCH = "kill_switch"


# =============================================================================
# MULTI-CHANNEL ALERTING SYSTEM
# =============================================================================


@dataclass
class Alert:
    """Alert data structure."""

    message: str
    level: str = AlertLevel.INFO
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    context: dict[str, Any] = field(default_factory=dict)
    rule_name: str | None = None
    alert_id: str | None = None


class AlertChannel(ABC):
    """Abstract base class for alert channels."""

    enabled: bool = False

    def __init__(self, enabled: bool = True) -> None:
        """Initialize alert channel.

        Args:
            enabled: Whether this channel is enabled.
        """
        self.enabled = enabled

    @abstractmethod
    def send(self, alert: Alert) -> bool:
        """Send an alert through this channel.

        Args:
            alert: Alert to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        pass


class TelegramAlerter(AlertChannel):
    """Telegram bot for sending alerts and notifications."""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        enabled: bool = True,
        max_per_minute: int = 20,
    ) -> None:
        """Initialize Telegram alerter.

        Args:
            bot_token: Telegram bot token. If None, reads from
                TELEGRAM_BOT_TOKEN env var.
            chat_id: Telegram chat ID to send alerts to. If None,
                reads from TELEGRAM_CHAT_ID env var.
            enabled: Whether alerts are enabled.
            max_per_minute: Maximum messages per minute (rate limiting).
        """
        super().__init__(enabled)
        self.bot_token = bot_token or os.getenv(
            "TELEGRAM_BOT_TOKEN",
        )
        self.chat_id = chat_id or os.getenv(
            "TELEGRAM_CHAT_ID",
        )
        self.enabled = enabled and bool(self.bot_token and self.chat_id)
        self.bot: Bot | None = None
        self._max_per_minute = max_per_minute
        self._sent_timestamps: list[datetime] = []

        if self.enabled and self.bot_token:
            self.bot = Bot(token=self.bot_token)

    def _send_message_async(
        self,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: Any = None,
    ) -> None:
        """Helper to send message asynchronously without blocking.

        Args:
            text: Message text.
            parse_mode: Parse mode (Markdown or HTML).
            reply_markup: Reply markup (e.g., inline keyboard).
        """
        if not self.chat_id or not self.bot:
            return

        async def _async_send() -> None:
            try:
                bot = self.bot
                chat_id = self.chat_id
                if bot is None or chat_id is None:
                    return
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
            except TelegramError as exc:
                _LOGGER.error("Failed to send Telegram alert: %s", exc)
            except Exception as exc:
                _LOGGER.error("Unexpected error sending Telegram alert: %s", exc)

        # Try to run in existing event loop, otherwise run in new one
        try:
            asyncio.get_running_loop()
            asyncio.create_task(_async_send())
        except RuntimeError:
            # No running event loop, run in new one
            try:
                asyncio.run(_async_send())
            except RuntimeError:
                _LOGGER.warning("Could not send Telegram alert: no event loop")

    def send_alert(
        self,
        message: str,
        level: str = AlertLevel.INFO,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Send an alert message to Telegram.

        Args:
            message: Alert message.
            level: Alert severity level.
            context: Additional context to include in the alert.

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        if not self.enabled or not self.bot:
            return False

        if not message.strip():
            _LOGGER.error("Telegram alert message cannot be empty")
            return False

        try:
            now_utc = datetime.now(UTC)
            self._sent_timestamps = _keep_recent(self._sent_timestamps, now_utc)
            if len(self._sent_timestamps) >= self._max_per_minute:
                _LOGGER.warning(
                    "Telegram alert rate-limited: %d messages in last minute",
                    len(self._sent_timestamps),
                )
                return False

            formatted_message = self._format_message(message, level, context)
            self._send_message_async(text=formatted_message)
            self._sent_timestamps.append(now_utc)
            return True
        except Exception as exc:
            _LOGGER.error("Unexpected error sending Telegram alert: %s", exc)
            return False

    def send_trade_alert(
        self,
        ticker: str,
        side: str,
        quantity: int,
        price: Decimal,
        timestamp: datetime | None = None,
    ) -> bool:
        """Send a trade execution alert.

        Args:
            ticker: Ticker symbol.
            side: Trade side (BUY/SELL).
            quantity: Quantity traded.
            price: Trade price.
            timestamp: Trade timestamp (defaults to now).

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        message = f"""
*Trade Executed*

*Ticker:* {ticker}
*Side:* {side}
*Quantity:* {quantity}
*Price:* {price:.2f}
*Time:* {timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")}
"""
        return self.send_alert(message, AlertLevel.INFO)

    def send_error_alert(
        self,
        component: str,
        error_message: str,
        exc_type: str | None = None,
    ) -> bool:
        """Send an error alert.

        Args:
            component: Component where error occurred.
            error_message: Error message.
            exc_type: Exception type (if applicable).

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        message = f"""
*Error Alert*

*Component:* {component}
*Error:* {error_message}
"""
        if exc_type:
            message += f"*Type:* {exc_type}\n"

        return self.send_alert(message, AlertLevel.ERROR)

    def send_health_alert(
        self,
        service: str,
        status: str,
        details: str | None = None,
    ) -> bool:
        """Send a health status alert.

        Args:
            service: Service name.
            status: Service status (UP/DOWN/DEGRADED).
            details: Additional details about the status.

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        message = f"""
*Health Alert*

*Service:* {service}
*Status:* {status}
"""
        if details:
            message += f"*Details:* {details}\n"

        level = AlertLevel.CRITICAL if status == "DOWN" else AlertLevel.WARNING

        return self.send_alert(message, level)

    def send_pnl_alert(
        self,
        pnl: Decimal,
        daily_pnl: Decimal | None = None,
        open_positions: int = 0,
    ) -> bool:
        """Send a PnL alert.

        Args:
            pnl: Current PnL.
            daily_pnl: Daily PnL.
            open_positions: Number of open positions.

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        message = f"""
*PnL Update*

*Total PnL:* {pnl:.2f}
"""
        if daily_pnl is not None:
            daily_emoji = "GREEN" if daily_pnl >= 0 else "RED"
            message += f"*Daily PnL:* {daily_emoji} {daily_pnl:.2f}\n"

        message += f"*Open Positions:* {open_positions}"

        return self.send_alert(message, AlertLevel.INFO)

    def send_model_alert(
        self,
        model_name: str,
        status: str,
        details: str | None = None,
    ) -> bool:
        """Send an ML model status alert.

        Args:
            model_name: Name of the model.
            status: Model status.
            details: Additional details.

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        message = f"""
*ML Model Alert*

*Model:* {model_name}
*Status:* {status}
"""
        if details:
            message += f"*Details:* {details}\n"

        level = AlertLevel.ERROR if status != "AVAILABLE" else AlertLevel.INFO

        return self.send_alert(message, level)

    def send_data_source_failure_alert(
        self,
        source: str,
        failure_count: int,
        time_window: str = "5 minutes",
    ) -> bool:
        """Send alert when data source fails multiple times.

        Args:
            source: Data source name (e.g., "KiteProvider").
            failure_count: Number of failures in the time window.
            time_window: Time window for failure count.

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        message = f"""
*Data Source Failure Alert*

*Source:* {source}
*Failures:* {failure_count} in {time_window}
*Severity:* CRITICAL

Immediate attention required. Check connection and logs.
"""
        return self.send_alert(message, AlertLevel.CRITICAL)

    def send_fallback_source_alert(
        self,
        from_source: str,
        to_source: str,
        reason: str | None = None,
    ) -> bool:
        """Send alert when fallback data source is used.

        Args:
            from_source: Primary source that failed.
            to_source: Fallback source being used.
            reason: Reason for fallback (optional).

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        message = f"""
*Data Source Fallback Alert*

*From:* {from_source}
*To:* {to_source}
"""
        if reason:
            message += f"*Reason:* {reason}\n"

        message += "\nSystem is operating on fallback source."

        return self.send_alert(message, AlertLevel.WARNING)

    def send_token_expiry_alert(
        self,
        token_type: str,
        minutes_remaining: int,
    ) -> bool:
        """Send alert when token is about to expire.

        Args:
            token_type: Type of token (e.g., "Kite").
            minutes_remaining: Minutes until expiry.

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        message = f"""
*Token Expiry Alert*

*Token Type:* {token_type}
*Expires in:* {minutes_remaining} minutes

Action required: Refresh token immediately to avoid service disruption.
"""
        level = AlertLevel.CRITICAL if minutes_remaining <= 5 else AlertLevel.WARNING

        return self.send_alert(message, level)

    def send_with_actions(
        self,
        message: str,
        buttons: Sequence[tuple[str, str]] | None = None,
        level: str = AlertLevel.INFO,
    ) -> bool:
        """Send an alert with action buttons.

        Args:
            message: Alert message.
            buttons: List of (button_text, callback_data) tuples.
            level: Alert severity level.

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        if not self.enabled or not self.bot:
            return False

        try:
            keyboard = None
            if buttons:
                keyboard = [
                    [InlineKeyboardButton(text, callback_data=callback)]
                    for text, callback in buttons
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            else:
                reply_markup = None

            formatted_message = self._format_message(message, level)
            self._send_message_async(
                text=formatted_message,
                reply_markup=reply_markup,
            )
            return True
        except Exception as exc:
            _LOGGER.error("Unexpected error sending Telegram alert: %s", exc)
            return False

    def send_kill_switch_alert(
        self,
        reason: str,
        engaged_utc: datetime,
    ) -> bool:
        """Send a kill switch engagement alert.

        Args:
            reason: Reason for kill switch engagement.
            engaged_utc: UTC timestamp when kill switch was engaged.

        Returns:
            True if alert was sent successfully, False otherwise.
        """
        if engaged_utc.tzinfo != UTC:
            _LOGGER.error("engaged_utc must be timezone-aware UTC datetime")
            return False

        message = f"""
*🚨 KILL SWITCH ENGAGED 🚨*

*Reason:* {reason}
*Engaged At:* {engaged_utc.strftime("%Y-%m-%d %H:%M:%S UTC")}

All open orders have been cancelled. New orders are blocked.
Manual disengagement required to resume trading.
"""
        return self.send_alert(message, AlertLevel.CRITICAL)

    def _format_message(
        self,
        message: str,
        level: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Format alert message with timestamp and level.

        Args:
            message: Alert message.
            level: Alert severity level.
            context: Additional context.

        Returns:
            Formatted message.
        """
        level_key = (
            AlertLevel(level) if level in AlertLevel.__members__.values() else AlertLevel.INFO
        )
        level_emoji: str = {
            AlertLevel.INFO: "INFO",
            AlertLevel.WARNING: "WARNING",
            AlertLevel.ERROR: "ERROR",
            AlertLevel.CRITICAL: "CRITICAL",
        }.get(level_key, "INFO")

        formatted = f"""
*{level_emoji} Alert*
*Time:* {datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")}

{message}
"""

        if context:
            formatted += "\n*Context:*\n"
            for key, value in context.items():
                formatted += f"  *{key}:* {value}\n"

        return formatted

    def send(self, alert: Alert) -> bool:
        """Send alert via Telegram (implements AlertChannel interface).

        Args:
            alert: Alert to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        return self.send_alert(alert.message, alert.level, alert.context)


def _keep_recent(history: list[datetime], now_utc: datetime) -> list[datetime]:
    """Keep only timestamps from the last minute.

    Args:
        history: List of timestamps.
        now_utc: Current UTC datetime.

    Returns:
        Filtered list of timestamps from the last minute.
    """
    threshold = now_utc - timedelta(minutes=1)
    return [stamp for stamp in history if stamp >= threshold]


class EmailChannel(AlertChannel):
    """Email alert channel using SMTP."""

    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int = 587,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        from_email: str | None = None,
        to_emails: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        """Initialize email alert channel.

        Args:
            smtp_host: SMTP server host.
            smtp_port: SMTP server port.
            smtp_user: SMTP username.
            smtp_password: SMTP password.
            from_email: From email address.
            to_emails: List of recipient email addresses.
            enabled: Whether this channel is enabled.
        """
        super().__init__(enabled)
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST")
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user or os.getenv("SMTP_USER")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
        self.from_email = from_email or os.getenv("EMAIL_FROM")
        self.to_emails = to_emails or os.getenv("EMAIL_TO", "").split(",")
        self.to_emails = [email.strip() for email in self.to_emails if email.strip()]

        self.enabled = (
            enabled
            and bool(self.smtp_host and self.smtp_user and self.smtp_password)
            and len(self.to_emails) > 0
        )

    def send(self, alert: Alert) -> bool:
        """Send alert via email.

        Args:
            alert: Alert to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            subject = f"[{alert.level}] {alert.rule_name or 'Alert'}"
            body = self._format_body(alert)

            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = self.from_email or "noreply@iatb.local"
            msg["To"] = ", ".join(self.to_emails)

            if self.smtp_host and self.smtp_user and self.smtp_password:
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)

            return True
        except Exception as exc:
            _LOGGER.error("Failed to send email alert: %s", exc)
            return False

    def _format_body(self, alert: Alert) -> str:
        """Format alert body for email.

        Args:
            alert: Alert to format.

        Returns:
            Formatted email body.
        """
        body = f"""
Alert Level: {alert.level}
Timestamp: {alert.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")}
Rule: {alert.rule_name or 'N/A'}
Alert ID: {alert.alert_id or 'N/A'}

Message:
{alert.message}
"""
        if alert.context:
            body += "\nContext:\n"
            for key, value in alert.context.items():
                body += f"  {key}: {value}\n"

        return body


class WebhookChannel(AlertChannel):
    """Webhook alert channel using HTTP POST."""

    def __init__(
        self,
        webhook_url: str | None = None,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> None:
        """Initialize webhook alert channel.

        Args:
            webhook_url: Webhook URL endpoint.
            headers: Additional HTTP headers.
            enabled: Whether this channel is enabled.
        """
        super().__init__(enabled)
        self.webhook_url = webhook_url or os.getenv("WEBHOOK_URL")
        self.headers = headers or {}

        if self.webhook_url:
            try:
                result = urlparse(self.webhook_url)
                self.enabled = enabled and bool(result.scheme and result.netloc)
            except Exception:
                self.enabled = False
        else:
            self.enabled = False

    async def send_async(self, alert: Alert) -> bool:
        """Send alert via webhook asynchronously.

        Args:
            alert: Alert to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.enabled or not self.webhook_url:
            return False

        try:
            payload = {
                "message": alert.message,
                "level": alert.level,
                "timestamp": alert.timestamp.isoformat(),
                "rule_name": alert.rule_name,
                "alert_id": alert.alert_id,
                "context": alert.context,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status < 400
        except Exception as exc:
            _LOGGER.error("Failed to send webhook alert: %s", exc)
            return False

    def send(self, alert: Alert) -> bool:
        """Send alert via webhook (synchronous wrapper).

        Args:
            alert: Alert to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            loop = asyncio.get_running_loop()
            future = asyncio.ensure_future(self.send_async(alert))
            return loop.run_until_complete(future)
        except RuntimeError:
            return asyncio.run(self.send_async(alert))
        except Exception as exc:
            _LOGGER.error("Failed to send webhook alert: %s", exc)
            return False


# =============================================================================
# ALERT RULES ENGINE
# =============================================================================


@dataclass
class AlertRule:
    """Alert rule definition."""

    name: str
    condition: Callable[[dict[str, Any]], bool]
    level: str = AlertLevel.WARNING
    enabled: bool = True
    description: str = ""


class AlertRulesEngine:
    """Engine for evaluating and triggering alert rules."""

    def __init__(self) -> None:
        """Initialize alert rules engine."""
        self.rules: dict[str, AlertRule] = {}
        self._initialize_default_rules()

    def _initialize_default_rules(self) -> None:
        """Initialize default alert rules."""
        # Token expiry rule
        self.add_rule(
            AlertRule(
                name="token_expiry",
                condition=self._check_token_expiry,
                level=AlertLevel.CRITICAL,
                description="Alert when broker token is about to expire",
            )
        )

        # Position limit breach rule
        self.add_rule(
            AlertRule(
                name="position_limit_breach",
                condition=self._check_position_limit_breach,
                level=AlertLevel.CRITICAL,
                description="Alert when position limit is exceeded",
            )
        )

        # Daily loss threshold rule
        self.add_rule(
            AlertRule(
                name="daily_loss_threshold",
                condition=self._check_daily_loss_threshold,
                level=AlertLevel.CRITICAL,
                description="Alert when daily loss exceeds threshold",
            )
        )

        # Data source failure rule
        self.add_rule(
            AlertRule(
                name="data_source_failure",
                condition=self._check_data_source_failure,
                level=AlertLevel.ERROR,
                description="Alert when data source fails repeatedly",
            )
        )

    def add_rule(self, rule: AlertRule) -> None:
        """Add or update an alert rule.

        Args:
            rule: Alert rule to add.
        """
        self.rules[rule.name] = rule

    def remove_rule(self, rule_name: str) -> None:
        """Remove an alert rule.

        Args:
            rule_name: Name of rule to remove.
        """
        if rule_name in self.rules:
            del self.rules[rule_name]

    def evaluate_rules(
        self,
        context: dict[str, Any],
    ) -> list[tuple[AlertRule, dict[str, Any]]]:
        """Evaluate all enabled rules against context.

        Args:
            context: Context data for rule evaluation.

        Returns:
            List of (rule, context) tuples for triggered rules.
        """
        triggered = []
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            try:
                if rule.condition(context):
                    triggered.append((rule, context))
            except Exception as exc:
                _LOGGER.error("Error evaluating rule %s: %s", rule.name, exc)

        return triggered

    # Default rule conditions
    def _check_token_expiry(self, context: dict[str, Any]) -> bool:
        """Check if token is about to expire.

        Args:
            context: Context with 'token_type' and 'minutes_remaining'.

        Returns:
            True if token expires in 10 minutes or less.
        """
        minutes_remaining = int(context.get("minutes_remaining", 999))
        return minutes_remaining <= 10

    def _check_position_limit_breach(self, context: dict[str, Any]) -> bool:
        """Check if position limit is breached.

        Args:
            context: Context with 'current_positions' and 'limit'.

        Returns:
            True if positions exceed limit.
        """
        current = int(context.get("current_positions", 0))
        limit = int(context.get("limit", 999))
        return current >= limit

    def _check_daily_loss_threshold(self, context: dict[str, Any]) -> bool:
        """Check if daily loss exceeds threshold.

        Args:
            context: Context with 'daily_pnl' and 'loss_threshold'.

        Returns:
            True if daily loss exceeds threshold.
        """
        # Use Decimal for financial comparison to avoid float precision issues
        daily_pnl_raw = context.get("daily_pnl", 0)
        threshold_raw = context.get("loss_threshold", -999999)
        daily_pnl = Decimal(str(daily_pnl_raw))
        threshold = Decimal(str(threshold_raw))
        return daily_pnl <= threshold

    def _check_data_source_failure(self, context: dict[str, Any]) -> bool:
        """Check if data source is failing.

        Args:
            context: Context with 'failure_count' and 'time_window'.

        Returns:
            True if failure count exceeds threshold.
        """
        failure_count = int(context.get("failure_count", 0))
        threshold = int(context.get("failure_threshold", 3))
        return failure_count >= threshold


# =============================================================================
# ALERT THROTTLING
# =============================================================================


class AlertThrottler:
    """Throttle alerts to prevent spam (max 1 per minute per rule)."""

    def __init__(self, min_interval_seconds: int = 60) -> None:
        """Initialize alert throttler.

        Args:
            min_interval_seconds: Minimum seconds between alerts for same rule.
        """
        self.min_interval_seconds = min_interval_seconds
        self._last_sent: dict[str, datetime] = {}

    def should_send(self, rule_name: str) -> bool:
        """Check if alert should be sent based on throttling.

        Args:
            rule_name: Name of the alert rule.

        Returns:
            True if alert can be sent, False if throttled.
        """
        if rule_name not in self._last_sent:
            return True

        last_sent = self._last_sent[rule_name]
        elapsed = (datetime.now(UTC) - last_sent).total_seconds()

        if elapsed >= self.min_interval_seconds:
            return True

        _LOGGER.info(
            "Alert throttled for rule '%s': %d seconds since last alert",
            rule_name,
            int(elapsed),
        )
        return False

    def record_sent(self, rule_name: str) -> None:
        """Record that an alert was sent for a rule.

        Args:
            rule_name: Name of the alert rule.
        """
        self._last_sent[rule_name] = datetime.now(UTC)

    def reset(self, rule_name: str | None = None) -> None:
        """Reset throttling for a rule or all rules.

        Args:
            rule_name: Name of rule to reset. If None, reset all.
        """
        if rule_name:
            self._last_sent.pop(rule_name, None)
        else:
            self._last_sent.clear()


# =============================================================================
# ALERT ACKNOWLEDGMENT TRACKING
# =============================================================================


@dataclass
class AlertAcknowledgment:
    """Alert acknowledgment record."""

    alert_id: str
    rule_name: str
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    acknowledged_via: str | None = None


class AlertAcknowledgmentTracker:
    """Track alert acknowledgments."""

    def __init__(self) -> None:
        """Initialize acknowledgment tracker."""
        self.acknowledgments: dict[str, AlertAcknowledgment] = {}

    def register_alert(
        self,
        alert_id: str,
        rule_name: str,
    ) -> None:
        """Register a new alert for acknowledgment tracking.

        Args:
            alert_id: Unique alert identifier.
            rule_name: Name of the rule that triggered the alert.
        """
        self.acknowledgments[alert_id] = AlertAcknowledgment(
            alert_id=alert_id,
            rule_name=rule_name,
        )

    def acknowledge(
        self,
        alert_id: str,
        acknowledged_by: str,
        acknowledged_via: str,
    ) -> bool:
        """Acknowledge an alert.

        Args:
            alert_id: Alert identifier to acknowledge.
            acknowledged_by: User/service acknowledging.
            acknowledged_via: Channel used for acknowledgment.

        Returns:
            True if acknowledged successfully, False if not found.
        """
        if alert_id not in self.acknowledgments:
            return False

        ack = self.acknowledgments[alert_id]
        ack.acknowledged = True
        ack.acknowledged_by = acknowledged_by
        ack.acknowledged_at = datetime.now(UTC)
        ack.acknowledged_via = acknowledged_via

        _LOGGER.info(
            "Alert '%s' acknowledged by %s via %s",
            alert_id,
            acknowledged_by,
            acknowledged_via,
        )
        return True

    def is_acknowledged(self, alert_id: str) -> bool:
        """Check if alert is acknowledged.

        Args:
            alert_id: Alert identifier.

        Returns:
            True if acknowledged, False otherwise.
        """
        return self.acknowledgments.get(alert_id, AlertAcknowledgment(alert_id, "")).acknowledged

    def get_unacknowledged(
        self,
        rule_name: str | None = None,
    ) -> list[AlertAcknowledgment]:
        """Get list of unacknowledged alerts.

        Args:
            rule_name: Optional filter by rule name.

        Returns:
            List of unacknowledged alerts.
        """
        unacknowledged = [ack for ack in self.acknowledgments.values() if not ack.acknowledged]

        if rule_name:
            unacknowledged = [ack for ack in unacknowledged if ack.rule_name == rule_name]

        return unacknowledged

    def cleanup_old_alerts(self, max_age_hours: int = 24) -> int:
        """Clean up old acknowledged alerts.

        Args:
            max_age_hours: Maximum age in hours to keep.

        Returns:
            Number of alerts cleaned up.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        to_remove = []

        for alert_id, ack in self.acknowledgments.items():
            if ack.acknowledged and ack.acknowledged_at and ack.acknowledged_at < cutoff:
                to_remove.append(alert_id)

        for alert_id in to_remove:
            del self.acknowledgments[alert_id]

        return len(to_remove)


# =============================================================================
# MULTI-CHANNEL ALERT MANAGER
# =============================================================================


class MultiChannelAlertManager:
    """Unified manager for multi-channel alerting with rules and throttling."""

    def __init__(
        self,
        channels: list[AlertChannel] | None = None,
        rules_engine: AlertRulesEngine | None = None,
        throttler: AlertThrottler | None = None,
        acknowledgment_tracker: AlertAcknowledgmentTracker | None = None,
    ) -> None:
        """Initialize multi-channel alert manager.

        Args:
            channels: List of alert channels.
            rules_engine: Rules engine instance.
            throttler: Alert throttler instance.
            acknowledgment_tracker: Acknowledgment tracker instance.
        """
        self.channels = channels or []
        self.rules_engine = rules_engine or AlertRulesEngine()
        self.throttler = throttler or AlertThrottler()
        self.ack_tracker = acknowledgment_tracker or AlertAcknowledgmentTracker()
        self._alert_counter = 0

    def add_channel(self, channel: AlertChannel) -> None:
        """Add an alert channel.

        Args:
            channel: Alert channel to add.
        """
        if channel not in self.channels:
            self.channels.append(channel)

    def send_alert(
        self,
        message: str,
        level: str = AlertLevel.INFO,
        context: dict[str, Any] | None = None,
        rule_name: str | None = None,
    ) -> str | None:
        """Send alert through all enabled channels.

        Args:
            message: Alert message.
            level: Alert severity level.
            context: Additional context.
            rule_name: Name of rule that triggered alert.

        Returns:
            Alert ID if sent, None if throttled or no channels enabled.
        """
        if rule_name and not self.throttler.should_send(rule_name):
            return None

        self._alert_counter += 1
        alert_id = f"alert_{self._alert_counter}_{int(datetime.now(UTC).timestamp())}"

        alert = Alert(
            message=message,
            level=level,
            context=context or {},
            rule_name=rule_name,
            alert_id=alert_id,
        )

        self.ack_tracker.register_alert(alert_id, rule_name or "manual")

        for channel in self.channels:
            if channel.enabled:
                try:
                    channel.send(alert)
                except Exception as exc:
                    _LOGGER.error(
                        "Failed to send alert via %s: %s",
                        channel.__class__.__name__,
                        exc,
                    )

        if rule_name:
            self.throttler.record_sent(rule_name)

        return alert_id

    def evaluate_and_alert(self, context: dict[str, Any]) -> list[str]:
        """Evaluate all rules and send alerts for triggered ones.

        Args:
            context: Context data for rule evaluation.

        Returns:
            List of alert IDs sent.
        """
        triggered = self.rules_engine.evaluate_rules(context)
        alert_ids = []

        for rule, rule_context in triggered:
            alert_id = self.send_alert(
                message=f"Rule '{rule.name}' triggered: {rule.description}",
                level=rule.level,
                context=rule_context,
                rule_name=rule.name,
            )
            if alert_id:
                alert_ids.append(alert_id)

        return alert_ids

    def acknowledge(
        self,
        alert_id: str,
        acknowledged_by: str = "system",
        acknowledged_via: str = "api",
    ) -> bool:
        """Acknowledge an alert.

        Args:
            alert_id: Alert identifier.
            acknowledged_by: User/service acknowledging.
            acknowledged_via: Channel used.

        Returns:
            True if acknowledged, False otherwise.
        """
        return self.ack_tracker.acknowledge(alert_id, acknowledged_by, acknowledged_via)

    def get_unacknowledged_alerts(
        self,
        rule_name: str | None = None,
    ) -> list[AlertAcknowledgment]:
        """Get unacknowledged alerts.

        Args:
            rule_name: Optional filter by rule name.

        Returns:
            List of unacknowledged alerts.
        """
        return self.ack_tracker.get_unacknowledged(rule_name)

    def cleanup_old_alerts(self, max_age_hours: int = 24) -> int:
        """Clean up old acknowledged alerts.

        Args:
            max_age_hours: Maximum age in hours.

        Returns:
            Number of alerts cleaned up.
        """
        return self.ack_tracker.cleanup_old_alerts(max_age_hours)


# =============================================================================
# GLOBAL ALERTER INSTANCE
# =============================================================================

# Global alerter instance
_alerter: TelegramAlerter | None = None


def get_alerter() -> TelegramAlerter:
    """Get or create global Telegram alerter instance.

    Returns:
        TelegramAlerter instance.
    """
    global _alerter
    if _alerter is None:
        _alerter = TelegramAlerter()
    return _alerter


# Global multi-channel manager instance
_multi_channel_manager: MultiChannelAlertManager | None = None


def get_multi_channel_manager() -> MultiChannelAlertManager:
    """Get or create global multi-channel alert manager.

    Returns:
        MultiChannelAlertManager instance.
    """
    global _multi_channel_manager
    if _multi_channel_manager is None:
        _multi_channel_manager = MultiChannelAlertManager(
            channels=[
                TelegramAlerter(),  # Uses existing Telegram alerter
                EmailChannel(),
                WebhookChannel(),
            ]
        )
    return _multi_channel_manager
