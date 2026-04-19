"""Tests for Pre-Market Token Validator (Risk 2 Mitigation)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from scripts.pre_market_token_validator import (
    AlertManager,
    PreMarketTokenValidator,
    TokenStatus,
    ValidationResult,
)


@pytest.fixture
def mock_token_manager():
    """Mock ZerodhaTokenManager."""
    with patch("scripts.pre_market_token_validator.ZerodhaTokenManager") as mock:
        mock_instance = MagicMock()
        mock_instance.is_token_fresh.return_value = True
        mock_instance.clear_token = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def validator(mock_token_manager):
    """Create PreMarketTokenValidator instance with mocked dependencies."""
    with patch.dict(
        "os.environ",
        {
            "ZERODHA_API_KEY": "test_api_key",
            "ZERODHA_API_SECRET": "test_api_secret",
            "ZERODHA_TOTP_SECRET": "JBSWY3DPEHPK3PXP",
        },
    ):
        validator = PreMarketTokenValidator()
        validator._token_manager = mock_token_manager
        yield validator


# ── TokenStatus Tests ──


def test_token_status_enum():
    """Test TokenStatus enum values."""
    assert TokenStatus.FRESH.value == "fresh"
    assert TokenStatus.EXPIRED.value == "expired"
    assert TokenStatus.MISSING.value == "missing"
    assert TokenStatus.ERROR.value == "error"


# ── ValidationResult Tests ──


def test_validation_result_initialization():
    """Test ValidationResult initialization."""
    now = datetime.now(UTC)
    expiry = now + timedelta(hours=6)

    result = ValidationResult(
        status=TokenStatus.FRESH,
        message="Test message",
        timestamp_utc=now,
        token_expiry_utc=expiry,
        auto_relogin_success=True,
    )

    assert result.status == TokenStatus.FRESH
    assert result.message == "Test message"
    assert result.timestamp_utc == now
    assert result.token_expiry_utc == expiry
    assert result.auto_relogin_success is True


def test_validation_result_to_dict():
    """Test ValidationResult.to_dict() method."""
    now = datetime.now(UTC)
    expiry = now + timedelta(hours=6)

    result = ValidationResult(
        status=TokenStatus.FRESH,
        message="Test message",
        timestamp_utc=now,
        token_expiry_utc=expiry,
    )

    result_dict = result.to_dict()

    assert result_dict["status"] == "fresh"
    assert result_dict["message"] == "Test message"
    assert result_dict["timestamp_utc"] == now.isoformat()
    assert result_dict["token_expiry_utc"] == expiry.isoformat()
    assert result_dict["auto_relogin_success"] is False


def test_validation_result_to_dict_no_expiry():
    """Test ValidationResult.to_dict() with no expiry time."""
    now = datetime.now(UTC)

    result = ValidationResult(
        status=TokenStatus.ERROR,
        message="Error message",
        timestamp_utc=now,
    )

    result_dict = result.to_dict()

    assert result_dict["token_expiry_utc"] is None


# ── AlertManager Tests ──


@pytest.fixture
def alert_manager():
    """Create AlertManager instance."""
    logger = MagicMock(spec=logging.Logger)
    return AlertManager(logger)


def test_alert_manager_send_alert_info(alert_manager):
    """Test AlertManager.send_alert() with INFO level."""
    result = ValidationResult(
        status=TokenStatus.FRESH,
        message="Token is fresh",
        timestamp_utc=datetime.now(UTC),
    )

    alert_manager.send_alert(result)

    alert_manager._logger.info.assert_called_once()
    alert_manager._logger.critical.assert_not_called()


def test_alert_manager_send_alert_critical(alert_manager):
    """Test AlertManager.send_alert() with CRITICAL level."""
    result = ValidationResult(
        status=TokenStatus.EXPIRED,
        message="Token expired",
        timestamp_utc=datetime.now(UTC),
    )

    alert_manager.send_alert(result)

    alert_manager._logger.critical.assert_called_once()
    alert_manager._logger.info.assert_not_called()


def test_alert_manager_send_alert_error(alert_manager):
    """Test AlertManager.send_alert() with ERROR status."""
    result = ValidationResult(
        status=TokenStatus.ERROR,
        message="Validation error",
        timestamp_utc=datetime.now(UTC),
    )

    alert_manager.send_alert(result)

    alert_manager._logger.critical.assert_called_once()


def test_alert_manager_format_alert(alert_manager):
    """Test AlertManager._format_alert() method."""
    now = datetime.now(UTC)
    expiry = now + timedelta(hours=6)

    result = ValidationResult(
        status=TokenStatus.FRESH,
        message="Test message",
        timestamp_utc=now,
        token_expiry_utc=expiry,
    )

    formatted = alert_manager._format_alert(result, "INFO")

    assert "TOKEN VALIDATION ALERT [INFO]" in formatted
    assert "Status: FRESH" in formatted
    assert "Message: Test message" in formatted
    assert "Auto-Relogin: FAILED or NOT ATTEMPTED" not in formatted


def test_alert_manager_format_alert_with_relogin(alert_manager):
    """Test AlertManager._format_alert() with auto-relogin."""
    now = datetime.now(UTC)

    result = ValidationResult(
        status=TokenStatus.FRESH,
        message="Auto-relogin successful",
        timestamp_utc=now,
        auto_relogin_success=True,
    )

    formatted = alert_manager._format_alert(result, "INFO")

    assert "Auto-Relogin: SUCCESS" in formatted


# ── PreMarketTokenValidator Tests ──


def test_validator_initialization():
    """Test PreMarketTokenValidator initialization."""
    with patch.dict(
        "os.environ",
        {
            "ZERODHA_API_KEY": "test_key",
            "ZERODHA_API_SECRET": "test_secret",
            "ZERODHA_TOTP_SECRET": "totp_secret",
        },
    ):
        with patch("scripts.pre_market_token_validator.ZerodhaTokenManager"):
            validator = PreMarketTokenValidator()
            assert validator._api_key == "test_key"
            assert validator._api_secret == "test_secret"
            assert validator._totp_secret == "totp_secret"


def test_validator_initialization_missing_credentials():
    """Test PreMarketTokenValidator initialization with missing credentials."""
    from iatb.core.exceptions import ConfigError

    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ConfigError):
            PreMarketTokenValidator()


def test_validate_token_fresh(validator):
    """Test validate_token() with fresh token."""
    validator._token_manager.is_token_fresh.return_value = True

    with patch.object(
        validator, "_get_token_expiry", return_value=datetime.now(UTC) + timedelta(hours=2)
    ):
        result = validator.validate_token()

    assert result.status == TokenStatus.FRESH
    assert "fresh" in result.message.lower() and "valid" in result.message.lower()
    assert result.auto_relogin_success is False


def test_validate_token_expired_with_totp(validator):
    """Test validate_token() with expired token and TOTP configured."""
    validator._token_manager.is_token_fresh.return_value = False
    validator._totp_secret = "JBSWY3DPEHPK3PXP"

    with patch.object(
        validator, "_get_token_expiry", return_value=datetime.now(UTC) - timedelta(hours=1)
    ):
        with patch.object(validator, "_attempt_auto_relogin", return_value=True):
            result = validator.validate_token()

    assert result.status == TokenStatus.FRESH
    assert "auto-relogin successful" in result.message.lower()
    assert result.auto_relogin_success is True


def test_validate_token_expired_totp_fails(validator):
    """Test validate_token() with expired token but auto-relogin fails."""
    validator._token_manager.is_token_fresh.return_value = False
    validator._totp_secret = "JBSWY3DPEHPK3PXP"

    with patch.object(
        validator, "_get_token_expiry", return_value=datetime.now(UTC) - timedelta(hours=1)
    ):
        with patch.object(validator, "_attempt_auto_relogin", return_value=False):
            result = validator.validate_token()

    assert result.status == TokenStatus.EXPIRED
    assert "auto-relogin failed" in result.message.lower()
    assert result.auto_relogin_success is False


def test_validate_token_expired_no_totp(validator):
    """Test validate_token() with expired token and no TOTP."""
    validator._token_manager.is_token_fresh.return_value = False
    validator._totp_secret = None

    with patch.object(
        validator, "_get_token_expiry", return_value=datetime.now(UTC) - timedelta(hours=1)
    ):
        result = validator.validate_token()

    assert result.status == TokenStatus.EXPIRED
    assert "no totp configured" in result.message.lower()
    assert result.auto_relogin_success is False


def test_validate_token_error(validator):
    """Test validate_token() with exception."""
    validator._token_manager.is_token_fresh.side_effect = Exception("Test error")

    result = validator.validate_token()

    assert result.status == TokenStatus.ERROR
    assert "validation error" in result.message.lower()
    assert "Test error" in result.message


def test_get_token_expiry(validator):
    """Test _get_token_expiry() method."""
    now = datetime.now(UTC)
    expected_expiry = now + timedelta(hours=6)

    # Mock keyring module (it's imported inside the function)
    import keyring  # noqa: PLC0415

    def mock_get_password(service, username):
        # The function calls get_password with specific service/username combos
        if service == "iatb_zerodha" and username == "token_timestamp_utc":
            return now.isoformat()
        return "test_token"

    with patch.object(keyring, "get_password", side_effect=mock_get_password):
        with patch.object(validator, "_calculate_next_expiry", return_value=expected_expiry):
            expiry = validator._get_token_expiry()

    assert expiry == expected_expiry


def test_get_token_expiry_no_timestamp(validator):
    """Test _get_token_expiry() with no timestamp."""
    import keyring  # noqa: PLC0415

    with patch.object(keyring, "get_password", return_value=None):
        expiry = validator._get_token_expiry()

    assert expiry is None


def test_get_token_expiry_invalid_timestamp(validator):
    """Test _get_token_expiry() with invalid timestamp."""
    import keyring  # noqa: PLC0415

    with patch.object(keyring, "get_password") as mock_get:
        mock_get.side_effect = ["test_token", "invalid_timestamp", "test_token"]
        expiry = validator._get_token_expiry()

    assert expiry is None


def test_calculate_next_expiry_same_day(validator):
    """Test _calculate_next_expiry() for same day before 6 AM."""
    # 0:00 UTC = 5:30 AM IST (before 6 AM)
    token_time = datetime(2026, 4, 19, 0, 0, tzinfo=UTC)
    expiry = validator._calculate_next_expiry(token_time)

    # 6 AM IST = 0:30 UTC
    expected = datetime(2026, 4, 19, 0, 30, tzinfo=UTC)
    assert expiry == expected


def test_calculate_next_expiry_next_day(validator):
    """Test _calculate_next_expiry() for after 6 AM."""
    # 8:00 UTC = 1:30 PM IST (after 6 AM)
    token_time = datetime(2026, 4, 19, 8, 0, tzinfo=UTC)
    expiry = validator._calculate_next_expiry(token_time)

    # Next day 6 AM IST = 0:30 UTC
    expected = datetime(2026, 4, 20, 0, 30, tzinfo=UTC)
    assert expiry == expected


def test_attempt_auto_relogin_success(validator):
    """Test _attempt_auto_relogin() success."""
    with patch("subprocess.run") as mock_run:
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_run.return_value = mock_process
        validator._token_manager.is_token_fresh.return_value = True

        result = validator._attempt_auto_relogin()

    assert result is True
    validator._token_manager.clear_token.assert_called_once()
    mock_run.assert_called_once()


def test_attempt_auto_relogin_command_fails(validator):
    """Test _attempt_auto_relogin() when command fails."""
    with patch("subprocess.run") as mock_run:
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stderr = "Login failed"
        mock_run.return_value = mock_process

        result = validator._attempt_auto_relogin()

    assert result is False


def test_attempt_auto_relogin_timeout(validator):
    """Test _attempt_auto_relogin() with timeout."""
    from subprocess import TimeoutExpired

    with patch("subprocess.run", side_effect=TimeoutExpired("cmd", 300)):
        result = validator._attempt_auto_relogin()

    assert result is False


def test_attempt_auto_relogin_exception(validator):
    """Test _attempt_auto_relogin() with exception."""
    with patch("subprocess.run", side_effect=Exception("Unexpected error")):
        result = validator._attempt_auto_relogin()

    assert result is False


def test_should_run_at_scheduled_time_true(validator):
    """Test should_run_at_scheduled_time() at scheduled time."""
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    ist_tz = ZoneInfo("Asia/Kolkata")

    with patch("scripts.pre_market_token_validator.datetime") as mock_dt:
        # Set current time to 9:00 AM IST
        now_ist = datetime(2026, 4, 19, 9, 0, 0, tzinfo=ist_tz)
        mock_dt.now.return_value = now_ist

        result = validator.should_run_at_scheduled_time(9, 0)

    assert result is True


def test_should_run_at_scheduled_time_within_window(validator):
    """Test should_run_at_scheduled_time() within 1-minute window."""
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    ist_tz = ZoneInfo("Asia/Kolkata")

    with patch("scripts.pre_market_token_validator.datetime") as mock_dt:
        # Set current time to 9:00:30 AM IST (30 seconds past)
        now_ist = datetime(2026, 4, 19, 9, 0, 30, tzinfo=ist_tz)
        mock_dt.now.return_value = now_ist

        result = validator.should_run_at_scheduled_time(9, 0)

    assert result is True


def test_should_run_at_scheduled_time_false(validator):
    """Test should_run_at_scheduled_time() outside window."""
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    ist_tz = ZoneInfo("Asia/Kolkata")

    with patch("scripts.pre_market_token_validator.datetime") as mock_dt:
        # Set current time to 8:00 AM IST (1 hour before)
        now_ist = datetime(2026, 4, 19, 8, 0, 0, tzinfo=ist_tz)
        mock_dt.now.return_value = now_ist

        result = validator.should_run_at_scheduled_time(9, 0)

    assert result is False


def test_run_once_success(validator):
    """Test run_once() with fresh token."""
    validator._token_manager.is_token_fresh.return_value = True

    with patch.object(
        validator, "_get_token_expiry", return_value=datetime.now(UTC) + timedelta(hours=2)
    ):
        exit_code = validator.run_once()

    assert exit_code == 0


def test_run_once_expired_relogin_success(validator):
    """Test run_once() with expired token but successful relogin."""
    validator._token_manager.is_token_fresh.return_value = False
    validator._totp_secret = "JBSWY3DPEHPK3PXP"

    with patch.object(
        validator, "_get_token_expiry", return_value=datetime.now(UTC) - timedelta(hours=1)
    ):
        with patch.object(validator, "_attempt_auto_relogin", return_value=True):
            exit_code = validator.run_once()

    assert exit_code == 0


def test_run_once_failure(validator):
    """Test run_once() with expired token and failed relogin."""
    validator._token_manager.is_token_fresh.return_value = False
    validator._totp_secret = "JBSWY3DPEHPK3PXP"

    with patch.object(
        validator, "_get_token_expiry", return_value=datetime.now(UTC) - timedelta(hours=1)
    ):
        with patch.object(validator, "_attempt_auto_relogin", return_value=False):
            exit_code = validator.run_once()

    assert exit_code == 1


@pytest.mark.asyncio
async def test_run_scheduled_success(validator):
    """Test run_scheduled() success."""
    validator._token_manager.is_token_fresh.return_value = True

    with patch.object(validator, "should_run_at_scheduled_time", return_value=True):
        with patch.object(
            validator, "_get_token_expiry", return_value=datetime.now(UTC) + timedelta(hours=2)
        ):
            exit_code = await validator.run_scheduled(9, 0)

    assert exit_code == 0


@pytest.mark.asyncio
async def test_run_scheduled_waits_for_time(validator):
    """Test run_scheduled() waits until scheduled time."""
    validator._token_manager.is_token_fresh.return_value = True

    call_count = {"count": 0}

    def should_run_side_effect(*_):
        call_count["count"] += 1
        # Return True on second call (after one sleep)
        return call_count["count"] >= 2

    with patch.object(
        validator, "should_run_at_scheduled_time", side_effect=should_run_side_effect
    ):
        with patch("asyncio.sleep") as mock_sleep:
            with patch.object(validator, "validate_token") as mock_validate:
                mock_validate.return_value = ValidationResult(
                    status=TokenStatus.FRESH,
                    message="Fresh",
                    timestamp_utc=datetime.now(UTC),
                )

                exit_code = await validator.run_scheduled(9, 0)

                # Should have slept once
                assert mock_sleep.call_count >= 1

    assert exit_code == 0


# ── Integration Tests ──


def test_validator_with_alert_manager(validator):
    """Test validator integration with alert manager."""
    validator._token_manager.is_token_fresh.return_value = True

    with patch.object(
        validator, "_get_token_expiry", return_value=datetime.now(UTC) + timedelta(hours=2)
    ):
        exit_code = validator.run_once()

    assert exit_code == 0
    # Alert should have been sent (check that alert_manager was called)
    # We can't directly check the logger since it's a real logger, not a mock


def test_validator_error_path(validator):
    """Test validator handles errors gracefully."""
    validator._token_manager.is_token_fresh.side_effect = RuntimeError("Test error")

    exit_code = validator.run_once()

    assert exit_code == 1
    # Error should have been handled without crashing
