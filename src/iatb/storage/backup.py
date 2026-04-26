"""
Automated backup and restore for SQLite, DuckDB, configuration, and trading state.
"""

import hashlib
import json
import logging
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from iatb.core.exceptions import ConfigError

_LOGGER = logging.getLogger(__name__)


def _require_positive_int(value: int, name: str) -> None:
    if value <= 0:
        msg = f"{name} must be positive, got {value}"
        raise ConfigError(msg)


def _require_non_empty(value: str, name: str) -> None:
    if not value.strip():
        msg = f"{name} cannot be empty"
        raise ConfigError(msg)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class BackupConfig:
    """Configuration for backup operations."""

    backup_root: Path
    retention_count: int = 24
    sqlite_db_paths: tuple[Path, ...] = ()
    duckdb_db_paths: tuple[Path, ...] = ()
    config_dirs: tuple[Path, ...] = ()
    state_export_path: Path | None = None

    def __post_init__(self) -> None:
        _require_positive_int(self.retention_count, "retention_count")


@dataclass(frozen=True)
class BackupManifest:
    """Manifest of a single backup snapshot."""

    backup_id: str
    timestamp_utc: str
    sqlite_files: tuple[dict[str, str], ...] = ()
    duckdb_files: tuple[dict[str, str], ...] = ()
    config_files: tuple[dict[str, str], ...] = ()
    state_file: dict[str, str] | None = None
    checksums: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BackupResult:
    """Result of a backup or restore operation."""

    success: bool
    backup_id: str
    timestamp_utc: str
    backup_dir: str
    files_backed_up: int = 0
    error_message: str = ""


class BackupManager:
    """Manages automated backup and restore of databases, configs, and state."""

    def __init__(self, config: BackupConfig) -> None:
        self._config = config

    def create_backup(self) -> BackupResult:
        """Create a full backup snapshot with manifest."""
        now = datetime.now(UTC)
        backup_id = now.strftime("backup_%Y%m%dT%H%M%S") + f"_{now.microsecond:06d}Z"
        backup_dir = self._config.backup_root / backup_id
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            manifest = self._build_manifest(backup_id, now, backup_dir)
            manifest_path = backup_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(self._manifest_to_dict(manifest), indent=2, default=str),
                encoding="utf-8",
            )
            self.cleanup_old_backups()
            return BackupResult(
                success=True,
                backup_id=backup_id,
                timestamp_utc=now.isoformat(),
                backup_dir=str(backup_dir),
                files_backed_up=len(manifest.checksums),
            )
        except Exception as exc:
            _LOGGER.exception("Backup failed for %s", backup_id)
            return BackupResult(
                success=False,
                backup_id=backup_id,
                timestamp_utc=now.isoformat(),
                backup_dir=str(backup_dir),
                error_message=str(exc),
            )

    def restore_backup(self, backup_id: str) -> BackupResult:
        """Restore from a backup snapshot with integrity validation."""
        backup_dir = self._config.backup_root / backup_id
        manifest_path = backup_dir / "manifest.json"
        if not manifest_path.exists():
            msg = f"Backup manifest not found: {manifest_path}"
            raise ConfigError(msg)
        manifest = self._load_manifest(manifest_path)
        self._validate_checksums(manifest, backup_dir)
        now = datetime.now(UTC)
        try:
            self._restore_sqlite(manifest, backup_dir)
            self._restore_duckdb(manifest, backup_dir)
            self._restore_configs(manifest, backup_dir)
            self._restore_state(manifest, backup_dir)
            _LOGGER.info("Restored backup %s successfully", backup_id)
            return BackupResult(
                success=True,
                backup_id=backup_id,
                timestamp_utc=now.isoformat(),
                backup_dir=str(backup_dir),
                files_backed_up=len(manifest.checksums),
            )
        except Exception as exc:
            _LOGGER.exception("Restore failed for %s", backup_id)
            return BackupResult(
                success=False,
                backup_id=backup_id,
                timestamp_utc=now.isoformat(),
                backup_dir=str(backup_dir),
                error_message=str(exc),
            )

    def list_backups(self) -> list[dict[str, Any]]:
        """List all available backup snapshots."""
        backups: list[dict[str, Any]] = []
        if not self._config.backup_root.exists():
            return backups
        for entry in sorted(self._config.backup_root.iterdir(), reverse=True):
            if not entry.is_dir() or not (entry / "manifest.json").exists():
                continue
            manifest = self._load_manifest(entry / "manifest.json")
            backups.append(
                {
                    "backup_id": manifest.backup_id,
                    "timestamp_utc": manifest.timestamp_utc,
                    "files_count": len(manifest.checksums),
                }
            )
        return backups

    def cleanup_old_backups(self) -> int:
        """Remove oldest backups exceeding retention count."""
        if not self._config.backup_root.exists():
            return 0
        entries = sorted(
            [e for e in self._config.backup_root.iterdir() if e.is_dir()],
            reverse=True,
        )
        removed = 0
        for entry in entries[self._config.retention_count :]:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
            _LOGGER.info("Removed old backup: %s", entry.name)
        return removed

    def _build_manifest(self, backup_id: str, now: datetime, backup_dir: Path) -> BackupManifest:
        checksums: dict[str, str] = {}
        sqlite_files = self._backup_sqlite(backup_dir, checksums)
        duckdb_files = self._backup_duckdb(backup_dir, checksums)
        config_files = self._backup_configs(backup_dir, checksums)
        state_file = self._export_state(backup_dir, checksums)
        return BackupManifest(
            backup_id=backup_id,
            timestamp_utc=now.isoformat(),
            sqlite_files=tuple(sqlite_files),
            duckdb_files=tuple(duckdb_files),
            config_files=tuple(config_files),
            state_file=state_file,
            checksums=checksums,
        )

    def _backup_sqlite(self, backup_dir: Path, checksums: dict[str, str]) -> list[dict[str, str]]:
        files: list[dict[str, str]] = []
        for src in self._config.sqlite_db_paths:
            if not src.exists():
                _LOGGER.warning("SQLite DB not found, skipping: %s", src)
                continue
            dest = backup_dir / f"sqlite_{src.name}"
            self._sqlite_online_backup(src, dest)
            checksums[dest.name] = _file_sha256(dest)
            files.append({"source": str(src), "dest": dest.name})
        return files

    @staticmethod
    def _sqlite_online_backup(src: Path, dest: Path) -> None:
        src_conn = sqlite3.connect(str(src))
        try:
            dest_conn = sqlite3.connect(str(dest))
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            src_conn.close()

    def _backup_duckdb(self, backup_dir: Path, checksums: dict[str, str]) -> list[dict[str, str]]:
        files: list[dict[str, str]] = []
        for src in self._config.duckdb_db_paths:
            if not src.exists():
                _LOGGER.warning("DuckDB DB not found, skipping: %s", src)
                continue
            dest = backup_dir / f"duckdb_{src.name}"
            shutil.copy2(src, dest)
            checksums[dest.name] = _file_sha256(dest)
            files.append({"source": str(src), "dest": dest.name})
        return files

    def _backup_configs(self, backup_dir: Path, checksums: dict[str, str]) -> list[dict[str, str]]:
        files: list[dict[str, str]] = []
        config_subdir = backup_dir / "configs"
        config_subdir.mkdir(exist_ok=True)
        for cfg_dir in self._config.config_dirs:
            if not cfg_dir.exists():
                _LOGGER.warning("Config dir not found, skipping: %s", cfg_dir)
                continue
            for toml_file in cfg_dir.glob("*.toml"):
                dest = config_subdir / toml_file.name
                shutil.copy2(toml_file, dest)
                rel_key = f"configs/{dest.name}"
                checksums[rel_key] = _file_sha256(dest)
                files.append({"source": str(toml_file), "dest": rel_key})
        return files

    def _export_state(self, backup_dir: Path, checksums: dict[str, str]) -> dict[str, str] | None:
        src = self._config.state_export_path
        if src is None or not src.exists():
            _LOGGER.info("State export path not configured or missing, skipping")
            return None
        dest = backup_dir / "state_export.json"
        shutil.copy2(src, dest)
        checksums[dest.name] = _file_sha256(dest)
        return {"source": str(src), "dest": dest.name}

    def _validate_checksums(self, manifest: BackupManifest, backup_dir: Path) -> None:
        for rel_path, expected_hash in manifest.checksums.items():
            full_path = backup_dir / rel_path
            if not full_path.exists():
                msg = f"Backup file missing: {rel_path}"
                raise ConfigError(msg)
            actual_hash = _file_sha256(full_path)
            if actual_hash != expected_hash:
                msg = (
                    f"Checksum mismatch for {rel_path}: expected {expected_hash}, got {actual_hash}"
                )
                raise ConfigError(msg)

    def _restore_sqlite(self, manifest: BackupManifest, backup_dir: Path) -> None:
        for entry in manifest.sqlite_files:
            src = backup_dir / entry["dest"]
            dest = Path(entry["source"])
            if not src.exists():
                msg = f"SQLite backup file missing: {src}"
                raise ConfigError(msg)
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._sqlite_online_backup(src, dest)
            _LOGGER.info("Restored SQLite: %s -> %s", src, dest)

    def _restore_duckdb(self, manifest: BackupManifest, backup_dir: Path) -> None:
        for entry in manifest.duckdb_files:
            src = backup_dir / entry["dest"]
            dest = Path(entry["source"])
            if not src.exists():
                msg = f"DuckDB backup file missing: {src}"
                raise ConfigError(msg)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            _LOGGER.info("Restored DuckDB: %s -> %s", src, dest)

    def _restore_configs(self, manifest: BackupManifest, backup_dir: Path) -> None:
        for entry in manifest.config_files:
            src = backup_dir / entry["dest"]
            dest = Path(entry["source"])
            if not src.exists():
                msg = f"Config backup file missing: {src}"
                raise ConfigError(msg)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            _LOGGER.info("Restored config: %s -> %s", src, dest)

    def _restore_state(self, manifest: BackupManifest, backup_dir: Path) -> None:
        if manifest.state_file is None:
            return
        src = backup_dir / manifest.state_file["dest"]
        dest = Path(manifest.state_file["source"])
        if not src.exists():
            msg = f"State backup file missing: {src}"
            raise ConfigError(msg)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        _LOGGER.info("Restored state: %s -> %s", src, dest)

    @staticmethod
    def _manifest_to_dict(manifest: BackupManifest) -> dict[str, Any]:
        return {
            "backup_id": manifest.backup_id,
            "timestamp_utc": manifest.timestamp_utc,
            "sqlite_files": list(manifest.sqlite_files),
            "duckdb_files": list(manifest.duckdb_files),
            "config_files": list(manifest.config_files),
            "state_file": manifest.state_file,
            "checksums": manifest.checksums,
        }

    @staticmethod
    def _load_manifest(path: Path) -> BackupManifest:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            msg = f"Failed to read manifest: {path}"
            raise ConfigError(msg) from exc
        required_keys = {"backup_id", "timestamp_utc", "checksums"}
        missing = required_keys - set(data.keys())
        if missing:
            msg = f"Manifest missing required keys: {missing}"
            raise ConfigError(msg)
        return BackupManifest(
            backup_id=str(data["backup_id"]),
            timestamp_utc=str(data["timestamp_utc"]),
            sqlite_files=tuple(data.get("sqlite_files", [])),
            duckdb_files=tuple(data.get("duckdb_files", [])),
            config_files=tuple(data.get("config_files", [])),
            state_file=data.get("state_file"),
            checksums=dict(data["checksums"]),
        )


def export_trading_state(
    positions: dict[str, tuple[Decimal, Decimal]],
    pending_orders: dict[str, dict[str, Any]],
    output_path: Path,
) -> Path:
    """Export positions and pending orders to a JSON state file."""
    _require_non_empty(str(output_path), "output_path")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    state_data: dict[str, Any] = {
        "exported_at_utc": datetime.now(UTC).isoformat(),
        "positions": {
            symbol: {
                "quantity": str(qty),
                "avg_entry_price": str(price),
            }
            for symbol, (qty, price) in positions.items()
        },
        "pending_orders": {
            order_id: {
                **order_data,
                "quantity": str(order_data.get("quantity", Decimal("0"))),
                "price": str(order_data.get("price", Decimal("0"))),
            }
            for order_id, order_data in pending_orders.items()
        },
    }
    output_path.write_text(json.dumps(state_data, indent=2, default=str), encoding="utf-8")
    _LOGGER.info("Trading state exported to %s", output_path)
    return output_path


def load_trading_state(
    state_path: Path,
) -> tuple[dict[str, tuple[Decimal, Decimal]], dict[str, dict[str, Any]]]:
    """Load positions and pending orders from a JSON state file."""
    if not state_path.exists():
        msg = f"State file not found: {state_path}"
        raise ConfigError(msg)
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        msg = f"Failed to read state file: {state_path}"
        raise ConfigError(msg) from exc
    positions: dict[str, tuple[Decimal, Decimal]] = {}
    for symbol, pos_data in data.get("positions", {}).items():
        qty = Decimal(str(pos_data["quantity"]))
        price = Decimal(str(pos_data["avg_entry_price"]))
        positions[symbol] = (qty, price)
    pending_orders: dict[str, dict[str, Any]] = {}
    for order_id, order_data in data.get("pending_orders", {}).items():
        pending_orders[order_id] = order_data
    return positions, pending_orders
