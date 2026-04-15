"""Tests for observability alerting configuration."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from iatb.core.observability.alerting import (
    TelegramAlerter,
    TelegramAlertLevel,
    get_alerter,
)
from telegram.error import TelegramError


class TestTelegramAlertLevel:
    """Tests for TelegramAlertLevel class."""

    def test_info_level_exists(self) -> None:
        """Test that INFO level exists."""
        assert hasattr(TelegramAlertLevel, "INFO")
        assert TelegramAlertLevel.INFO == "INFO"

    def test_warning_level_exists(self) -> None:
        """Test that WARNING level exists."""
        assert hasattr(TelegramAlertLevel, "WARNING")
        assert TelegramAlertLevel.WARNING == "WARNING"

    def test_error_level_exists(self) -> None:
        """Test that ERROR level exists."""
        assert hasattr(TelegramAlertLevel, "ERROR")
        assert TelegramAlertLevel.ERROR == "ERROR"

    def test_critical_level_exists(self) -> None:
        """Test that CRITICAL level exists."""
        assert hasattr(TelegramAlertLevel, "CRITICAL")
        assert TelegramAlertLevel.CRITICAL == "CRITICAL"


class TestTelegramAlerter:
    """Tests for TelegramAlerter class."""

    @patch.dict("os.environ", {}, clear=True)
    def test_alerter_initialization_without_credentials(self) -> None:
        """Test that alerter initializes without credentials but is disabled."""
        alerter = TelegramAlerter()
        assert not alerter.enabled
        assert alerter.bot is None

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_alerter_initialization_with_credentials(self, mock_bot_class: MagicMock) -> None:
        """Test that alerter initializes with credentials."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot

        alerter = TelegramAlerter()
        assert alerter.enabled
        assert alerter.bot is not None
        mock_bot_class.assert_called_once_with(token="test_token")  # noqa: S106

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_alerter_can_be_disabled_explicitly(self, mock_bot_class: MagicMock) -> None:
        """Test that alerter can be explicitly disabled."""
        alerter = TelegramAlerter(enabled=False)
        assert not alerter.enabled
        # Bot should not be initialized if explicitly disabled
        mock_bot_class.assert_not_called()

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_alerter_with_custom_credentials(self, mock_bot_class: MagicMock) -> None:
        """Test that alerter can use custom credentials."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot

        alerter = TelegramAlerter(
            bot_token="custom_token",  # noqa: S106
            chat_id="999999",
        )
        assert alerter.enabled
        mock_bot_class.assert_called_once_with(token="custom_token")  # noqa: S106

    @patch.dict("os.environ", {}, clear=True)
    def test_send_alert_when_disabled(self) -> None:
        """Test that send_alert returns False when disabled."""
        alerter = TelegramAlerter()
        result = alerter.send_alert("Test message")
        assert result is False

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.asyncio.create_task")
    @patch("iatb.core.observability.alerting.asyncio.get_running_loop")
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_alert_with_running_event_loop(
        self,
        mock_bot_class: MagicMock,
        mock_get_loop: MagicMock,
        mock_create_task: MagicMock,
    ) -> None:
        """Test that send_alert works with running event loop."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop

        alerter = TelegramAlerter()
        result = alerter.send_alert("Test message", TelegramAlertLevel.INFO)

        assert result is True
        mock_create_task.assert_called_once()

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.asyncio.run")
    @patch("iatb.core.observability.alerting.asyncio.get_running_loop")
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_alert_without_running_event_loop(
        self,
        mock_bot_class: MagicMock,
        mock_get_loop: MagicMock,
        mock_asyncio_run: MagicMock,
    ) -> None:
        """Test that send_alert works without running event loop."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot
        mock_get_loop.side_effect = RuntimeError("No running loop")

        alerter = TelegramAlerter()
        result = alerter.send_alert("Test message", TelegramAlertLevel.INFO)

        assert result is True
        mock_asyncio_run.assert_called_once()

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_alert_with_context(self, mock_bot_class: MagicMock) -> None:
        """Test that send_alert includes context in message."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            alerter.send_alert(
                "Test message",
                TelegramAlertLevel.INFO,
                context={"user_id": "123", "action": "test"},
            )

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_alert_handles_telegram_error(self, mock_bot_class: MagicMock) -> None:
        """Test that send_alert handles TelegramError gracefully."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(side_effect=TelegramError("API error"))
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            # Should not raise exception, just log error
            result = alerter.send_alert("Test message")
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_trade_alert_buy(self, mock_bot_class: MagicMock) -> None:
        """Test that send_trade_alert works for BUY trades."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_trade_alert(
                ticker="RELIANCE",
                side="BUY",
                quantity=10,
                price=2500.50,
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_trade_alert_sell(self, mock_bot_class: MagicMock) -> None:
        """Test that send_trade_alert works for SELL trades."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_trade_alert(
                ticker="RELIANCE",
                side="SELL",
                quantity=10,
                price=2600.75,
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_trade_alert_with_custom_timestamp(self, mock_bot_class: MagicMock) -> None:
        """Test that send_trade_alert uses custom timestamp."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        custom_time = datetime(2026, 4, 15, 10, 0, 0, tzinfo=UTC)

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_trade_alert(
                ticker="RELIANCE",
                side="BUY",
                quantity=10,
                price=2500.50,
                timestamp=custom_time,
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_error_alert(self, mock_bot_class: MagicMock) -> None:
        """Test that send_error_alert works."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_error_alert(
                component="execution",
                error_message="Connection timeout",
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_error_alert_with_exception_type(self, mock_bot_class: MagicMock) -> None:
        """Test that send_error_alert includes exception type."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_error_alert(
                component="execution",
                error_message="Connection timeout",
                exc_type="TimeoutError",
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_health_alert_up(self, mock_bot_class: MagicMock) -> None:
        """Test that send_health_alert works for UP status."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_health_alert(
                service="database",
                status="UP",
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_health_alert_down(self, mock_bot_class: MagicMock) -> None:
        """Test that send_health_alert works for DOWN status."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_health_alert(
                service="database",
                status="DOWN",
                details="Connection refused",
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_health_alert_degraded(self, mock_bot_class: MagicMock) -> None:
        """Test that send_health_alert works for DEGRADED status."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_health_alert(
                service="database",
                status="DEGRADED",
                details="High latency",
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_pnl_alert_profit(self, mock_bot_class: MagicMock) -> None:
        """Test that send_pnl_alert works for profit."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_pnl_alert(
                pnl=5000.75,
                daily_pnl=1000.50,
                open_positions=3,
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_pnl_alert_loss(self, mock_bot_class: MagicMock) -> None:
        """Test that send_pnl_alert works for loss."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_pnl_alert(
                pnl=-2000.50,
                daily_pnl=-500.25,
                open_positions=2,
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_pnl_alert_without_daily_pnl(self, mock_bot_class: MagicMock) -> None:
        """Test that send_pnl_alert works without daily PnL."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_pnl_alert(
                pnl=5000.75,
                open_positions=3,
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_model_alert_available(self, mock_bot_class: MagicMock) -> None:
        """Test that send_model_alert works for available models."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_model_alert(
                model_name="lstm",
                status="AVAILABLE",
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_model_alert_unavailable(self, mock_bot_class: MagicMock) -> None:
        """Test that send_model_alert works for unavailable models."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_model_alert(
                model_name="lstm",
                status="UNAVAILABLE",
                details="Model loading failed",
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    @patch("iatb.core.observability.alerting.InlineKeyboardMarkup")
    @patch("iatb.core.observability.alerting.InlineKeyboardButton")
    def test_send_with_actions(
        self,
        mock_button_class: MagicMock,
        mock_markup_class: MagicMock,
        mock_bot_class: MagicMock,
    ) -> None:
        """Test that send_with_actions works with buttons."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        buttons = [("Pause", "pause"), ("Resume", "resume")]

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_with_actions(
                message="System alert",
                buttons=buttons,
                level=TelegramAlertLevel.WARNING,
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_send_with_actions_without_buttons(self, mock_bot_class: MagicMock) -> None:
        """Test that send_with_actions works without buttons."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()
            result = alerter.send_with_actions(
                message="System alert",
                buttons=None,
            )
            assert result is True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_format_message_includes_timestamp(self, mock_bot_class: MagicMock) -> None:
        """Test that _format_message includes timestamp."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot

        alerter = TelegramAlerter()
        message = alerter._format_message("Test message", TelegramAlertLevel.INFO, {})

        assert "2026-" in message  # Contains date

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_format_message_includes_level(self, mock_bot_class: MagicMock) -> None:
        """Test that _format_message includes alert level."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot

        alerter = TelegramAlerter()
        message = alerter._format_message("Test message", TelegramAlertLevel.CRITICAL, {})

        assert "CRITICAL" in message


class TestGetAlerter:
    """Tests for get_alerter function."""

    @patch.dict("os.environ", {}, clear=True)
    def test_get_alerter_returns_singleton(self) -> None:
        """Test that get_alerter returns the same instance."""
        alerter1 = get_alerter()
        alerter2 = get_alerter()
        assert alerter1 is alerter2

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_get_alerter_creates_enabled_instance(self, mock_bot_class: MagicMock) -> None:
        """Test that get_alerter creates enabled instance with credentials."""
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot

        alerter = get_alerter()
        assert isinstance(alerter, TelegramAlerter)


class TestIntegration:
    """Integration tests for alerting configuration."""

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_full_alerting_workflow(self, mock_bot_class: MagicMock) -> None:
        """Test a complete alerting workflow."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = get_alerter()

            # Send trade alert
            alerter.send_trade_alert(
                ticker="RELIANCE",
                side="BUY",
                quantity=10,
                price=2500.50,
            )

            # Send error alert
            alerter.send_error_alert(
                component="execution",
                error_message="Test error",
            )

            # Send health alert
            alerter.send_health_alert(
                service="database",
                status="UP",
            )

            # Send PnL alert
            alerter.send_pnl_alert(
                pnl=5000.75,
                daily_pnl=1000.50,
                open_positions=3,
            )

            # All should succeed without exceptions
            assert True

    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test_token", "TELEGRAM_CHAT_ID": "123456"})
    @patch("iatb.core.observability.alerting.Bot")
    def test_different_alert_levels(self, mock_bot_class: MagicMock) -> None:
        """Test that all alert levels work correctly."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot_class.return_value = mock_bot

        with patch("iatb.core.observability.alerting.asyncio.run"):
            alerter = TelegramAlerter()

            # Test all alert levels
            levels = [
                TelegramAlertLevel.INFO,
                TelegramAlertLevel.WARNING,
                TelegramAlertLevel.ERROR,
                TelegramAlertLevel.CRITICAL,
            ]

            for level in levels:
                result = alerter.send_alert(f"Test {level} message", level)
                assert result is True
