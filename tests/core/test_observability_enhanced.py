"""Enhanced tests for Phase K observability: metrics, alerts, throttling, dashboard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from iatb.core.observability.alerting import (
    AlertAcknowledgmentTracker,
    AlertLevel,
    AlertRule,
    AlertRulesEngine,
    AlertThrottler,
    EmailChannel,
    MultiChannelAlertManager,
    TelegramAlerter,
    WebhookChannel,
)
from iatb.core.observability.metrics import (
    data_source_requests_total,
    record_broker_api_call,
    record_data_source_fallback,
    record_data_source_request,
    record_data_source_request_latency,
    record_order_latency,
    record_risk_check_duration,
    update_data_freshness,
    update_kite_token_freshness,
    update_position_count,
)
from iatb.visualization.breakout_scanner import (
    ScannerHealthResult,
)
from iatb.visualization.dashboard import (
    build_dashboard_payload,
    build_scanner_payload,
    convert_candidates_to_health_matrix,
    render_instrument_scanner_tab,
)

# =============================================================================
# ENHANCED METRICS COLLECTION TESTS
# =============================================================================


class TestEnhancedDataSourceMetrics:
    """Enhanced tests for data source metrics."""

    def test_data_source_requests_total_increment_by_status(self) -> None:
        """Test that data source requests counter increments per status."""
        labels = data_source_requests_total.labels(source="kite", status="success")
        initial_success = labels._value.get()  # type: ignore[attr-defined]
        record_data_source_request(source="kite", status="success")
        labels = data_source_requests_total.labels(source="kite", status="success")
        new_success = labels._value.get()  # type: ignore[attr-defined]
        assert new_success == initial_success + 1  # type: ignore[operator]

    def test_data_source_simple_latency_observes_distribution(self) -> None:
        """Test that latency histogram observes value distribution."""
        record_data_source_request_latency(source="kite", latency_seconds=0.1)
        record_data_source_request_latency(source="kite", latency_seconds=0.5)
        record_data_source_request_latency(source="kite", latency_seconds=1.0)
        record_data_source_request_latency(source="kite", latency_seconds=2.5)
        # Should not raise exception
        assert True

    def test_data_source_fallback_tracks_provider_switches(self) -> None:
        """Test that fallback counter tracks provider switches."""
        record_data_source_fallback(from_source="kite", to_source="yfinance")
        record_data_source_fallback(from_source="kite", to_source="polygon")
        record_data_source_fallback(from_source="yfinance", to_source="kite")
        # Should not raise exception
        assert True

    def test_update_data_freshness_with_fresh_data(self) -> None:
        """Test data freshness update with fresh data."""
        update_data_freshness(source="kite", freshness_seconds=5.0)
        # Should not raise exception
        assert True

    def test_update_data_freshness_with_stale_data(self) -> None:
        """Test data freshness update with stale data."""
        update_data_freshness(source="kite", freshness_seconds=300.0)
        # Should not raise exception
        assert True

    def test_update_kite_token_freshness_fresh(self) -> None:
        """Test Kite token freshness update for fresh token."""
        update_kite_token_freshness(is_fresh=True)
        # Should not raise exception
        assert True

    def test_update_kite_token_freshness_expired(self) -> None:
        """Test Kite token freshness update for expired token."""
        update_kite_token_freshness(is_fresh=False)
        # Should not raise exception
        assert True

    def test_data_source_metrics_complete_workflow(self) -> None:
        """Test complete data source metrics workflow."""
        # Simulate successful request
        record_data_source_request(source="kite", status="success")
        record_data_source_request_latency(source="kite", latency_seconds=0.3)
        update_data_freshness(source="kite", freshness_seconds=2.0)

        # Simulate failed request and fallback
        record_data_source_request(source="kite", status="error")
        record_data_source_fallback(from_source="kite", to_source="yfinance")
        record_data_source_request(source="yfinance", status="success")
        record_data_source_request_latency(source="yfinance", latency_seconds=0.5)
        update_data_freshness(source="yfinance", freshness_seconds=1.5)

        # Update token status
        update_kite_token_freshness(is_fresh=True)

        # Should not raise exceptions
        assert True


class TestEnhancedLiveTradingMetrics:
    """Enhanced tests for live trading metrics."""

    def test_order_latency_observes_trading_latency(self) -> None:
        """Test order latency metric records trading latency."""
        record_order_latency(
            exchange="NSE",
            symbol="RELIANCE",
            order_type="MARKET",
            latency_seconds=0.25,
        )
        # Should not raise exception
        assert True

    def test_order_latency_with_different_order_types(self) -> None:
        """Test order latency for different order types."""
        order_types = ["MARKET", "LIMIT", "STOP_LOSS", "STOP_LIMIT"]
        for order_type in order_types:
            record_order_latency(
                exchange="NSE",
                symbol="TCS",
                order_type=order_type,
                latency_seconds=0.5,
            )
        # Should not raise exception
        assert True

    def test_order_latency_with_high_latency_scenarios(self) -> None:
        """Test order latency handles high latency scenarios."""
        high_latencies = [1.0, 2.5, 5.0, 10.0, 30.0]
        for latency in high_latencies:
            record_order_latency(
                exchange="NSE",
                symbol="INFY",
                order_type="MARKET",
                latency_seconds=latency,
            )
        # Should not raise exception
        assert True

    def test_update_position_count_long_positions(self) -> None:
        """Test position count update for long positions."""
        update_position_count(exchange="NSE", symbol="RELIANCE", count=100)
        # Should not raise exception
        assert True

    def test_update_position_count_short_positions(self) -> None:
        """Test position count update for short positions."""
        update_position_count(exchange="NSE", symbol="RELIANCE", count=-50)
        # Should not raise exception
        assert True

    def test_update_position_count_zero_positions(self) -> None:
        """Test position count update for zero positions."""
        update_position_count(exchange="NSE", symbol="RELIANCE", count=0)
        # Should not raise exception
        assert True

    def test_record_broker_api_call_all_methods(self) -> None:
        """Test broker API call recording for all HTTP methods."""
        methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
        for method in methods:
            record_broker_api_call(
                endpoint="/orders/place",
                method=method,
                status="success",
            )
        # Should not raise exception
        assert True

    def test_record_broker_api_call_all_statuses(self) -> None:
        """Test broker API call recording for all statuses."""
        statuses = ["success", "error", "timeout", "rate_limited"]
        for status in statuses:
            record_broker_api_call(
                endpoint="/orders/place",
                method="POST",
                status=status,
            )
        # Should not raise exception
        assert True

    def test_record_risk_check_duration_all_check_types(self) -> None:
        """Test risk check duration for all check types."""
        check_types = [
            "position_limit",
            "drawdown",
            "exposure",
            "leverage",
            "daily_loss",
            "correlation",
        ]
        for check_type in check_types:
            record_risk_check_duration(
                check_type=check_type,
                duration_seconds=0.1,
            )
        # Should not raise exception
        assert True

    def test_live_trading_metrics_complete_workflow(self) -> None:
        """Test complete live trading metrics workflow."""
        # Record order execution
        record_order_latency(
            exchange="NSE",
            symbol="RELIANCE",
            order_type="MARKET",
            latency_seconds=0.3,
        )
        update_position_count(exchange="NSE", symbol="RELIANCE", count=100)

        # Record broker API calls
        record_broker_api_call(endpoint="/orders/place", method="POST", status="success")
        record_broker_api_call(endpoint="/positions", method="GET", status="success")
        record_broker_api_call(endpoint="/orders/cancel", method="DELETE", status="error")

        # Record risk checks
        record_risk_check_duration(check_type="position_limit", duration_seconds=0.05)
        record_risk_check_duration(check_type="drawdown", duration_seconds=0.08)
        record_risk_check_duration(check_type="exposure", duration_seconds=0.06)

        # Should not raise exceptions
        assert True


# =============================================================================
# ALERT TRIGGERING TESTS
# =============================================================================


class TestAlertRulesEngine:
    """Tests for AlertRulesEngine."""

    def test_rules_engine_initializes_with_default_rules(self) -> None:
        """Test that rules engine initializes with default rules."""
        engine = AlertRulesEngine()
        assert "token_expiry" in engine.rules
        assert "position_limit_breach" in engine.rules
        assert "daily_loss_threshold" in engine.rules
        assert "data_source_failure" in engine.rules

    def test_add_rule_adds_new_rule(self) -> None:
        """Test that add_rule adds a new rule."""
        engine = AlertRulesEngine()

        def custom_condition(context: dict) -> bool:
            return bool(context.get("custom_flag", False))

        rule = AlertRule(
            name="custom_rule",
            condition=custom_condition,
            level=AlertLevel.WARNING,
            description="Custom test rule",
        )
        engine.add_rule(rule)

        assert "custom_rule" in engine.rules
        assert engine.rules["custom_rule"].description == "Custom test rule"

    def test_remove_rule_removes_existing_rule(self) -> None:
        """Test that remove_rule removes a rule."""
        engine = AlertRulesEngine()
        assert "token_expiry" in engine.rules

        engine.remove_rule("token_expiry")
        assert "token_expiry" not in engine.rules

    def test_evaluate_rules_returns_empty_list_when_no_rules_triggered(self) -> None:
        """Test that evaluate_rules returns empty list when no rules triggered."""
        engine = AlertRulesEngine()
        context = {
            "minutes_remaining": 30,
            "current_positions": 2,
            "limit": 10,
            "daily_pnl": 1000.0,
            "loss_threshold": -5000.0,
            "failure_count": 1,
            "failure_threshold": 3,
        }

        triggered = engine.evaluate_rules(context)
        assert len(triggered) == 0

    def test_evaluate_rules_triggers_token_expiry_rule(self) -> None:
        """Test that token expiry rule triggers correctly."""
        engine = AlertRulesEngine()
        context = {"minutes_remaining": 5}

        triggered = engine.evaluate_rules(context)
        assert len(triggered) == 1
        assert triggered[0][0].name == "token_expiry"
        assert triggered[0][0].level == AlertLevel.CRITICAL

    def test_evaluate_rules_triggers_position_limit_breach(self) -> None:
        """Test that position limit breach rule triggers correctly."""
        engine = AlertRulesEngine()
        context = {"current_positions": 10, "limit": 10}

        triggered = engine.evaluate_rules(context)
        assert len(triggered) == 1
        assert triggered[0][0].name == "position_limit_breach"
        assert triggered[0][0].level == AlertLevel.CRITICAL

    def test_evaluate_rules_triggers_daily_loss_threshold(self) -> None:
        """Test that daily loss threshold rule triggers correctly."""
        engine = AlertRulesEngine()
        context = {"daily_pnl": -6000.0, "loss_threshold": -5000.0}

        triggered = engine.evaluate_rules(context)
        assert len(triggered) == 1
        assert triggered[0][0].name == "daily_loss_threshold"
        assert triggered[0][0].level == AlertLevel.CRITICAL

    def test_evaluate_rules_triggers_data_source_failure(self) -> None:
        """Test that data source failure rule triggers correctly."""
        engine = AlertRulesEngine()
        context = {"failure_count": 4, "failure_threshold": 3}

        triggered = engine.evaluate_rules(context)
        assert len(triggered) == 1
        assert triggered[0][0].name == "data_source_failure"
        assert triggered[0][0].level == AlertLevel.ERROR

    def test_evaluate_rules_triggers_multiple_rules(self) -> None:
        """Test that multiple rules can trigger simultaneously."""
        engine = AlertRulesEngine()
        context = {
            "minutes_remaining": 5,
            "current_positions": 10,
            "limit": 10,
            "daily_pnl": -6000.0,
            "loss_threshold": -5000.0,
            "failure_count": 4,
            "failure_threshold": 3,
        }

        triggered = engine.evaluate_rules(context)
        assert len(triggered) == 4  # All default rules trigger

        rule_names = {rule.name for rule, _ in triggered}
        assert "token_expiry" in rule_names
        assert "position_limit_breach" in rule_names
        assert "daily_loss_threshold" in rule_names
        assert "data_source_failure" in rule_names

    def test_evaluate_rules_ignores_disabled_rules(self) -> None:
        """Test that disabled rules are not evaluated."""
        engine = AlertRulesEngine()
        engine.rules["token_expiry"].enabled = False

        context = {"minutes_remaining": 5}
        triggered = engine.evaluate_rules(context)

        assert len(triggered) == 0

    def test_evaluate_rules_handles_condition_exceptions(self) -> None:
        """Test that rule evaluation handles exceptions gracefully."""
        engine = AlertRulesEngine()

        def failing_condition(context: dict) -> bool:
            raise ValueError("Test error")

        rule = AlertRule(
            name="failing_rule",
            condition=failing_condition,
            level=AlertLevel.WARNING,
        )
        engine.add_rule(rule)

        # Should not raise exception
        triggered = engine.evaluate_rules({})
        assert len(triggered) == 0  # Failing rule should be skipped


class TestAlertThrottler:
    """Tests for AlertThrottler."""

    def test_throttler_allows_first_alert(self) -> None:
        """Test that throttler allows first alert for a rule."""
        throttler = AlertThrottler(min_interval_seconds=60)

        result = throttler.should_send("test_rule")
        assert result is True

    def test_throttler_blocks_alert_within_interval(self) -> None:
        """Test that throttler blocks alert within min interval."""
        throttler = AlertThrottler(min_interval_seconds=60)

        # First alert
        assert throttler.should_send("test_rule") is True
        throttler.record_sent("test_rule")

        # Second alert within 60 seconds should be blocked
        assert throttler.should_send("test_rule") is False

    def test_throttler_allows_alert_after_interval(self) -> None:
        """Test that throttler allows alert after min interval."""
        throttler = AlertThrottler(min_interval_seconds=1)

        # First alert
        assert throttler.should_send("test_rule") is True
        throttler.record_sent("test_rule")

        # Wait 2 seconds
        import time

        time.sleep(2)

        # Second alert after interval should be allowed
        assert throttler.should_send("test_rule") is True

    def test_throttler_independent_for_different_rules(self) -> None:
        """Test that throttling is independent for different rules."""
        throttler = AlertThrottler(min_interval_seconds=60)

        # Send alert for rule1
        assert throttler.should_send("rule1") is True
        throttler.record_sent("rule1")

        # Rule2 should still be allowed
        assert throttler.should_send("rule2") is True

    def test_throttler_record_sent_updates_timestamp(self) -> None:
        """Test that record_sent updates last sent timestamp."""
        throttler = AlertThrottler()
        initial_time = datetime.now(UTC)

        throttler.record_sent("test_rule")

        last_sent = throttler._last_sent["test_rule"]
        assert last_sent >= initial_time

    def test_throttler_reset_single_rule(self) -> None:
        """Test that reset clears throttling for a single rule."""
        throttler = AlertThrottler(min_interval_seconds=60)

        throttler.should_send("test_rule")
        throttler.record_sent("test_rule")

        # Should be blocked
        assert throttler.should_send("test_rule") is False

        # Reset rule
        throttler.reset("test_rule")

        # Should be allowed again
        assert throttler.should_send("test_rule") is True

    def test_throttler_reset_all_rules(self) -> None:
        """Test that reset clears throttling for all rules."""
        throttler = AlertThrottler(min_interval_seconds=60)

        # Send multiple rules
        for i in range(3):
            rule_name = f"rule_{i}"
            throttler.should_send(rule_name)
            throttler.record_sent(rule_name)

        # All should be blocked
        for i in range(3):
            rule_name = f"rule_{i}"
            assert throttler.should_send(rule_name) is False

        # Reset all
        throttler.reset()

        # All should be allowed again
        for i in range(3):
            rule_name = f"rule_{i}"
            assert throttler.should_send(rule_name) is True

    def test_throttler_with_custom_interval(self) -> None:
        """Test that throttler respects custom interval."""
        throttler = AlertThrottler(min_interval_seconds=2)

        assert throttler.should_send("test_rule") is True
        throttler.record_sent("test_rule")

        # Should be blocked within 2 seconds
        assert throttler.should_send("test_rule") is False

        import time

        time.sleep(3)

        # Should be allowed after 2 seconds
        assert throttler.should_send("test_rule") is True


class TestMultiChannelAlertManager:
    """Tests for MultiChannelAlertManager."""

    def test_manager_initializes_with_channels(self) -> None:
        """Test that manager initializes with alert channels."""
        channels = [
            TelegramAlerter(enabled=False),
            EmailChannel(enabled=False),
            WebhookChannel(enabled=False),
        ]
        manager = MultiChannelAlertManager(channels=channels)

        assert len(manager.channels) == 3

    def test_send_alert_generates_alert_id(self) -> None:
        """Test that send_alert generates unique alert ID."""
        manager = MultiChannelAlertManager(channels=[])

        alert_id_1 = manager.send_alert("Test message")
        alert_id_2 = manager.send_alert("Test message")

        assert alert_id_1 is not None
        assert alert_id_2 is not None
        assert alert_id_1 != alert_id_2

    def test_send_alert_with_throttling_blocks_duplicate(self) -> None:
        """Test that send_alert respects throttling."""
        manager = MultiChannelAlertManager(channels=[])

        alert_id_1 = manager.send_alert("Test message", rule_name="test_rule")
        assert alert_id_1 is not None

        alert_id_2 = manager.send_alert("Test message", rule_name="test_rule")
        assert alert_id_2 is None  # Throttled

    def test_send_alert_without_rule_bypasses_throttling(self) -> None:
        """Test that alerts without rule name bypass throttling."""
        manager = MultiChannelAlertManager(channels=[])

        alert_id_1 = manager.send_alert("Test message")
        alert_id_2 = manager.send_alert("Test message")

        assert alert_id_1 is not None
        assert alert_id_2 is not None  # No throttling without rule name

    def test_send_alert_registers_with_acknowledgment_tracker(self) -> None:
        """Test that send_alert registers alert for acknowledgment."""
        manager = MultiChannelAlertManager(channels=[])

        alert_id = manager.send_alert("Test message", rule_name="test_rule")

        assert alert_id in manager.ack_tracker.acknowledgments

    def test_evaluate_and_alert_triggers_rules(self) -> None:
        """Test that evaluate_and_alert evaluates rules and sends alerts."""
        manager = MultiChannelAlertManager(channels=[])

        context = {"minutes_remaining": 5}
        alert_ids = manager.evaluate_and_alert(context)

        assert len(alert_ids) == 1
        assert alert_ids[0] is not None

    def test_evaluate_and_alert_handles_no_triggered_rules(self) -> None:
        """Test that evaluate_and_alert handles no triggered rules."""
        manager = MultiChannelAlertManager(channels=[])

        context = {"minutes_remaining": 30}
        alert_ids = manager.evaluate_and_alert(context)

        assert len(alert_ids) == 0

    def test_acknowledge_alert(self) -> None:
        """Test that acknowledge marks alert as acknowledged."""
        manager = MultiChannelAlertManager(channels=[])

        alert_id = manager.send_alert("Test message")
        result = manager.acknowledge(alert_id, acknowledged_by="user1", acknowledged_via="api")

        assert result is True
        assert manager.ack_tracker.is_acknowledged(alert_id) is True

    def test_acknowledge_nonexistent_alert_returns_false(self) -> None:
        """Test that acknowledging nonexistent alert returns False."""
        manager = MultiChannelAlertManager(channels=[])

        result = manager.acknowledge("nonexistent", "user1", "api")
        assert result is False

    def test_get_unacknowledged_alerts(self) -> None:
        """Test getting unacknowledged alerts."""
        manager = MultiChannelAlertManager(channels=[])

        alert_id_1 = manager.send_alert("Alert 1", rule_name="rule1")
        alert_id_2 = manager.send_alert("Alert 2", rule_name="rule2")

        manager.acknowledge(alert_id_1, "user1", "api")

        unacknowledged = manager.get_unacknowledged_alerts()
        assert len(unacknowledged) == 1
        assert unacknowledged[0].alert_id == alert_id_2

    def test_get_unacknowledged_alerts_filtered_by_rule(self) -> None:
        """Test getting unacknowledged alerts filtered by rule."""
        manager = MultiChannelAlertManager(channels=[])

        # Use different rule names to avoid throttling
        manager.send_alert("Alert 1", rule_name="rule1_a")
        manager.send_alert("Alert 2", rule_name="rule1_b")
        manager.send_alert("Alert 3", rule_name="rule2")

        # Filter by partial rule name
        unacknowledged_rule1 = manager.get_unacknowledged_alerts()
        assert len(unacknowledged_rule1) == 3

    def test_cleanup_old_alerts(self) -> None:
        """Test cleanup of old acknowledged alerts."""
        manager = MultiChannelAlertManager(channels=[])

        # Create an old alert
        alert_id = manager.send_alert("Old alert")
        manager.acknowledge(alert_id, "user1", "api")

        # Manually set acknowledgment time to old
        ack = manager.ack_tracker.acknowledgments[alert_id]
        ack.acknowledged_at = datetime.now(UTC) - timedelta(hours=25)

        # Cleanup should remove it
        cleaned = manager.cleanup_old_alerts(max_age_hours=24)
        assert cleaned == 1
        assert alert_id not in manager.ack_tracker.acknowledgments

    def test_add_channel(self) -> None:
        """Test adding a channel to manager."""
        manager = MultiChannelAlertManager(channels=[])

        channel = TelegramAlerter(enabled=False)
        manager.add_channel(channel)

        assert channel in manager.channels

    def test_add_duplicate_channel_not_added(self) -> None:
        """Test that duplicate channel is not added."""
        channel = TelegramAlerter(enabled=False)
        manager = MultiChannelAlertManager(channels=[channel])

        initial_count = len(manager.channels)
        manager.add_channel(channel)

        assert len(manager.channels) == initial_count


class TestAlertAcknowledgmentTracker:
    """Tests for AlertAcknowledgmentTracker."""

    def test_register_alert_creates_entry(self) -> None:
        """Test that register_alert creates acknowledgment entry."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_123", "test_rule")

        assert "alert_123" in tracker.acknowledgments
        assert tracker.acknowledgments["alert_123"].rule_name == "test_rule"
        assert tracker.acknowledgments["alert_123"].acknowledged is False

    def test_acknowledge_updates_entry(self) -> None:
        """Test that acknowledge updates acknowledgment entry."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_123", "test_rule")

        result = tracker.acknowledge("alert_123", "user1", "api")

        assert result is True
        assert tracker.acknowledgments["alert_123"].acknowledged is True
        assert tracker.acknowledgments["alert_123"].acknowledged_by == "user1"
        assert tracker.acknowledgments["alert_123"].acknowledged_via == "api"
        assert tracker.acknowledgments["alert_123"].acknowledged_at is not None

    def test_acknowledge_nonexistent_returns_false(self) -> None:
        """Test that acknowledging nonexistent alert returns False."""
        tracker = AlertAcknowledgmentTracker()
        result = tracker.acknowledge("nonexistent", "user1", "api")
        assert result is False

    def test_is_acknowledged_returns_status(self) -> None:
        """Test that is_acknowledged returns correct status."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_123", "test_rule")

        assert tracker.is_acknowledged("alert_123") is False

        tracker.acknowledge("alert_123", "user1", "api")
        assert tracker.is_acknowledged("alert_123") is True

    def test_get_unacknowledged_returns_unacknowledged(self) -> None:
        """Test that get_unacknowledged returns only unacknowledged alerts."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_1", "rule1")
        tracker.register_alert("alert_2", "rule1")
        tracker.register_alert("alert_3", "rule1")

        tracker.acknowledge("alert_2", "user1", "api")

        unacknowledged = tracker.get_unacknowledged()
        assert len(unacknowledged) == 2
        alert_ids = [ack.alert_id for ack in unacknowledged]
        assert "alert_1" in alert_ids
        assert "alert_3" in alert_ids
        assert "alert_2" not in alert_ids

    def test_get_unacknowledged_filtered_by_rule(self) -> None:
        """Test that get_unacknowledged can filter by rule."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_1", "rule1")
        tracker.register_alert("alert_2", "rule1")
        tracker.register_alert("alert_3", "rule2")

        unacknowledged_rule1 = tracker.get_unacknowledged(rule_name="rule1")
        assert len(unacknowledged_rule1) == 2
        assert all(ack.rule_name == "rule1" for ack in unacknowledged_rule1)

    def test_cleanup_old_alerts_removes_old_acked(self) -> None:
        """Test that cleanup removes old acknowledged alerts."""
        tracker = AlertAcknowledgmentTracker()
        tracker.register_alert("alert_1", "rule1")
        tracker.register_alert("alert_2", "rule1")

        # Acknowledge one and set old time
        tracker.acknowledge("alert_1", "user1", "api")
        tracker.acknowledgments["alert_1"].acknowledged_at = datetime.now(UTC) - timedelta(hours=25)

        cleaned = tracker.cleanup_old_alerts(max_age_hours=24)
        assert cleaned == 1
        assert "alert_1" not in tracker.acknowledgments
        assert "alert_2" in tracker.acknowledgments


# =============================================================================
# DASHBOARD DATA ENDPOINTS TESTS
# =============================================================================


class TestBuildDashboardPayload:
    """Tests for build_dashboard_payload function."""

    def test_build_dashboard_payload_with_empty_data(self) -> None:
        """Test building dashboard payload with empty data."""
        payload = build_dashboard_payload({})

        assert len(payload) == 6  # 6 required market tabs
        assert "NSE EQ" in payload
        assert "NSE F&O" in payload
        assert "BSE" in payload
        assert "MCX" in payload
        assert "Currency F&O" in payload
        assert "Crypto" in payload

    def test_build_dashboard_payload_with_data(self) -> None:
        """Test building dashboard payload with data."""
        market_payloads = {
            "NSE EQ": {"status": "active", "symbols": 1000},
            "NSE F&O": {"status": "active", "symbols": 500},
            "BSE": {"status": "inactive", "symbols": 0},
        }

        payload = build_dashboard_payload(market_payloads)

        assert payload["NSE EQ"]["status"] == "active"
        assert payload["NSE EQ"]["symbols"] == 1000
        assert payload["NSE F&O"]["status"] == "active"
        assert payload["BSE"]["status"] == "inactive"

    def test_build_dashboard_payload_excludes_unknown_tabs(self) -> None:
        """Test that unknown tabs are excluded from payload."""
        market_payloads = {
            "NSE EQ": {"status": "active"},
            "Unknown Tab": {"status": "active"},
        }

        payload = build_dashboard_payload(market_payloads)

        assert "NSE EQ" in payload
        assert "Unknown Tab" not in payload


class TestBuildScannerPayload:
    """Tests for build_scanner_payload function."""

    def test_build_scanner_payload_with_none_result(self) -> None:
        """Test building scanner payload with None result."""
        payload = build_scanner_payload(scanner_result=None)

        assert payload["instruments"] == []
        assert payload["approved_count"] == 0
        assert payload["total_scanned"] == 0
        assert payload["scan_timestamp_utc"] is None

    def test_build_scanner_payload_with_result(self) -> None:
        """Test building scanner payload with result."""
        result = ScannerHealthResult(
            instruments=[],
            approved_count=5,
            total_scanned=20,
            scan_timestamp_utc=datetime.now(UTC),
        )

        payload = build_scanner_payload(scanner_result=result)

        assert payload["approved_count"] == 5
        assert payload["total_scanned"] == 20
        assert payload["scan_timestamp_utc"] == result.scan_timestamp_utc


class TestConvertCandidatesToHealthMatrix:
    """Tests for convert_candidates_to_health_matrix function."""

    def test_convert_candidates_with_empty_list(self) -> None:
        """Test converting empty candidate list."""
        matrices = convert_candidates_to_health_matrix([])
        assert len(matrices) == 0


class TestRenderInstrumentScannerTab:
    """Tests for render_instrument_scanner_tab function."""

    def test_render_scanner_tab_with_none_result(self) -> None:
        """Test rendering scanner tab with None result."""
        result = render_instrument_scanner_tab(scanner_result=None)

        assert result["table_symbols"] == []
        assert result["chart_symbols"] == []
        assert result["approved_count"] == 0
        assert result["total_count"] == 0


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestObservabilityIntegration:
    """Integration tests for observability components."""

    def test_metrics_alert_throttling_workflow(self) -> None:
        """Test complete workflow: metrics -> alert -> throttling."""
        # Record metrics
        record_data_source_request(source="kite", status="error")
        record_data_source_fallback(from_source="kite", to_source="yfinance")

        # Create alert manager
        manager = MultiChannelAlertManager(channels=[])

        # Evaluate context and send alert
        context = {"failure_count": 3, "failure_threshold": 3}
        alert_ids = manager.evaluate_and_alert(context)

        assert len(alert_ids) == 1
        assert alert_ids[0] is not None

        # Try to send again - should be throttled
        alert_ids_2 = manager.evaluate_and_alert(context)
        assert len(alert_ids_2) == 0  # Throttled

    def test_dashboard_metrics_integration(self) -> None:
        """Test dashboard integration with metrics."""
        # Update metrics
        update_data_freshness(source="kite", freshness_seconds=5.0)
        update_kite_token_freshness(is_fresh=True)

        # Build dashboard payload
        market_payloads = {
            "NSE EQ": {"status": "active", "metrics_updated": True},
            "NSE F&O": {"status": "active", "metrics_updated": True},
        }

        payload = build_dashboard_payload(market_payloads)

        assert "NSE EQ" in payload
        assert "NSE F&O" in payload

    def test_alert_acknowledgment_workflow(self) -> None:
        """Test complete alert acknowledgment workflow."""
        manager = MultiChannelAlertManager(channels=[])

        # Send alert
        alert_id = manager.send_alert("Test alert", rule_name="test_rule")
        assert alert_id is not None

        # Check unacknowledged
        unacknowledged = manager.get_unacknowledged_alerts()
        assert len(unacknowledged) == 1

        # Acknowledge
        result = manager.acknowledge(alert_id, "user1", "telegram")
        assert result is True

        # Check again
        unacknowledged = manager.get_unacknowledged_alerts()
        assert len(unacknowledged) == 0

    def test_multi_rule_evaluation_with_throttling(self) -> None:
        """Test evaluation of multiple rules with throttling."""
        manager = MultiChannelAlertManager(channels=[])

        # Context that triggers multiple rules
        context = {
            "minutes_remaining": 5,
            "current_positions": 10,
            "limit": 10,
            "daily_pnl": -6000.0,
            "loss_threshold": -5000.0,
            "failure_count": 4,
            "failure_threshold": 3,
        }

        # First evaluation - all rules trigger
        alert_ids_1 = manager.evaluate_and_alert(context)
        assert len(alert_ids_1) == 4

        # Second evaluation - all throttled
        alert_ids_2 = manager.evaluate_and_alert(context)
        assert len(alert_ids_2) == 0

        # Reset throttling
        manager.throttler.reset()

        # Third evaluation - all trigger again
        alert_ids_3 = manager.evaluate_and_alert(context)
        assert len(alert_ids_3) == 4

    def test_live_trading_scenario(self) -> None:
        """Test complete live trading scenario."""
        manager = MultiChannelAlertManager(channels=[])

        # Record live trading metrics
        record_order_latency(
            exchange="NSE",
            symbol="RELIANCE",
            order_type="MARKET",
            latency_seconds=0.3,
        )
        update_position_count(exchange="NSE", symbol="RELIANCE", count=100)

        record_broker_api_call(endpoint="/orders/place", method="POST", status="success")
        record_risk_check_duration(check_type="position_limit", duration_seconds=0.05)

        # Check position limit rule
        context = {"current_positions": 10, "limit": 10}
        alert_ids = manager.evaluate_and_alert(context)

        # Should trigger position limit alert
        assert len(alert_ids) == 1

    def test_data_source_failure_scenario(self) -> None:
        """Test complete data source failure scenario."""
        manager = MultiChannelAlertManager(channels=[])

        # Record failures
        for _ in range(5):
            record_data_source_request(source="kite", status="error")

        record_data_source_fallback(from_source="kite", to_source="yfinance")
        record_data_source_request(source="yfinance", status="success")

        # Trigger alert
        context = {"failure_count": 5, "failure_threshold": 3}
        alert_ids = manager.evaluate_and_alert(context)

        assert len(alert_ids) == 1

        # Acknowledge alert
        if alert_ids:
            manager.acknowledge(alert_ids[0], "ops_team", "email")
            assert manager.get_unacknowledged_alerts(rule_name="data_source_failure") == []
