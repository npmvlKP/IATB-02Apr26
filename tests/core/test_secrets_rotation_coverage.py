"""Coverage tests for iatb.core.secrets_rotation — secrets rotation manager."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from freezegun import freeze_time
from iatb.core.exceptions import ConfigError
from iatb.core.secrets_rotation import (
    RotationEvent,
    RotationPolicy,
    RotationStatus,
    SecretMetadata,
    SecretsRotationManager,
    SecretType,
    _hash_value,
    _set_env_secret,
    _validate_utc,
)


class TestSecretType:
    def test_api_key_value(self) -> None:
        assert SecretType.API_KEY == "api_key"

    def test_api_secret_value(self) -> None:
        assert SecretType.API_SECRET == "api_secret"

    def test_access_token_value(self) -> None:
        assert SecretType.ACCESS_TOKEN == "access_token"

    def test_refresh_token_value(self) -> None:
        assert SecretType.REFRESH_TOKEN == "refresh_token"

    def test_hmac_key_value(self) -> None:
        assert SecretType.HMAC_KEY == "hmac_key"

    def test_database_key_value(self) -> None:
        assert SecretType.DATABASE_KEY == "database_key"


class TestRotationStatus:
    def test_pending(self) -> None:
        assert RotationStatus.PENDING == "PENDING"

    def test_in_progress(self) -> None:
        assert RotationStatus.IN_PROGRESS == "IN_PROGRESS"

    def test_completed(self) -> None:
        assert RotationStatus.COMPLETED == "COMPLETED"

    def test_failed(self) -> None:
        assert RotationStatus.FAILED == "FAILED"


class TestSecretMetadata:
    def test_is_expired_when_expired(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = datetime(2024, 1, 2, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        now = datetime(2024, 1, 3, tzinfo=UTC)
        assert meta.is_expired(now) is True

    def test_is_expired_when_not_expired(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = datetime(2024, 12, 31, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        now = datetime(2024, 6, 15, tzinfo=UTC)
        assert meta.is_expired(now) is False

    def test_is_expired_at_exact_expiry_boundary(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = datetime(2024, 6, 15, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        assert meta.is_expired(expires) is True

    def test_is_expired_just_before_expiry_boundary(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = datetime(2024, 6, 15, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        just_before = expires - timedelta(seconds=1)
        assert meta.is_expired(just_before) is False

    def test_is_expired_without_now_defaults_to_current(self) -> None:
        created = datetime(2020, 1, 1, tzinfo=UTC)
        expires = datetime(2020, 12, 31, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        assert meta.is_expired() is True

    @freeze_time("2024-06-15T10:00:00Z")
    def test_time_until_expiry_positive(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = datetime(2024, 7, 1, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        remaining = meta.time_until_expiry
        assert remaining.total_seconds() > 0

    @freeze_time("2024-12-01T00:00:00Z")
    def test_time_until_expiry_zero_when_expired(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = datetime(2024, 6, 1, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        assert meta.time_until_expiry == timedelta(0)

    def test_get_usage_ratio_halfway(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = datetime(2024, 1, 3, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        now = datetime(2024, 1, 2, tzinfo=UTC)
        ratio = meta.get_usage_ratio(now)
        assert ratio == Decimal("0.5")

    def test_get_usage_ratio_fully_used(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = datetime(2024, 1, 2, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        now = datetime(2024, 1, 3, tzinfo=UTC)
        ratio = meta.get_usage_ratio(now)
        assert ratio == Decimal("1.0")

    def test_get_usage_ratio_zero_total_lifetime(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = created
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        ratio = meta.get_usage_ratio(created)
        assert ratio == Decimal("1.0")

    def test_get_usage_ratio_just_started(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = datetime(2024, 12, 31, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        now = datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC)
        ratio = meta.get_usage_ratio(now)
        assert ratio > Decimal("0")
        assert ratio < Decimal("1")

    def test_frozen_dataclass(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = datetime(2024, 12, 31, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        with pytest.raises(AttributeError):
            meta.key_name = "changed"  # type: ignore[misc]

    def test_rotation_count_default_zero(self) -> None:
        created = datetime(2024, 1, 1, tzinfo=UTC)
        expires = datetime(2024, 12, 31, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            created_at=created,
            expires_at=expires,
        )
        assert meta.rotation_count == 0
        assert meta.last_rotated_at is None


class TestRotationPolicy:
    def test_valid_policy(self) -> None:
        policy = RotationPolicy(
            secret_type=SecretType.API_KEY,
            rotation_interval=timedelta(hours=24),
        )
        assert policy.rotation_interval == timedelta(hours=24)
        assert policy.max_rotation_attempts == 3
        assert policy.require_acknowledgment is True

    def test_zero_rotation_interval_raises(self) -> None:
        with pytest.raises(ConfigError, match="rotation_interval must be positive"):
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(0),
            )

    def test_negative_rotation_interval_raises(self) -> None:
        with pytest.raises(ConfigError, match="rotation_interval must be positive"):
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(seconds=-1),
            )

    def test_zero_max_rotation_attempts_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_rotation_attempts must be positive"):
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
                max_rotation_attempts=0,
            )

    def test_custom_warning_before_expiry(self) -> None:
        policy = RotationPolicy(
            secret_type=SecretType.API_KEY,
            rotation_interval=timedelta(hours=24),
            warning_before_expiry=timedelta(hours=2),
        )
        assert policy.warning_before_expiry == timedelta(hours=2)

    def test_no_acknowledgment(self) -> None:
        policy = RotationPolicy(
            secret_type=SecretType.API_KEY,
            rotation_interval=timedelta(hours=24),
            require_acknowledgment=False,
        )
        assert policy.require_acknowledgment is False


class TestRotationEvent:
    def test_fields(self) -> None:
        now = datetime(2024, 6, 15, tzinfo=UTC)
        event = RotationEvent(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            status=RotationStatus.COMPLETED,
            timestamp=now,
            previous_hash="abc123",
            new_hash="def456",
        )
        assert event.status == RotationStatus.COMPLETED
        assert event.error_message is None

    def test_with_error_message(self) -> None:
        now = datetime(2024, 6, 15, tzinfo=UTC)
        event = RotationEvent(
            secret_type=SecretType.API_KEY,
            key_name="test_key",
            status=RotationStatus.FAILED,
            timestamp=now,
            previous_hash="abc123",
            new_hash="def456",
            error_message="rotation failed",
        )
        assert event.error_message == "rotation failed"


class TestValidateUTC:
    def test_utc_passes(self) -> None:
        _validate_utc(datetime(2024, 6, 15, tzinfo=UTC))

    def test_naive_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            _validate_utc(datetime(2024, 6, 15))

    def test_non_utc_tz_raises(self) -> None:
        from datetime import timezone

        ist = timezone(timedelta(hours=5, minutes=30))
        with pytest.raises(ConfigError, match="UTC"):
            _validate_utc(datetime(2024, 6, 15, tzinfo=ist))


class TestHashValue:
    def test_deterministic(self) -> None:
        h1 = _hash_value("test_value")
        h2 = _hash_value("test_value")
        assert h1 == h2

    def test_different_values_different_hashes(self) -> None:
        h1 = _hash_value("value1")
        h2 = _hash_value("value2")
        assert h1 != h2

    def test_hash_length(self) -> None:
        h = _hash_value("test")
        assert len(h) == 16


class TestSetEnvSecret:
    def test_sets_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_env_secret("TEST_SECRET_KEY_2024", "secret_val")
        import os

        assert os.environ.get("TEST_SECRET_KEY_2024") == "secret_val"
        monkeypatch.delenv("TEST_SECRET_KEY_2024", raising=False)


class TestSecretsRotationManagerRegisterPolicy:
    def test_register_policy_stores_policy(self) -> None:
        mgr = SecretsRotationManager()
        policy = RotationPolicy(
            secret_type=SecretType.API_KEY,
            rotation_interval=timedelta(hours=24),
        )
        mgr.register_policy(policy)
        assert mgr._policies[SecretType.API_KEY] is policy

    def test_register_policy_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        mgr = SecretsRotationManager()
        policy = RotationPolicy(
            secret_type=SecretType.HMAC_KEY,
            rotation_interval=timedelta(hours=48),
        )
        with caplog.at_level(logging.INFO):
            mgr.register_policy(policy)
        assert any("Rotation policy registered" in r.message for r in caplog.records)

    def test_register_policy_overwrites_existing(self) -> None:
        mgr = SecretsRotationManager()
        p1 = RotationPolicy(
            secret_type=SecretType.API_KEY,
            rotation_interval=timedelta(hours=24),
        )
        p2 = RotationPolicy(
            secret_type=SecretType.API_KEY,
            rotation_interval=timedelta(hours=12),
        )
        mgr.register_policy(p1)
        mgr.register_policy(p2)
        assert mgr._policies[SecretType.API_KEY].rotation_interval == timedelta(
            hours=12
        )


class TestSecretsRotationManagerRegisterSecret:
    def _make_manager(self) -> SecretsRotationManager:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        return mgr

    def test_register_secret_returns_metadata(self) -> None:
        mgr = self._make_manager()
        now = datetime(2024, 6, 15, tzinfo=UTC)
        meta = mgr.register_secret(SecretType.API_KEY, "my_api_key", now)
        assert meta.secret_type == SecretType.API_KEY
        assert meta.key_name == "my_api_key"
        assert meta.created_at == now
        assert meta.expires_at == now + timedelta(hours=24)
        assert meta.rotation_count == 0

    def test_register_secret_stores_in_metadata(self) -> None:
        mgr = self._make_manager()
        now = datetime(2024, 6, 15, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "my_api_key", now)
        assert "my_api_key" in mgr._metadata

    def test_register_secret_no_policy_raises(self) -> None:
        mgr = SecretsRotationManager()
        now = datetime(2024, 6, 15, tzinfo=UTC)
        with pytest.raises(ConfigError, match="No rotation policy registered"):
            mgr.register_secret(SecretType.API_KEY, "my_key", now)

    def test_register_secret_naive_datetime_raises(self) -> None:
        mgr = self._make_manager()
        with pytest.raises(ConfigError, match="UTC"):
            mgr.register_secret(SecretType.API_KEY, "my_key", datetime(2024, 6, 15))

    def test_register_secret_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        mgr = self._make_manager()
        now = datetime(2024, 6, 15, tzinfo=UTC)
        with caplog.at_level(logging.INFO):
            mgr.register_secret(SecretType.API_KEY, "my_api_key", now)
        assert any(
            "Secret registered for rotation" in r.message for r in caplog.records
        )


class TestSecretsRotationManagerCheckRotationNeeded:
    def _make_manager_with_secret(
        self,
        interval: timedelta = timedelta(hours=24),
        warning: timedelta = timedelta(hours=1),
    ) -> tuple[SecretsRotationManager, datetime]:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=interval,
                warning_before_expiry=warning,
            )
        )
        now = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "my_key", now)
        return mgr, now

    def test_no_rotation_needed_when_far_from_expiry(self) -> None:
        mgr, created = self._make_manager_with_secret()
        check_time = created + timedelta(hours=22)
        needed = mgr.check_rotation_needed(check_time)
        assert needed == []

    def test_rotation_needed_within_warning_window(self) -> None:
        mgr, created = self._make_manager_with_secret(
            interval=timedelta(hours=24),
            warning=timedelta(hours=2),
        )
        check_time = created + timedelta(hours=23)
        needed = mgr.check_rotation_needed(check_time)
        assert len(needed) == 1
        assert needed[0].key_name == "my_key"

    def test_rotation_needed_at_exact_warning_time(self) -> None:
        mgr, created = self._make_manager_with_secret(
            interval=timedelta(hours=24),
            warning=timedelta(hours=1),
        )
        warning_time = created + timedelta(hours=23)
        needed = mgr.check_rotation_needed(warning_time)
        assert len(needed) == 1

    def test_rotation_needed_just_before_warning_time(self) -> None:
        mgr, created = self._make_manager_with_secret(
            interval=timedelta(hours=24),
            warning=timedelta(hours=1),
        )
        just_before = created + timedelta(hours=22, minutes=59, seconds=59)
        needed = mgr.check_rotation_needed(just_before)
        assert needed == []

    def test_check_rotation_needed_naive_datetime_raises(self) -> None:
        mgr, _ = self._make_manager_with_secret()
        with pytest.raises(ConfigError, match="UTC"):
            mgr.check_rotation_needed(datetime(2024, 6, 15))

    def test_multiple_secrets_only_ones_near_expiry(self) -> None:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
                warning_before_expiry=timedelta(hours=2),
            )
        )
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.HMAC_KEY,
                rotation_interval=timedelta(hours=48),
                warning_before_expiry=timedelta(hours=2),
            )
        )
        now = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "short_lived", now)
        mgr.register_secret(SecretType.HMAC_KEY, "long_lived", now)
        check_time = now + timedelta(hours=23)
        needed = mgr.check_rotation_needed(check_time)
        keys = {m.key_name for m in needed}
        assert "short_lived" in keys
        assert "long_lived" not in keys

    def test_check_rotation_needed_skips_missing_policy(self) -> None:
        mgr = SecretsRotationManager()
        now = datetime(2024, 6, 15, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type="orphan_type",
            key_name="orphan_key",
            created_at=now,
            expires_at=now + timedelta(seconds=1),
        )
        mgr._metadata["orphan_key"] = meta
        needed = mgr.check_rotation_needed(now)
        assert needed == []


class TestSecretsRotationManagerRotateSecret:
    def _make_manager_with_secret(
        self,
    ) -> tuple[SecretsRotationManager, datetime]:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        now = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "my_key", now)
        return mgr, now

    def test_rotate_secret_returns_new_metadata(self) -> None:
        mgr, _ = self._make_manager_with_secret()
        rotate_time = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        new_meta = mgr.rotate_secret("my_key", "new_secret_value", rotate_time)
        assert new_meta.rotation_count == 1
        assert new_meta.last_rotated_at == rotate_time
        assert new_meta.created_at == rotate_time
        assert new_meta.expires_at == rotate_time + timedelta(hours=24)

    def test_rotate_secret_updates_metadata(self) -> None:
        mgr, _ = self._make_manager_with_secret()
        rotate_time = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        mgr.rotate_secret("my_key", "new_value", rotate_time)
        status = mgr.get_secret_status("my_key")
        assert status is not None
        assert status.rotation_count == 1

    def test_rotate_secret_records_history(self) -> None:
        mgr, _ = self._make_manager_with_secret()
        rotate_time = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        mgr.rotate_secret("my_key", "new_value", rotate_time)
        history = mgr.get_rotation_history("my_key")
        assert len(history) == 1
        assert history[0].status == RotationStatus.COMPLETED
        assert history[0].key_name == "my_key"

    def test_rotate_secret_sets_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mgr, _ = self._make_manager_with_secret()
        rotate_time = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        mgr.rotate_secret("my_key", "rotated_env_val", rotate_time)  # noqa: SIM112
        import os

        try:
            assert os.environ.get("my_key") == "rotated_env_val"  # noqa: SIM112
        finally:
            monkeypatch.delenv("my_key", raising=False)

    def test_rotate_secret_unregistered_key_raises(self) -> None:
        mgr = SecretsRotationManager()
        now = datetime(2024, 6, 15, tzinfo=UTC)
        with pytest.raises(ConfigError, match="Secret not registered"):
            mgr.rotate_secret("unknown_key", "val", now)

    def test_rotate_secret_naive_datetime_raises(self) -> None:
        mgr, _ = self._make_manager_with_secret()
        with pytest.raises(ConfigError, match="UTC"):
            mgr.rotate_secret("my_key", "val", datetime(2024, 6, 15))

    def test_rotate_secret_missing_policy_raises(self) -> None:
        mgr = SecretsRotationManager()
        now = datetime(2024, 6, 15, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type="orphan_type",
            key_name="orphan_key",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        mgr._metadata["orphan_key"] = meta
        with pytest.raises(ConfigError, match="No policy for secret type"):
            mgr.rotate_secret("orphan_key", "val", now)

    def test_rotate_secret_increments_rotation_count(self) -> None:
        mgr, _ = self._make_manager_with_secret()
        t1 = datetime(2024, 6, 15, 8, 0, tzinfo=UTC)
        t2 = datetime(2024, 6, 15, 16, 0, tzinfo=UTC)
        mgr.rotate_secret("my_key", "val1", t1)
        mgr.rotate_secret("my_key", "val2", t2)
        status = mgr.get_secret_status("my_key")
        assert status is not None
        assert status.rotation_count == 2

    def test_rotate_secret_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        mgr, _ = self._make_manager_with_secret()
        rotate_time = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        with caplog.at_level(logging.INFO):
            mgr.rotate_secret("my_key", "new_val", rotate_time)
        assert any("Secret rotated" in r.message for r in caplog.records)


class TestSecretsRotationManagerGetHistory:
    def _make_manager_with_history(
        self,
    ) -> tuple[SecretsRotationManager, datetime]:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.HMAC_KEY,
                rotation_interval=timedelta(hours=48),
            )
        )
        now = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "key_a", now)
        mgr.register_secret(SecretType.HMAC_KEY, "key_b", now)
        mgr.rotate_secret("key_a", "val1", now + timedelta(hours=8))
        mgr.rotate_secret("key_b", "val2", now + timedelta(hours=10))
        return mgr, now

    def test_get_all_history(self) -> None:
        mgr, _ = self._make_manager_with_history()
        history = mgr.get_rotation_history()
        assert len(history) == 2

    def test_get_history_filtered_by_key(self) -> None:
        mgr, _ = self._make_manager_with_history()
        history = mgr.get_rotation_history("key_a")
        assert len(history) == 1
        assert history[0].key_name == "key_a"

    def test_get_history_no_match_returns_empty(self) -> None:
        mgr, _ = self._make_manager_with_history()
        history = mgr.get_rotation_history("nonexistent")
        assert history == []

    def test_get_history_returns_copy(self) -> None:
        mgr, _ = self._make_manager_with_history()
        h1 = mgr.get_rotation_history()
        h2 = mgr.get_rotation_history()
        assert h1 is not h2


class TestSecretsRotationManagerGetStatus:
    def test_get_secret_status_found(self) -> None:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        now = datetime(2024, 6, 15, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "my_key", now)
        status = mgr.get_secret_status("my_key")
        assert status is not None
        assert status.key_name == "my_key"

    def test_get_secret_status_not_found(self) -> None:
        mgr = SecretsRotationManager()
        assert mgr.get_secret_status("missing") is None

    def test_get_all_secrets_status(self) -> None:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        now = datetime(2024, 6, 15, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "key1", now)
        mgr.register_secret(SecretType.API_KEY, "key2", now)
        all_statuses = mgr.get_all_secrets_status()
        assert len(all_statuses) == 2

    def test_get_all_secrets_status_empty(self) -> None:
        mgr = SecretsRotationManager()
        assert mgr.get_all_secrets_status() == []


class TestSecretsRotationManagerIsValid:
    def test_is_valid_not_expired(self) -> None:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        now = datetime(2024, 6, 15, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "my_key", now)
        assert mgr.is_secret_valid("my_key", now + timedelta(hours=1)) is True

    def test_is_valid_expired(self) -> None:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        now = datetime(2024, 6, 15, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "my_key", now)
        assert mgr.is_secret_valid("my_key", now + timedelta(hours=25)) is False

    def test_is_valid_unknown_key(self) -> None:
        mgr = SecretsRotationManager()
        assert mgr.is_secret_valid("unknown_key") is False

    def test_is_valid_without_now_uses_current(self) -> None:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        created = datetime(2020, 1, 1, tzinfo=UTC)
        meta = SecretMetadata(
            secret_type=SecretType.API_KEY,
            key_name="old_key",
            created_at=created,
            expires_at=created + timedelta(hours=1),
        )
        mgr._metadata["old_key"] = meta
        assert mgr.is_secret_valid("old_key") is False


class TestSecretsRotationManagerScheduleRotation:
    def _make_manager_with_secret(
        self,
    ) -> tuple[SecretsRotationManager, datetime]:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        now = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "my_key", now)
        return mgr, now

    def test_schedule_rotation_stores_pending(self) -> None:
        mgr, _ = self._make_manager_with_secret()
        rotate_at = datetime(2024, 6, 16, 0, 0, tzinfo=UTC)
        mgr.schedule_rotation("my_key", rotate_at)
        assert "my_key" in mgr._pending_rotations
        assert mgr._pending_rotations["my_key"] == rotate_at

    def test_schedule_rotation_unregistered_key_raises(self) -> None:
        mgr = SecretsRotationManager()
        rotate_at = datetime(2024, 6, 16, 0, 0, tzinfo=UTC)
        with pytest.raises(ConfigError, match="Secret not registered"):
            mgr.schedule_rotation("unknown_key", rotate_at)

    def test_schedule_rotation_naive_datetime_raises(self) -> None:
        mgr, _ = self._make_manager_with_secret()
        with pytest.raises(ConfigError, match="UTC"):
            mgr.schedule_rotation("my_key", datetime(2024, 6, 16))


class TestSecretsRotationManagerProcessScheduled:
    def _make_manager_with_secret(
        self,
    ) -> tuple[SecretsRotationManager, datetime]:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        now = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "my_key", now)
        return mgr, now

    def test_process_returns_due_keys(self) -> None:
        mgr, now = self._make_manager_with_secret()
        rotate_at = now + timedelta(hours=6)
        mgr.schedule_rotation("my_key", rotate_at)
        due = mgr.process_scheduled_rotations(rotate_at)
        assert due == ["my_key"]

    def test_process_removes_pending_after_due(self) -> None:
        mgr, now = self._make_manager_with_secret()
        rotate_at = now + timedelta(hours=6)
        mgr.schedule_rotation("my_key", rotate_at)
        mgr.process_scheduled_rotations(rotate_at + timedelta(seconds=1))
        assert "my_key" not in mgr._pending_rotations

    def test_process_not_due_returns_empty(self) -> None:
        mgr, now = self._make_manager_with_secret()
        rotate_at = now + timedelta(hours=6)
        mgr.schedule_rotation("my_key", rotate_at)
        due = mgr.process_scheduled_rotations(now + timedelta(hours=3))
        assert due == []

    def test_process_scheduled_naive_datetime_raises(self) -> None:
        mgr, _ = self._make_manager_with_secret()
        with pytest.raises(ConfigError, match="UTC"):
            mgr.process_scheduled_rotations(datetime(2024, 6, 15))

    def test_process_multiple_scheduled_rotations(self) -> None:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        now = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "key1", now)
        mgr.register_secret(SecretType.API_KEY, "key2", now)
        mgr.schedule_rotation("key1", now + timedelta(hours=6))
        mgr.schedule_rotation("key2", now + timedelta(hours=12))
        due = mgr.process_scheduled_rotations(now + timedelta(hours=12))
        assert set(due) == {"key1", "key2"}

    def test_process_partial_scheduled_rotations(self) -> None:
        mgr = SecretsRotationManager()
        mgr.register_policy(
            RotationPolicy(
                secret_type=SecretType.API_KEY,
                rotation_interval=timedelta(hours=24),
            )
        )
        now = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
        mgr.register_secret(SecretType.API_KEY, "key1", now)
        mgr.register_secret(SecretType.API_KEY, "key2", now)
        mgr.schedule_rotation("key1", now + timedelta(hours=6))
        mgr.schedule_rotation("key2", now + timedelta(hours=12))
        due = mgr.process_scheduled_rotations(now + timedelta(hours=7))
        assert due == ["key1"]
        assert "key2" in mgr._pending_rotations
