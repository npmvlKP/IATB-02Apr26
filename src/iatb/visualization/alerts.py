"""
Telegram alert helpers with deterministic rate limiting.
Provides proven python-telegram-bot integration for breakout, regime change,
and safe exit alerts with 20 msg/min rate limiting.
"""

import importlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.scanner.instrument_scanner import ScannerCandidate

AlertSender = Callable[[str, str], None]


class AlertType(StrEnum):
    BREAKOUT = "breakout"
    REGIME_CHANGE = "regime_change"
    KILL_SWITCH = "kill_switch"
    SAFE_EXIT = "safe_exit"


class TelegramAlertDispatcher:
    """Rate-limited Telegram alert sender (default 20 messages per minute)."""

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
        telegram = importlib.import_module("telegram")
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


def _keep_recent(history: list[datetime], now_utc: datetime) -> list[datetime]:
    threshold = now_utc - timedelta(minutes=1)
    return [stamp for stamp in history if stamp >= threshold]


def send_breakout_alert(
    dispatcher: TelegramAlertDispatcher,
    candidate: ScannerCandidate,
    now_utc: datetime | None = None,
) -> bool:
    """Send formatted breakout alert for scanner candidate."""
    message = (
        f"🚀 BREAKOUT DETECTED\n"
        f"Symbol: {candidate.symbol}\n"
        f"Exchange: {candidate.exchange.value}\n"
        f"Category: {candidate.category.value}\n"
        f"Change: {candidate.pct_change:+.2f}%\n"
        f"Composite Score: {candidate.composite_score:.2f}\n"
        f"Sentiment: {candidate.sentiment_score:+.2f}\n"
        f"Volume Ratio: {candidate.volume_ratio:.2f}\n"
        f"Exit Probability: {candidate.exit_probability:.2%}\n"
        f"Rank: #{candidate.rank}\n"
        f"Time: {candidate.timestamp_utc.isoformat()}"
    )
    return dispatcher.send_alert(AlertType.BREAKOUT, message, now_utc)


def send_regime_change_alert(
    dispatcher: TelegramAlertDispatcher,
    old_regime: MarketRegime | str,
    new_regime: MarketRegime | str,
    context: str = "",
    now_utc: datetime | None = None,
) -> bool:
    """Send formatted regime change alert."""
    old_val = old_regime.value if hasattr(old_regime, "value") else str(old_regime)
    new_val = new_regime.value if hasattr(new_regime, "value") else str(new_regime)
    message = (
        f"📊 REGIME CHANGE\n"
        f"From: {old_val}\n"
        f"To: {new_val}\n"
        f"{context}\n"
        f"Time: {(now_utc or datetime.now(UTC)).isoformat()}"
    )
    return dispatcher.send_alert(AlertType.REGIME_CHANGE, message, now_utc)


def send_safe_exit_alert(
    dispatcher: TelegramAlertDispatcher,
    symbol: str,
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: Decimal,
    pnl: Decimal,
    reason: str = "",
    now_utc: datetime | None = None,
) -> bool:
    """Send formatted safe exit alert."""
    pnl_pct = (pnl / (entry_price * quantity)) * Decimal("100")
    message = (
        f"✅ SAFE EXIT EXECUTED\n"
        f"Symbol: {symbol}\n"
        f"Entry: {entry_price:.2f}\n"
        f"Exit: {exit_price:.2f}\n"
        f"Quantity: {quantity}\n"
        f"PnL: {pnl:+.2f} ({pnl_pct:+.2f}%)\n"
        f"Reason: {reason}\n"
        f"Time: {(now_utc or datetime.now(UTC)).isoformat()}"
    )
    return dispatcher.send_alert(AlertType.SAFE_EXIT, message, now_utc)


def send_kill_switch_alert(
    dispatcher: TelegramAlertDispatcher,
    reason: str,
    now_utc: datetime | None = None,
) -> bool:
    """Send formatted kill switch alert."""
    message = (
        f"🛑 KILL SWITCH ACTIVATED\n"
        f"Reason: {reason}\n"
        f"Time: {(now_utc or datetime.now(UTC)).isoformat()}\n"
        f"All trading operations halted."
    )
    return dispatcher.send_alert(AlertType.KILL_SWITCH, message, now_utc)
