"""Tests for P0 critical fixes: credentials, static IP, and token expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import keyring
import pytest
from iatb.broker.token_manager import (
    ZerodhaTokenManager,
    _get_pre_market_utc,
)
from iatb.core.exceptions import ConfigError
from iatb.risk.sebi_compliance import (
    SEBIComplianceConfig,
    SEBIComplianceManager,
    assert_static_ip_allowed,
    validate_static_ip_format,
    validate_static_ips_config,
)


class TestPreMarketTokenValidation:
    """Tests for pre-market token validation."""

    def test_is_token_valid_for_pre_market_no_token(self) -> None:
        """Test pre-market validation returns False when no token stored."""
        with patch.object(keyring, "get_password", return_value=None):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            assert manager.is_token_valid_for_pre_market() is False

    def test_is_token_valid_for_pre_market_no_timestamp(self) -> None:
        """Test pre-market validation returns False when no timestamp stored."""
        with patch.object(keyring, "get_password", side_effect=["test_token", None]):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            assert manager.is_token_valid_for_pre_market() is False

    def test_is_token_valid_for_pre_market_invalid_timestamp(self) -> None:
        """Test pre-market validation returns False with invalid timestamp."""
        with patch.object(keyring, "get_password", side_effect=["test_token", "invalid"]):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            assert manager.is_token_valid_for_pre_market() is False

    def test_is_token_valid_for_pre_market_valid(self) -> None:
        """Test pre-market validation returns True for valid token."""
        token_time = datetime(2026, 4, 28, 0, 0, 0, tzinfo=UTC)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["test_token", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                now_time = datetime(2026, 4, 28, 0, 20, 0, tzinfo=UTC)
                mock_dt.now.return_value = now_time
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine

                manager = ZerodhaTokenManager(
                    api_key="test_key",
                    api_secret="test_secret",  # noqa: S106
                )
                assert manager.is_token_valid_for_pre_market() is True

    def test_is_token_valid_for_pre_market_expired(self) -> None:
        """Test pre-market validation returns False for expired token."""
        old_time = datetime.now(UTC) - timedelta(days=2)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["test_token", old_time.isoformat()],
        ):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            assert manager.is_token_valid_for_pre_market() is False


class TestTokenAutoRefresh:
    """Tests for token auto-refresh with TOTP."""

    def test_should_refresh_token_no_token(self) -> None:
        """Test should_refresh_token returns True when no token stored."""
        with patch.object(keyring, "get_password", return_value=None):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            assert manager.should_refresh_token() is True

    def test_should_refresh_token_no_timestamp(self) -> None:
        """Test should_refresh_token returns True when no timestamp stored."""
        with patch.object(keyring, "get_password", side_effect=["test_token", None]):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            assert manager.should_refresh_token() is True

    def test_should_refresh_token_invalid_timestamp(self) -> None:
        """Test should_refresh_token returns True with invalid timestamp."""
        with patch.object(keyring, "get_password", side_effect=["test_token", "invalid"]):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            assert manager.should_refresh_token() is True

    def test_should_refresh_token_near_expiry(self) -> None:
        """Test should_refresh_token returns True when token near expiry."""
        token_time = datetime(2026, 4, 28, 0, 10, 0, tzinfo=UTC)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["test_token", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                now_time = datetime(2026, 4, 28, 0, 5, 0, tzinfo=UTC)
                mock_dt.now.return_value = now_time
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine

                manager = ZerodhaTokenManager(
                    api_key="test_key",
                    api_secret="test_secret",  # noqa: S106
                )
                assert manager.should_refresh_token(buffer_minutes=30) is True

    def test_should_refresh_token_fresh(self) -> None:
        """Test should_refresh_token returns False for fresh token."""
        fresh_time = datetime.now(UTC) + timedelta(hours=5)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["test_token", fresh_time.isoformat()],
        ):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            assert manager.should_refresh_token(buffer_minutes=30) is False

    def test_should_refresh_token_custom_buffer(self) -> None:
        """Test should_refresh_token with custom buffer minutes."""
        token_time = datetime(2026, 4, 28, 0, 15, 0, tzinfo=UTC)
        with patch.object(
            keyring,
            "get_password",
            side_effect=lambda service, key: (
                "test_token"
                if key == "access_token"
                else token_time.isoformat()
            ),
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                now_time = datetime(2026, 4, 28, 0, 5, 0, tzinfo=UTC)
                mock_dt.now.return_value = now_time
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine

                manager = ZerodhaTokenManager(
                    api_key="test_key",
                    api_secret="test_secret",  # noqa: S106
                )
                assert manager.should_refresh_token(buffer_minutes=60) is True
                assert manager.should_refresh_token(buffer_minutes=30) is True

    def test_auto_refresh_token_not_needed(self) -> None:
        """Test auto_refresh_token returns None when refresh not needed."""
        fresh_time = datetime.now(UTC) + timedelta(hours=5)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["test_token", fresh_time.isoformat()],
        ):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
                totp_secret="JBSWY3DPEHPK3PXP",  # noqa: S106
            )
            result = manager.auto_refresh_token()
            assert result is None

    def test_auto_refresh_token_no_totp_secret(self) -> None:
        """Test auto_refresh_token raises error without TOTP secret."""
        token_time = datetime(2026, 4, 28, 0, 10, 0, tzinfo=UTC)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["test_token", token_time.isoformat()],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                now_time = datetime(2026, 4, 28, 0, 5, 0, tzinfo=UTC)
                mock_dt.now.return_value = now_time
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine

                manager = ZerodhaTokenManager(
                    api_key="test_key",
                    api_secret="test_secret",  # noqa: S106
                    totp_secret=None,
                )
                with pytest.raises(ValueError, match="TOTP secret not configured"):
                    manager.auto_refresh_token()

    def test_auto_refresh_token_no_request_token(self) -> None:
        """Test auto_refresh_token raises error without request token."""
        token_time = datetime(2026, 4, 28, 0, 10, 0, tzinfo=UTC)
        with patch.object(
            keyring,
            "get_password",
            side_effect=["test_token", token_time.isoformat(), None],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                now_time = datetime(2026, 4, 28, 0, 5, 0, tzinfo=UTC)
                mock_dt.now.return_value = now_time
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine

                manager = ZerodhaTokenManager(
                    api_key="test_key",
                    api_secret="test_secret",  # noqa: S106
                    totp_secret="JBSWY3DPEHPK3PXP",  # noqa: S106
                )
                with pytest.raises(ValueError, match="No saved request token"):
                    manager.auto_refresh_token()

    def test_auto_refresh_token_success(self) -> None:
        """Test auto_refresh_token successfully refreshes token."""
        token_time = datetime(2026, 4, 28, 0, 10, 0, tzinfo=UTC)
        mock_http_post = MagicMock(return_value={"data": {"access_token": "new_access_token"}})

        with patch.object(
            keyring,
            "get_password",
            side_effect=[
                "test_token",
                token_time.isoformat(),
                "request_token",
                "2026-04-28",
            ],
        ):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                now_time = datetime(2026, 4, 28, 0, 5, 0, tzinfo=UTC)
                mock_dt.now.return_value = now_time
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine

                with patch.object(keyring, "set_password") as mock_set:
                    manager = ZerodhaTokenManager(
                        api_key="test_key",
                        api_secret="test_secret",  # noqa: S106
                        totp_secret="JBSWY3DPEHPK3PXP",  # noqa: S106
                        http_post=mock_http_post,
                    )
                    result = manager.auto_refresh_token()
                    assert result == "new_access_token"
                    assert mock_set.call_count >= 2


class TestPreMarketTimeCalculation:
    """Tests for pre-market time calculation."""

    def test_get_pre_market_utc_same_day_before_9am(self) -> None:
        """Test pre-market calculation for same day before 9 AM."""
        token_time = datetime(2026, 4, 28, 0, 0, tzinfo=UTC)
        pre_market = _get_pre_market_utc(token_time)
        expected = datetime(2026, 4, 28, 3, 30, tzinfo=UTC)
        assert pre_market == expected

    def test_get_pre_market_utc_same_day_after_9am(self) -> None:
        """Test pre-market calculation for after 9 AM."""
        token_time = datetime(2026, 4, 28, 10, 0, tzinfo=UTC)
        pre_market = _get_pre_market_utc(token_time)
        expected = datetime(2026, 4, 29, 3, 30, tzinfo=UTC)
        assert pre_market == expected

    def test_get_pre_market_utc_exactly_9am(self) -> None:
        """Test pre-market calculation at exactly 9 AM."""
        token_time = datetime(2026, 4, 28, 3, 30, 0, tzinfo=UTC)
        pre_market = _get_pre_market_utc(token_time)
        expected = datetime(2026, 4, 29, 3, 30, tzinfo=UTC)
        assert pre_market == expected


class TestStaticIPValidation:
    """Tests for static IP validation."""

    def test_validate_static_ip_format_valid_ips(self) -> None:
        """Test validation of valid IPv4 addresses."""
        assert validate_static_ip_format("192.168.1.1") is True
        assert validate_static_ip_format("10.0.0.1") is True
        assert validate_static_ip_format("172.16.0.1") is True
        assert validate_static_ip_format("255.255.255.255") is True

    def test_validate_static_ip_format_invalid_ips(self) -> None:
        """Test validation of invalid IPv4 addresses."""
        assert validate_static_ip_format("256.1.1.1") is False
        assert validate_static_ip_format("192.168.1") is False
        assert validate_static_ip_format("192.168.1.1.1") is False
        assert validate_static_ip_format("not.an.ip") is False
        assert validate_static_ip_format("") is False

    def test_validate_static_ips_config_all_valid(self) -> None:
        """Test validation when all IPs are valid."""
        validate_static_ips_config(("192.168.1.1", "10.0.0.1", "172.16.0.1"))

    def test_validate_static_ips_config_with_invalid_ip(self) -> None:
        """Test validation fails when one IP is invalid."""
        with pytest.raises(ConfigError, match="invalid static IP addresses"):
            validate_static_ips_config(("192.168.1.1", "256.1.1.1", "10.0.0.1"))

    def test_assert_static_ip_allowed_valid(self) -> None:
        """Test that valid IP in allow-list passes."""
        assert_static_ip_allowed("192.168.1.1", ("192.168.1.1", "10.0.0.1"))

    def test_assert_static_ip_allowed_empty_source(self) -> None:
        """Test that empty source IP is rejected."""
        with pytest.raises(ConfigError, match="source IP address cannot be empty"):
            assert_static_ip_allowed("", ("192.168.1.1",))

    def test_assert_static_ip_allowed_invalid_format(self) -> None:
        """Test that invalid IP format is rejected."""
        with pytest.raises(ConfigError, match="source IP address has invalid format"):
            assert_static_ip_allowed("not.an.ip", ("192.168.1.1",))

    def test_assert_static_ip_allowed_not_in_list(self) -> None:
        """Test that IP not in allow-list is rejected."""
        with pytest.raises(ConfigError, match="not in allowed static IPs"):
            assert_static_ip_allowed("192.168.1.99", ("192.168.1.1", "10.0.0.1"))


class TestSEBIComplianceManager:
    """Tests for SEBI compliance manager."""

    def test_sebi_compliance_manager_initialization(self, tmp_path: Path) -> None:
        """Test SEBI compliance manager initialization."""
        config = SEBIComplianceConfig(
            algo_id="ALG-101",
            audit_db_path=tmp_path / "audit.db",
            static_ips=("192.168.1.1",),
        )
        manager = SEBIComplianceManager(config)
        assert manager._config.algo_id == "ALG-101"
        assert manager._config.static_ips == ("192.168.1.1",)

    def test_sebi_compliance_manager_empty_algo_id(self, tmp_path: Path) -> None:
        """Test that manager rejects empty algo_id."""
        with pytest.raises(ConfigError, match="algo_id cannot be empty"):
            SEBIComplianceManager(
                SEBIComplianceConfig(
                    algo_id="  ",
                    audit_db_path=tmp_path / "audit.db",
                    static_ips=("192.168.1.1",),
                )
            )

    def test_sebi_compliance_manager_empty_static_ips(self, tmp_path: Path) -> None:
        """Test that manager rejects empty static_ips."""
        with pytest.raises(ConfigError, match="static_ips cannot be empty"):
            SEBIComplianceManager(
                SEBIComplianceConfig(
                    algo_id="ALG-101",
                    audit_db_path=tmp_path / "audit.db",
                    static_ips=(),
                )
            )

    def test_is_static_ip_allowed(self, tmp_path: Path) -> None:
        """Test static IP allow-list check."""
        manager = SEBIComplianceManager(
            SEBIComplianceConfig(
                algo_id="ALG-101",
                audit_db_path=tmp_path / "audit.db",
                static_ips=("192.168.1.1", "10.0.0.1"),
            )
        )
        assert manager.is_static_ip_allowed("192.168.1.1") is True
        assert manager.is_static_ip_allowed("10.0.0.1") is True
        assert manager.is_static_ip_allowed("192.168.1.99") is False


class TestEnvFileSecurity:
    """Tests for .env file security."""

    def test_env_file_deleted(self) -> None:
        """Test that .env file has been deleted."""
        env_path = Path.cwd() / ".env"
        assert not env_path.exists(), ".env file should be deleted"

    def test_env_example_exists(self) -> None:
        """Test that .env.example file exists."""
        env_example_path = Path.cwd() / ".env.example"
        assert env_example_path.exists(), ".env.example file should exist"

    def test_env_example_has_placeholders(self) -> None:
        """Test that .env.example has placeholder values."""
        env_example_path = Path.cwd() / ".env.example"
        content = env_example_path.read_text()
        assert "your_api_key_here" in content
        assert "your_api_secret_here" in content
        assert "BROKER_OAUTH_2FA_VERIFIED=false" in content

    def test_gitignore_has_env(self) -> None:
        """Test that .gitignore includes .env."""
        gitignore_path = Path.cwd() / ".gitignore"
        content = gitignore_path.read_text()
        assert ".env" in content, ".gitignore should include .env"


class TestConfigSettings:
    """Tests for config/settings.toml."""

    def test_settings_toml_has_static_ip(self) -> None:
        """Test that settings.toml has static_ip configured."""
        settings_path = Path.cwd() / "config" / "settings.toml"
        content = settings_path.read_text()
        assert "static_ip" in content, "settings.toml should have static_ip"
        assert "192.168.1.100" in content, "settings.toml should have placeholder IP"

    def test_settings_toml_not_placeholder(self) -> None:
        """Test that settings.toml does not have placeholder text."""
        settings_path = Path.cwd() / "config" / "settings.toml"
        content = settings_path.read_text()
        assert (
            "your.static.ip.address" not in content
        ), "settings.toml should not have placeholder text"
