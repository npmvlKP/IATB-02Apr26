"""Comprehensive coverage tests for iatb.risk.sebi_compliance."""

from datetime import UTC, datetime, time
from pathlib import Path

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.sebi_compliance import (
    SEBIComplianceConfig,
    SEBIComplianceManager,
    assert_static_ip_allowed,
    validate_static_ip_format,
    validate_static_ips_config,
)


def _make_config(**overrides: object) -> SEBIComplianceConfig:
    defaults = {
        "algo_id": "ALGO-001",
        "audit_db_path": Path(":memory:"),
        "static_ips": ("192.168.1.1", "10.0.0.1"),
        "auto_logout_ist": time(3, 0),
        "require_oauth_2fa": True,
    }
    defaults.update(overrides)
    return SEBIComplianceConfig(**defaults)


_NOW = datetime(2026, 5, 25, 10, 0, tzinfo=UTC)


class TestSEBIComplianceConfig:
    def test_valid_config(self) -> None:
        cfg = _make_config()
        assert cfg.algo_id == "ALGO-001"

    def test_frozen(self) -> None:
        cfg = _make_config()
        with pytest.raises(AttributeError):
            cfg.algo_id = "other"


class TestSEBIComplianceManagerInit:
    def test_valid_init(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        assert mgr._config.algo_id == "ALGO-001"

    def test_empty_algo_id_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="algo_id"):
            SEBIComplianceManager(
                _make_config(algo_id="  ", audit_db_path=tmp_path / "test.db")
            )

    def test_empty_static_ips_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="static_ips"):
            SEBIComplianceManager(
                _make_config(static_ips=(), audit_db_path=tmp_path / "test.db")
            )


class TestInjectAlgoId:
    def test_injects_missing_algo_id(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        result = mgr.inject_algo_id({"symbol": "RELIANCE"})
        assert result["algo_id"] == "ALGO-001"
        assert result["symbol"] == "RELIANCE"

    def test_matching_algo_id_passes(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        result = mgr.inject_algo_id({"algo_id": "ALGO-001", "symbol": "RELIANCE"})
        assert result["algo_id"] == "ALGO-001"

    def test_mismatched_algo_id_raises(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        with pytest.raises(ConfigError, match="mismatched"):
            mgr.inject_algo_id({"algo_id": "WRONG-ID"})


class TestIsStaticIpAllowed:
    def test_allowed_ip(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        assert mgr.is_static_ip_allowed("192.168.1.1") is True

    def test_disallowed_ip(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        assert mgr.is_static_ip_allowed("1.2.3.4") is False


class TestAssertOauth2fa:
    def test_both_verified_passes(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        mgr.assert_oauth_2fa_verified(True, True)

    def test_oauth_not_verified_raises(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        with pytest.raises(ConfigError, match="OAuth 2FA"):
            mgr.assert_oauth_2fa_verified(False, True)

    def test_2fa_not_verified_raises(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        with pytest.raises(ConfigError, match="OAuth 2FA"):
            mgr.assert_oauth_2fa_verified(True, False)

    def test_both_false_raises(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        with pytest.raises(ConfigError, match="OAuth 2FA"):
            mgr.assert_oauth_2fa_verified(False, False)

    def test_skip_when_not_required(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(
            _make_config(require_oauth_2fa=False, audit_db_path=tmp_path / "test.db")
        )
        mgr.assert_oauth_2fa_verified(False, False)


class TestShouldAutoLogout:
    def test_before_cutoff(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(
            _make_config(
                auto_logout_ist=time(8, 30), audit_db_path=tmp_path / "test.db"
            )
        )
        now_utc = datetime(2026, 5, 25, 2, 0, tzinfo=UTC)
        assert mgr.should_auto_logout(now_utc) is False

    def test_after_cutoff(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(
            _make_config(auto_logout_ist=time(3, 0), audit_db_path=tmp_path / "test.db")
        )
        now_utc = datetime(2026, 5, 25, 4, 0, tzinfo=UTC)
        assert mgr.should_auto_logout(now_utc) is True

    def test_naive_datetime_raises(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        with pytest.raises(ConfigError, match="timezone-aware"):
            mgr.should_auto_logout(datetime(2026, 5, 25, 10, 0))


class TestAssertLiveSessionAllowed:
    def test_allowed_ip_and_before_cutoff(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(
            _make_config(
                auto_logout_ist=time(8, 30), audit_db_path=tmp_path / "test.db"
            )
        )
        now_utc = datetime(2026, 5, 25, 2, 0, tzinfo=UTC)
        mgr.assert_live_session_allowed("192.168.1.1", now_utc)

    def test_disallowed_ip_raises(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(_make_config(audit_db_path=tmp_path / "test.db"))
        with pytest.raises(ConfigError, match="static IP"):
            mgr.assert_live_session_allowed("1.2.3.4", _NOW)

    def test_after_cutoff_raises(self, tmp_path: Path) -> None:
        mgr = SEBIComplianceManager(
            _make_config(auto_logout_ist=time(3, 0), audit_db_path=tmp_path / "test.db")
        )
        now_utc = datetime(2026, 5, 25, 4, 0, tzinfo=UTC)
        with pytest.raises(ConfigError, match="cutoff"):
            mgr.assert_live_session_allowed("192.168.1.1", now_utc)


class TestValidateStaticIpFormat:
    def test_valid_ip(self) -> None:
        assert validate_static_ip_format("192.168.1.1") is True

    def test_valid_ip_with_spaces(self) -> None:
        assert validate_static_ip_format(" 192.168.1.1 ") is True

    def test_invalid_ip(self) -> None:
        assert validate_static_ip_format("999.1.1.1") is False

    def test_empty_ip(self) -> None:
        assert validate_static_ip_format("") is False

    def test_non_numeric(self) -> None:
        assert validate_static_ip_format("abc.def.ghi.jkl") is False

    def test_localhost(self) -> None:
        assert validate_static_ip_format("127.0.0.1") is True

    def test_boundary_255(self) -> None:
        assert validate_static_ip_format("255.255.255.255") is True

    def test_boundary_0(self) -> None:
        assert validate_static_ip_format("0.0.0.0") is True

    def test_partial_ip(self) -> None:
        assert validate_static_ip_format("192.168.1") is False


class TestValidateStaticIpsConfig:
    def test_all_valid(self) -> None:
        validate_static_ips_config(("192.168.1.1", "10.0.0.1"))

    def test_invalid_ip_raises(self) -> None:
        with pytest.raises(ConfigError, match="invalid static IP"):
            validate_static_ips_config(("192.168.1.1", "999.1.1.1"))


class TestAssertStaticIpAllowed:
    def test_allowed_ip(self) -> None:
        assert_static_ip_allowed("192.168.1.1", ("192.168.1.1", "10.0.0.1"))

    def test_disallowed_ip_raises(self) -> None:
        with pytest.raises(ConfigError, match="not in allowed"):
            assert_static_ip_allowed("1.2.3.4", ("192.168.1.1",))

    def test_empty_ip_raises(self) -> None:
        with pytest.raises(ConfigError, match="cannot be empty"):
            assert_static_ip_allowed("", ("192.168.1.1",))

    def test_whitespace_only_ip_raises(self) -> None:
        with pytest.raises(ConfigError, match="cannot be empty"):
            assert_static_ip_allowed("  ", ("192.168.1.1",))

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ConfigError, match="invalid format"):
            assert_static_ip_allowed("abc", ("192.168.1.1",))

    def test_custom_broker(self) -> None:
        with pytest.raises(ConfigError, match="custom_broker"):
            assert_static_ip_allowed(
                "1.2.3.4", ("192.168.1.1",), broker="custom_broker"
            )
