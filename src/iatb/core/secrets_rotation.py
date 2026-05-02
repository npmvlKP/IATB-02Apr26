"""
Secrets Rotation Manager.

Provides automated secrets rotation with configurable policies,
rotation scheduling, and integration support for external vaults.
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from iatb.core.exceptions import ConfigError

_LOGGER = logging.getLogger(__name__)


class SecretType:
    """Types of secrets managed by the rotation system."""

    API_KEY = "api_key"  # noqa: S105  # nosec B105
    API_SECRET = "api_secret"  # noqa: S105  # nosec B105
    ACCESS_TOKEN = "access_token"  # noqa: S105  # nosec B105
    REFRESH_TOKEN = "refresh_token"  # noqa: S105  # nosec B105
    HMAC_KEY = "hmac_key"  # noqa: S105
    DATABASE_KEY = "database_key"


class RotationStatus:
    """Status of a secret rotation."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SecretMetadata:
    """Metadata for a managed secret."""

    secret_type: str
    key_name: str
    created_at: datetime
    expires_at: datetime
    rotation_count: int = 0
    last_rotated_at: datetime | None = None

    def is_expired(self, now_utc: datetime | None = None) -> bool:
        """Check if secret has expired.

        Args:
            now_utc: Optional UTC datetime for calculation.
                     If None, uses current UTC time.
        """
        now = now_utc if now_utc is not None else datetime.now(UTC)
        return now >= self.expires_at

    @property
    def time_until_expiry(self) -> timedelta:
        """Time remaining until expiry."""
        now = datetime.now(UTC)
        remaining = self.expires_at - now
        return remaining if remaining.total_seconds() > 0 else timedelta(0)

    def get_usage_ratio(self, now_utc: datetime | None = None) -> Decimal:
        """Ratio of lifetime used (0.0 to 1.0).

        Args:
            now_utc: Optional UTC datetime for calculation.
                     If None, uses current UTC time.
        """
        total = (self.expires_at - self.created_at).total_seconds()
        if total <= 0:
            return Decimal("1.0")
        now = now_utc if now_utc is not None else datetime.now(UTC)
        elapsed = (now - self.created_at).total_seconds()
        ratio = Decimal(str(elapsed)) / Decimal(str(total))
        return min(ratio, Decimal("1.0"))


@dataclass(frozen=True)
class RotationPolicy:
    """Policy defining how and when a secret should be rotated."""

    secret_type: str
    rotation_interval: timedelta
    warning_before_expiry: timedelta = timedelta(hours=1)
    max_rotation_attempts: int = 3
    require_acknowledgment: bool = True

    def __post_init__(self) -> None:
        if self.rotation_interval.total_seconds() <= 0:
            msg = "rotation_interval must be positive"
            raise ConfigError(msg)
        if self.max_rotation_attempts <= 0:
            msg = "max_rotation_attempts must be positive"
            raise ConfigError(msg)


@dataclass
class RotationEvent:
    """Record of a rotation event."""

    secret_type: str
    key_name: str
    status: str
    timestamp: datetime
    previous_hash: str
    new_hash: str
    error_message: str | None = None


class SecretsRotationManager:
    """Manages automated secrets rotation with configurable policies."""

    def __init__(self) -> None:
        self._policies: dict[str, RotationPolicy] = {}
        self._metadata: dict[str, SecretMetadata] = {}
        self._rotation_history: list[RotationEvent] = []
        self._pending_rotations: dict[str, datetime] = {}

    def register_policy(self, policy: RotationPolicy) -> None:
        """Register a rotation policy for a secret type."""
        self._policies[policy.secret_type] = policy
        _LOGGER.info(
            "Rotation policy registered",
            extra={
                "secret_type": policy.secret_type,
                "interval_hours": policy.rotation_interval.total_seconds() / 3600,
            },
        )

    def register_secret(
        self,
        secret_type: str,
        key_name: str,
        now_utc: datetime,
    ) -> SecretMetadata:
        """Register a new secret for rotation tracking."""
        _validate_utc(now_utc)
        policy = self._policies.get(secret_type)
        if policy is None:
            msg = f"No rotation policy registered for secret type: {secret_type}"
            raise ConfigError(msg)
        metadata = SecretMetadata(
            secret_type=secret_type,
            key_name=key_name,
            created_at=now_utc,
            expires_at=now_utc + policy.rotation_interval,
        )
        self._metadata[key_name] = metadata
        _LOGGER.info(
            "Secret registered for rotation",
            extra={"key_name": key_name, "secret_type": secret_type},
        )
        return metadata

    def check_rotation_needed(self, now_utc: datetime) -> list[SecretMetadata]:
        """Check which secrets need rotation."""
        _validate_utc(now_utc)
        needed: list[SecretMetadata] = []
        for meta in self._metadata.values():
            policy = self._policies.get(meta.secret_type)
            if policy is None:
                continue
            warning_time = meta.expires_at - policy.warning_before_expiry
            if now_utc >= warning_time:
                needed.append(meta)
        return needed

    def rotate_secret(
        self,
        key_name: str,
        new_value: str,
        now_utc: datetime,
    ) -> SecretMetadata:
        """Rotate a secret with the new value."""
        _validate_utc(now_utc)
        old_meta = self._metadata.get(key_name)
        if old_meta is None:
            msg = f"Secret not registered: {key_name}"
            raise ConfigError(msg)
        policy = self._policies.get(old_meta.secret_type)
        if policy is None:
            msg = f"No policy for secret type: {old_meta.secret_type}"
            raise ConfigError(msg)
        old_hash = _hash_value(old_meta.key_name)
        new_hash = _hash_value(new_value)
        event = RotationEvent(
            secret_type=old_meta.secret_type,
            key_name=key_name,
            status=RotationStatus.COMPLETED,
            timestamp=now_utc,
            previous_hash=old_hash,
            new_hash=new_hash,
        )
        self._rotation_history.append(event)
        new_meta = SecretMetadata(
            secret_type=old_meta.secret_type,
            key_name=key_name,
            created_at=now_utc,
            expires_at=now_utc + policy.rotation_interval,
            rotation_count=old_meta.rotation_count + 1,
            last_rotated_at=now_utc,
        )
        self._metadata[key_name] = new_meta
        _set_env_secret(key_name, new_value)
        _LOGGER.info(
            "Secret rotated",
            extra={
                "key_name": key_name,
                "rotation_count": new_meta.rotation_count,
            },
        )
        return new_meta

    def get_rotation_history(self, key_name: str | None = None) -> list[RotationEvent]:
        """Get rotation events, optionally filtered by key name."""
        if key_name is None:
            return list(self._rotation_history)
        return [e for e in self._rotation_history if e.key_name == key_name]

    def get_secret_status(self, key_name: str) -> SecretMetadata | None:
        """Get current status of a managed secret."""
        return self._metadata.get(key_name)

    def get_all_secrets_status(self) -> list[SecretMetadata]:
        """Get status of all managed secrets."""
        return list(self._metadata.values())

    def is_secret_valid(self, key_name: str) -> bool:
        """Check if a secret is valid (not expired)."""
        meta = self._metadata.get(key_name)
        if meta is None:
            return False
        return not meta.is_expired()

    def schedule_rotation(self, key_name: str, rotate_at: datetime) -> None:
        """Schedule a rotation for a specific time."""
        _validate_utc(rotate_at)
        if key_name not in self._metadata:
            msg = f"Secret not registered: {key_name}"
            raise ConfigError(msg)
        self._pending_rotations[key_name] = rotate_at

    def process_scheduled_rotations(self, now_utc: datetime) -> list[str]:
        """Process all scheduled rotations that are due."""
        _validate_utc(now_utc)
        due: list[str] = []
        for key_name, rotate_at in list(self._pending_rotations.items()):
            if now_utc >= rotate_at:
                due.append(key_name)
                del self._pending_rotations[key_name]
        return due


def _hash_value(value: str) -> str:
    """Create SHA-256 hash of a secret value for tracking."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _set_env_secret(key_name: str, value: str) -> None:
    """Set a secret value as an environment variable."""
    os.environ[key_name] = value


def _validate_utc(dt: datetime) -> None:
    """Validate datetime is UTC-aware."""
    if dt.tzinfo != UTC:
        msg = "datetime must be UTC-aware"
        raise ConfigError(msg)
