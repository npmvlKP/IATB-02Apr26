"""Tests for multi-channel alerting system."""

import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_external_deps():
    mocks = {
        "aiohttp": MagicMock(),
        "telegram": MagicMock(),
        "telegram.error": MagicMock(),
        "telegram.error.TelegramError": Exception,
    }
    original = {}
    for mod in mocks:
        original[mod] = sys.modules.get(mod)
        sys.modules[mod] = mocks[mod]
    yield
    for mod, orig in original.items():
        if orig is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = orig


class TestAlert:
    def test_creation_defaults(self) -> None:
        from iatb.core.observability.alerting import Alert

        alert = Alert(message="test")
        assert alert.message == "test"
        assert alert.level == "INFO"
        assert alert.context == {}
        assert alert.rule_name is None
        assert alert.alert_id is None

    def test_creation_with_all_fields(self) -> None:
        from iatb.core.observability.alerting import Alert

        ts = datetime.now(UTC)
        alert = Alert(
            message="test",
            level="CRITICAL",
            timestamp=ts,
            context={"key": "value"},
            rule_name="test_rule",
            alert_id="alert_1",
        )
        assert alert.message == "test"
        assert alert.level == "CRITICAL"
        assert alert.timestamp == ts
        assert alert.context == {"key": "value"}
        assert alert.rule_name == "test_rule"
        assert alert.alert_id == "alert_1"


class TestAlertLevel:
    def test_values(self) -> None:
        from iatb.core.observability.alerting import AlertLevel

        assert AlertLevel.INFO == "INFO"
        assert AlertLevel.WARNING == "WARNING"
        assert AlertLevel.ERROR == "ERROR"
        assert AlertLevel.CRITICAL == "CRITICAL"


class TestAlertThrottler:
    def test_first_send_allowed(self) -> None:
        from iatb.core.observability.alerting import AlertThrottler

        throttler = AlertThrottler()
        assert throttler.should_send("rule1")

    def test_second_send_throttled(self) -> None:
        from iatb.core.observability.alerting import AlertThrottler

        throttler = AlertThrottler(min_interval_seconds=60)
        throttler.record_sent("rule1")
        assert not throttler.should_send("rule1")

    def test_different_rules_not_throttled(self) -> None:
        from iatb.core.observability.alerting import AlertThrottler

        throttler = AlertThrottler()
        throttler.record_sent("rule1")
        assert throttler.should_send("rule2")

    def test_reset_allows_resend(self) -> None:
        from iatb.core.observability.alerting import AlertThrottler

        throttler = AlertThrottler(min_interval_seconds=60)
        throttler.record_sent("rule1")
        throttler.reset("rule1")
        assert throttler.should_send("rule1")

    def test_reset_all(self) -> None:
        from iatb.core.observability.alerting import AlertThrottler

        throttler = AlertThrottler()
        throttler.record_sent("rule1")
        throttler.record_sent("rule2")
        throttler.reset()
        assert throttler.should_send("rule1")
        assert throttler.should_send("rule2")


class TestAlertAcknowledgmentTracker:
    def test_register_and_acknowledge(self) -> None:
        from iatb.core.observability.alerting import AlertAcknowledgmentTracker

        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_1", "test_rule")
        result = tracker.acknowledge("alert_1", "user1", "api")
        assert result is True
        assert tracker.is_acknowledged("alert_1")

    def test_acknowledge_nonexistent(self) -> None:
        from iatb.core.observability.alerting import AlertAcknowledgmentTracker

        tracker = AlertAcknowledgmentTracker()
        assert tracker.acknowledge("nonexistent", "user1", "api") is False

    def test_get_unacknowledged(self) -> None:
        from iatb.core.observability.alerting import AlertAcknowledgmentTracker

        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_1", "rule1")
        tracker.register_alert("alert_2", "rule1")
        tracker.acknowledge("alert_1", "user1", "api")
        unack = tracker.get_unacknowledged()
        assert len(unack) == 1
        assert unack[0].alert_id == "alert_2"

    def test_cleanup_old_alerts(self) -> None:
        from iatb.core.observability.alerting import AlertAcknowledgmentTracker

        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_1", "rule1")
        tracker.acknowledge("alert_1", "user1", "api")
        tracker.acknowledgments["alert_1"].acknowledged_at = datetime.now(UTC) - timedelta(hours=1)
        cleaned = tracker.cleanup_old_alerts(max_age_hours=0)
        assert cleaned == 1


class TestAlertRulesEngine:
    def test_default_rules_initialized(self) -> None:
        from iatb.core.observability.alerting import AlertRulesEngine

        engine = AlertRulesEngine()
        assert "token_expiry" in engine.rules
        assert "position_limit_breach" in engine.rules
        assert "daily_loss_threshold" in engine.rules
        assert "data_source_failure" in engine.rules

    def test_evaluate_token_expiry_triggered(self) -> None:
        from iatb.core.observability.alerting import AlertRulesEngine

        engine = AlertRulesEngine()
        triggered = engine.evaluate_rules({"minutes_remaining": 5})
        assert len(triggered) == 1
        assert triggered[0][0].name == "token_expiry"

    def test_evaluate_no_trigger(self) -> None:
        from iatb.core.observability.alerting import AlertRulesEngine

        engine = AlertRulesEngine()
        triggered = engine.evaluate_rules({"minutes_remaining": 999})
        assert len(triggered) == 0

    def test_add_and_remove_rule(self) -> None:
        from iatb.core.observability.alerting import AlertRule, AlertRulesEngine

        engine = AlertRulesEngine()
        engine.remove_rule("token_expiry")
        assert "token_expiry" not in engine.rules

        engine.add_rule(AlertRule(name="custom", condition=lambda ctx: False))
        assert "custom" in engine.rules

    def test_disabled_rule_not_evaluated(self) -> None:
        from iatb.core.observability.alerting import AlertRulesEngine

        engine = AlertRulesEngine()
        engine.rules["token_expiry"].enabled = False
        triggered = engine.evaluate_rules({"minutes_remaining": 0})
        assert len(triggered) == 0


class TestMultiChannelAlertManager:
    def test_send_alert_with_no_channels(self) -> None:
        from iatb.core.observability.alerting import MultiChannelAlertManager

        manager = MultiChannelAlertManager(channels=[])
        alert_id = manager.send_alert("test", "INFO")
        assert alert_id is not None

    def test_send_alert_throttled(self) -> None:
        from iatb.core.observability.alerting import (
            Alert,
            AlertChannel,
            MultiChannelAlertManager,
        )

        class AlwaysSendChannel(AlertChannel):
            def __init__(self) -> None:
                self.enabled = True
                self.sent: list[Alert] = []

            def send(self, alert: Alert) -> bool:
                self.sent.append(alert)
                return True

        manager = MultiChannelAlertManager(channels=[AlwaysSendChannel()])
        manager.send_alert("test1", "INFO", rule_name="rule1")
        assert manager.send_alert("test2", "INFO", rule_name="rule1") is None

    def test_evaluate_and_alert(self) -> None:
        from iatb.core.observability.alerting import (
            Alert,
            AlertChannel,
            MultiChannelAlertManager,
        )

        class AlwaysSendChannel(AlertChannel):
            def __init__(self) -> None:
                self.enabled = True
                self.sent: list[Alert] = []

            def send(self, alert: Alert) -> bool:
                self.sent.append(alert)
                return True

        manager = MultiChannelAlertManager(channels=[AlwaysSendChannel()])
        alert_ids = manager.evaluate_and_alert({"minutes_remaining": 0})
        assert len(alert_ids) == 1

    def test_acknowledge(self) -> None:
        from iatb.core.observability.alerting import MultiChannelAlertManager

        manager = MultiChannelAlertManager()
        alert_id = manager.send_alert("test", "INFO", rule_name="rule1")
        result = manager.acknowledge(alert_id, "user1", "api")
        assert result is True

    def test_get_unacknowledged(self) -> None:
        from iatb.core.observability.alerting import MultiChannelAlertManager

        manager = MultiChannelAlertManager()
        manager.send_alert("test", "INFO", rule_name="rule1")
        unack = manager.get_unacknowledged_alerts()
        assert len(unack) >= 1


class TestGetAlerter:
    def test_returns_singleton(self) -> None:
        import iatb.core.observability.alerting as _mod

        original = _mod._alerter
        _mod._alerter = None
        try:
            a1 = _mod.get_alerter()
            a2 = _mod.get_alerter()
            assert a1 is a2
        finally:
            _mod._alerter = original


class TestGetMultiChannelManager:
    def test_returns_singleton(self) -> None:
        import iatb.core.observability.alerting as _mod

        original = _mod._multi_channel_manager
        _mod._multi_channel_manager = None
        try:
            m1 = _mod.get_multi_channel_manager()
            m2 = _mod.get_multi_channel_manager()
            assert m1 is m2
        finally:
            _mod._multi_channel_manager = original
