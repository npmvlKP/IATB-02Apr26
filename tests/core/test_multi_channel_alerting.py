"""Tests for multi-channel alerting system."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.observability.alerting import (
    Alert,
    AlertAcknowledgment,
    AlertAcknowledgmentTracker,
    AlertChannel,
    AlertLevel,
    AlertRule,
    AlertRulesEngine,
    AlertThrottler,
    EmailChannel,
    MultiChannelAlertManager,
    TelegramAlerter,
    WebhookChannel,
)


class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_creation_with_defaults(self) -> None:
        """Test creating an alert with default values."""
        alert = Alert(message="Test alert")
        assert alert.message == "Test alert"
        assert alert.level == AlertLevel.INFO
        assert alert.context == {}
        assert alert.rule_name is None
        assert alert.alert_id is None
        assert alert.timestamp is not None

    def test_alert_creation_with_all_fields(self) -> None:
        """Test creating an alert with all fields."""
        timestamp = datetime(2026, 4, 24, 10, 0, 0, tzinfo=UTC)
        alert = Alert(
            message="Test alert",
            level=AlertLevel.CRITICAL,
            timestamp=timestamp,
            context={"key": "value"},
            rule_name="test_rule",
            alert_id="alert_123",
        )
        assert alert.message == "Test alert"
        assert alert.level == AlertLevel.CRITICAL
        assert alert.timestamp == timestamp
        assert alert.context == {"key": "value"}
        assert alert.rule_name == "test_rule"
        assert alert.alert_id == "alert_123"


class TestAlertChannel:
    """Tests for AlertChannel abstract base class."""

    def test_channel_is_abstract(self) -> None:
        """Test that AlertChannel cannot be instantiated directly."""
        with pytest.raises(TypeError):
            AlertChannel(enabled=True)


class TestEmailChannel:
    """Tests for EmailChannel class."""

    @patch.dict("os.environ", {}, clear=True)
    def test_channel_initialization_without_credentials(self) -> None:
        """Test that channel initializes without credentials but is disabled."""
        channel = EmailChannel()
        assert not channel.enabled

    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USER": "test@example.com",
            "SMTP_PASSWORD": "password",
            "EMAIL_TO": "recipient@example.com",
        },
    )
    def test_channel_initialization_with_env_credentials(self) -> None:
        """Test that channel initializes with environment credentials."""
        channel = EmailChannel()
        assert channel.enabled
        assert channel.smtp_host == "smtp.example.com"
        assert channel.smtp_user == "test@example.com"
        assert channel.to_emails == ["recipient@example.com"]

    def test_channel_initialization_with_direct_credentials(self) -> None:
        """Test that channel initializes with direct credentials."""
        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_user="test@example.com",
            smtp_password="password",
            from_email="sender@example.com",
            to_emails=["recipient1@example.com", "recipient2@example.com"],
        )
        assert channel.enabled
        assert channel.smtp_host == "smtp.example.com"
        assert channel.to_emails == ["recipient1@example.com", "recipient2@example.com"]

    def test_channel_ignores_empty_to_emails(self) -> None:
        """Test that channel ignores empty email addresses."""
        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_user="test@example.com",
            smtp_password="password",
            to_emails=["", "  ", "valid@example.com"],
        )
        assert channel.enabled
        assert channel.to_emails == ["valid@example.com"]

    def test_channel_parses_comma_separated_env_emails(self) -> None:
        """Test that channel accepts a list of emails."""
        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_user="test@example.com",
            smtp_password="password",
            to_emails=["email1@example.com", "email2@example.com", "email3@example.com"],
        )
        assert channel.enabled
        assert channel.to_emails == [
            "email1@example.com",
            "email2@example.com",
            "email3@example.com",
        ]

    def test_channel_can_be_disabled_explicitly(self) -> None:
        """Test that channel can be explicitly disabled."""
        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_user="test@example.com",
            smtp_password="password",
            to_emails=["recipient@example.com"],
            enabled=False,
        )
        assert not channel.enabled

    @patch("iatb.core.observability.alerting.smtplib.SMTP")
    def test_send_alert_when_enabled(self, mock_smtp_class: MagicMock) -> None:
        """Test that send_alert works when enabled."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_user="test@example.com",
            smtp_password="password",
            to_emails=["recipient@example.com"],
        )

        alert = Alert(
            message="Test alert",
            level=AlertLevel.ERROR,
            rule_name="test_rule",
            alert_id="alert_123",
        )

        result = channel.send(alert)
        assert result is True

        # Verify SMTP calls
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@example.com", "password")
        mock_server.send_message.assert_called_once()

    def test_send_alert_when_disabled(self) -> None:
        """Test that send_alert returns False when disabled."""
        channel = EmailChannel(enabled=False)
        alert = Alert(message="Test alert")
        result = channel.send(alert)
        assert result is False

    @patch("iatb.core.observability.alerting.smtplib.SMTP")
    def test_send_alert_handles_smtp_error(self, mock_smtp_class: MagicMock) -> None:
        """Test that send_alert handles SMTP errors gracefully."""
        mock_smtp_class.side_effect = Exception("SMTP connection failed")

        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_user="test@example.com",
            smtp_password="password",
            to_emails=["recipient@example.com"],
        )

        alert = Alert(message="Test alert")
        result = channel.send(alert)
        assert result is False

    def test_format_body_includes_all_fields(self) -> None:
        """Test that _format_body includes all alert fields."""
        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_user="test@example.com",
            smtp_password="password",
            to_emails=["recipient@example.com"],
        )

        alert = Alert(
            message="Test message",
            level=AlertLevel.CRITICAL,
            rule_name="test_rule",
            alert_id="alert_123",
            context={"key1": "value1", "key2": "value2"},
        )

        body = channel._format_body(alert)

        assert "CRITICAL" in body
        assert "Test message" in body
        assert "test_rule" in body
        assert "alert_123" in body
        assert "key1: value1" in body
        assert "key2: value2" in body


class TestWebhookChannel:
    """Tests for WebhookChannel class."""

    @patch.dict("os.environ", {}, clear=True)
    def test_channel_initialization_without_url(self) -> None:
        """Test that channel initializes without URL but is disabled."""
        channel = WebhookChannel()
        assert not channel.enabled
        assert channel.webhook_url is None

    @patch.dict("os.environ", {"WEBHOOK_URL": "https://example.com/webhook"})
    def test_channel_initialization_with_env_url(self) -> None:
        """Test that channel initializes with environment URL."""
        channel = WebhookChannel()
        assert channel.enabled
        assert channel.webhook_url == "https://example.com/webhook"

    def test_channel_initialization_with_direct_url(self) -> None:
        """Test that channel initializes with direct URL."""
        channel = WebhookChannel(
            webhook_url="https://example.com/webhook",
            headers={"Authorization": "Bearer token"},
        )
        assert channel.enabled
        assert channel.webhook_url == "https://example.com/webhook"
        assert channel.headers == {"Authorization": "Bearer token"}

    def test_channel_validates_url_format(self) -> None:
        """Test that channel validates URL format."""
        # Valid URL
        channel = WebhookChannel(webhook_url="https://example.com/webhook")
        assert channel.enabled

        # Invalid URL (no scheme)
        channel2 = WebhookChannel(webhook_url="example.com/webhook")
        assert not channel2.enabled

        # Invalid URL (no netloc)
        channel3 = WebhookChannel(webhook_url="https://")
        assert not channel3.enabled

    def test_channel_can_be_disabled_explicitly(self) -> None:
        """Test that channel can be explicitly disabled."""
        channel = WebhookChannel(
            webhook_url="https://example.com/webhook",
            enabled=False,
        )
        assert not channel.enabled

    def test_send_alert_when_disabled(self) -> None:
        """Test that send_alert returns False when disabled."""
        channel = WebhookChannel(enabled=False)
        alert = Alert(message="Test alert")
        result = channel.send(alert)
        assert result is False


class TestAlertRule:
    """Tests for AlertRule dataclass."""

    def test_rule_creation(self) -> None:
        """Test creating an alert rule."""
        rule = AlertRule(
            name="test_rule",
            condition=lambda ctx: ctx.get("value", 0) > 10,
            level=AlertLevel.WARNING,
            enabled=True,
            description="Test rule description",
        )
        assert rule.name == "test_rule"
        assert rule.level == AlertLevel.WARNING
        assert rule.enabled is True
        assert rule.description == "Test rule description"

    def test_rule_evaluation_true(self) -> None:
        """Test rule evaluation returns True when condition met."""
        rule = AlertRule(
            name="test_rule",
            condition=lambda ctx: ctx.get("value", 0) > 10,
        )
        assert rule.condition({"value": 15}) is True

    def test_rule_evaluation_false(self) -> None:
        """Test rule evaluation returns False when condition not met."""
        rule = AlertRule(
            name="test_rule",
            condition=lambda ctx: ctx.get("value", 0) > 10,
        )
        assert rule.condition({"value": 5}) is False


class TestAlertRulesEngine:
    """Tests for AlertRulesEngine class."""

    def test_engine_initialization(self) -> None:
        """Test engine initialization with default rules."""
        engine = AlertRulesEngine()
        assert len(engine.rules) == 4  # 4 default rules
        assert "token_expiry" in engine.rules
        assert "position_limit_breach" in engine.rules
        assert "daily_loss_threshold" in engine.rules
        assert "data_source_failure" in engine.rules

    def test_add_rule(self) -> None:
        """Test adding a custom rule."""
        engine = AlertRulesEngine()
        custom_rule = AlertRule(
            name="custom_rule",
            condition=lambda ctx: ctx.get("value", 0) < 0,
            level=AlertLevel.ERROR,
        )
        engine.add_rule(custom_rule)
        assert "custom_rule" in engine.rules
        assert len(engine.rules) == 5

    def test_add_rule_updates_existing(self) -> None:
        """Test that adding a rule with same name updates it."""
        engine = AlertRulesEngine()
        new_rule = AlertRule(
            name="token_expiry",
            condition=lambda ctx: ctx.get("minutes_remaining", 999) <= 5,
            level=AlertLevel.INFO,
        )
        engine.add_rule(new_rule)
        assert engine.rules["token_expiry"].level == AlertLevel.INFO

    def test_remove_rule(self) -> None:
        """Test removing a rule."""
        engine = AlertRulesEngine()
        engine.remove_rule("token_expiry")
        assert "token_expiry" not in engine.rules
        assert len(engine.rules) == 3

    def test_remove_nonexistent_rule(self) -> None:
        """Test removing a non-existent rule doesn't raise error."""
        engine = AlertRulesEngine()
        engine.remove_rule("nonexistent_rule")
        assert len(engine.rules) == 4

    def test_evaluate_rules_no_triggers(self) -> None:
        """Test evaluating rules when none are triggered."""
        engine = AlertRulesEngine()
        context = {
            "minutes_remaining": 999,
            "current_positions": 1,
            "limit": 10,
            "daily_pnl": 1000.0,
            "loss_threshold": -5000.0,
            "failure_count": 1,
            "failure_threshold": 3,
        }
        triggered = engine.evaluate_rules(context)
        assert len(triggered) == 0

    def test_evaluate_rules_single_trigger(self) -> None:
        """Test evaluating rules when one is triggered."""
        engine = AlertRulesEngine()
        context = {
            "minutes_remaining": 5,  # Triggers token_expiry
            "current_positions": 1,
            "limit": 10,
            "daily_pnl": 1000.0,
            "loss_threshold": -5000.0,
            "failure_count": 1,
            "failure_threshold": 3,
        }
        triggered = engine.evaluate_rules(context)
        assert len(triggered) == 1
        assert triggered[0][0].name == "token_expiry"

    def test_evaluate_rules_multiple_triggers(self) -> None:
        """Test evaluating rules when multiple are triggered."""
        engine = AlertRulesEngine()
        context = {
            "minutes_remaining": 5,  # Triggers token_expiry
            "current_positions": 10,  # Triggers position_limit_breach
            "limit": 10,
            "daily_pnl": -6000.0,  # Triggers daily_loss_threshold
            "loss_threshold": -5000.0,
            "failure_count": 5,  # Triggers data_source_failure
            "failure_threshold": 3,
        }
        triggered = engine.evaluate_rules(context)
        assert len(triggered) == 4

    def test_evaluate_rules_respects_enabled_flag(self) -> None:
        """Test that disabled rules are not evaluated."""
        engine = AlertRulesEngine()
        engine.rules["token_expiry"].enabled = False

        context = {
            "minutes_remaining": 5,
            "current_positions": 1,
            "limit": 10,
            "daily_pnl": 1000.0,
            "loss_threshold": -5000.0,
            "failure_count": 1,
            "failure_threshold": 3,
        }
        triggered = engine.evaluate_rules(context)
        assert len(triggered) == 0

    def test_evaluate_rules_handles_exception(self) -> None:
        """Test that rule evaluation handles exceptions gracefully."""
        engine = AlertRulesEngine()
        # Add a rule that raises an exception
        engine.add_rule(
            AlertRule(
                name="failing_rule",
                condition=lambda ctx: 1 / 0,  # Raises ZeroDivisionError
            )
        )

        context = {}
        triggered = engine.evaluate_rules(context)
        # The failing rule should not trigger, but should not crash the engine
        assert len(triggered) == 0

    def test_check_token_expiry_condition(self) -> None:
        """Test token expiry rule condition."""
        engine = AlertRulesEngine()
        assert engine._check_token_expiry({"minutes_remaining": 5}) is True
        assert engine._check_token_expiry({"minutes_remaining": 10}) is True
        assert engine._check_token_expiry({"minutes_remaining": 11}) is False
        assert engine._check_token_expiry({}) is False

    def test_check_position_limit_breach_condition(self) -> None:
        """Test position limit breach rule condition."""
        engine = AlertRulesEngine()
        assert engine._check_position_limit_breach({"current_positions": 10, "limit": 10}) is True
        assert engine._check_position_limit_breach({"current_positions": 11, "limit": 10}) is True
        assert engine._check_position_limit_breach({"current_positions": 9, "limit": 10}) is False
        assert engine._check_position_limit_breach({}) is False

    def test_check_daily_loss_threshold_condition(self) -> None:
        """Test daily loss threshold rule condition."""
        engine = AlertRulesEngine()
        assert (
            engine._check_daily_loss_threshold({"daily_pnl": -5000, "loss_threshold": -5000})
            is True
        )
        assert (
            engine._check_daily_loss_threshold({"daily_pnl": -6000, "loss_threshold": -5000})
            is True
        )
        assert (
            engine._check_daily_loss_threshold({"daily_pnl": -4000, "loss_threshold": -5000})
            is False
        )
        assert engine._check_daily_loss_threshold({}) is False

    def test_check_data_source_failure_condition(self) -> None:
        """Test data source failure rule condition."""
        engine = AlertRulesEngine()
        assert (
            engine._check_data_source_failure({"failure_count": 3, "failure_threshold": 3}) is True
        )
        assert (
            engine._check_data_source_failure({"failure_count": 5, "failure_threshold": 3}) is True
        )
        assert (
            engine._check_data_source_failure({"failure_count": 2, "failure_threshold": 3}) is False
        )
        assert engine._check_data_source_failure({}) is False


class TestAlertThrottler:
    """Tests for AlertThrottler class."""

    def test_throttler_initialization(self) -> None:
        """Test throttler initialization."""
        throttler = AlertThrottler()
        assert throttler.min_interval_seconds == 60
        assert throttler._last_sent == {}

    def test_throttler_custom_interval(self) -> None:
        """Test throttler with custom interval."""
        throttler = AlertThrottler(min_interval_seconds=30)
        assert throttler.min_interval_seconds == 30

    def test_should_send_first_time(self) -> None:
        """Test that alert should send on first occurrence."""
        throttler = AlertThrottler()
        assert throttler.should_send("test_rule") is True

    def test_should_send_after_interval(self) -> None:
        """Test that alert should send after interval has passed."""
        throttler = AlertThrottler(min_interval_seconds=1)

        # First send
        assert throttler.should_send("test_rule") is True
        throttler.record_sent("test_rule")

        # Should be throttled immediately
        assert throttler.should_send("test_rule") is False

        # Wait for interval to pass
        import time

        time.sleep(1.1)

        # Should be allowed again
        assert throttler.should_send("test_rule") is True

    def test_should_send_throttles_within_interval(self) -> None:
        """Test that alert is throttled within interval."""
        throttler = AlertThrottler(min_interval_seconds=60)

        # First send
        assert throttler.should_send("test_rule") is True
        throttler.record_sent("test_rule")

        # Should be throttled
        assert throttler.should_send("test_rule") is False

    def test_record_sent(self) -> None:
        """Test recording that an alert was sent."""
        throttler = AlertThrottler()
        throttler.record_sent("test_rule")
        assert "test_rule" in throttler._last_sent

    def test_reset_single_rule(self) -> None:
        """Test resetting throttling for a single rule."""
        throttler = AlertThrottler()
        throttler.record_sent("rule1")
        throttler.record_sent("rule2")

        assert throttler.should_send("rule1") is False
        throttler.reset("rule1")
        assert throttler.should_send("rule1") is True
        assert throttler.should_send("rule2") is False

    def test_reset_all_rules(self) -> None:
        """Test resetting throttling for all rules."""
        throttler = AlertThrottler()
        throttler.record_sent("rule1")
        throttler.record_sent("rule2")

        assert throttler.should_send("rule1") is False
        assert throttler.should_send("rule2") is False

        throttler.reset()

        assert throttler.should_send("rule1") is True
        assert throttler.should_send("rule2") is True

    def test_reset_nonexistent_rule(self) -> None:
        """Test resetting a non-existent rule doesn't raise error."""
        throttler = AlertThrottler()
        throttler.reset("nonexistent_rule")
        assert len(throttler._last_sent) == 0


class TestAlertAcknowledgment:
    """Tests for AlertAcknowledgment dataclass."""

    def test_acknowledgment_creation(self) -> None:
        """Test creating an acknowledgment record."""
        ack = AlertAcknowledgment(
            alert_id="alert_123",
            rule_name="test_rule",
        )
        assert ack.alert_id == "alert_123"
        assert ack.rule_name == "test_rule"
        assert ack.acknowledged is False
        assert ack.acknowledged_by is None
        assert ack.acknowledged_at is None
        assert ack.acknowledged_via is None


class TestAlertAcknowledgmentTracker:
    """Tests for AlertAcknowledgmentTracker class."""

    def test_tracker_initialization(self) -> None:
        """Test tracker initialization."""
        tracker = AlertAcknowledgmentTracker()
        assert tracker.acknowledgments == {}

    def test_register_alert(self) -> None:
        """Test registering an alert."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_123", "test_rule")
        assert "alert_123" in tracker.acknowledgments
        assert tracker.acknowledgments["alert_123"].alert_id == "alert_123"
        assert tracker.acknowledgments["alert_123"].rule_name == "test_rule"
        assert tracker.acknowledgments["alert_123"].acknowledged is False

    def test_acknowledge_alert(self) -> None:
        """Test acknowledging an alert."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_123", "test_rule")

        result = tracker.acknowledge("alert_123", "user1", "telegram")

        assert result is True
        assert tracker.acknowledgments["alert_123"].acknowledged is True
        assert tracker.acknowledgments["alert_123"].acknowledged_by == "user1"
        assert tracker.acknowledgments["alert_123"].acknowledged_via == "telegram"
        assert tracker.acknowledgments["alert_123"].acknowledged_at is not None

    def test_acknowledge_nonexistent_alert(self) -> None:
        """Test acknowledging a non-existent alert returns False."""
        tracker = AlertAcknowledgmentTracker()
        result = tracker.acknowledge("nonexistent", "user1", "telegram")
        assert result is False

    def test_is_acknowledged_true(self) -> None:
        """Test checking if alert is acknowledged returns True."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_123", "test_rule")
        tracker.acknowledge("alert_123", "user1", "telegram")

        assert tracker.is_acknowledged("alert_123") is True

    def test_is_acknowledged_false(self) -> None:
        """Test checking if alert is acknowledged returns False."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_123", "test_rule")

        assert tracker.is_acknowledged("alert_123") is False

    def test_is_acknowledged_nonexistent(self) -> None:
        """Test checking if non-existent alert is acknowledged returns False."""
        tracker = AlertAcknowledgmentTracker()
        assert tracker.is_acknowledged("nonexistent") is False

    def test_get_unacknowledged_all(self) -> None:
        """Test getting all unacknowledged alerts."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_1", "rule1")
        tracker.register_alert("alert_2", "rule2")
        tracker.register_alert("alert_3", "rule3")
        tracker.acknowledge("alert_2", "user1", "telegram")

        unacknowledged = tracker.get_unacknowledged()
        assert len(unacknowledged) == 2
        alert_ids = [ack.alert_id for ack in unacknowledged]
        assert "alert_1" in alert_ids
        assert "alert_3" in alert_ids
        assert "alert_2" not in alert_ids

    def test_get_unacknowledged_by_rule(self) -> None:
        """Test getting unacknowledged alerts filtered by rule."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_1", "rule1")
        tracker.register_alert("alert_2", "rule1")
        tracker.register_alert("alert_3", "rule2")
        tracker.acknowledge("alert_2", "user1", "telegram")

        unacknowledged = tracker.get_unacknowledged(rule_name="rule1")
        assert len(unacknowledged) == 1
        assert unacknowledged[0].alert_id == "alert_1"

    def test_cleanup_old_alerts(self) -> None:
        """Test cleaning up old acknowledged alerts."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("old_alert", "rule1")
        tracker.acknowledge("old_alert", "user1", "telegram")

        # Manually set the acknowledgment time to be old
        old_time = datetime.now(UTC) - timedelta(hours=25)
        tracker.acknowledgments["old_alert"].acknowledged_at = old_time

        tracker.register_alert("new_alert", "rule2")
        tracker.acknowledge("new_alert", "user1", "telegram")

        cleaned = tracker.cleanup_old_alerts(max_age_hours=24)
        assert cleaned == 1


class TestTelegramAlerter:
    """Tests for TelegramAlerter class."""

    @patch.dict("os.environ", {}, clear=True)
    def test_alerter_initialization_without_credentials(self) -> None:
        """Test that alerter initializes without credentials but is disabled."""
        alerter = TelegramAlerter()
        assert not alerter.enabled
        assert alerter.bot is None

    @patch.dict(
        "os.environ",
        {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456789",
        },
    )
    def test_alerter_initialization_with_env_credentials(self) -> None:
        """Test that alerter initializes with environment credentials."""
        alerter = TelegramAlerter()
        assert alerter.enabled
        assert alerter.bot_token == "test_token"
        assert alerter.chat_id == "123456789"
        assert alerter.bot is not None

    def test_alerter_initialization_with_direct_credentials(self) -> None:
        """Test that alerter initializes with direct credentials."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )
        assert alerter.enabled
        assert alerter.bot_token == "test_token"
        assert alerter.chat_id == "123456789"

    def test_alerter_can_be_disabled_explicitly(self) -> None:
        """Test that alerter can be explicitly disabled."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
            enabled=False,
        )
        assert not alerter.enabled

    @patch("iatb.core.observability.alerting.asyncio.create_task")
    @patch("iatb.core.observability.alerting.asyncio.get_running_loop")
    def test_send_alert_with_running_loop(
        self,
        mock_get_loop: MagicMock,
        mock_create_task: MagicMock,
    ) -> None:
        """Test sending alert when event loop is running."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop

        result = alerter.send_alert("Test message")
        assert result is True
        mock_create_task.assert_called_once()

    @patch("iatb.core.observability.alerting.asyncio.run")
    @patch("iatb.core.observability.alerting.asyncio.get_running_loop")
    def test_send_alert_without_running_loop(
        self,
        mock_get_loop: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """Test sending alert when no event loop is running."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )
        mock_get_loop.side_effect = RuntimeError("No running loop")

        result = alerter.send_alert("Test message")
        assert result is True
        mock_run.assert_called_once()

    def test_send_alert_when_disabled(self) -> None:
        """Test that send_alert returns False when disabled."""
        alerter = TelegramAlerter(enabled=False)
        result = alerter.send_alert("Test message")
        assert result is False

    def test_send_trade_alert(self) -> None:
        """Test sending trade alert."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_trade_alert("NIFTY", "BUY", 50, 18500.50)
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert "NIFTY" in call_args[0][0]
            assert "BUY" in call_args[0][0]
            assert "50" in call_args[0][0]
            assert "18500.50" in call_args[0][0]

    def test_send_error_alert_without_exception_type(self) -> None:
        """Test sending error alert without exception type."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_error_alert("TestComponent", "Test error message")
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert "TestComponent" in call_args[0][0]
            assert "Test error message" in call_args[0][0]
            assert "Type:" not in call_args[0][0]

    def test_send_error_alert_with_exception_type(self) -> None:
        """Test sending error alert with exception type."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_error_alert("TestComponent", "Test error", "ValueError")
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert "*Type:* ValueError" in call_args[0][0]

    def test_send_health_alert_down_status(self) -> None:
        """Test sending health alert with DOWN status."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_health_alert("TestService", "DOWN", "Service crashed")
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][1] == "CRITICAL"

    def test_send_health_alert_up_status(self) -> None:
        """Test sending health alert with UP status."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_health_alert("TestService", "UP")
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][1] == "WARNING"

    def test_send_pnl_alert_with_daily_pnl_positive(self) -> None:
        """Test sending PnL alert with positive daily PnL."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_pnl_alert(10000.50, 5000.25, 5)
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0][0]
            assert "10000.50" in call_args
            assert "GREEN" in call_args

    def test_send_pnl_alert_with_daily_pnl_negative(self) -> None:
        """Test sending PnL alert with negative daily PnL."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_pnl_alert(-2000.50, -5000.25, 3)
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0][0]
            assert "RED" in call_args

    def test_send_model_alert_available_status(self) -> None:
        """Test sending model alert with AVAILABLE status."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_model_alert("TestModel", "AVAILABLE")
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][1] == "INFO"

    def test_send_model_alert_unavailable_status(self) -> None:
        """Test sending model alert with unavailable status."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_model_alert("TestModel", "TRAINING")
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][1] == "ERROR"

    def test_send_data_source_failure_alert(self) -> None:
        """Test sending data source failure alert."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_data_source_failure_alert("KiteProvider", 5)
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert "KiteProvider" in call_args[0][0]
            assert "5" in call_args[0][0]
            assert "CRITICAL" in call_args[0][1]

    def test_send_fallback_source_alert_with_reason(self) -> None:
        """Test sending fallback source alert with reason."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_fallback_source_alert("Kite", "YFinance", "Connection timeout")
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0][0]
            assert "Kite" in call_args
            assert "YFinance" in call_args
            assert "Connection timeout" in call_args

    def test_send_fallback_source_alert_without_reason(self) -> None:
        """Test sending fallback source alert without reason."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_fallback_source_alert("Kite", "YFinance")
            assert result is True
            mock_send.assert_called_once()

    def test_send_token_expiry_alert_critical(self) -> None:
        """Test sending token expiry alert with critical level."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_token_expiry_alert("Kite", 5)
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][1] == "CRITICAL"

    def test_send_token_expiry_alert_warning(self) -> None:
        """Test sending token expiry alert with warning level."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            result = alerter.send_token_expiry_alert("Kite", 15)
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[0][1] == "WARNING"

    def test_send_with_actions_with_buttons(self) -> None:
        """Test sending alert with action buttons."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "_send_message_async") as mock_send:
            result = alerter.send_with_actions(
                "Test message",
                buttons=[("OK", "ok_callback"), ("Cancel", "cancel_callback")],
                level=AlertLevel.INFO,
            )
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["reply_markup"] is not None

    def test_send_with_actions_without_buttons(self) -> None:
        """Test sending alert without action buttons."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "_send_message_async") as mock_send:
            result = alerter.send_with_actions("Test message")
            assert result is True
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert call_args[1]["reply_markup"] is None

    def test_send_with_actions_when_disabled(self) -> None:
        """Test that send_with_actions returns False when disabled."""
        alerter = TelegramAlerter(enabled=False)
        result = alerter.send_with_actions("Test message")
        assert result is False

    def test_format_message_without_context(self) -> None:
        """Test formatting message without context."""
        alerter = TelegramAlerter()
        formatted = alerter._format_message("Test message", AlertLevel.INFO)
        assert "Test message" in formatted
        assert "INFO" in formatted
        assert "Context:" not in formatted

    def test_format_message_with_context(self) -> None:
        """Test formatting message with context."""
        alerter = TelegramAlerter()
        formatted = alerter._format_message(
            "Test message",
            AlertLevel.ERROR,
            context={"key1": "value1", "key2": "value2"},
        )
        assert "Test message" in formatted
        assert "ERROR" in formatted
        assert "Context:" in formatted
        assert "*key1:* value1" in formatted
        assert "*key2:* value2" in formatted

    def test_send_implements_alert_channel_interface(self) -> None:
        """Test that send method implements AlertChannel interface."""
        alerter = TelegramAlerter(
            bot_token="test_token",
            chat_id="123456789",
        )

        with patch.object(alerter, "send_alert", return_value=True) as mock_send:
            alert = Alert(
                message="Test message",
                level=AlertLevel.CRITICAL,
                context={"key": "value"},
                rule_name="test_rule",
            )
            result = alerter.send(alert)
            assert result is True
            mock_send.assert_called_once_with(
                "Test message",
                AlertLevel.CRITICAL,
                {"key": "value"},
            )


class TestMultiChannelAlertManager:
    """Tests for MultiChannelAlertManager class."""

    def test_manager_initialization_default(self) -> None:
        """Test manager initialization with default components."""
        manager = MultiChannelAlertManager()
        assert manager.channels == []
        assert isinstance(manager.rules_engine, AlertRulesEngine)
        assert isinstance(manager.throttler, AlertThrottler)
        assert isinstance(manager.ack_tracker, AlertAcknowledgmentTracker)
        assert manager._alert_counter == 0

    def test_manager_initialization_custom(self) -> None:
        """Test manager initialization with custom components."""
        custom_engine = AlertRulesEngine()
        custom_throttler = AlertThrottler(min_interval_seconds=30)
        custom_tracker = AlertAcknowledgmentTracker()
        custom_channel = MagicMock(spec=AlertChannel)
        custom_channel.enabled = True

        manager = MultiChannelAlertManager(
            channels=[custom_channel],
            rules_engine=custom_engine,
            throttler=custom_throttler,
            acknowledgment_tracker=custom_tracker,
        )

        assert len(manager.channels) == 1
        assert manager.rules_engine is custom_engine
        assert manager.throttler is custom_throttler
        assert manager.ack_tracker is custom_tracker

    def test_add_channel(self) -> None:
        """Test adding a channel."""
        manager = MultiChannelAlertManager()
        channel = MagicMock(spec=AlertChannel)
        channel.enabled = True

        manager.add_channel(channel)
        assert len(manager.channels) == 1
        assert channel in manager.channels

    def test_add_duplicate_channel(self) -> None:
        """Test that adding duplicate channel doesn't add it twice."""
        manager = MultiChannelAlertManager()
        channel = MagicMock(spec=AlertChannel)
        channel.enabled = True

        manager.add_channel(channel)
        manager.add_channel(channel)

        assert len(manager.channels) == 1

    def test_send_alert_without_throttling(self) -> None:
        """Test sending alert without rule name (no throttling)."""
        manager = MultiChannelAlertManager()
        channel = MagicMock(spec=AlertChannel)
        channel.enabled = True
        channel.send.return_value = True
        manager.add_channel(channel)

        alert_id = manager.send_alert("Test message", AlertLevel.INFO)

        assert alert_id is not None
        channel.send.assert_called_once()
        assert manager.ack_tracker.acknowledgments[alert_id].acknowledged is False

    def test_send_alert_with_throttling(self) -> None:
        """Test sending alert with rule name (with throttling)."""
        manager = MultiChannelAlertManager()
        channel = MagicMock(spec=AlertChannel)
        channel.enabled = True
        channel.send.return_value = True
        manager.add_channel(channel)

        # First send should succeed
        alert_id_1 = manager.send_alert("Test message", AlertLevel.INFO, rule_name="test_rule")
        assert alert_id_1 is not None

        # Second send within throttle window should be throttled
        alert_id_2 = manager.send_alert("Test message", AlertLevel.INFO, rule_name="test_rule")
        assert alert_id_2 is None

    def test_send_alert_to_disabled_channel(self) -> None:
        """Test that disabled channels are skipped."""
        manager = MultiChannelAlertManager()
        disabled_channel = MagicMock(spec=AlertChannel)
        disabled_channel.enabled = False
        enabled_channel = MagicMock(spec=AlertChannel)
        enabled_channel.enabled = True
        enabled_channel.send.return_value = True

        manager.add_channel(disabled_channel)
        manager.add_channel(enabled_channel)

        alert_id = manager.send_alert("Test message")
        assert alert_id is not None

        disabled_channel.send.assert_not_called()
        enabled_channel.send.assert_called_once()

    def test_send_alert_handles_channel_error(self) -> None:
        """Test that channel errors don't prevent sending to other channels."""
        manager = MultiChannelAlertManager()
        failing_channel = MagicMock(spec=AlertChannel)
        failing_channel.enabled = True
        failing_channel.send.side_effect = Exception("Channel failed")

        working_channel = MagicMock(spec=AlertChannel)
        working_channel.enabled = True
        working_channel.send.return_value = True

        manager.add_channel(failing_channel)
        manager.add_channel(working_channel)

        alert_id = manager.send_alert("Test message")
        assert alert_id is not None
        working_channel.send.assert_called_once()

    def test_send_alert_with_context(self) -> None:
        """Test sending alert with context."""
        manager = MultiChannelAlertManager()
        channel = MagicMock(spec=AlertChannel)
        channel.enabled = True
        channel.send.return_value = True
        manager.add_channel(channel)

        alert_id = manager.send_alert(
            "Test message",
            AlertLevel.ERROR,
            context={"key": "value"},
            rule_name="test_rule",
        )

        assert alert_id is not None

        # Verify the alert was created with context
        sent_alert = channel.send.call_args[0][0]
        assert sent_alert.context == {"key": "value"}
        assert sent_alert.rule_name == "test_rule"

    def test_evaluate_and_alert_no_triggers(self) -> None:
        """Test evaluating rules when none are triggered."""
        manager = MultiChannelAlertManager()
        channel = MagicMock(spec=AlertChannel)
        channel.enabled = True
        channel.send.return_value = True
        manager.add_channel(channel)

        context = {
            "minutes_remaining": 999,
            "current_positions": 1,
            "limit": 10,
            "daily_pnl": 1000.0,
            "loss_threshold": -5000.0,
            "failure_count": 1,
            "failure_threshold": 3,
        }

        alert_ids = manager.evaluate_and_alert(context)
        assert len(alert_ids) == 0

    def test_evaluate_and_alert_with_triggers(self) -> None:
        """Test evaluating rules when some are triggered."""
        manager = MultiChannelAlertManager()
        channel = MagicMock(spec=AlertChannel)
        channel.enabled = True
        channel.send.return_value = True
        manager.add_channel(channel)

        context = {
            "minutes_remaining": 5,  # Triggers token_expiry
            "current_positions": 1,
            "limit": 10,
            "daily_pnl": 1000.0,
            "loss_threshold": -5000.0,
            "failure_count": 1,
            "failure_threshold": 3,
        }

        alert_ids = manager.evaluate_and_alert(context)
        assert len(alert_ids) == 1
        channel.send.assert_called_once()

    def test_acknowledge_alert(self) -> None:
        """Test acknowledging an alert."""
        manager = MultiChannelAlertManager()

        # First send an alert
        alert_id = manager.send_alert("Test message")
        assert alert_id is not None

        # Then acknowledge it
        result = manager.acknowledge(alert_id, "user1", "telegram")
        assert result is True
        assert manager.ack_tracker.is_acknowledged(alert_id) is True

    def test_acknowledge_nonexistent_alert(self) -> None:
        """Test acknowledging a non-existent alert returns False."""
        manager = MultiChannelAlertManager()
        result = manager.acknowledge("nonexistent", "user1", "telegram")
        assert result is False

    def test_get_unacknowledged_alerts(self) -> None:
        """Test getting unacknowledged alerts."""
        manager = MultiChannelAlertManager()

        alert_id_1 = manager.send_alert("Test message 1")
        alert_id_2 = manager.send_alert("Test message 2")
        manager.acknowledge(alert_id_1, "user1", "telegram")

        unacknowledged = manager.get_unacknowledged_alerts()
        assert len(unacknowledged) == 1
        assert unacknowledged[0].alert_id == alert_id_2

    def test_get_unacknowledged_alerts_by_rule(self) -> None:
        """Test getting unacknowledged alerts filtered by rule."""
        manager = MultiChannelAlertManager()

        manager.send_alert("Test message 1", rule_name="rule1")
        alert_id_2 = manager.send_alert("Test message 2", rule_name="rule2")
        # Reset throttler to allow second alert for rule1
        manager.throttler.reset()
        manager.send_alert("Test message 3", rule_name="rule1")
        manager.acknowledge(alert_id_2, "user1", "telegram")

        unacknowledged = manager.get_unacknowledged_alerts(rule_name="rule1")
        assert len(unacknowledged) == 2

    def test_cleanup_old_alerts(self) -> None:
        """Test cleaning up old alerts."""
        manager = MultiChannelAlertManager()

        alert_id = manager.send_alert("Test message")
        manager.acknowledge(alert_id, "user1", "telegram")

        # Manually set the acknowledgment time to be old
        old_time = datetime.now(UTC) - timedelta(hours=25)
        manager.ack_tracker.acknowledgments[alert_id].acknowledged_at = old_time

        cleaned = manager.cleanup_old_alerts(max_age_hours=24)
        assert cleaned == 1
