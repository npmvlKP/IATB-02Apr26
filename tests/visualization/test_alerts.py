import random
import warnings
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from iatb.visualization.alerts import AlertType, TelegramAlertDispatcher

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_telegram_alert_dispatcher_rate_limit_with_injected_sender() -> None:
    sent: list[tuple[str, str]] = []
    test_bot_token = "test-bot-token"  # noqa: S105
    dispatcher = TelegramAlertDispatcher(
        bot_token=test_bot_token,
        chat_id="chat",
        max_per_minute=2,
        sender=lambda chat_id, text: sent.append((chat_id, text)),
    )
    start = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    assert dispatcher.send_alert(AlertType.BREAKOUT, "msg-1", start)
    assert dispatcher.send_alert(AlertType.KILL_SWITCH, "msg-2", start + timedelta(seconds=1))
    assert not dispatcher.send_alert(AlertType.REGIME_CHANGE, "msg-3", start + timedelta(seconds=2))
    assert len(sent) == 2
    assert sent[0][1].startswith("[breakout]")


def test_telegram_alert_dispatcher_default_sender_and_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, str]] = []
    test_bot_token = "test-bot-token"  # noqa: S105

    class _Bot:
        def __init__(self, token: str) -> None:
            _ = token

        def send_message(self, chat_id: str, text: str) -> None:
            sent.append((chat_id, text))

    monkeypatch.setattr(
        "iatb.visualization.alerts.importlib.import_module", lambda _: SimpleNamespace(Bot=_Bot)
    )
    dispatcher = TelegramAlertDispatcher(bot_token=test_bot_token, chat_id="chat")
    assert dispatcher.send_alert(
        AlertType.BREAKOUT, "hello", datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    )
    with pytest.raises(ConfigError, match="cannot be empty"):
        dispatcher.send_alert(AlertType.BREAKOUT, "   ", datetime(2026, 1, 5, 4, 1, tzinfo=UTC))
    with pytest.raises(ConfigError, match="timezone-aware UTC"):
        dispatcher.send_alert(AlertType.BREAKOUT, "x", datetime(2026, 1, 5, 4, 0))  # noqa: DTZ001


def test_telegram_alert_dispatcher_rejects_empty_bot_token() -> None:
    """Test that empty bot_token raises ConfigError."""
    with pytest.raises(ConfigError, match="bot_token and chat_id cannot be empty"):
        TelegramAlertDispatcher(bot_token="", chat_id="chat")


def test_telegram_alert_dispatcher_rejects_whitespace_bot_token() -> None:
    """Test that whitespace-only bot_token raises ConfigError."""
    with pytest.raises(ConfigError, match="bot_token and chat_id cannot be empty"):
        TelegramAlertDispatcher(bot_token="   ", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_rejects_empty_chat_id() -> None:
    """Test that empty chat_id raises ConfigError."""
    with pytest.raises(ConfigError, match="bot_token and chat_id cannot be empty"):
        TelegramAlertDispatcher(bot_token="token", chat_id="")  # noqa: S106


def test_telegram_alert_dispatcher_rejects_non_positive_max_per_minute() -> None:
    """Test that non-positive max_per_minute raises ConfigError."""
    with pytest.raises(ConfigError, match="max_per_minute must be positive"):
        TelegramAlertDispatcher(
            bot_token="token",  # noqa: S106
            chat_id="chat",
            max_per_minute=0,
        )
    with pytest.raises(ConfigError, match="max_per_minute must be positive"):
        TelegramAlertDispatcher(
            bot_token="token",  # noqa: S106
            chat_id="chat",
            max_per_minute=-1,
        )


def test_telegram_alert_dispatcher_sender_failure_missing_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that missing telegram module raises ConfigError."""
    monkeypatch.setattr(
        "iatb.visualization.alerts.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError("No module named 'telegram'")),
    )
    with pytest.raises(ConfigError, match="python-telegram-bot dependency is required"):
        TelegramAlertDispatcher(bot_token="token", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_sender_failure_no_bot_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that missing Bot class raises ConfigError."""
    monkeypatch.setattr(
        "iatb.visualization.alerts.importlib.import_module",
        lambda _: SimpleNamespace(Bot=None),
    )
    with pytest.raises(ConfigError, match="telegram.Bot class is unavailable"):
        TelegramAlertDispatcher(bot_token="token", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_sender_failure_bot_not_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that non-callable Bot class raises ConfigError."""
    monkeypatch.setattr(
        "iatb.visualization.alerts.importlib.import_module",
        lambda _: SimpleNamespace(Bot="not_callable"),
    )
    with pytest.raises(ConfigError, match="telegram.Bot class is unavailable"):
        TelegramAlertDispatcher(bot_token="token", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_sender_failure_no_send_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that missing send_message method raises ConfigError."""

    class _Bot:
        def __init__(self, token: str) -> None:
            _ = token

    monkeypatch.setattr(
        "iatb.visualization.alerts.importlib.import_module",
        lambda _: SimpleNamespace(Bot=_Bot),
    )
    with pytest.raises(ConfigError, match="telegram.Bot.send_message is unavailable"):
        TelegramAlertDispatcher(bot_token="token", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_sender_failure_send_message_not_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that non-callable send_message raises ConfigError."""

    class _Bot:
        def __init__(self, token: str) -> None:
            _ = token

        send_message = "not_callable"

    monkeypatch.setattr(
        "iatb.visualization.alerts.importlib.import_module",
        lambda _: SimpleNamespace(Bot=_Bot),
    )
    with pytest.raises(ConfigError, match="telegram.Bot.send_message is unavailable"):
        TelegramAlertDispatcher(bot_token="token", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_resets_after_minute_window() -> None:
    """Test that rate limit resets after 1 minute window."""
    sent: list[tuple[str, str]] = []
    dispatcher = TelegramAlertDispatcher(
        bot_token="token",  # noqa: S106
        chat_id="chat",
        max_per_minute=2,
        sender=lambda chat_id, text: sent.append((chat_id, text)),
    )
    start = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    # Send 2 messages (at limit)
    assert dispatcher.send_alert(AlertType.BREAKOUT, "msg-1", start)
    assert dispatcher.send_alert(AlertType.BREAKOUT, "msg-2", start + timedelta(seconds=30))
    assert len(sent) == 2
    # After 1 minute, should be able to send again
    assert dispatcher.send_alert(AlertType.BREAKOUT, "msg-3", start + timedelta(seconds=61))
    assert len(sent) == 3
