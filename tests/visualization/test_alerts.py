import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    ScannerCandidate,
)
from iatb.visualization.alerts import (
    AlertType,
    TelegramAlertDispatcher,
    send_breakout_alert,
    send_kill_switch_alert,
    send_regime_change_alert,
    send_safe_exit_alert,
)

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


def test_send_breakout_alert() -> None:
    """Test send_breakout_alert formats and sends message correctly."""
    sent: list[tuple[str, str]] = []
    dispatcher = TelegramAlertDispatcher(
        bot_token="token",  # noqa: S106
        chat_id="chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
    )
    candidate = ScannerCandidate(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        pct_change=Decimal("5.25"),
        composite_score=Decimal("0.85"),
        sentiment_score=Decimal("0.80"),
        volume_ratio=Decimal("3.5"),
        exit_probability=Decimal("0.75"),
        is_tradable=True,
        regime="uptrend",  # type: ignore[arg-type]
        rank=1,
        timestamp_utc=datetime(2026, 1, 5, 10, 30, tzinfo=UTC),
        metadata={"adx": "45.5", "atr_pct": "2.1", "strength_score": "0.9"},
    )
    result = send_breakout_alert(dispatcher, candidate)
    assert result is True
    assert len(sent) == 1
    message = sent[0][1]
    assert "[breakout]" in message
    assert "RELIANCE" in message
    assert "+5.25%" in message
    assert "Rank: #1" in message


def test_send_regime_change_alert() -> None:
    """Test send_regime_change_alert formats and sends message correctly."""
    sent: list[tuple[str, str]] = []
    dispatcher = TelegramAlertDispatcher(
        bot_token="token",  # noqa: S106
        chat_id="chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
    )
    result = send_regime_change_alert(
        dispatcher,
        "sideways",  # type: ignore[arg-type]
        "uptrend",  # type: ignore[arg-type]
        "Breadth ratio exceeded 1.2",
        datetime(2026, 1, 5, 10, 30, tzinfo=UTC),
    )
    assert result is True
    assert len(sent) == 1
    message = sent[0][1]
    assert "[regime_change]" in message
    assert "From: sideways" in message
    assert "To: uptrend" in message
    assert "Breadth ratio exceeded 1.2" in message


def test_send_safe_exit_alert() -> None:
    """Test send_safe_exit_alert formats and sends message correctly."""
    sent: list[tuple[str, str]] = []
    dispatcher = TelegramAlertDispatcher(
        bot_token="token",  # noqa: S106
        chat_id="chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
    )
    result = send_safe_exit_alert(
        dispatcher,
        symbol="INFY",
        entry_price=Decimal("1500.00"),
        exit_price=Decimal("1550.00"),
        quantity=Decimal("10"),
        pnl=Decimal("500.00"),
        reason="Take profit target reached",
        now_utc=datetime(2026, 1, 5, 10, 30, tzinfo=UTC),
    )
    assert result is True
    assert len(sent) == 1
    message = sent[0][1]
    assert "[safe_exit]" in message
    assert "INFY" in message
    assert "Entry: 1500.00" in message
    assert "Exit: 1550.00" in message
    assert "+500.00" in message
    assert "Take profit target reached" in message


def test_send_kill_switch_alert() -> None:
    """Test send_kill_switch_alert formats and sends message correctly."""
    sent: list[tuple[str, str]] = []
    dispatcher = TelegramAlertDispatcher(
        bot_token="token",  # noqa: S106
        chat_id="chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
    )
    result = send_kill_switch_alert(
        dispatcher,
        "Daily loss limit exceeded: -5%",
        datetime(2026, 1, 5, 10, 30, tzinfo=UTC),
    )
    assert result is True
    assert len(sent) == 1
    message = sent[0][1]
    assert "[kill_switch]" in message
    assert "KILL SWITCH ACTIVATED" in message
    assert "Daily loss limit exceeded: -5%" in message
    assert "All trading operations halted" in message


def test_alert_type_safe_exit_exists() -> None:
    """Test that SAFE_EXIT alert type exists."""
    assert AlertType.SAFE_EXIT.value == "safe_exit"


def test_breakout_alert_with_negative_change() -> None:
    """Test breakout alert with negative percentage change."""
    sent: list[tuple[str, str]] = []
    dispatcher = TelegramAlertDispatcher(
        bot_token="token",  # noqa: S106
        chat_id="chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
    )
    candidate = ScannerCandidate(
        symbol="TATASTEEL",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        pct_change=Decimal("-3.20"),
        composite_score=Decimal("0.75"),
        sentiment_score=Decimal("-0.85"),
        volume_ratio=Decimal("2.5"),
        exit_probability=Decimal("0.60"),
        is_tradable=True,
        regime="downtrend",  # type: ignore[arg-type]
        rank=1,
        timestamp_utc=datetime(2026, 1, 5, 10, 30, tzinfo=UTC),
        metadata={"adx": "38.2", "atr_pct": "1.8", "strength_score": "0.7"},
    )
    result = send_breakout_alert(dispatcher, candidate)
    assert result is True
    assert len(sent) == 1
    message = sent[0][1]
    assert "-3.20%" in message


def test_safe_exit_alert_with_loss() -> None:
    """Test safe exit alert with negative PnL."""
    sent: list[tuple[str, str]] = []
    dispatcher = TelegramAlertDispatcher(
        bot_token="token",  # noqa: S106
        chat_id="chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
    )
    result = send_safe_exit_alert(
        dispatcher,
        symbol="HDFC",
        entry_price=Decimal("1600.00"),
        exit_price=Decimal("1580.00"),
        quantity=Decimal("10"),
        pnl=Decimal("-200.00"),
        reason="Stop loss triggered",
        now_utc=datetime(2026, 1, 5, 10, 30, tzinfo=UTC),
    )
    assert result is True
    assert len(sent) == 1
    message = sent[0][1]
    assert "-200.00" in message
    assert "Stop loss triggered" in message
