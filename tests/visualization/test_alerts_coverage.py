"""
Coverage augmentation tests for visualization/alerts.py.

These tests complement test_alerts.py by adding behavioral coverage
for boundary conditions, isolation, export integrity, and deprecation
warning behavior.
"""

from __future__ import annotations

import builtins
import importlib
import warnings
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import iatb.visualization.alerts as alerts_mod
import pytest
from iatb.core.exceptions import ConfigError

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from iatb.visualization.alerts import (
        AlertLevel,
        AlertType,
        TelegramAlertDispatcher,
        TelegramAlerter,
        _build_sender,
    )


UTC_START = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
TEST_TOKEN = "test-bot-token"  # noqa: S105


class TestSendAlertDefaultNowUtc:
    """send_alert with now_utc=None uses datetime.now(UTC) internally."""

    def test_sends_successfully_without_explicit_now_utc(self) -> None:
        sent: list[tuple[str, str]] = []
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            sender=lambda c, t: sent.append((c, t)),
        )
        result = dispatcher.send_alert(AlertType.BREAKOUT, "automatic-time")
        assert result is True

        assert len(sent) == 1
        assert sent[0][1] == "[breakout] automatic-time"

    def test_rate_limit_works_with_default_now_utc(self) -> None:
        sent: list[tuple[str, str]] = []
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            max_per_minute=1,
            sender=lambda c, t: sent.append((c, t)),
        )
        assert dispatcher.send_alert(AlertType.BREAKOUT, "first")
        assert not dispatcher.send_alert(AlertType.BREAKOUT, "second")
        assert len(sent) == 1


class TestRateLimitBoundaries:
    """Rate limiting at exact boundary values."""

    def test_max_per_minute_one_allows_exactly_one(self) -> None:
        sent: list[tuple[str, str]] = []
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            max_per_minute=1,
            sender=lambda c, t: sent.append((c, t)),
        )
        now = UTC_START
        assert dispatcher.send_alert(AlertType.BREAKOUT, "msg-1", now)
        assert not dispatcher.send_alert(
            AlertType.BREAKOUT, "msg-2", now + timedelta(seconds=1)
        )
        assert not dispatcher.send_alert(
            AlertType.BREAKOUT, "msg-3", now + timedelta(seconds=59)
        )

    def test_max_per_minute_one_resets_after_minute(self) -> None:
        sent: list[tuple[str, str]] = []
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            max_per_minute=1,
            sender=lambda c, t: sent.append((c, t)),
        )
        now = UTC_START
        assert dispatcher.send_alert(AlertType.BREAKOUT, "msg-1", now)
        assert not dispatcher.send_alert(
            AlertType.BREAKOUT, "msg-2", now + timedelta(seconds=30)
        )
        assert dispatcher.send_alert(
            AlertType.BREAKOUT, "msg-3", now + timedelta(seconds=61)
        )
        assert len(sent) == 2

    def test_max_per_minute_five_allows_five_consecutive(self) -> None:
        sent: list[tuple[str, str]] = []
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            max_per_minute=5,
            sender=lambda c, t: sent.append((c, t)),
        )
        now = UTC_START
        for i in range(5):
            assert dispatcher.send_alert(
                AlertType.BREAKOUT, f"msg-{i}", now + timedelta(seconds=i)
            )
        assert not dispatcher.send_alert(
            AlertType.BREAKOUT, "msg-6", now + timedelta(seconds=5)
        )
        assert len(sent) == 5

    def test_max_per_minute_ten_allows_ten_consecutive(self) -> None:
        sent: list[tuple[str, str]] = []
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            max_per_minute=10,
            sender=lambda c, t: sent.append((c, t)),
        )
        now = UTC_START
        for i in range(10):
            assert dispatcher.send_alert(
                AlertType.BREAKOUT, f"msg-{i}", now + timedelta(seconds=i * 2)
            )
        assert not dispatcher.send_alert(
            AlertType.BREAKOUT, "overflow", now + timedelta(seconds=20)
        )
        assert len(sent) == 10


class TestAlertTypePayloadFormatting:
    """Payload formatting with all AlertType values."""

    def test_breakout_payload_format(self) -> None:
        sent: list[tuple[str, str]] = []
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            sender=lambda c, t: sent.append((c, t)),
        )
        dispatcher.send_alert(AlertType.BREAKOUT, "price-surge", UTC_START)
        assert sent[0][1] == "[breakout] price-surge"

    def test_kill_switch_payload_format(self) -> None:
        sent: list[tuple[str, str]] = []
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            sender=lambda c, t: sent.append((c, t)),
        )
        dispatcher.send_alert(AlertType.KILL_SWITCH, "emergency-stop", UTC_START)
        assert sent[0][1] == "[kill_switch] emergency-stop"

    def test_regime_change_payload_format(self) -> None:
        sent: list[tuple[str, str]] = []
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            sender=lambda c, t: sent.append((c, t)),
        )
        dispatcher.send_alert(AlertType.REGIME_CHANGE, "bull-to-bear", UTC_START)
        assert sent[0][1] == "[regime_change] bull-to-bear"


class TestSenderCallbackArguments:
    """Sender callback receives correct chat_id and formatted payload."""

    def test_chat_id_passed_to_sender(self) -> None:
        captured: dict[str, str] = {}

        def capture(chat_id: str, text: str) -> None:
            captured["chat_id"] = chat_id
            captured["text"] = text

        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="target-chat-42",
            sender=capture,
        )
        dispatcher.send_alert(AlertType.BREAKOUT, "hello", UTC_START)
        assert captured["chat_id"] == "target-chat-42"

    def test_payload_includes_alert_type_prefix_and_message(self) -> None:
        sent: list[tuple[str, str]] = []
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            sender=lambda c, t: sent.append((c, t)),
        )
        dispatcher.send_alert(AlertType.KILL_SWITCH, "liquidation-warning", UTC_START)
        assert sent[0][1].startswith("[kill_switch]")
        assert "liquidation-warning" in sent[0][1]


class TestBuildSenderTokenPropagation:
    """_build_sender passes bot_token through to Bot constructor."""

    def test_bot_token_passed_to_constructor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_tokens: list[str] = []

        class _Bot:
            def __init__(self, token: str) -> None:
                captured_tokens.append(token)

            def send_message(self, chat_id: str, text: str) -> None:
                pass

        def _mock_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "telegram":
                return SimpleNamespace(Bot=_Bot)
            return original_import(name, *args, **kwargs)

        original_import = builtins.__import__
        monkeypatch.setattr(builtins, "__import__", _mock_import)
        sender = _build_sender("custom-token-99")
        assert callable(sender)
        sender("chat", "test")
        assert captured_tokens == ["custom-token-99"]


class TestDispatcherIsolation:
    """Multiple dispatcher instances have independent rate-limit state."""

    def test_independent_rate_limits(self) -> None:
        sent_a: list[tuple[str, str]] = []
        sent_b: list[tuple[str, str]] = []
        dispatcher_a = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-a",
            max_per_minute=1,
            sender=lambda c, t: sent_a.append((c, t)),
        )
        dispatcher_b = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-b",
            max_per_minute=1,
            sender=lambda c, t: sent_b.append((c, t)),
        )
        now = UTC_START
        assert dispatcher_a.send_alert(AlertType.BREAKOUT, "a-1", now)
        assert dispatcher_b.send_alert(AlertType.BREAKOUT, "b-1", now)
        assert not dispatcher_a.send_alert(
            AlertType.BREAKOUT, "a-2", now + timedelta(seconds=1)
        )
        assert not dispatcher_b.send_alert(
            AlertType.BREAKOUT, "b-2", now + timedelta(seconds=1)
        )
        assert len(sent_a) == 1
        assert len(sent_b) == 1

    def test_different_max_per_minute_independent(self) -> None:
        sent_a: list[tuple[str, str]] = []
        sent_b: list[tuple[str, str]] = []
        dispatcher_a = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-a",
            max_per_minute=2,
            sender=lambda c, t: sent_a.append((c, t)),
        )
        dispatcher_b = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-b",
            max_per_minute=1,
            sender=lambda c, t: sent_b.append((c, t)),
        )
        now = UTC_START
        assert dispatcher_a.send_alert(AlertType.BREAKOUT, "a-1", now)
        assert dispatcher_b.send_alert(AlertType.BREAKOUT, "b-1", now)
        assert dispatcher_a.send_alert(
            AlertType.BREAKOUT, "a-2", now + timedelta(seconds=1)
        )
        assert not dispatcher_b.send_alert(
            AlertType.BREAKOUT, "b-2", now + timedelta(seconds=1)
        )
        assert len(sent_a) == 2
        assert len(sent_b) == 1


class TestInitValidationEdgeCases:
    """Additional init validation edge cases beyond existing tests."""

    def test_rejects_negative_max_per_minute_with_large_value(self) -> None:
        with pytest.raises(ConfigError, match="max_per_minute must be positive"):
            TelegramAlertDispatcher(
                bot_token=TEST_TOKEN,
                chat_id="chat-id",
                max_per_minute=-1000,
            )

    def test_accepts_large_max_per_minute(self) -> None:
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            max_per_minute=9999,
            sender=lambda c, t: None,
        )
        assert dispatcher.send_alert(AlertType.BREAKOUT, "ok", UTC_START)


class TestModuleExports:
    """Module __all__ exports and re-export integrity."""

    def test_alert_type_in_all(self) -> None:
        from iatb.visualization.alerts import __all__ as exports

        assert "AlertType" in exports

    def test_alert_level_in_all(self) -> None:
        from iatb.visualization.alerts import __all__ as exports

        assert "AlertLevel" in exports

    def test_telegram_alert_dispatcher_in_all(self) -> None:
        from iatb.visualization.alerts import __all__ as exports

        assert "TelegramAlertDispatcher" in exports

    def test_telegram_alerter_in_all(self) -> None:
        from iatb.visualization.alerts import __all__ as exports

        assert "TelegramAlerter" in exports

    def test_telegram_alerter_re_export_is_core_class(self) -> None:
        from iatb.core.observability.alerting import TelegramAlerter as CoreAlerter

        assert TelegramAlerter is CoreAlerter

    def test_alert_type_re_export_is_core_class(self) -> None:
        from iatb.core.observability.alerting import AlertType as CoreAlertType

        assert AlertType is CoreAlertType

    def test_alert_level_re_export_is_core_class(self) -> None:
        from iatb.core.observability.alerting import AlertLevel as CoreAlertLevel

        assert AlertLevel is CoreAlertLevel


class TestDeprecationWarning:
    """Module-level deprecation warning is raised on import."""

    def test_direct_import_raises_deprecation_warning(self) -> None:
        with pytest.warns(
            DeprecationWarning, match="iatb.visualization.alerts is deprecated"
        ):
            importlib.reload(alerts_mod)


class TestTimeZoneValidation:
    """Time zone validation for send_alert now_utc parameter."""

    def test_rejects_non_utc_timezone(self) -> None:
        import zoneinfo

        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            sender=lambda c, t: None,
        )
        ist = zoneinfo.ZoneInfo("Asia/Kolkata")
        non_utc_ts = datetime(2026, 1, 5, 9, 30, tzinfo=ist)
        with pytest.raises(ConfigError, match="timezone-aware UTC"):
            dispatcher.send_alert(AlertType.BREAKOUT, "x", non_utc_ts)

    def test_accepts_utc_timezone(self) -> None:
        dispatcher = TelegramAlertDispatcher(
            bot_token=TEST_TOKEN,
            chat_id="chat-id",
            sender=lambda c, t: None,
        )
        result = dispatcher.send_alert(AlertType.BREAKOUT, "valid", UTC_START)
        assert result is True
