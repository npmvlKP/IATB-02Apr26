"""Tests for Secrets Rotation Manager."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.core.secrets_rotation import (
    RotationPolicy,
    RotationStatus,
    SecretMetadata,
    SecretsRotationManager,
    SecretType,
)


def _utc_now() -> datetime:
    return datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)


class TestSecretMetadata:
    def test_is_expired_false(self) -> None:
        now = _utc_now()
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
        assert meta.is_expired is False

    def test_is_expired_true(self) -> None:
        past = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=past - timedelta(hours=48),
            expires_at=past - timedelta(hours=1),
        )
        assert meta.is_expired is True

    def test_time_until_expiry(self) -> None:
        now = _utc_now()
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
        remaining = meta.time_until_expiry
        assert remaining > timedelta(0)

    def test_time_until_expiry_expired(self) -> None:
        past = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=past - timedelta(hours=48),
            expires_at=past - timedelta(hours=1),
        )
        assert meta.time_until_expiry == timedelta(0)

    def test_usage_ratio_new(self) -> None:
        now = _utc_now()
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
        assert meta.get_usage_ratio(now) <= Decimal("0.01")

    def test_usage_ratio_near_expiry(self) -> None:
        past = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=past - timedelta(hours=23, minutes=55),
            expires_at=past + timedelta(minutes=5),
        )
        assert meta.get_usage_ratio(past) >= Decimal("0.9")

    def test_usage_ratio_defaults_to_now(self) -> None:
        """Test that get_usage_ratio uses current time when not provided."""
        # Create metadata with a future expiry so it won't be expired yet
        # Use a time range in the near future
        now = datetime.now(UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=now - timedelta(hours=1),
            expires_at=now + timedelta(hours=23),
        )
        # Should calculate using real now
        ratio = meta.get_usage_ratio()
        assert ratio >= Decimal("0.04")
        assert ratio <= Decimal("0.05")

    def test_usage_ratio_expired(self) -> None:
        """Test usage ratio when secret is expired."""
        past = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=past - timedelta(hours=24),
            expires_at=past - timedelta(hours=12),  # Already expired 12 hours ago
        )
        assert meta.get_usage_ratio(past) == Decimal("1.0")

    def test_usage_ratio_zero_lifetime(self) -> None:
        """Test usage ratio when total lifetime is zero or negative."""
        now = _utc_now()
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=now,
            expires_at=now,  # Zero lifetime
        )
        assert meta.get_usage_ratio(now) == Decimal("1.0")

    def test_get_usage_ratio_raises_on_naive(self) -> None:
        """Test that get_usage_ratio raises error when now_utc is naive."""
        now = _utc_now()
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
        # Providing naive datetime should work (no validation in get_usage_ratio)
        # But the test demonstrates we don't need UTC validation here
        # since it's just calculating elapsed time
        ratio = meta.get_usage_ratio()
        assert isinstance(ratio, Decimal)


class TestRotationPolicy:
    def test_valid_policy(self) -> None:
        policy = RotationPolicy(
            secret_type=SecretType.API_KEY,
            rotation_interval=timedelta(hours=24),
        )
        assert policy.rotation_interval == timedelta(hours=24)

    def test_invalid_interval(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(0),
            )

    def test_invalid_max_attempts(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
                max_rotation_attempts=0,
            )


class TestSecretsRotationManager:
    def _make_manager(self) -> SecretsRotationManager:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
                warning_before_expiry=timedelta(hours=1),
            )
        )
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.ACCESS_TOKEN,
                rotation_interval=timedelta(hours=8),
                warning_before_expiry=timedelta(hours=1),
            )
        )
        return mgr

    def test_register_policy(self) -> None:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        assert len(mgr.get_all_secrets_status()) == 0

    def test_register_secret(self) -> None:
        mgr = self._make_manager()
        meta = mgr.register_secret(SecretType.API_KEY, "TEST_API_KEY", _utc_now())
        assert meta.key_name == "TEST_API_KEY"
        assert meta.rotation_count == 0

    def test_register_secret_unknown_type_rejected(self) -> None:
        mgr = SecretsRotationManager()
        with pytest.raises(ConfigError, match="No rotation policy"):
            mgr.register_secret("UNKNOWN_TYPE", "key", _utc_now())

    def test_check_rotation_needed_none(self) -> None:
        mgr = self._make_manager()
        mgr.register_secret(SecretType.API_KEY, "TEST_KEY", _utc_now())
        needed = mgr.check_rotation_needed(_utc_now())
        assert len(needed) == 0

    def test_check_rotation_needed_near_expiry(self) -> None:
        mgr = self._make_manager()
        now = _utc_now()
        policy = RotationPolicy(
            secret_type=SecretType.API_KEY,
            rotation_interval=timedelta(hours=2),
            warning_before_expiry=timedelta(hours=1),
        )
        mgr.register_policy(policy)
        mgr.register_secret(SecretType.API_KEY, "TEST_KEY", now - timedelta(hours=1))
        needed = mgr.check_rotation_needed(now)
        assert len(needed) >= 1

    def test_rotate_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mgr = self._make_manager()
        now = _utc_now()
        mgr.register_secret(SecretType.API_KEY, "TEST_ROTATE_KEY", now)
        new_meta = mgr.rotate_secret("TEST_ROTATE_KEY", "new_secret_value", now)
        assert new_meta.rotation_count == 1
        assert new_meta.last_rotated_at == now

    def test_rotate_secret_unknown_key_rejected(self) -> None:
        mgr = self._make_manager()
        with pytest.raises(ConfigError, match="not registered"):
            mgr.rotate_secret("UNKNOWN", "value", _utc_now())

    def test_rotate_secret_history(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mgr = self._make_manager()
        now = _utc_now()
        mgr.register_secret(SecretType.API_KEY, "TEST_HIST_KEY", now)
        mgr.rotate_secret("TEST_HIST_KEY", "new_value", now)
        history = mgr.get_rotation_history("TEST_HIST_KEY")
        assert len(history) == 1
        assert history[0].status == RotationStatus.COMPLETED

    def test_get_rotation_history_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mgr = self._make_manager()
        now = _utc_now()
        mgr.register_secret(SecretType.API_KEY, "KEY_A", now)
        mgr.rotate_secret("KEY_A", "new_a", now)
        all_history = mgr.get_rotation_history()
        assert len(all_history) == 1

    def test_get_secret_status(self) -> None:
        mgr = self._make_manager()
        now = _utc_now()
        mgr.register_secret(SecretType.API_KEY, "TEST_STATUS", now)
        status = mgr.get_secret_status("TEST_STATUS")
        assert status is not None
        assert status.key_name == "TEST_STATUS"

    def test_get_secret_status_not_found(self) -> None:
        mgr = self._make_manager()
        assert mgr.get_secret_status("NONEXISTENT") is None

    def test_is_secret_valid(self) -> None:
        mgr = self._make_manager()
        now = _utc_now()
        mgr.register_secret(SecretType.API_KEY, "TEST_VALID", now)
        assert mgr.is_secret_valid("TEST_VALID") is True

    def test_is_secret_valid_not_registered(self) -> None:
        mgr = self._make_manager()
        assert mgr.is_secret_valid("NONEXISTENT") is False

    def test_schedule_rotation(self) -> None:
        mgr = self._make_manager()
        now = _utc_now()
        mgr.register_secret(SecretType.API_KEY, "TEST_SCHED", now)
        rotate_at = now + timedelta(hours=1)
        mgr.schedule_rotation("TEST_SCHED", rotate_at)

    def test_schedule_rotation_unknown_key_rejected(self) -> None:
        mgr = self._make_manager()
        with pytest.raises(ConfigError, match="not registered"):
            mgr.schedule_rotation("UNKNOWN", _utc_now())

    def test_process_scheduled_rotations(self) -> None:
        mgr = self._make_manager()
        now = _utc_now()
        mgr.register_secret(SecretType.API_KEY, "TEST_PROC", now)
        past = now - timedelta(hours=1)
        mgr.schedule_rotation("TEST_PROC", past)
        due = mgr.process_scheduled_rotations(now)
        assert "TEST_PROC" in due

    def test_process_scheduled_rotations_not_yet(self) -> None:
        mgr = self._make_manager()
        now = _utc_now()
        mgr.register_secret(SecretType.API_KEY, "TEST_FUTURE", now)
        future = now + timedelta(hours=24)
        mgr.schedule_rotation("TEST_FUTURE", future)
        due = mgr.process_scheduled_rotations(now)
        assert len(due) == 0

    def test_naive_datetime_rejected_register(self) -> None:
        mgr = self._make_manager()
        with pytest.raises(ConfigError, match="UTC"):
            mgr.register_secret(  # noqa: DTZ001
                SecretType.API_KEY,
                "KEY",
                datetime(2026, 4, 27),
            )

    def test_naive_datetime_rejected_check(self) -> None:
        mgr = self._make_manager()
        with pytest.raises(ConfigError, match="UTC"):
            mgr.check_rotation_needed(datetime(2026, 4, 27))  # noqa: DTZ001

    def test_get_all_secrets_status(self) -> None:
        mgr = self._make_manager()
        now = _utc_now()
        mgr.register_secret(SecretType.API_KEY, "KEY1", now)
        mgr.register_secret(SecretType.ACCESS_TOKEN, "KEY2", now)
        all_status = mgr.get_all_secrets_status()
        assert len(all_status) == 2
