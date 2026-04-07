"""
SEBI compliance utilities for execution controls and audit guarantees.

Includes static IP validation for broker API access per SEBI guidelines.
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path

from iatb.core.clock import Clock
from iatb.core.exceptions import ConfigError
from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord

_LOGGER = logging.getLogger(__name__)

# IPv4 pattern for validation
_IPV4_PATTERN = re.compile(
    r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
)


@dataclass(frozen=True)
class SEBIComplianceConfig:
    algo_id: str
    audit_db_path: Path
    static_ips: tuple[str, ...]
    auto_logout_ist: time = time(3, 0)
    require_oauth_2fa: bool = True


class SEBIComplianceManager:
    """Validates live session requirements and persists compliance audit records."""

    def __init__(self, config: SEBIComplianceConfig) -> None:
        if not config.algo_id.strip():
            msg = "algo_id cannot be empty"
            raise ConfigError(msg)
        if not config.static_ips:
            msg = "static_ips cannot be empty"
            raise ConfigError(msg)
        self._config = config
        self._store = SQLiteStore(config.audit_db_path)

    def inject_algo_id(self, payload: dict[str, str]) -> dict[str, str]:
        if "algo_id" in payload and payload["algo_id"] != self._config.algo_id:
            msg = "payload contains mismatched algo_id"
            raise ConfigError(msg)
        merged = dict(payload)
        merged["algo_id"] = self._config.algo_id
        return merged

    def append_audit_record(self, record: TradeAuditRecord) -> None:
        self._assert_algo_id(record)
        self._store.append_trade(record)

    def is_static_ip_allowed(self, source_ip: str) -> bool:
        return source_ip in self._config.static_ips

    def assert_oauth_2fa_verified(
        self, oauth_authenticated: bool, two_factor_verified: bool
    ) -> None:
        if not self._config.require_oauth_2fa:
            return
        if oauth_authenticated and two_factor_verified:
            return
        msg = "OAuth 2FA verification is required before broker API access"
        raise ConfigError(msg)

    def should_auto_logout(self, now_utc: datetime) -> bool:
        if now_utc.tzinfo != UTC:
            msg = "now_utc must be timezone-aware UTC datetime"
            raise ConfigError(msg)
        now_ist = Clock.to_ist(now_utc).time()
        return now_ist >= self._config.auto_logout_ist

    def assert_live_session_allowed(self, source_ip: str, now_utc: datetime) -> None:
        if not self.is_static_ip_allowed(source_ip):
            msg = "source IP is not in configured static IP allow-list"
            raise ConfigError(msg)
        if self.should_auto_logout(now_utc):
            msg = "live session must be logged out after configured IST cutoff"
            raise ConfigError(msg)

    def _assert_algo_id(self, record: TradeAuditRecord) -> None:
        algo_id = record.metadata.get("algo_id", "").strip()
        if not algo_id:
            msg = "audit record metadata must include non-empty algo_id"
            raise ConfigError(msg)
        if algo_id != self._config.algo_id:
            msg = "audit record algo_id does not match configured algo_id"
            raise ConfigError(msg)


def validate_static_ip_format(ip_address: str) -> bool:
    """Validate that an IP address is a valid IPv4 format."""
    return bool(_IPV4_PATTERN.match(ip_address.strip()))


def validate_static_ips_config(static_ips: tuple[str, ...]) -> None:
    """Validate all configured static IPs have valid IPv4 format.

    Raises ConfigError if any IP is invalid.
    """
    invalid_ips: list[str] = []
    for ip_address in static_ips:
        if not validate_static_ip_format(ip_address):
            invalid_ips.append(ip_address)
    if invalid_ips:
        msg = f"invalid static IP addresses: {', '.join(invalid_ips)}"
        raise ConfigError(msg)
    _LOGGER.info(
        "Static IP validation passed",
        extra={"ip_count": len(static_ips), "timestamp_utc": datetime.now(UTC).isoformat()},
    )


def assert_static_ip_allowed(
    source_ip: str,
    allowed_ips: tuple[str, ...],
    *,
    broker: str = "zerodha",
) -> None:
    """Assert source IP is in allowed static IP list for broker API access.

    SEBI requires algo trading to originate from registered static IPs.
    """
    normalized_source = source_ip.strip()
    if not normalized_source:
        msg = "source IP address cannot be empty"
        raise ConfigError(msg)
    if not validate_static_ip_format(normalized_source):
        msg = f"source IP address has invalid format: {source_ip}"
        raise ConfigError(msg)
    if normalized_source not in allowed_ips:
        _LOGGER.warning(
            "Static IP validation failed",
            extra={
                "source_ip": normalized_source,
                "broker": broker,
                "timestamp_utc": datetime.now(UTC).isoformat(),
            },
        )
        msg = f"source IP {source_ip} not in allowed static IPs for {broker}"
        raise ConfigError(msg)
    _LOGGER.info(
        "Static IP validation passed",
        extra={"source_ip": normalized_source, "broker": broker},
    )
