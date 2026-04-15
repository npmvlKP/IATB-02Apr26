"""Tests for observability alerting configuration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from iatb.core.observability.alerting import (
    TelegramAlerter,
    TelegramAlertLevel,
    get_alerter,
)
from telegram.error import TelegramError


class TestTelegramAlertLevel:
    """Test cases for TelegramAlertLevel."""

    def test_alert_level_info_exists(self) -> None:
        """Test that INFO level exists."""
        assert hasattr(TelegramAlertLevel, "INFO")
        assert TelegramAlertLevel.INFO == "INFO"

    def test_alert_level_warning_exists(self) -> None:
        """Test that WARNING level exists."""
        assert hasattr(TelegramAlertLevel, "WARNING")
        assert TelegramAlertLevel.WARNING == "WARNING"

    def test_alert_level_error_exists(self) -> None:
        """Test that ERROR level exists."""
        assert hasattr(TelegramAlertLevel, "ERROR")
        assert TelegramAlertLevel.ERROR == "ERROR"

    def test_alert_level_critical_exists(self) -> None:
        """Test that CRITICAL level exists."""
        assert hasattr(TelegramAlertLevel, "CRITICAL")
        assert TelegramAlertLevel.CRITICAL == "CRITICAL"


class TestTelegramAlerter:
    """Test cases for TelegramAlerter class."""

    def test_alerter_init_with_no_credentials(self) -> None:
        """Test that alerter initializes without credentials but is disabled."""
        with patch.dict("os.environ", {}, clear=True):
            alerter = TelegramAlerter(bot_token=None, chat_id=None)
            assert alerter.enabled is False

    @patch("iatb.core.observability.alerting.Bot")
    def test_alerter_init_with_credentials(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """Test that alerter initializes with credentials and is enabled."""
        alerter = TelegramAlerter(  # noqa: S106
            bot_token="test_token",  # noqa: S106
            chat_id="test_chat",
        )
        assert alerter.enabled is True
        assert alerter.bot_token == "test_token"  # noqa: S105
        assert alerter.chat_id == "test_chat"

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_alert_when_enabled(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """Test that send_alert sends message when enabled."""
        mock_bot_instance = MagicMock()
        mock_bot.return_value = mock_bot_instance

        alerter = TelegramAlerter(  # noqa: S106
            bot_token="test_token",  # noqa: S106
            chat_id="test_chat",
        )
        result = alerter.send_alert("Test message", TelegramAlertLevel.INFO)

        assert result is True
        mock_bot_instance.send_message.assert_called_once()

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_alert_when_disabled(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """Test that send_alert returns False when disabled."""
        alerter = TelegramAlerter(enabled=False)
        result = alerter.send_alert("Test message", TelegramAlertLevel.INFO)

        assert result is False
        mock_bot.assert_not_called()

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_alert_handles_telegram_error(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """Test that send_alert handles TelegramError gracefully."""
        mock_bot_instance = MagicMock()
        mock_bot_instance.send_message.side_effect = TelegramError("API error")
        mock_bot.return_value = mock_bot_instance

        alerter = TelegramAlerter(  # noqa: S106
            bot_token="test_token",  # noqa: S106
            chat_id="test_chat",
        )
        result = alerter.send_alert("Test message", TelegramAlertLevel.INFO)

        # Returns True because alerter is enabled (fire-and-forget pattern)
        # Error is logged asynchronously but doesn't affect return value
        assert result is True

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_trade_alert(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """Test that send_trade_alert sends formatted trade message."""
        mock_bot_instance = MagicMock()
        mock_bot.return_value = mock_bot_instance

        alerter = TelegramAlerter(  # noqa: S106
            bot_token="test_token",  # noqa: S106
            chat_id="test_chat",
        )
        result = alerter.send_trade_alert(
            ticker="RELIANCE",
            side="BUY",
            quantity=100,
            price=2500.0,
        )

        assert result is True
        mock_bot_instance.send_message.assert_called_once()
        call_args = mock_bot_instance.send_message.call_args
        assert "RELIANCE" in str(call_args)
        assert "BUY" in str(call_args)

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_error_alert(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """Test that send_error_alert sends formatted error message."""
        mock_bot_instance = MagicMock()
        mock_bot.return_value = mock_bot_instance

        alerter = TelegramAlerter(  # noqa: S106
            bot_token="test_token",  # noqa: S106
            chat_id="test_chat",
        )
        result = alerter.send_error_alert(
            component="api",
            error_message="Connection failed",
            exc_type="ConnectionError",
        )

        assert result is True
        mock_bot_instance.send_message.assert_called_once()

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_health_alert(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """Test that send_health_alert sends formatted health message."""
        mock_bot_instance = MagicMock()
        mock_bot.return_value = mock_bot_instance

        alerter = TelegramAlerter(  # noqa: S106
            bot_token="test_token",  # noqa: S106
            chat_id="test_chat",
        )
        result = alerter.send_health_alert(
            service="broker",
            status="DOWN",
            details="Connection lost",
        )

        assert result is True
        mock_bot_instance.send_message.assert_called_once()

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_pnl_alert(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """Test that send_pnl_alert sends formatted PnL message."""
        mock_bot_instance = MagicMock()
        mock_bot.return_value = mock_bot_instance

        alerter = TelegramAlerter(  # noqa: S106
            bot_token="test_token",  # noqa: S106
            chat_id="test_chat",
        )
        result = alerter.send_pnl_alert(
            pnl=5000.0,
            daily_pnl=1000.0,
            open_positions=3,
        )

        assert result is True
        mock_bot_instance.send_message.assert_called_once()

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_model_alert(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """Test that send_model_alert sends formatted model message."""
        mock_bot_instance = MagicMock()
        mock_bot.return_value = mock_bot_instance

        alerter = TelegramAlerter(  # noqa: S106
            bot_token="test_token",  # noqa: S106
            chat_id="test_chat",
        )
        result = alerter.send_model_alert(
            model_name="lstm",
            status="AVAILABLE",
            details="Loaded successfully",
        )

        assert result is True
        mock_bot_instance.send_message.assert_called_once()

    @patch("iatb.core.observability.alerting.Bot")
    def test_send_with_actions(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """Test that send_with_actions sends message with buttons."""
        mock_bot_instance = MagicMock()
        mock_bot.return_value = mock_bot_instance

        alerter = TelegramAlerter(  # noqa: S106
            bot_token="test_token",  # noqa: S106
            chat_id="test_chat",
        )
        result = alerter.send_with_actions(
            message="Test with actions",
            buttons=[("Button 1", "action1"), ("Button 2", "action2")],
            level=TelegramAlertLevel.INFO,
        )

        assert result is True
        mock_bot_instance.send_message.assert_called_once()

    @patch("iatb.core.observability.alerting.Bot")
    def test_format_message_includes_timestamp(
        self,
        mock_bot: MagicMock,
    ) -> None:
        """Test that _format_message includes timestamp."""
        alerter = TelegramAlerter(  # noqa: S106
            bot_token="test_token",  # noqa: S106
            chat_id="test_chat",
        )
        message = alerter._format_message(
            "Test message",
            TelegramAlertLevel.INFO,
        )

        assert "INFO" in message
        assert "UTC" in message


class TestGetAlerter:
    """Test cases for get_alerter function."""

    @patch("iatb.core.observability.alerting.TelegramAlerter")
    def test_get_alerter_returns_instance(
        self,
        mock_alerter_class: MagicMock,
    ) -> None:
        """Test that get_alerter returns alerter instance."""
        mock_alerter = MagicMock()
        mock_alerter_class.return_value = mock_alerter

        alerter = get_alerter()
        assert alerter is mock_alerter

    @patch("iatb.core.observability.alerting.TelegramAlerter")
    def test_get_alerter_returns_same_instance(
        self,
        mock_alerter_class: MagicMock,
    ) -> None:
        """Test that get_alerter returns same instance on subsequent calls."""
        mock_alerter = MagicMock()
        mock_alerter_class.return_value = mock_alerter

        alerter1 = get_alerter()
        alerter2 = get_alerter()
        assert alerter1 is alerter2


class TestTelegramAlertLevels:
    """Test alert level values."""

    def test_info_level_value(self) -> None:
        """Test INFO level value."""
        assert TelegramAlertLevel.INFO == "INFO"

    def test_warning_level_value(self) -> None:
        """Test WARNING level value."""
        assert TelegramAlertLevel.WARNING == "WARNING"

    def test_error_level_value(self) -> None:
        """Test ERROR level value."""
        assert TelegramAlertLevel.ERROR == "ERROR"

    def test_critical_level_value(self) -> None:
        """Test CRITICAL level value."""
        assert TelegramAlertLevel.CRITICAL == "CRITICAL"
