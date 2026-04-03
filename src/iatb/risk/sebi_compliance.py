"""
SEBI compliance utilities for execution controls and audit guarantees.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path

from iatb.core.clock import Clock
from iatb.core.exceptions import ConfigError
from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord


@dataclass(frozen=True)
class SEBIComplianceConfig:
    algo_id: str
    audit_db_path: Path
    static_ips: tuple[str, ...]
    auto_logout_ist: time = time(3, 0)


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
        self._store.append_trade(record)

    def is_static_ip_allowed(self, source_ip: str) -> bool:
        return source_ip in self._config.static_ips

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
