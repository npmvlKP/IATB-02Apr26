"""
Telegram alert helpers with deterministic rate limiting.

DEPRECATED: This module is deprecated. All alerting functionality has been
consolidated into iatb.core.observability.alerting. Please import from there instead.

Migration guide:
- AlertType -> iatb.core.observability.alerting.AlertType
- TelegramAlertDispatcher -> iatb.core.observability.alerting.TelegramAlerter
- AlertLevel -> iatb.core.observability.alerting.AlertLevel
"""

import warnings
from collections.abc import Callable
from datetime import UTC, datetime

from iatb.core.exceptions import ConfigError
from iatb.core.observability.alerting import (
    AlertLevel,
    AlertType,
    TelegramAlerter,
    _keep_recent,
)

warnings.warn(
    "iatb.visualization.alerts is deprecated. "
    "Please import from iatb.core.observability.alerting instead.",
    DeprecationWarning,
    stacklevel=2,
)

AlertSender = Callable[[str, str], None]


class TelegramAlertDispatcher:
    """Rate-limited Telegram alert sender (default 20 messages per minute).

    DEPRECATED: Use iatb.core.observability.alerting.TelegramAlerter instead.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        max_per_minute: int = 20,
        sender: AlertSender | None = None,
    ) -> None:
        if not bot_token.strip() or not chat_id.strip():
            msg = "bot_token and chat_id cannot be empty"
            raise ConfigError(msg)
        if max_per_minute <= 0:
            msg = "max_per_minute must be positive"
            raise ConfigError(msg)
        self._chat_id = chat_id
        self._max_per_minute = max_per_minute
        self._sender = sender or _build_sender(bot_token)
        self._sent_timestamps: list[datetime] = []

    def send_alert(
        self, alert_type: AlertType, message: str, now_utc: datetime | None = None
    ) -> bool:
        if not message.strip():
            msg = "message cannot be empty"
            raise ConfigError(msg)
        anchor = now_utc or datetime.now(UTC)
        if anchor.tzinfo != UTC:
            msg = "now_utc must be timezone-aware UTC datetime"
            raise ConfigError(msg)
        self._sent_timestamps = _keep_recent(self._sent_timestamps, anchor)
        if len(self._sent_timestamps) >= self._max_per_minute:
            return False
        payload = f"[{alert_type.value}] {message}"
        self._sender(self._chat_id, payload)
        self._sent_timestamps.append(anchor)
        return True


def _build_sender(bot_token: str) -> AlertSender:
    try:
        telegram = __import__("telegram")
    except ModuleNotFoundError as exc:
        msg = "python-telegram-bot dependency is required for alerts"
        raise ConfigError(msg) from exc
    bot_cls = getattr(telegram, "Bot", None)
    if not callable(bot_cls):
        msg = "telegram.Bot class is unavailable"
        raise ConfigError(msg)
    bot = bot_cls(token=bot_token)
    send_message = getattr(bot, "send_message", None)
    if not callable(send_message):
        msg = "telegram.Bot.send_message is unavailable"
        raise ConfigError(msg)
    return lambda chat_id, text: send_message(chat_id=chat_id, text=text)


__all__ = ["AlertType", "AlertLevel", "TelegramAlertDispatcher", "TelegramAlerter"]
