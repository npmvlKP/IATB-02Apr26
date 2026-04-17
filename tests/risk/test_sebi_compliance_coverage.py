"""Additional tests for sebi_compliance.py to improve coverage to 90%+."""

import random
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.risk.sebi_compliance import (
    SEBIComplianceConfig,
    SEBIComplianceManager,
    assert_static_ip_allowed,
    validate_static_ip_format,
    validate_static_ips_config,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_sebi_compliance_constructor_empty_algo_id(tmp_path: Path) -> None:
    """Test that constructor rejects empty algo_id."""
    with pytest.raises(ConfigError, match="algo_id cannot be empty"):
        SEBIComplianceManager(
            SEBIComplianceConfig(
                algo_id="  ",  # Whitespace only
                audit_db_path=tmp_path / "audit.db",
                static_ips=("192.168.1.1",),
            )
        )


def test_sebi_compliance_constructor_empty_static_ips(tmp_path: Path) -> None:
    """Test that constructor rejects empty static_ips."""
    with pytest.raises(ConfigError, match="static_ips cannot be empty"):
        SEBIComplianceManager(
            SEBIComplianceConfig(
                algo_id="ALG-101",
                audit_db_path=tmp_path / "audit.db",
                static_ips=(),  # Empty tuple
            )
        )


def test_validate_static_ip_format_valid() -> None:
    """Test validation of valid IPv4 addresses."""
    assert validate_static_ip_format("192.168.1.1") is True
    assert validate_static_ip_format("10.0.0.1") is True
    assert validate_static_ip_format("172.16.0.1") is True
    assert validate_static_ip_format("255.255.255.255") is True
    assert validate_static_ip_format("  192.168.1.1  ") is True  # With whitespace


def test_validate_static_ip_format_invalid() -> None:
    """Test validation of invalid IPv4 addresses."""
    assert validate_static_ip_format("256.1.1.1") is False  # Octet > 255
    assert validate_static_ip_format("192.168.1") is False  # Missing octet
    assert validate_static_ip_format("192.168.1.1.1") is False  # Too many octets
    assert validate_static_ip_format("not.an.ip") is False
    assert validate_static_ip_format("") is False
    assert validate_static_ip_format("192.168.1.-1") is False  # Negative octet


def test_validate_static_ips_config_all_valid(tmp_path: Path) -> None:
    """Test validation when all IPs are valid."""
    # Should not raise
    validate_static_ips_config(("192.168.1.1", "10.0.0.1", "172.16.0.1"))


def test_validate_static_ips_config_with_invalid_ip(tmp_path: Path) -> None:
    """Test validation fails when one IP is invalid."""
    with pytest.raises(ConfigError, match="invalid static IP addresses"):
        validate_static_ips_config(("192.168.1.1", "256.1.1.1", "10.0.0.1"))


def test_validate_static_ips_config_multiple_invalid(tmp_path: Path) -> None:
    """Test validation fails when multiple IPs are invalid."""
    with pytest.raises(ConfigError, match="invalid static IP addresses"):
        validate_static_ips_config(("256.1.1.1", "not.an.ip", "10.0.0.1"))


def test_assert_static_ip_allowed_valid() -> None:
    """Test that valid IP in allow-list passes."""
    # Should not raise
    assert_static_ip_allowed("192.168.1.1", ("192.168.1.1", "10.0.0.1"))


def test_assert_static_ip_allowed_empty_source() -> None:
    """Test that empty source IP is rejected."""
    with pytest.raises(ConfigError, match="source IP address cannot be empty"):
        assert_static_ip_allowed("", ("192.168.1.1",))


def test_assert_static_ip_allowed_whitespace_only() -> None:
    """Test that whitespace-only source IP is rejected."""
    with pytest.raises(ConfigError, match="source IP address cannot be empty"):
        assert_static_ip_allowed("   ", ("192.168.1.1",))


def test_assert_static_ip_allowed_invalid_format() -> None:
    """Test that invalid IP format is rejected."""
    with pytest.raises(ConfigError, match="source IP address has invalid format"):
        assert_static_ip_allowed("not.an.ip", ("192.168.1.1",))


def test_assert_static_ip_allowed_not_in_list() -> None:
    """Test that IP not in allow-list is rejected."""
    with pytest.raises(ConfigError, match="not in allowed static IPs"):
        assert_static_ip_allowed("192.168.1.99", ("192.168.1.1", "10.0.0.1"))


def test_assert_static_ip_allowed_with_broker_name() -> None:
    """Test that broker name is included in error message."""
    with pytest.raises(ConfigError, match="not in allowed static IPs for zerodha"):
        assert_static_ip_allowed("192.168.1.99", ("192.168.1.1",), broker="zerodha")


def test_assert_static_ip_allowed_custom_broker() -> None:
    """Test that custom broker name is used in error."""
    with pytest.raises(ConfigError, match="not in allowed static IPs for custom"):
        assert_static_ip_allowed("192.168.1.99", ("192.168.1.1",), broker="custom")


def test_sebi_compliance_inject_algo_id_with_mismatch(tmp_path: Path) -> None:
    """Test that inject_algo_id rejects mismatched algo_id."""
    manager = SEBIComplianceManager(
        SEBIComplianceConfig("ALG-101", tmp_path / "audit.db", ("192.168.1.1",))
    )
    with pytest.raises(ConfigError, match="payload contains mismatched algo_id"):
        manager.inject_algo_id({"algo_id": "ALG-999"})


def test_sebi_compliance_inject_algo_id_adds_algo_id(tmp_path: Path) -> None:
    """Test that inject_algo_id adds algo_id to payload."""
    manager = SEBIComplianceManager(
        SEBIComplianceConfig("ALG-101", tmp_path / "audit.db", ("192.168.1.1",))
    )
    payload = manager.inject_algo_id({"symbol": "NIFTY"})
    assert payload["algo_id"] == "ALG-101"
    assert payload["symbol"] == "NIFTY"


def test_sebi_compliance_oauth_2fa_not_required(tmp_path: Path) -> None:
    """Test OAuth 2FA check when not required."""
    config = SEBIComplianceConfig(
        "ALG-101", tmp_path / "audit.db", ("192.168.1.1",), require_oauth_2fa=False
    )
    manager = SEBIComplianceManager(config)
    # Should not raise even without 2FA
    manager.assert_oauth_2fa_verified(oauth_authenticated=False, two_factor_verified=False)


def test_sebi_compliance_oauth_2fa_only_oauth(tmp_path: Path) -> None:
    """Test OAuth 2FA check fails with only OAuth."""
    manager = SEBIComplianceManager(
        SEBIComplianceConfig("ALG-101", tmp_path / "audit.db", ("192.168.1.1",))
    )
    with pytest.raises(ConfigError, match="OAuth 2FA verification is required"):
        manager.assert_oauth_2fa_verified(oauth_authenticated=True, two_factor_verified=False)


def test_sebi_compliance_oauth_2fa_only_2fa(tmp_path: Path) -> None:
    """Test OAuth 2FA check fails with only 2FA."""
    manager = SEBIComplianceManager(
        SEBIComplianceConfig("ALG-101", tmp_path / "audit.db", ("192.168.1.1",))
    )
    with pytest.raises(ConfigError, match="OAuth 2FA verification is required"):
        manager.assert_oauth_2fa_verified(oauth_authenticated=False, two_factor_verified=True)


def test_sebi_compliance_auto_logout_custom_time(tmp_path: Path) -> None:
    """Test auto-logout with custom time."""
    config = SEBIComplianceConfig(
        "ALG-101",
        tmp_path / "audit.db",
        ("192.168.1.1",),
        auto_logout_ist=datetime(2024, 1, 1, 2, 0, tzinfo=UTC).time(),
    )
    manager = SEBIComplianceManager(config)
    # 2:00 AM IST = 20:30 UTC (previous day)
    assert manager.should_auto_logout(datetime(2024, 1, 1, 20, 30, tzinfo=UTC)) is True
    # 1:59 AM IST = 20:29 UTC (previous day)
    assert manager.should_auto_logout(datetime(2024, 1, 1, 20, 29, tzinfo=UTC)) is False


def test_sebi_compliance_auto_logout_naive_datetime(tmp_path: Path) -> None:
    """Test that auto-logout rejects naive datetime."""
    manager = SEBIComplianceManager(
        SEBIComplianceConfig("ALG-101", tmp_path / "audit.db", ("192.168.1.1",))
    )
    with pytest.raises(ConfigError, match="now_utc must be timezone-aware UTC datetime"):
        manager.should_auto_logout(
            datetime(2024, 1, 1, 10, 0)
        )  # Naive datetime without tzinfo # noqa: DTZ001


def test_sebi_compliance_is_static_ip_allowed_multiple(tmp_path: Path) -> None:
    """Test static IP check with multiple IPs."""
    manager = SEBIComplianceManager(
        SEBIComplianceConfig(
            "ALG-101", tmp_path / "audit.db", ("192.168.1.1", "10.0.0.1", "172.16.0.1")
        )
    )
    assert manager.is_static_ip_allowed("192.168.1.1") is True
    assert manager.is_static_ip_allowed("10.0.0.1") is True
    assert manager.is_static_ip_allowed("172.16.0.1") is True
    assert manager.is_static_ip_allowed("192.168.1.99") is False
