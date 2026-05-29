"""Coverage tests for iatb.core.observability.alerting module.

Tests Alert dataclass, TelegramAlerter, AlertRulesEngine,
AlertThrottler, AlertAcknowledgmentTracker, MultiChannelAlertManager,
EmailChannel, WebhookChannel, and global getters.

All external services (Telegram, SMTP, HTTP) are mocked.
No network calls in tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

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
    _utc_now,
    get_alerter,
    get_multi_channel_manager,
)


class TestAlertLevel:
    """Tests for AlertLevel enum."""

    def test_alert_level_values(self) -> None:
        assert AlertLevel.INFO == "INFO"
        assert AlertLevel.WARNING == "WARNING"
        assert AlertLevel.ERROR == "ERROR"
        assert AlertLevel.CRITICAL == "CRITICAL"


class TestAlertType:
    """Tests for AlertType enum."""

    def test_alert_type_values(self) -> None:
        assert AlertType.BREAKOUT == "breakout"
        assert AlertType.REGIME_CHANGE == "regime_change"
        assert AlertType.KILL_SWITCH == "kill_switch"


class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_defaults(self) -> None:
        alert = Alert(message="test message")
        assert alert.message == "test message"
        assert alert.level == AlertLevel.INFO
        assert alert.timestamp.tzinfo is not None
        assert alert.context == {}
        assert alert.rule_name is None
        assert alert.alert_id is None

    def test_alert_with_all_fields(self) -> None:
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        alert = Alert(
            message="test",
            level=AlertLevel.ERROR,
            timestamp=ts,
            context={"key": "value"},
            rule_name="test_rule",
            alert_id="alert_001",
        )
        assert alert.level == AlertLevel.ERROR
        assert alert.timestamp == ts
        assert alert.context == {"key": "value"}
        assert alert.rule_name == "test_rule"
        assert alert.alert_id == "alert_001"


class TestUtcNow:
    """Tests for _utc_now helper."""

    def test_utc_now_is_timezone_aware(self) -> None:
        result = _utc_now()
        assert result.tzinfo is not None
        assert result.tzinfo == UTC


class TestKeepRecent:
    """Tests for _keep_recent helper."""

    def test_keep_recent_filters_old(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        old = now - timedelta(minutes=2)
        recent = now - timedelta(seconds=30)
        history = [old, recent]
        result = _keep_recent(history, now)
        assert len(result) == 1
        assert recent in result

    def test_keep_recent_empty_list(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = _keep_recent([], now)
        assert result == []

    def test_keep_recent_all_recent(self) -> None:
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        r1 = now - timedelta(seconds=10)
        r2 = now - timedelta(seconds=20)
        result = _keep_recent([r1, r2], now)
        assert len(result) == 2


class TestTelegramAlerter:
    """Tests for TelegramAlerter with mocked Bot."""

    @patch("iatb.core.observability.alerting.Bot")
    def test_init_with_credentials(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        assert alerter.enabled is True
        assert alerter.bot is not None

    @patch("iatb.core.observability.alerting.Bot")
    def test_init_without_credentials_disabled(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(bot_token=None, chat_id=None, enabled=True)
        assert alerter.enabled is False

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_alert_success(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_alert("Test message", AlertLevel.INFO)
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_alert_empty_message(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_alert("   ", AlertLevel.INFO)
        assert result is False

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_alert_disabled(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(enabled=False)
        result = alerter.send_alert("Test", AlertLevel.INFO)
        assert result is False

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_trade_alert(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_trade_alert(
            ticker="RELIANCE",
            side="BUY",
            quantity=10,
            price=Decimal("2500.50"),
        )
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_trade_alert_with_timestamp(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        ts = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        result = alerter.send_trade_alert(
            ticker="TCS", side="SELL", quantity=5, price=Decimal("3500"), timestamp=ts
        )
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_error_alert(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_error_alert("engine", "connection failed")
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_error_alert_with_type(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_error_alert(
            "engine", "connection failed", exc_type="ConnectionError"
        )
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_health_alert_down(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_health_alert("broker", "DOWN")
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_health_alert_with_details(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_health_alert("broker", "DEGRADED", details="latency")
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_pnl_alert(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_pnl_alert(
            pnl=Decimal("5000.50"), daily_pnl=Decimal("1200"), open_positions=3
        )
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_pnl_alert_negative_daily(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_pnl_alert(
            pnl=Decimal("-500"), daily_pnl=Decimal("-200"), open_positions=1
        )
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_model_alert_available(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_model_alert("XGBoost", "AVAILABLE")
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_model_alert_unavailable(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_model_alert("XGBoost", "UNAVAILABLE")
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_data_source_failure_alert(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_data_source_failure_alert("KiteProvider", 5)
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_fallback_source_alert(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_fallback_source_alert(
            "KiteProvider", "YFinanceProvider", reason="timeout"
        )
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_token_expiry_alert_critical(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_token_expiry_alert("Kite", minutes_remaining=3)
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_token_expiry_alert_warning(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_token_expiry_alert("Kite", minutes_remaining=15)
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_kill_switch_alert_utc(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        engaged = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        result = alerter.send_kill_switch_alert("drawdown breach", engaged)
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_kill_switch_alert_naive_datetime(
        self, mock_bot_cls: MagicMock
    ) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        engaged = datetime(2026, 1, 1, 10, 0, 0)  # naive
        result = alerter.send_kill_switch_alert("drawdown breach", engaged)
        assert result is False

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_with_actions(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_with_actions(
            "Action needed",
            buttons=[("Acknowledge", "ack"), ("Dismiss", "dismiss")],
        )
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_with_actions_no_buttons(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        result = alerter.send_with_actions("No buttons", buttons=None)
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_implements_channel_interface(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True
        )
        alert = Alert(message="channel test", level=AlertLevel.INFO)
        result = alerter.send(alert)
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_rate_limiting(self, mock_bot_cls: MagicMock) -> None:
        alerter = TelegramAlerter(
            bot_token="fake_token", chat_id="fake_chat", enabled=True, max_per_minute=2
        )
        assert alerter.send_alert("msg1") is True
        assert alerter.send_alert("msg2") is True
        # Third message within same minute should be rate-limited
        assert alerter.send_alert("msg3") is False


class TestEmailChannel:
    """Tests for EmailChannel with mocked SMTP."""

    @patch("iatb.core.observability.alerting.smtplib.SMTP")
    def test_email_init_with_credentials(self, mock_smtp: MagicMock) -> None:
        ch = EmailChannel(
            smtp_host="smtp.test.com",
            smtp_user="user@test.com",
            smtp_password="pass123",
            from_email="from@test.com",
            to_emails=["to@test.com"],
            enabled=True,
        )
        assert ch.enabled is True

    @patch("iatb.core.observability.alerting.smtplib.SMTP")
    def test_email_init_without_credentials(self, mock_smtp: MagicMock) -> None:
        ch = EmailChannel(
            smtp_host=None,
            smtp_user=None,
            smtp_password=None,
            enabled=True,
        )
        assert ch.enabled is False

    @patch("iatb.core.observability.alerting.smtplib.SMTP")
    def test_email_send_disabled(self, mock_smtp: MagicMock) -> None:
        ch = EmailChannel(enabled=False)
        alert = Alert(message="test")
        assert ch.send(alert) is False

    @patch("iatb.core.observability.alerting.smtplib.SMTP")
    def test_email_send_success(self, mock_smtp: MagicMock) -> None:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        ch = EmailChannel(
            smtp_host="smtp.test.com",
            smtp_user="user@test.com",
            smtp_password="pass",
            from_email="from@test.com",
            to_emails=["to@test.com"],
            enabled=True,
        )
        alert = Alert(message="email test", level=AlertLevel.WARNING)
        result = ch.send(alert)
        assert result is True

    def test_email_format_body(self) -> None:
        ch = EmailChannel(
            smtp_host="smtp.test.com",
            smtp_user="user",
            smtp_password="pass",
            from_email="from@test.com",
            to_emails=["to@test.com"],
            enabled=True,
        )
        alert = Alert(
            message="test body",
            level=AlertLevel.ERROR,
            context={"key": "val"},
            rule_name="rule1",
            alert_id="id1",
        )
        body = ch._format_body(alert)
        assert "test body" in body
        assert "ERROR" in body
        assert "key" in body


class TestWebhookChannel:
    """Tests for WebhookChannel with mocked HTTP."""

    def test_webhook_init_with_valid_url(self) -> None:
        ch = WebhookChannel(webhook_url="https://hooks.example.com/alert", enabled=True)
        assert ch.enabled is True

    def test_webhook_init_with_invalid_url(self) -> None:
        ch = WebhookChannel(webhook_url="not-a-url", enabled=True)
        assert ch.enabled is False

    def test_webhook_init_without_url(self) -> None:
        ch = WebhookChannel(webhook_url=None, enabled=True)
        assert ch.enabled is False

    def test_webhook_send_disabled(self) -> None:
        ch = WebhookChannel(enabled=False)
        alert = Alert(message="test")
        assert ch.send(alert) is False


class TestAlertRulesEngine:
    """Tests for AlertRulesEngine."""

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
            condition=lambda ctx: ctx.get("flag", False),
            level=AlertLevel.WARNING,
        )
        engine.add_rule(custom_rule)
        assert "custom_rule" in engine.rules

    def test_remove_rule(self) -> None:
        engine = AlertRulesEngine()
        engine.remove_rule("token_expiry")
        assert "token_expiry" not in engine.rules

    def test_evaluate_token_expiry_triggered(self) -> None:
        engine = AlertRulesEngine()
        ctx = {"minutes_remaining": 5}
        triggered = engine.evaluate_rules(ctx)
        rule_names = [r.name for r, _ in triggered]
        assert "token_expiry" in rule_names

    def test_evaluate_token_expiry_not_triggered(self) -> None:
        engine = AlertRulesEngine()
        ctx = {"minutes_remaining": 30}
        triggered = engine.evaluate_rules(ctx)
        rule_names = [r.name for r, _ in triggered]
        assert "token_expiry" not in rule_names

    def test_evaluate_position_limit_breach(self) -> None:
        engine = AlertRulesEngine()
        ctx = {"current_positions": 10, "limit": 10}
        triggered = engine.evaluate_rules(ctx)
        rule_names = [r.name for r, _ in triggered]
        assert "position_limit_breach" in rule_names

    def test_evaluate_position_limit_ok(self) -> None:
        engine = AlertRulesEngine()
        ctx = {"current_positions": 5, "limit": 10}
        triggered = engine.evaluate_rules(ctx)
        rule_names = [r.name for r, _ in triggered]
        assert "position_limit_breach" not in rule_names

    def test_evaluate_daily_loss_threshold(self) -> None:
        engine = AlertRulesEngine()
        ctx = {"daily_pnl": -6000, "loss_threshold": -5000}
        triggered = engine.evaluate_rules(ctx)
        rule_names = [r.name for r, _ in triggered]
        assert "daily_loss_threshold" in rule_names

    def test_evaluate_daily_loss_ok(self) -> None:
        engine = AlertRulesEngine()
        ctx = {"daily_pnl": -1000, "loss_threshold": -5000}
        triggered = engine.evaluate_rules(ctx)
        rule_names = [r.name for r, _ in triggered]
        assert "daily_loss_threshold" not in rule_names

    def test_evaluate_data_source_failure(self) -> None:
        engine = AlertRulesEngine()
        ctx = {"failure_count": 5, "failure_threshold": 3}
        triggered = engine.evaluate_rules(ctx)
        rule_names = [r.name for r, _ in triggered]
        assert "data_source_failure" in rule_names

    def test_evaluate_disabled_rule(self) -> None:
        engine = AlertRulesEngine()
        engine.rules["token_expiry"].enabled = False
        ctx = {"minutes_remaining": 1}
        triggered = engine.evaluate_rules(ctx)
        rule_names = [r.name for r, _ in triggered]
        assert "token_expiry" not in rule_names

    def test_evaluate_rule_exception_handled(self) -> None:
        engine = AlertRulesEngine()

        def bad_condition(ctx: dict) -> bool:
            raise ValueError("bad rule")

        engine.add_rule(AlertRule(name="bad_rule", condition=bad_condition))
        # Should not raise, just log
        triggered = engine.evaluate_rules({})
        assert all(r.name != "bad_rule" for r, _ in triggered)


class TestAlertThrottler:
    """Tests for AlertThrottler."""

    def test_should_send_first_time(self) -> None:
        throttler = AlertThrottler()
        assert throttler.should_send("rule1") is True

    def test_should_send_throttled(self) -> None:
        throttler = AlertThrottler(min_interval_seconds=60)
        throttler.record_sent("rule1")
        assert throttler.should_send("rule1") is False

    def test_record_sent(self) -> None:
        throttler = AlertThrottler()
        throttler.record_sent("rule1")
        assert "rule1" in throttler._last_sent

    def test_reset_specific_rule(self) -> None:
        throttler = AlertThrottler()
        throttler.record_sent("rule1")
        throttler.record_sent("rule2")
        throttler.reset("rule1")
        assert "rule1" not in throttler._last_sent
        assert "rule2" in throttler._last_sent

    def test_reset_all(self) -> None:
        throttler = AlertThrottler()
        throttler.record_sent("rule1")
        throttler.record_sent("rule2")
        throttler.reset()
        assert len(throttler._last_sent) == 0

    def test_zero_interval_allows_all(self) -> None:
        throttler = AlertThrottler(min_interval_seconds=0)
        throttler.record_sent("rule1")
        assert throttler.should_send("rule1") is True


class TestAlertAcknowledgmentTracker:
    """Tests for AlertAcknowledgmentTracker."""

    def test_register_alert(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_1", "rule_1")
        assert "alert_1" in tracker.acknowledgments

    def test_acknowledge_success(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_1", "rule_1")
        result = tracker.acknowledge("alert_1", "admin", "telegram")
        assert result is True
        assert tracker.acknowledgments["alert_1"].acknowledged is True
        assert tracker.acknowledgments["alert_1"].acknowledged_by == "admin"

    def test_acknowledge_not_found(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        result = tracker.acknowledge("nonexistent", "admin", "telegram")
        assert result is False

    def test_is_acknowledged(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_1", "rule_1")
        assert tracker.is_acknowledged("alert_1") is False
        tracker.acknowledge("alert_1", "admin", "api")
        assert tracker.is_acknowledged("alert_1") is True

    def test_is_acknowledged_not_found(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        assert tracker.is_acknowledged("nonexistent") is False

    def test_get_unacknowledged(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("a1", "rule1")
        tracker.register_alert("a2", "rule2")
        tracker.acknowledge("a1", "admin", "api")
        unack = tracker.get_unacknowledged()
        assert len(unack) == 1
        assert unack[0].alert_id == "a2"

    def test_get_unacknowledged_by_rule(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("a1", "rule1")
        tracker.register_alert("a2", "rule2")
        unack = tracker.get_unacknowledged(rule_name="rule1")
        assert len(unack) == 1
        assert unack[0].alert_id == "a1"

    def test_cleanup_old_alerts(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("old_alert", "rule1")
        tracker.acknowledge("old_alert", "admin", "api")
        # Manually set acknowledged_at to old time
        tracker.acknowledgments["old_alert"].acknowledged_at = datetime.now(
            tz=UTC
        ) - timedelta(hours=48)
        count = tracker.cleanup_old_alerts(max_age_hours=24)
        assert count == 1
        assert "old_alert" not in tracker.acknowledgments

    def test_cleanup_no_old_alerts(self) -> None:
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("a1", "rule1")
        count = tracker.cleanup_old_alerts(max_age_hours=24)
        assert count == 0


class TestMultiChannelAlertManager:
    """Tests for MultiChannelAlertManager."""

    def test_init_defaults(self) -> None:
        mgr = MultiChannelAlertManager()
        assert mgr.channels == []
        assert mgr.rules_engine is not None
        assert mgr.throttler is not None

    def test_add_channel(self) -> None:
        mgr = MultiChannelAlertManager()
        mock_channel = MagicMock(spec=AlertChannel)
        mock_channel.enabled = True
        mgr.add_channel(mock_channel)
        assert mock_channel in mgr.channels

    def test_add_channel_no_duplicates(self) -> None:
        mgr = MultiChannelAlertManager()
        mock_channel = MagicMock(spec=AlertChannel)
        mock_channel.enabled = True
        mgr.add_channel(mock_channel)
        mgr.add_channel(mock_channel)
        assert len(mgr.channels) == 1

    def test_send_alert_no_channels(self) -> None:
        mgr = MultiChannelAlertManager()
        result = mgr.send_alert("test msg")
        # Returns alert_id even without channels
        assert result is not None

    def test_send_alert_with_channel(self) -> None:
        mgr = MultiChannelAlertManager()
        mock_channel = MagicMock(spec=AlertChannel)
        mock_channel.enabled = True
        mock_channel.send.return_value = True
        mgr.add_channel(mock_channel)
        result = mgr.send_alert("test msg")
        assert result is not None
        mock_channel.send.assert_called_once()

    def test_send_alert_throttled(self) -> None:
        mgr = MultiChannelAlertManager()
        mock_throttler = MagicMock(spec=AlertThrottler)
        mock_throttler.should_send.return_value = False
        mgr.throttler = mock_throttler
        result = mgr.send_alert("test", rule_name="throttled_rule")
        assert result is None

    def test_evaluate_and_alert(self) -> None:
        mgr = MultiChannelAlertManager()
        mock_engine = MagicMock(spec=AlertRulesEngine)
        mock_rule = AlertRule(
            name="test_rule",
            condition=lambda ctx: True,
            level=AlertLevel.WARNING,
        )
        mock_engine.evaluate_rules.return_value = [(mock_rule, {})]
        mgr.rules_engine = mock_engine
        alert_ids = mgr.evaluate_and_alert({"test": True})
        assert len(alert_ids) >= 1

    def test_acknowledge_delegates(self) -> None:
        mgr = MultiChannelAlertManager()
        mock_tracker = MagicMock(spec=AlertAcknowledgmentTracker)
        mock_tracker.acknowledge.return_value = True
        mgr.ack_tracker = mock_tracker
        result = mgr.acknowledge("alert_1", "admin", "api")
        assert result is True

    def test_get_unacknowledged_alerts(self) -> None:
        mgr = MultiChannelAlertManager()
        mock_tracker = MagicMock(spec=AlertAcknowledgmentTracker)
        mock_tracker.get_unacknowledged.return_value = []
        mgr.ack_tracker = mock_tracker
        result = mgr.get_unacknowledged_alerts()
        assert result == []

    def test_cleanup_delegates(self) -> None:
        mgr = MultiChannelAlertManager()
        mock_tracker = MagicMock(spec=AlertAcknowledgmentTracker)
        mock_tracker.cleanup_old_alerts.return_value = 3
        mgr.ack_tracker = mock_tracker
        result = mgr.cleanup_old_alerts()
        assert result == 3

    def test_send_alert_channel_exception(self) -> None:
        mgr = MultiChannelAlertManager()
        mock_channel = MagicMock(spec=AlertChannel)
        mock_channel.enabled = True
        mock_channel.send.side_effect = ConnectionError("network error")
        mgr.add_channel(mock_channel)
        # Should not raise
        result = mgr.send_alert("test msg")
        assert result is not None


class TestGetAlerter:
    """Tests for get_alerter global getter."""

    @patch("iatb.core.observability.alerting.TelegramAlerter")
    def test_get_alerter_creates_instance(self, mock_cls: MagicMock) -> None:
        import iatb.core.observability.alerting as mod

        mod._alerter = None
        alerter = get_alerter()
        assert alerter is not None

    def test_get_alerter_returns_existing(self) -> None:
        import iatb.core.observability.alerting as mod

        mock_alerter = MagicMock(spec=TelegramAlerter)
        mod._alerter = mock_alerter
        result = get_alerter()
        assert result is mock_alerter
        mod._alerter = None  # cleanup


class TestGetMultiChannelManager:
    """Tests for get_multi_channel_manager global getter."""

    @patch("iatb.core.observability.alerting.TelegramAlerter")
    @patch("iatb.core.observability.alerting.EmailChannel")
    @patch("iatb.core.observability.alerting.WebhookChannel")
    def test_get_manager_creates_instance(
        self,
        mock_webhook: MagicMock,
        mock_email: MagicMock,
        mock_telegram: MagicMock,
    ) -> None:
        import iatb.core.observability.alerting as mod

        mod._multi_channel_manager = None
        manager = get_multi_channel_manager()
        assert manager is not None

    def test_get_manager_returns_existing(self) -> None:
        import iatb.core.observability.alerting as mod

        mock_mgr = MagicMock(spec=MultiChannelAlertManager)
        mod._multi_channel_manager = mock_mgr
        result = get_multi_channel_manager()
        assert result is mock_mgr
        mod._multi_channel_manager = None  # cleanup
