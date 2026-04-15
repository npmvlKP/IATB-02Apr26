"""Telegram alerting configuration for sending notifications."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from iatb.core.observability.logging_config import get_logger

_LOGGER = get_logger(__name__)


class TelegramAlertLevel:
    """Alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class TelegramAlerter:
    """Telegram bot for sending alerts and notifications."""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        enabled: bool = True,
    ) -> None:
        """Initialize Telegram alerter.

        Args:
            bot_token: Telegram bot token. If None, reads from
                TELEGRAM_BOT_TOKEN env var.
            chat_id: Telegram chat ID to send alerts to. If None,
                reads from TELEGRAM_CHAT_ID env var.
            enabled: Whether alerts are enabled.
        """
        self.bot_token = bot_token or os.getenv(
            "TELEGRAM_BOT_TOKEN",
        )
        self.chat_id = chat_id or os.getenv(
            "TELEGRAM_CHAT_ID",
        )
        self.enabled = enabled and bool(self.bot_token and self.chat_id)
        self.bot: Bot | None = None

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
        level: str = TelegramAlertLevel.INFO,
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

        try:
            formatted_message = self._format_message(message, level, context)
            self._send_message_async(text=formatted_message)
            return True
        except Exception as exc:
            _LOGGER.error("Unexpected error sending Telegram alert: %s", exc)
            return False

    def send_trade_alert(
        self,
        ticker: str,
        side: str,
        quantity: int,
        price: float,
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

        emoji = "🟢" if side == "BUY" else "🔴"
        message = f"""
{emoji} *Trade Executed*

*Ticker:* {ticker}
*Side:* {side}
*Quantity:* {quantity}
*Price:* ₹{price:.2f}
*Time:* {timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")}
"""
        return self.send_alert(message, TelegramAlertLevel.INFO)

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
🚨 *Error Alert*

*Component:* {component}
*Error:* {error_message}
"""
        if exc_type:
            message += f"*Type:* {exc_type}\n"

        return self.send_alert(message, TelegramAlertLevel.ERROR)

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
        emoji = {
            "UP": "✅",
            "DOWN": "❌",
            "DEGRADED": "⚠️",
        }.get(status, "ℹ️")

        message = f"""
{emoji} *Health Alert*

*Service:* {service}
*Status:* {status}
"""
        if details:
            message += f"*Details:* {details}\n"

        level = TelegramAlertLevel.CRITICAL if status == "DOWN" else TelegramAlertLevel.WARNING

        return self.send_alert(message, level)

    def send_pnl_alert(
        self,
        pnl: float,
        daily_pnl: float | None = None,
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
        emoji = "💰" if pnl >= 0 else "📉"
        message = f"""
{emoji} *PnL Update*

*Total PnL:* ₹{pnl:.2f}
"""
        if daily_pnl is not None:
            emoji = "💚" if daily_pnl >= 0 else "🔻"
            message += f"*Daily PnL:* {emoji} ₹{daily_pnl:.2f}\n"

        message += f"*Open Positions:* {open_positions}"

        return self.send_alert(message, TelegramAlertLevel.INFO)

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
        emoji = "🤖" if status == "AVAILABLE" else "⚠️"
        message = f"""
{emoji} *ML Model Alert*

*Model:* {model_name}
*Status:* {status}
"""
        if details:
            message += f"*Details:* {details}\n"

        level = TelegramAlertLevel.ERROR if status != "AVAILABLE" else TelegramAlertLevel.INFO

        return self.send_alert(message, level)

    def send_with_actions(
        self,
        message: str,
        buttons: Sequence[tuple[str, str]] | None = None,
        level: str = TelegramAlertLevel.INFO,
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
        level_emoji = {
            TelegramAlertLevel.INFO: "ℹ️",
            TelegramAlertLevel.WARNING: "⚠️",
            TelegramAlertLevel.ERROR: "🚨",
            TelegramAlertLevel.CRITICAL: "🔴",
        }.get(level, "ℹ️")

        formatted = f"""
{level_emoji} *{level} Alert*
*Time:* {datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")}

{message}
"""

        if context:
            formatted += "\n*Context:*\n"
            for key, value in context.items():
                formatted += f"  • *{key}:* {value}\n"

        return formatted


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
