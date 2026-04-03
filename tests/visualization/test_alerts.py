from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from iatb.core.exceptions import ConfigError
from iatb.visualization.alerts import AlertType, TelegramAlertDispatcher


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
