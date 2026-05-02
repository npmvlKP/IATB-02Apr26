import builtins
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

from iatb.core.observability.alerting import AlertLevel

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

    original_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "telegram":
            return SimpleNamespace(Bot=_Bot)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    dispatcher = TelegramAlertDispatcher(bot_token=test_bot_token, chat_id="chat")
    assert dispatcher.send_alert(
        AlertType.BREAKOUT, "hello", datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    )
    with pytest.raises(ConfigError, match="cannot be empty"):
        dispatcher.send_alert(AlertType.BREAKOUT, " ", datetime(2026, 1, 5, 4, 1, tzinfo=UTC))
    with pytest.raises(ConfigError, match="timezone-aware UTC"):
        dispatcher.send_alert(AlertType.BREAKOUT, "x", datetime(2026, 1, 5, 4, 0))  # noqa: DTZ001


def test_telegram_alert_dispatcher_rejects_empty_bot_token() -> None:
    with pytest.raises(ConfigError, match="bot_token and chat_id cannot be empty"):
        TelegramAlertDispatcher(bot_token="", chat_id="chat")


def test_telegram_alert_dispatcher_rejects_whitespace_bot_token() -> None:
    with pytest.raises(ConfigError, match="bot_token and chat_id cannot be empty"):
        TelegramAlertDispatcher(bot_token=" ", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_rejects_empty_chat_id() -> None:
    with pytest.raises(ConfigError, match="bot_token and chat_id cannot be empty"):
        TelegramAlertDispatcher(bot_token="token", chat_id="")  # noqa: S106


def test_telegram_alert_dispatcher_rejects_non_positive_max_per_minute() -> None:
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
    original_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "telegram":
            raise ModuleNotFoundError("No module named 'telegram'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    with pytest.raises(ConfigError, match="python-telegram-bot dependency is required"):
        TelegramAlertDispatcher(bot_token="token", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_sender_failure_no_bot_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "telegram":
            return SimpleNamespace(Bot=None)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    with pytest.raises(ConfigError, match="telegram.Bot class is unavailable"):
        TelegramAlertDispatcher(bot_token="token", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_sender_failure_bot_not_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "telegram":
            return SimpleNamespace(Bot="not_callable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    with pytest.raises(ConfigError, match="telegram.Bot class is unavailable"):
        TelegramAlertDispatcher(bot_token="token", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_sender_failure_no_send_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Bot:
        def __init__(self, token: str) -> None:
            _ = token

    original_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "telegram":
            return SimpleNamespace(Bot=_Bot)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    with pytest.raises(ConfigError, match="telegram.Bot.send_message is unavailable"):
        TelegramAlertDispatcher(bot_token="token", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_sender_failure_send_message_not_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Bot:
        def __init__(self, token: str) -> None:
            _ = token

        send_message = "not_callable"

    original_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "telegram":
            return SimpleNamespace(Bot=_Bot)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    with pytest.raises(ConfigError, match="telegram.Bot.send_message is unavailable"):
        TelegramAlertDispatcher(bot_token="token", chat_id="chat")  # noqa: S106


def test_telegram_alert_dispatcher_resets_after_minute_window() -> None:
    sent: list[tuple[str, str]] = []
    dispatcher = TelegramAlertDispatcher(
        bot_token="token",  # noqa: S106
        chat_id="chat",
        max_per_minute=2,
        sender=lambda chat_id, text: sent.append((chat_id, text)),
    )
    start = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    assert dispatcher.send_alert(AlertType.BREAKOUT, "msg-1", start)
    assert dispatcher.send_alert(AlertType.BREAKOUT, "msg-2", start + timedelta(seconds=30))
    assert len(sent) == 2
    assert dispatcher.send_alert(AlertType.BREAKOUT, "msg-3", start + timedelta(seconds=61))
    assert len(sent) == 3


class TestConsolidatedAlertLevel:
    def test_alert_level_same_as_core(self) -> None:
        assert AlertLevel.INFO == "INFO"
        assert AlertLevel.WARNING == "WARNING"
        assert AlertLevel.ERROR == "ERROR"
        assert AlertLevel.CRITICAL == "CRITICAL"

    def test_alert_type_same_as_core(self) -> None:
        from iatb.core.observability.alerting import AlertType as CoreAlertType

        assert AlertType.BREAKOUT is CoreAlertType.BREAKOUT
        assert AlertType.KILL_SWITCH is CoreAlertType.KILL_SWITCH
        assert AlertType.REGIME_CHANGE is CoreAlertType.REGIME_CHANGE
