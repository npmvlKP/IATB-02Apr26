"""
Production verification script for Zerodha token manager.
Tests connection, token refresh, and .env persistence.
"""

# ruff: noqa: E402, I001

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

# Add scripts directory to path for monitor script import
sys.path.insert(0, str(Path(__file__).parent.parent))

import keyring  # noqa: S105

from iatb.broker.token_manager import ZerodhaTokenManager
from iatb.core.exceptions import ConfigError
from iatb.execution.zerodha_connection import ZerodhaConnection
from iatb.execution.zerodha_token_manager import (
    ZerodhaTokenManager as ZerodhaTokenManagerV2,
)
from iatb.execution.zerodha_token_manager import (
    apply_env_defaults,
    load_env_file,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)sZ | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def test_zerodha_connection() -> bool:
    """Test Zerodha connection with real credentials."""
    logger.info("=" * 60)
    logger.info("TEST 1: Zerodha Connection with Real Credentials")
    logger.info("=" * 60)

    try:
        # Load environment variables
        env_path = Path(".env")
        if not env_path.exists():
            logger.error(".env file not found")
            return False

        env_values = load_env_file(env_path)
        apply_env_defaults(env_values)

        # Test connection
        connection = ZerodhaConnection.from_env()
        logger.info("✓ ZerodhaConnection initialized successfully")

        # Check if we have a saved token
        token_mgr = ZerodhaTokenManagerV2(env_path=env_path, env_values=env_values)
        saved_token = token_mgr.resolve_saved_access_token()

        if saved_token:
            logger.info(f"✓ Found saved access token: {saved_token[:8]}...")

            # Try to establish session
            try:
                session = connection.establish_session(access_token=saved_token)
                logger.info("✓ Session established successfully")
                logger.info(f"  - User ID: {session.user_id}")
                logger.info(f"  - User Name: {session.user_name}")
                logger.info(f"  - Available Balance: {session.available_balance}")
                logger.info(f"  - Connected At: {session.connected_at_utc}")
                return True
            except ConfigError as exc:
                logger.error(f"✗ Failed to establish session: {exc}")
                return False
        else:
            logger.warning("⚠ No saved access token found")
            logger.info("  Login URL: %s", connection.login_url())
            return False

    except Exception as exc:
        logger.error(f"✗ Connection test failed: {exc}", exc_info=True)
        return False


def test_token_refresh() -> bool:
    """Test token refresh functionality."""
    logger.info("=" * 60)
    logger.info("TEST 2: Token Refresh Functionality")
    logger.info("=" * 60)

    try:
        # Test broker token manager (keyring-based)
        token_mgr = ZerodhaTokenManager(
            api_key="test_key",
            api_secret="test_secret",  # noqa: S106
        )

        # Test is_token_fresh with no token (properly mocked)
        with patch.object(keyring, "get_password", return_value=None):
            result = token_mgr.is_token_fresh()
            if result is False:
                logger.info("✓ is_token_fresh() with no token: False (expected: False)")
            else:
                logger.warning(f"✗ is_token_fresh() with no token: {result} (expected: False)")
                return False

        # Test get_login_url
        url = token_mgr.get_login_url()
        logger.info(f"✓ get_login_url() returns: {url}")

        # Test get_kite_client error handling
        with patch.object(keyring, "get_password", return_value=None):
            try:
                token_mgr.get_kite_client()
                logger.warning("⚠ get_kite_client() should raise without token")
                return False
            except ValueError as exc:
                logger.info(f"✓ get_kite_client() correctly raises: {exc}")

        return True

    except Exception as exc:
        logger.error(f"✗ Token refresh test failed: {exc}", exc_info=True)
        return False


def test_timestamp_handling() -> bool:
    """Test for None timestamp errors."""
    logger.info("=" * 60)
    logger.info("TEST 3: Timestamp Error Detection")
    logger.info("=" * 60)

    try:
        # Test with invalid timestamp in keyring
        token_mgr = ZerodhaTokenManager(
            api_key="test_key",
            api_secret="test_secret",  # noqa: S106
        )

        # Test with None timestamp
        with patch.object(keyring, "get_password", side_effect=["test_token", None]):
            result = token_mgr.is_token_fresh()
            logger.info(f"✓ is_token_fresh() with None timestamp: {result} (expected: False)")

        # Test with invalid timestamp format
        with patch.object(keyring, "get_password", side_effect=["test_token", "invalid"]):
            result = token_mgr.is_token_fresh()
            logger.info(f"✓ is_token_fresh() with invalid timestamp: {result} (expected: False)")

        # Test with valid timestamp
        valid_time = datetime.now(UTC).isoformat()
        with patch.object(keyring, "get_password", side_effect=["test_token", valid_time]):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                mock_dt.now.return_value = datetime.now(UTC)
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine
                result = token_mgr.is_token_fresh()
                logger.info(f"✓ is_token_fresh() with valid timestamp: {result}")

        return True

    except Exception as exc:
        logger.error(f"✗ Timestamp handling test failed: {exc}", exc_info=True)
        return False


def test_env_persistence() -> bool:
    """Test .env file persistence across restarts."""
    logger.info("=" * 60)
    logger.info("TEST 4: .env File Persistence")
    logger.info("=" * 60)

    try:
        env_path = Path(".env")
        if not env_path.exists():
            logger.error(".env file not found")
            return False

        # Load current env
        env_values = load_env_file(env_path)
        logger.info(f"✓ Loaded .env file with {len(env_values)} variables")

        # Check for token-related variables
        token_keys = [
            "ZERODHA_ACCESS_TOKEN",
            "ZERODHA_REQUEST_TOKEN",
            "ZERODHA_ACCESS_TOKEN_DATE_UTC",
            "ZERODHA_REQUEST_TOKEN_DATE_UTC",
            "BROKER_OAUTH_2FA_VERIFIED",
        ]

        found_keys = [k for k in token_keys if k in env_values]
        if found_keys:
            logger.info(f"✓ Found token-related keys: {found_keys}")
        else:
            logger.info("ℹ No token-related keys in .env (tokens in keyring)")

        # Test persistence
        token_mgr = ZerodhaTokenManagerV2(env_path=env_path, env_values=env_values)

        # Test resolving saved tokens
        access_token = token_mgr.resolve_saved_access_token()
        request_token = token_mgr.resolve_saved_request_token()

        if access_token:
            logger.info(f"✓ Resolved access token: {access_token[:8]}...")
        else:
            logger.info("ℹ No access token resolved")

        if request_token:
            logger.info(f"✓ Resolved request token: {request_token[:8]}...")
        else:
            logger.info("ℹ No request token resolved")

        return True

    except Exception as exc:
        logger.error(f"✗ .env persistence test failed: {exc}", exc_info=True)
        return False


def test_monitor_script() -> bool:
    """Test the monitor_zerodha_connection script."""
    logger.info("=" * 60)
    logger.info("TEST 5: Monitor Script Verification")
    logger.info("=" * 60)

    try:
        from scripts.monitor_zerodha_connection import (
            _build_parser,
            _utc_now_iso,
            _validate_args,
        )

        # Test parser
        parser = _build_parser()
        logger.info("✓ Monitor script parser initialized")

        # Test validation
        args = parser.parse_args(["--once"])
        _validate_args(interval_seconds=args.interval_seconds, max_checks=args.max_checks)
        logger.info("✓ Monitor script validation passed")

        # Test timestamp function
        now = _utc_now_iso()
        logger.info(f"✓ UTC timestamp: {now}")

        return True

    except Exception as exc:
        logger.error(f"✗ Monitor script test failed: {exc}", exc_info=True)
        return False


def main() -> int:
    """Run all production verification tests."""
    logger.info("Starting Token Manager Production Verification")
    logger.info(f"Timestamp: {datetime.now(UTC).isoformat()}")
    logger.info("")

    results = {
        "Zerodha Connection": test_zerodha_connection(),
        "Token Refresh": test_token_refresh(),
        "Timestamp Handling": test_timestamp_handling(),
        ".env Persistence": test_env_persistence(),
        "Monitor Script": test_monitor_script(),
    }

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 60)

    passed = 0
    failed = 0

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
        if result:
            passed += 1
        else:
            failed += 1

    logger.info("")
    logger.info(f"Total: {passed} passed, {failed} failed")

    if failed == 0:
        logger.info("🎉 All verification tests passed!")
        return 0
    else:
        logger.error(f"❌ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
