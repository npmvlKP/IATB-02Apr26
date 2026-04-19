#!/usr/bin/env python
"""
Pre-Market Token Validator — Risk 2 Mitigation Strategy.

This script runs at 9:00 AM IST (configurable) to:
1. Validate token freshness before market opens
2. Trigger automated re-login with TOTP if token expired
3. Send alerts on token expiry or login failure
4. Ensure trading system has valid access token at market open

Usage:
    poetry run python scripts/pre_market_token_validator.py [--scheduled]

Environment Variables Required:
    ZERODHA_API_KEY or KITE_API_KEY
    ZERODHA_API_SECRET or KITE_API_SECRET
    ZERODHA_TOTP_SECRET or KITE_TOTP_SECRET (optional but recommended for auto-login)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime, time, timedelta
from enum import Enum
from pathlib import Path

from iatb.broker.token_manager import ZerodhaTokenManager
from iatb.core.exceptions import ConfigError

# ── Configuration ──

_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_SCHEDULED_HOUR = 9  # 9:00 AM IST
_DEFAULT_SCHEDULED_MINUTE = 0
_ZERODHA_EXPIRY_HOUR = 6  # 6 AM IST (when tokens expire)
_TOKEN_VALIDITY_BUFFER_MINUTES = 30  # Buffer before expiry to refresh

_LOGGER_NAME = "iatb.scripts.pre_market_validator"


class TokenStatus(Enum):
    """Token validation status."""

    FRESH = "fresh"
    EXPIRED = "expired"
    MISSING = "missing"
    ERROR = "error"


class ValidationResult:
    """Result of token validation."""

    def __init__(
        self,
        status: TokenStatus,
        message: str,
        timestamp_utc: datetime,
        token_expiry_utc: datetime | None = None,
        auto_relogin_success: bool = False,
    ) -> None:
        """Initialize validation result.

        Args:
            status: Token status.
            message: Human-readable message.
            timestamp_utc: Validation timestamp in UTC.
            token_expiry_utc: Token expiry time in UTC (if available).
            auto_relogin_success: Whether auto-relogin was successful.
        """
        self.status = status
        self.message = message
        self.timestamp_utc = timestamp_utc
        self.token_expiry_utc = token_expiry_utc
        self.auto_relogin_success = auto_relogin_success

    def to_dict(self) -> dict[str, str | bool | None]:
        """Convert result to dictionary for logging/alerting."""
        return {
            "status": self.status.value,
            "message": self.message,
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "token_expiry_utc": self.token_expiry_utc.isoformat()
            if self.token_expiry_utc
            else None,
            "auto_relogin_success": self.auto_relogin_success,
        }


# ── Alerting System ──


class AlertManager:
    """Manages token expiry alerts."""

    def __init__(self, logger: logging.Logger) -> None:
        """Initialize alert manager.

        Args:
            logger: Logger instance for output.
        """
        self._logger = logger

    def send_alert(self, result: ValidationResult) -> None:
        """Send alert for token validation result.

        Args:
            result: Validation result to alert on.
        """
        alert_level = (
            "CRITICAL" if result.status in (TokenStatus.EXPIRED, TokenStatus.ERROR) else "INFO"
        )

        alert_msg = self._format_alert(result, alert_level)

        # Log the alert
        if alert_level == "CRITICAL":
            self._logger.critical(alert_msg)
        else:
            self._logger.info(alert_msg)

        # TODO: Extend to external alerting (Telegram, Email, Slack)
        # This is a placeholder for future enhancement
        # self._send_external_alert(result, alert_level)

    def _format_alert(self, result: ValidationResult, level: str) -> str:
        """Format alert message.

        Args:
            result: Validation result.
            level: Alert level.

        Returns:
            Formatted alert message.
        """
        timestamp_ist = result.timestamp_utc.astimezone(self._get_ist_timezone())
        time_str = timestamp_ist.strftime("%Y-%m-%d %H:%M:%S IST")

        expiry_str = "N/A"
        if result.token_expiry_utc:
            expiry_ist = result.token_expiry_utc.astimezone(self._get_ist_timezone())
            expiry_str = expiry_ist.strftime("%Y-%m-%d %H:%M:%S IST")

        lines = [
            "=" * 70,
            f"TOKEN VALIDATION ALERT [{level}]",
            f"Timestamp: {time_str}",
            f"Status: {result.status.value.upper()}",
            f"Message: {result.message}",
            f"Token Expiry: {expiry_str}",
        ]

        if result.auto_relogin_success:
            lines.append("Auto-Relogin: SUCCESS")
        elif result.status in (TokenStatus.EXPIRED, TokenStatus.MISSING):
            lines.append("Auto-Relogin: FAILED or NOT ATTEMPTED")

        lines.append("=" * 70)
        return "\n".join(lines)

    @staticmethod
    def _get_ist_timezone():
        """Get IST timezone object."""
        from zoneinfo import ZoneInfo  # noqa: PLC0415

        return ZoneInfo("Asia/Kolkata")


# ── Token Validator ──


class PreMarketTokenValidator:
    """Validates and refreshes Zerodha tokens before market open."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        totp_secret: str | None = None,
    ) -> None:
        """Initialize pre-market token validator.

        Args:
            api_key: Zerodha API key (from env if not provided).
            api_secret: Zerodha API secret (from env if not provided).
            totp_secret: TOTP secret for 2FA (from env if not provided).
        """
        self._api_key = api_key or os.getenv("ZERODHA_API_KEY") or os.getenv("KITE_API_KEY")
        self._api_secret = (
            api_secret or os.getenv("ZERODHA_API_SECRET") or os.getenv("KITE_API_SECRET")
        )
        self._totp_secret = (
            totp_secret or os.getenv("ZERODHA_TOTP_SECRET") or os.getenv("KITE_TOTP_SECRET")
        )

        self._logger = self._configure_logger()
        self._alert_manager = AlertManager(self._logger)

        if not self._api_key or not self._api_secret:
            msg = "ZERODHA_API_KEY and ZERODHA_API_SECRET must be set in environment"
            raise ConfigError(msg)

        self._token_manager = ZerodhaTokenManager(
            api_key=self._api_key,
            api_secret=self._api_secret,
            totp_secret=self._totp_secret,
        )
        self._logger.info("Pre-Market Token Validator initialized")

    def _configure_logger(self) -> logging.Logger:
        """Configure logger with UTC timestamps.

        Returns:
            Configured logger instance.
        """
        logger = logging.getLogger(_LOGGER_NAME)
        logger.setLevel(logging.INFO)

        # Remove existing handlers
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

        # Create formatter with UTC
        formatter = logging.Formatter(
            fmt="%(asctime)sZ | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        formatter.converter = self._get_utc_tuple

        # File handler
        file_handler = logging.FileHandler(
            _LOG_DIR / "pre_market_validation.log",
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        logger.propagate = False
        return logger

    @staticmethod
    def _get_utc_tuple(*_):
        """Get UTC time tuple for logging formatter."""
        return datetime.now(UTC).timetuple()

    def validate_token(self) -> ValidationResult:
        """Validate token freshness and attempt auto-relogin if needed.

        Returns:
            Validation result with status and details.
        """
        now_utc = datetime.now(UTC)
        self._logger.info("Starting token validation at %s", now_utc.isoformat())

        try:
            is_fresh = self._token_manager.is_token_fresh()
            if is_fresh:
                return self._handle_fresh_token(now_utc)
            return self._handle_expired_token(now_utc)
        except Exception as exc:
            self._logger.exception("Error during token validation: %s", exc)
            return ValidationResult(
                status=TokenStatus.ERROR,
                message=f"Validation error: {exc}",
                timestamp_utc=now_utc,
            )

    def _handle_fresh_token(self, now_utc: datetime) -> ValidationResult:
        """Handle case where token is fresh.

        Args:
            now_utc: Current time in UTC.

        Returns:
            Validation result with FRESH status.
        """
        self._logger.info("✓ Token is fresh and valid")
        token_expiry_utc = self._get_token_expiry()
        return ValidationResult(
            status=TokenStatus.FRESH,
            message="Token is valid and will remain fresh through trading hours",
            timestamp_utc=now_utc,
            token_expiry_utc=token_expiry_utc,
        )

    def _handle_expired_token(self, now_utc: datetime) -> ValidationResult:
        """Handle case where token is expired or missing.

        Args:
            now_utc: Current time in UTC.

        Returns:
            Validation result with EXPIRED or FRESH status (if relogin succeeds).
        """
        self._logger.warning("✗ Token is expired or missing")
        token_expiry_utc = self._get_token_expiry()

        if self._totp_secret:
            return self._attempt_relogin_with_totp(now_utc, token_expiry_utc)
        return self._handle_no_totp_configured(now_utc, token_expiry_utc)

    def _attempt_relogin_with_totp(
        self, now_utc: datetime, token_expiry_utc: datetime | None
    ) -> ValidationResult:
        """Attempt automated re-login with TOTP.

        Args:
            now_utc: Current time in UTC.
            token_expiry_utc: Token expiry time.

        Returns:
            Validation result.
        """
        self._logger.info("Attempting automated re-login with TOTP")
        relogin_success = self._attempt_auto_relogin()

        if relogin_success:
            self._logger.info("✓ Automated re-login successful")
            new_expiry = self._get_token_expiry()
            return ValidationResult(
                status=TokenStatus.FRESH,
                message="Token expired but auto-relogin successful",
                timestamp_utc=now_utc,
                token_expiry_utc=new_expiry,
                auto_relogin_success=True,
            )
        self._logger.error("✗ Automated re-login failed")
        return ValidationResult(
            status=TokenStatus.EXPIRED,
            message="Token expired and auto-relogin failed",
            timestamp_utc=now_utc,
            token_expiry_utc=token_expiry_utc,
            auto_relogin_success=False,
        )

    def _handle_no_totp_configured(
        self, now_utc: datetime, token_expiry_utc: datetime | None
    ) -> ValidationResult:
        """Handle case where TOTP is not configured.

        Args:
            now_utc: Current time in UTC.
            token_expiry_utc: Token expiry time.

        Returns:
            Validation result with EXPIRED status.
        """
        self._logger.warning("TOTP secret not configured, cannot auto-relogin")
        return ValidationResult(
            status=TokenStatus.EXPIRED,
            message="Token expired and no TOTP configured for auto-relogin",
            timestamp_utc=now_utc,
            token_expiry_utc=token_expiry_utc,
            auto_relogin_success=False,
        )

    def _get_token_expiry(self) -> datetime | None:
        """Get token expiry time from stored timestamp.

        Returns:
            Token expiry time in UTC, or None if not available.
        """
        import keyring  # noqa: PLC0415

        timestamp_str = keyring.get_password("iatb_zerodha", "token_timestamp_utc")
        if not timestamp_str:
            return None

        try:
            token_time = datetime.fromisoformat(timestamp_str)
            return self._calculate_next_expiry(token_time)
        except (ValueError, TypeError):
            return None

    def _calculate_next_expiry(self, token_time: datetime) -> datetime:
        """Calculate next 6 AM IST expiry time in UTC.

        Args:
            token_time: Token creation time.

        Returns:
            Next expiry time in UTC.
        """
        from zoneinfo import ZoneInfo  # noqa: PLC0415

        ist_tz = ZoneInfo("Asia/Kolkata")
        token_ist = token_time.astimezone(ist_tz)
        expiry_ist = datetime.combine(
            token_ist.date(),
            time(hour=_ZERODHA_EXPIRY_HOUR, minute=0),
            tzinfo=ist_tz,
        )

        if token_ist < expiry_ist:
            return expiry_ist.astimezone(UTC)
        return (expiry_ist + timedelta(days=1)).astimezone(UTC)

    def _attempt_auto_relogin(self) -> bool:
        """Attempt automated re-login using zerodha_connect.py.

        Returns:
            True if re-login successful, False otherwise.
        """
        try:
            import subprocess  # noqa: PLC0415

            # Clear stale token first
            self._logger.info("Clearing stale token...")
            self._token_manager.clear_token()

            # Run zerodha_connect.py with auto-login
            self._logger.info("Running automated re-login...")
            # Script path is trusted and hardcoded, no user input
            result: subprocess.CompletedProcess[str] = subprocess.run(
                [sys.executable, "scripts/zerodha_connect.py", "--auto-login"],  # noqa: S603
                cwd=Path.cwd(),
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes timeout
                check=False,  # Don't raise exception for non-zero exit
            )

            if result.returncode == 0:
                self._logger.info("Auto-relogin command succeeded")
                # Verify token is now fresh
                return self._token_manager.is_token_fresh()
            else:
                self._logger.error("Auto-relogin command failed: %s", result.stderr)
                return False

        except subprocess.TimeoutExpired:
            self._logger.error("Auto-relogin timed out after 5 minutes")
            return False
        except Exception as exc:
            self._logger.exception("Auto-relogin failed with exception: %s", exc)
            return False

    def should_run_at_scheduled_time(self, hour: int, minute: int) -> bool:
        """Check if current time matches scheduled validation time.

        Args:
            hour: Scheduled hour (in IST).
            minute: Scheduled minute.

        Returns:
            True if current time matches scheduled time (within 1 minute window).
        """
        from zoneinfo import ZoneInfo  # noqa: PLC0415

        ist_tz = ZoneInfo("Asia/Kolkata")
        now_ist = datetime.now(ist_tz)

        # Allow 1 minute window for scheduled execution
        time_diff = abs(
            (now_ist.hour * 60 + now_ist.minute) - (hour * 60 + minute),
        )

        return time_diff <= 1

    async def run_scheduled(
        self, hour: int = _DEFAULT_SCHEDULED_HOUR, minute: int = _DEFAULT_SCHEDULED_MINUTE
    ) -> int:
        """Run validation at scheduled time.

        Args:
            hour: Scheduled hour in IST.
            minute: Scheduled minute.

        Returns:
            Exit code (0 for success, 1 for failure).
        """
        self._logger.info("Waiting for scheduled time: %02d:%02d IST", hour, minute)

        # Wait until scheduled time
        while not self.should_run_at_scheduled_time(hour, minute):
            await asyncio.sleep(60)  # Check every minute

        # Run validation
        result = self.validate_token()
        self._alert_manager.send_alert(result)

        # Return 0 if token is fresh or auto-relogin succeeded, 1 otherwise
        if result.status == TokenStatus.FRESH:
            return 0
        if result.status == TokenStatus.EXPIRED and result.auto_relogin_success:
            return 0
        return 1

    def run_once(self) -> int:
        """Run validation once immediately.

        Returns:
            Exit code (0 for success, 1 for failure).
        """
        result = self.validate_token()
        self._alert_manager.send_alert(result)

        # Return 0 if token is fresh or auto-relogin succeeded, 1 otherwise
        if result.status == TokenStatus.FRESH:
            return 0
        if result.status == TokenStatus.EXPIRED and result.auto_relogin_success:
            return 0
        return 1


# ── Main Entry Point ──


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description="Pre-market token validation for Risk 2 mitigation",
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Run in scheduled mode (waits for 9:00 AM IST)",
    )
    parser.add_argument(
        "--hour",
        type=int,
        default=_DEFAULT_SCHEDULED_HOUR,
        help="Scheduled hour in IST (default: 9)",
    )
    parser.add_argument(
        "--minute",
        type=int,
        default=_DEFAULT_SCHEDULED_MINUTE,
        help="Scheduled minute in IST (default: 0)",
    )

    args = parser.parse_args()

    try:
        validator = PreMarketTokenValidator()

        if args.scheduled:
            return asyncio.run(validator.run_scheduled(args.hour, args.minute))
        else:
            return validator.run_once()

    except ConfigError as exc:
        logging.getLogger(_LOGGER_NAME).error("Configuration error: %s", exc)
        return 1
    except Exception as exc:
        logging.getLogger(_LOGGER_NAME).exception("Unexpected error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
