"""Supplemental coverage tests for observability alerting module.

Covers: Alert dataclass defaults, AlertLevel/AlertType enums, AlertChannel ABC,
TelegramAlerter disabled/rate-limited/empty-message paths, send_trade_alert,
send_error_alert, send_health_alert, send_pnl_alert, send_model_alert,
send_data_source_failure_alert, send_fallback_source_alert,
send_token_expiry_alert, send_with_actions, send_kill_switch_alert
with non-UTC datetime, _format_message with context, _keep_recent,
EmailChannel enabled/disabled/send error, WebhookChannel URL validation,
AlertRulesEngine add/remove/evaluate, default rule conditions,
AlertThrottler should_send/record_sent/reset, AlertAcknowledgmentTracker
register/acknowledge/is_acknowledged/get_unacknowledged/cleanup,
MultiChannelAlertManager send_alert/evaluate_and_alert/acknowledge/cleanup,
get_alerter singleton, get_multi_channel_manager singleton.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.observability.alerting import (
    Alert,
    AlertAcknowledgmentTracker,
    AlertChannel,
    AlertLevel,
    AlertRule,
    AlertRulesEngine,
    AlertThrottler,
    AlertType,
    EmailChannel,
    MultiChannelAlertManager,
    TelegramAlerter,
    WebhookChannel,
    _keep_recent,
    get_alerter,
    get_multi_channel_manager,
)


class TestAlertLevelEnum:
    def test_info_value(self) -> None:
        assert AlertLevel.INFO == "INFO"

    def test_warning_value(self) -> None:
        assert AlertLevel.WARNING == "WARNING"

    def test_error_value(self) -> None:
        assert AlertLevel.ERROR == "ERROR"

    def test_critical_value(self) -> None:
        assert AlertLevel.CRITICAL == "CRITICAL"


class TestAlertTypeEnum:
    def test_breakout_value(self) -> None:
        assert AlertType.BREAKOUT == "breakout"

    def test_regime_change_value(self) -> None:
        assert AlertType.REGIME_CHANGE == "regime_change"

    def test_kill_switch_value(self) -> None:
        assert AlertType.KILL_SWITCH == "kill_switch"


class TestAlertDataclass:
    def test_default_values(self) -> None:
        alert = Alert(message="test")
        assert alert.message == "test"
        assert alert.level == AlertLevel.INFO
        assert alert.context == {}
        assert alert.rule_name is None
        assert alert.alert_id is None

    def test_custom_values(self) -> None:
        alert = Alert(
            message="custom",
            level=AlertLevel.ERROR,
            context={"key": "value"},
            rule_name="rule-1",
            alert_id="id-1",
        )
        assert alert.level == AlertLevel.ERROR
        assert alert.context == {"key": "value"}
        assert alert.rule_name == "rule-1"
        assert alert.alert_id == "id-1"

    def test_timestamp_is_utc_aware(self) -> None:
        alert = Alert(message="ts-test")
        assert alert.timestamp.tzinfo is not None


class TestAlertChannelABC:
    def test_abstract_send_requires_implementation(self) -> None:
        with pytest.raises(TypeError):
            AlertChannel()  # type: ignore[abstract]

    def test_concrete_subclass(self) -> None:
        class ConcreteChannel(AlertChannel):
            def send(self, alert: Alert) -> bool:
                return True

        channel = ConcreteChannel(enabled=True)
        assert channel.enabled is True
        alert = Alert(message="test")
        assert channel.send(alert) is True

    def test_disabled_channel(self) -> None:
        class ConcreteChannel(AlertChannel):
            def send(self, alert: Alert) -> bool:
                return True

        channel = ConcreteChannel(enabled=False)
        assert channel.enabled is False


class TestTelegramAlerterDisabled:
    def test_disabled_without_token(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            alerter = TelegramAlerter(enabled=True)
            assert alerter.enabled is False

    def test_disabled_without_chat_id(self) -> None:
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "fake-token"}, clear=False):
            alerter = TelegramAlerter(bot_token="fake-token", enabled=True)
            assert alerter.enabled is False

    def test_send_alert_disabled_returns_false(self) -> None:
        alerter = TelegramAlerter(enabled=False)
        assert alerter.send_alert("test") is False

    def test_send_with_actions_disabled_returns_false(self) -> None:
        alerter = TelegramAlerter(enabled=False)
        assert alerter.send_with_actions("test") is False


class TestTelegramAlerterEmptyMessage:
    def test_empty_message_returns_false(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        alerter.enabled = True
        alerter.bot = MagicMock()
        with patch("iatb.core.observability.alerting._LOGGER"):
            result = alerter.send_alert(" ")
        assert result is False

    def test_empty_string_returns_false(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        alerter.enabled = True
        alerter.bot = MagicMock()
        with patch("iatb.core.observability.alerting._LOGGER"):
            result = alerter.send_alert("")
            assert result is False


class TestTelegramAlerterRateLimiting:
    def test_rate_limited_after_max_per_minute(self) -> None:
        alerter = TelegramAlerter(
            bot_token="fake-token",
            chat_id="123",
            enabled=True,
            max_per_minute=2,
        )
        alerter.enabled = True
        alerter.bot = MagicMock()
        now = datetime.now(UTC)
        alerter._sent_timestamps = [now, now]
        with patch("iatb.core.observability.alerting._LOGGER"):
            result = alerter.send_alert("rate-test")
            assert result is False

    def test_rate_resets_after_minute(self) -> None:
        alerter = TelegramAlerter(
            bot_token="fake-token",
            chat_id="123",
            enabled=True,
            max_per_minute=2,
        )
        old = datetime.now(UTC) - timedelta(seconds=61)
        alerter._sent_timestamps = [old, old]
        result = alerter.send_alert("after-minute")
        assert result is True


class TestTelegramAlerterTradeAlert:
    def test_send_trade_alert_returns_true(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True):
            result = alerter.send_trade_alert(
                ticker="RELIANCE",
                side="BUY",
                quantity=100,
                price=Decimal("2500.50"),
            )
            assert result is True

    def test_send_trade_alert_with_timestamp(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        ts = datetime(2026, 5, 15, 10, 0, tzinfo=UTC)
        with patch.object(alerter, "send_alert", return_value=True):
            result = alerter.send_trade_alert(
                ticker="NIFTY",
                side="SELL",
                quantity=50,
                price=Decimal("22000"),
                timestamp=ts,
            )
            assert result is True


class TestTelegramAlerterErrorAlert:
    def test_send_error_alert_with_exc_type(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True):
            result = alerter.send_error_alert(
                component="Engine", error_message="crash", exc_type="RuntimeError"
            )
            assert result is True

    def test_send_error_alert_without_exc_type(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True):
            result = alerter.send_error_alert(component="Engine", error_message="crash")
            assert result is True


class TestTelegramAlerterHealthAlert:
    def test_down_status_is_critical(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True) as mock:
            alerter.send_health_alert(service="DB", status="DOWN")
            call_args = mock.call_args
            assert call_args[0][1] == AlertLevel.CRITICAL

    def test_degraded_status_is_warning(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True) as mock:
            alerter.send_health_alert(service="DB", status="DEGRADED")
            call_args = mock.call_args
            assert call_args[0][1] == AlertLevel.WARNING

    def test_health_alert_with_details(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True):
            result = alerter.send_health_alert(
                service="Redis", status="DOWN", details="Connection refused"
            )
            assert result is True


class TestTelegramAlerterPnLAlert:
    def test_pnl_alert_with_daily(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True):
            result = alerter.send_pnl_alert(
                pnl=Decimal("5000"), daily_pnl=Decimal("1200"), open_positions=3
            )
            assert result is True

    def test_pnl_alert_negative_daily(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True):
            result = alerter.send_pnl_alert(
                pnl=Decimal("-500"), daily_pnl=Decimal("-200")
            )
            assert result is True

    def test_pnl_alert_without_daily(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True):
            result = alerter.send_pnl_alert(pnl=Decimal("1000"))
            assert result is True


class TestTelegramAlerterModelAlert:
    def test_model_not_available_is_error(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True) as mock:
            alerter.send_model_alert(model_name="v2", status="OFFLINE")
            call_args = mock.call_args
            assert call_args[0][1] == AlertLevel.ERROR

    def test_model_available_is_info(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True) as mock:
            alerter.send_model_alert(model_name="v2", status="AVAILABLE")
            call_args = mock.call_args
            assert call_args[0][1] == AlertLevel.INFO

    def test_model_alert_with_details(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True):
            result = alerter.send_model_alert(
                model_name="v3", status="DEGRADED", details="High latency"
            )
            assert result is True


class TestTelegramAlerterDataSourceAlerts:
    def test_data_source_failure_alert(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True) as mock:
            alerter.send_data_source_failure_alert(
                source="KiteProvider", failure_count=5, time_window="10 minutes"
            )
            call_args = mock.call_args
            assert call_args[0][1] == AlertLevel.CRITICAL

    def test_fallback_source_alert_with_reason(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True) as mock:
            alerter.send_fallback_source_alert(
                from_source="KiteProvider",
                to_source="YahooProvider",
                reason="Timeout",
            )
            call_args = mock.call_args
            assert call_args[0][1] == AlertLevel.WARNING

    def test_fallback_source_alert_without_reason(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True):
            result = alerter.send_fallback_source_alert(
                from_source="KiteProvider", to_source="YahooProvider"
            )
            assert result is True


class TestTelegramAlerterTokenExpiry:
    def test_critical_when_under_5_minutes(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True) as mock:
            alerter.send_token_expiry_alert(token_type="Kite", minutes_remaining=3)
            call_args = mock.call_args
            assert call_args[0][1] == AlertLevel.CRITICAL

    def test_warning_when_over_5_minutes(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True) as mock:
            alerter.send_token_expiry_alert(token_type="Kite", minutes_remaining=10)
            call_args = mock.call_args
            assert call_args[0][1] == AlertLevel.WARNING

    def test_boundary_at_5_minutes_is_critical(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "send_alert", return_value=True) as mock:
            alerter.send_token_expiry_alert(token_type="Kite", minutes_remaining=5)
            call_args = mock.call_args
            assert call_args[0][1] == AlertLevel.CRITICAL


class TestTelegramAlerterSendWithActions:
    def test_send_with_buttons(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "_send_message_async"):
            result = alerter.send_with_actions(
                message="Action needed",
                buttons=[("Acknowledge", "ack"), ("Dismiss", "dismiss")],
                level=AlertLevel.WARNING,
            )
            assert result is True

    def test_send_without_buttons(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        with patch.object(alerter, "_send_message_async"):
            result = alerter.send_with_actions(message="No buttons")
            assert result is True


class TestTelegramAlerterKillSwitchAlert:
    def test_non_utc_datetime_returns_false(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        naive_dt = datetime(2026, 5, 15, 10, 0)
        result = alerter.send_kill_switch_alert(
            reason="Max loss exceeded", engaged_utc=naive_dt
        )
        assert result is False

    def test_utc_datetime_passes(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        utc_dt = datetime(2026, 5, 15, 10, 0, tzinfo=UTC)
        with patch.object(alerter, "send_alert", return_value=True):
            result = alerter.send_kill_switch_alert(
                reason="Max loss exceeded", engaged_utc=utc_dt
            )
            assert result is True


class TestFormatMessage:
    def test_format_with_context(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        result = alerter._format_message(
            "test message", AlertLevel.ERROR, {"key1": "val1"}
        )
        assert "key1" in result
        assert "val1" in result

    def test_format_without_context(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        result = alerter._format_message("test message", AlertLevel.INFO)
        assert "test message" in result

    def test_format_unknown_level_defaults_to_info(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        result = alerter._format_message("test", "UNKNOWN_LEVEL")
        assert "INFO" in result


class TestKeepRecent:
    def test_filters_old_timestamps(self) -> None:
        now = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)
        old = now - timedelta(seconds=120)
        recent = now - timedelta(seconds=30)
        result = _keep_recent([old, recent], now)
        assert len(result) == 1
        assert recent in result

    def test_empty_list_returns_empty(self) -> None:
        now = datetime.now(UTC)
        assert _keep_recent([], now) == []

    def test_all_recent_keeps_all(self) -> None:
        now = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)
        stamps = [now - timedelta(seconds=i) for i in range(5)]
        result = _keep_recent(stamps, now)
        assert len(result) == 5


class TestTelegramAlerterSend:
    def test_send_implements_alert_channel(self) -> None:
        alerter = TelegramAlerter(bot_token="fake-token", chat_id="123", enabled=True)
        alert = Alert(message="channel test", level=AlertLevel.WARNING)
        with patch.object(alerter, "send_alert", return_value=True):
            assert alerter.send(alert) is True


class TestEmailChannel:
    def test_disabled_without_config(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            channel = EmailChannel(enabled=True)
            assert channel.enabled is False

    def test_enabled_with_full_config(self) -> None:
        channel = EmailChannel(
            smtp_host="smtp.test.com",
            smtp_user="user@test.com",
            smtp_password="pass",
            from_email="from@test.com",
            to_emails=["to@test.com"],
            enabled=True,
        )
        assert channel.enabled is True

    def test_disabled_returns_false(self) -> None:
        channel = EmailChannel(enabled=False)
        alert = Alert(message="test")
        assert channel.send(alert) is False

    def test_send_failure_returns_false(self) -> None:
        channel = EmailChannel(
            smtp_host="smtp.test.com",
            smtp_user="user@test.com",
            smtp_password="pass",
            from_email="from@test.com",
            to_emails=["to@test.com"],
            enabled=True,
        )
        alert = Alert(message="test")
        with patch(
            "iatb.core.observability.alerting.smtplib.SMTP",
            side_effect=OSError("SMTP error"),
        ):
            assert channel.send(alert) is False

    def test_format_body_with_context(self) -> None:
        channel = EmailChannel(enabled=False)
        alert = Alert(
            message="body test",
            level=AlertLevel.ERROR,
            context={"host": "server1"},
            rule_name="rule-1",
            alert_id="id-1",
        )
        body = channel._format_body(alert)
        assert "body test" in body
        assert "host" in body
        assert "rule-1" in body
        assert "id-1" in body

    def test_format_body_without_context(self) -> None:
        channel = EmailChannel(enabled=False)
        alert = Alert(message="no ctx")
        body = channel._format_body(alert)
        assert "no ctx" in body

    def test_to_emails_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {"EMAIL_TO": "a@b.com, c@d.com"},
            clear=False,
        ):
            channel = EmailChannel(enabled=False)
            assert "a@b.com" in channel.to_emails
            assert "c@d.com" in channel.to_emails

    def test_empty_to_emails_disables(self) -> None:
        channel = EmailChannel(
            smtp_host="smtp.test.com",
            smtp_user="user",
            smtp_password="pass",
            from_email="from@test.com",
            to_emails=[],
            enabled=True,
        )
        assert channel.enabled is False


class TestWebhookChannel:
    def test_disabled_without_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            channel = WebhookChannel(enabled=True)
            assert channel.enabled is False

    def test_invalid_url_disables(self) -> None:
        channel = WebhookChannel(webhook_url="not-a-url", enabled=True)
        assert channel.enabled is False

    def test_valid_url_enables(self) -> None:
        channel = WebhookChannel(
            webhook_url="https://hooks.example.com/alert", enabled=True
        )
        assert channel.enabled is True

    def test_disabled_returns_false(self) -> None:
        channel = WebhookChannel(enabled=False)
        alert = Alert(message="test")
        assert channel.send(alert) is False

    def test_send_async_disabled_returns_false(self) -> None:
        channel = WebhookChannel(enabled=False)
        alert = Alert(message="test")
        import asyncio

        result = asyncio.run(channel.send_async(alert))
        assert result is False

    def test_url_parse_exception_disables(self) -> None:
        channel = WebhookChannel(webhook_url="://bad", enabled=True)
        assert channel.enabled is False


class TestAlertRulesEngine:
    def test_default_rules_initialized(self) -> None:
        engine = AlertRulesEngine()
        assert "token_expiry" in engine.rules
        assert "position_limit_breach" in engine.rules
        assert "daily_loss_threshold" in engine.rules
        assert "data_source_failure" in engine.rules

    def test_add_rule(self) -> None:
        engine = AlertRulesEngine()
        custom_rule = AlertRule(
            name="custom_rule",
            condition=lambda ctx: True,
            level=AlertLevel.WARNING,
        )
        engine.add_rule(custom_rule)
        assert "custom_rule" in engine.rules

    def test_remove_rule(self) -> None:
        engine = AlertRulesEngine()
        engine.remove_rule("token_expiry")
        assert "token_expiry" not in engine.rules

    def test_remove_nonexistent_rule_no_error(self) -> None:
        engine = AlertRulesEngine()
        engine.remove_rule("nonexistent")

    def test_evaluate_rules_triggered(self) -> None:
        engine = AlertRulesEngine()
        context = {"minutes_remaining": 5}
        triggered = engine.evaluate_rules(context)
        rule_names = [r.name for r, _ in triggered]
        assert "token_expiry" in rule_names

    def test_evaluate_rules_not_triggered(self) -> None:
        engine = AlertRulesEngine()
        context = {"minutes_remaining": 999}
        triggered = engine.evaluate_rules(context)
        rule_names = [r.name for r, _ in triggered]
        assert "token_expiry" not in rule_names

    def test_disabled_rule_not_evaluated(self) -> None:
        engine = AlertRulesEngine()
        engine.rules["token_expiry"].enabled = False
        context = {"minutes_remaining": 1}
        triggered = engine.evaluate_rules(context)
        rule_names = [r.name for r, _ in triggered]
        assert "token_expiry" not in rule_names

    def test_rule_condition_exception_handled(self) -> None:
        engine = AlertRulesEngine()

        def bad_condition(ctx: dict) -> bool:
            raise RuntimeError("boom")

        engine.add_rule(
            AlertRule(name="bad_rule", condition=bad_condition, level=AlertLevel.ERROR)
        )
        triggered = engine.evaluate_rules({})
        rule_names = [r.name for r, _ in triggered]
        assert "bad_rule" not in rule_names


class TestAlertRulesEngineConditions:
    def test_token_expiry_at_boundary(self) -> None:
        engine = AlertRulesEngine()
        assert engine._check_token_expiry({"minutes_remaining": 10}) is True
        assert engine._check_token_expiry({"minutes_remaining": 11}) is False

    def test_position_limit_breach_at_boundary(self) -> None:
        engine = AlertRulesEngine()
        assert (
            engine._check_position_limit_breach({"current_positions": 10, "limit": 10})
            is True
        )
        assert (
            engine._check_position_limit_breach({"current_positions": 9, "limit": 10})
            is False
        )

    def test_daily_loss_threshold_decimal(self) -> None:
        engine = AlertRulesEngine()
        assert (
            engine._check_daily_loss_threshold(
                {"daily_pnl": Decimal("-5000"), "loss_threshold": Decimal("-4000")}
            )
            is True
        )
        assert (
            engine._check_daily_loss_threshold(
                {"daily_pnl": Decimal("-3000"), "loss_threshold": Decimal("-4000")}
            )
            is False
        )

    def test_data_source_failure_at_threshold(self) -> None:
        engine = AlertRulesEngine()
        assert (
            engine._check_data_source_failure(
                {"failure_count": 3, "failure_threshold": 3}
            )
            is True
        )
        assert (
            engine._check_data_source_failure(
                {"failure_count": 2, "failure_threshold": 3}
            )
            is False
        )

    def test_defaults_for_missing_context(self) -> None:
        engine = AlertRulesEngine()
        assert engine._check_token_expiry({}) is False
        assert engine._check_position_limit_breach({}) is False
        assert engine._check_data_source_failure({}) is False


class TestAlertThrottler:
    def test_first_send_allowed(self) -> None:
        throttler = AlertThrottler()
        assert throttler.should_send("rule-1") is True

    def test_throttled_within_interval(self) -> None:
        throttler = AlertThrottler(min_interval_seconds=60)
        throttler.record_sent("rule-1")
        assert throttler.should_send("rule-1") is False

    def test_allowed_after_interval(self) -> None:
        throttler = AlertThrottler(min_interval_seconds=0)
        throttler.record_sent("rule-1")
        assert throttler.should_send("rule-1") is True

    def test_reset_specific_rule(self) -> None:
        throttler = AlertThrottler(min_interval_seconds=60)
        throttler.record_sent("rule-1")
        throttler.reset("rule-1")
        assert throttler.should_send("rule-1") is True

    def test_reset_all_rules(self) -> None:
        throttler = AlertThrottler(min_interval_seconds=60)
        throttler.record_sent("rule-1")
        throttler.record_sent("rule-2")
        throttler.reset()
        assert throttler.should_send("rule-1") is True
        assert throttler.should_send("rule-2") is True

    def test_different_rules_independent(self) -> None:
        throttler = AlertThrottler(min_interval_seconds=60)
        throttler.record_sent("rule-1")
        assert throttler.should_send("rule-2") is True


class TestAlertAcknowledgmentTracker:
    def test_register_and_acknowledge(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert-1", "rule-1")
        result = tracker.acknowledge("alert-1", "user1", "telegram")
        assert result is True
        assert tracker.is_acknowledged("alert-1") is True

    def test_acknowledge_unknown_alert_returns_false(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        result = tracker.acknowledge("unknown", "user1", "api")
        assert result is False

    def test_is_acknowledged_unknown_returns_false(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        assert tracker.is_acknowledged("unknown") is False

    def test_get_unacknowledged(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("a1", "rule-1")
        tracker.register_alert("a2", "rule-2")
        tracker.acknowledge("a1", "user1", "api")
        unack = tracker.get_unacknowledged()
        assert len(unack) == 1
        assert unack[0].alert_id == "a2"

    def test_get_unacknowledged_filtered_by_rule(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("a1", "rule-1")
        tracker.register_alert("a2", "rule-2")
        unack = tracker.get_unacknowledged(rule_name="rule-1")
        assert len(unack) == 1
        assert unack[0].alert_id == "a1"

    def test_cleanup_old_alerts(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("old-1", "rule-1")
        tracker.acknowledge("old-1", "user1", "api")
        ack = tracker.acknowledgments["old-1"]
        ack.acknowledged_at = datetime.now(UTC) - timedelta(hours=48)
        removed = tracker.cleanup_old_alerts(max_age_hours=24)
        assert removed == 1
        assert "old-1" not in tracker.acknowledgments

    def test_cleanup_does_not_remove_unacknowledged(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("unack-1", "rule-1")
        removed = tracker.cleanup_old_alerts(max_age_hours=0)
        assert removed == 0


class TestMultiChannelAlertManager:
    def test_send_alert_returns_alert_id(self) -> None:
        manager = MultiChannelAlertManager()
        alert_id = manager.send_alert("test message", AlertLevel.WARNING)
        assert alert_id is not None
        assert alert_id.startswith("alert_")

    def test_send_alert_throttled_returns_none(self) -> None:
        throttler = AlertThrottler(min_interval_seconds=60)
        manager = MultiChannelAlertManager(throttler=throttler)
        manager.send_alert("first", rule_name="rule-1")
        result = manager.send_alert("second", rule_name="rule-1")
        assert result is None

    def test_send_alert_without_rule_not_throttled(self) -> None:
        throttler = AlertThrottler(min_interval_seconds=60)
        manager = MultiChannelAlertManager(throttler=throttler)
        manager.send_alert("first")
        result = manager.send_alert("second")
        assert result is not None

    def test_add_channel(self) -> None:
        manager = MultiChannelAlertManager()

        class DummyChannel(AlertChannel):
            def send(self, alert: Alert) -> bool:
                return True

        ch = DummyChannel(enabled=True)
        manager.add_channel(ch)
        assert ch in manager.channels

    def test_add_duplicate_channel_ignored(self) -> None:
        manager = MultiChannelAlertManager()

        class DummyChannel(AlertChannel):
            def send(self, alert: Alert) -> bool:
                return True

        ch = DummyChannel(enabled=True)
        manager.add_channel(ch)
        manager.add_channel(ch)
        assert manager.channels.count(ch) == 1

    def test_channel_exception_handled(self) -> None:
        manager = MultiChannelAlertManager()

        class FailingChannel(AlertChannel):
            def send(self, alert: Alert) -> bool:
                raise RuntimeError("channel failed")

        manager.add_channel(FailingChannel(enabled=True))
        alert_id = manager.send_alert("test")
        assert alert_id is not None

    def test_evaluate_and_alert(self) -> None:
        engine = AlertRulesEngine()
        manager = MultiChannelAlertManager(rules_engine=engine)
        context = {"minutes_remaining": 5}
        alert_ids = manager.evaluate_and_alert(context)
        assert len(alert_ids) >= 1

    def test_acknowledge_delegates(self) -> None:
        manager = MultiChannelAlertManager()
        alert_id = manager.send_alert("test")
        result = manager.acknowledge(alert_id, "admin", "api")
        assert result is True

    def test_get_unacknowledged_alerts(self) -> None:
        manager = MultiChannelAlertManager()
        manager.send_alert("test1")
        manager.send_alert("test2")
        unack = manager.get_unacknowledged_alerts()
        assert len(unack) == 2

    def test_cleanup_old_alerts_delegates(self) -> None:
        manager = MultiChannelAlertManager()
        alert_id = manager.send_alert("old")
        manager.acknowledge(alert_id, "user", "api")
        ack = manager.ack_tracker.acknowledgments[alert_id]
        ack.acknowledged_at = datetime.now(UTC) - timedelta(hours=48)
        removed = manager.cleanup_old_alerts(max_age_hours=24)
        assert removed == 1


class TestGetAlerter:
    def test_returns_telegram_alerter(self) -> None:
        import iatb.core.observability.alerting as alerting_mod

        alerting_mod._alerter = None
        with patch.dict(os.environ, {}, clear=True):
            alerter = get_alerter()
            assert isinstance(alerter, TelegramAlerter)
            alerting_mod._alerter = None


class TestGetMultiChannelManager:
    def test_returns_manager(self) -> None:
        import iatb.core.observability.alerting as alerting_mod

        alerting_mod._multi_channel_manager = None
        with patch.dict(os.environ, {}, clear=True):
            manager = get_multi_channel_manager()
            assert isinstance(manager, MultiChannelAlertManager)
            alerting_mod._multi_channel_manager = None
