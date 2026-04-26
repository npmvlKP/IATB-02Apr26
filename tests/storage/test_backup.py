"""
Tests for automated backup and restore module.
"""

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from iatb.core.exceptions import ConfigError
from iatb.storage.backup import (
    BackupConfig,
    BackupManager,
    BackupManifest,
    BackupResult,
    _file_sha256,
    _require_non_empty,
    _require_positive_int,
    export_trading_state,
    load_trading_state,
)


def _create_sqlite_db(path: Path) -> Path:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE trade_audit_log (trade_id TEXT PRIMARY KEY, data TEXT NOT NULL)")
    conn.execute("INSERT INTO trade_audit_log VALUES ('t1', 'test-data-1')")
    conn.commit()
    conn.close()
    return path


def _create_duckdb_file(path: Path) -> Path:
    path.write_text("duckdb-fixture-content", encoding="utf-8")
    return path


def _create_toml_file(path: Path, content: str = "key = 'value'") -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _make_config(
    tmp_path: Path,
    sqlite_paths: list[Path] | None = None,
    duckdb_paths: list[Path] | None = None,
    config_dirs: list[Path] | None = None,
    state_path: Path | None = None,
    retention: int = 24,
) -> BackupConfig:
    return BackupConfig(
        backup_root=tmp_path / "backups",
        retention_count=retention,
        sqlite_db_paths=tuple(sqlite_paths or []),
        duckdb_db_paths=tuple(duckdb_paths or []),
        config_dirs=tuple(config_dirs or []),
        state_export_path=state_path,
    )


class TestRequirePositiveInt:
    def test_positive_value(self) -> None:
        _require_positive_int(1, "test")

    def test_zero_raises(self) -> None:
        with pytest.raises(ConfigError, match="test must be positive"):
            _require_positive_int(0, "test")

    def test_negative_raises(self) -> None:
        with pytest.raises(ConfigError, match="test must be positive"):
            _require_positive_int(-1, "test")

    def test_large_positive(self) -> None:
        _require_positive_int(1000000, "test")


class TestRequireNonEmpty:
    def test_non_empty_value(self) -> None:
        _require_non_empty("hello", "field")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ConfigError, match="field cannot be empty"):
            _require_non_empty("", "field")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ConfigError, match="field cannot be empty"):
            _require_non_empty("   ", "field")


class TestFileSha256:
    def test_returns_hex_string(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world", encoding="utf-8")
        result = _file_sha256(test_file)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("same content", encoding="utf-8")
        f2.write_text("same content", encoding="utf-8")
        assert _file_sha256(f1) == _file_sha256(f2)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content a", encoding="utf-8")
        f2.write_text("content b", encoding="utf-8")
        assert _file_sha256(f1) != _file_sha256(f2)

    def test_empty_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "empty.txt"
        test_file.write_text("", encoding="utf-8")
        result = _file_sha256(test_file)
        assert isinstance(result, str)
        assert len(result) == 64


class TestBackupConfig:
    def test_rejects_non_positive_retention(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="retention_count must be positive"):
            BackupConfig(backup_root=tmp_path / "b", retention_count=0)

    def test_rejects_negative_retention(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="retention_count must be positive"):
            BackupConfig(backup_root=tmp_path / "b", retention_count=-1)

    def test_default_values(self, tmp_path: Path) -> None:
        config = BackupConfig(backup_root=tmp_path / "b")
        assert config.retention_count == 24
        assert config.sqlite_db_paths == ()
        assert config.duckdb_db_paths == ()
        assert config.config_dirs == ()
        assert config.state_export_path is None

    def test_frozen_dataclass(self, tmp_path: Path) -> None:
        config = BackupConfig(backup_root=tmp_path / "b")
        with pytest.raises(AttributeError):
            config.retention_count = 10  # type: ignore[misc]


class TestBackupManifest:
    def test_default_values(self) -> None:
        manifest = BackupManifest(
            backup_id="test",
            timestamp_utc="2025-01-01T00:00:00+00:00",
        )
        assert manifest.sqlite_files == ()
        assert manifest.duckdb_files == ()
        assert manifest.config_files == ()
        assert manifest.state_file is None
        assert manifest.checksums == {}

    def test_frozen_dataclass(self) -> None:
        manifest = BackupManifest(
            backup_id="test",
            timestamp_utc="2025-01-01T00:00:00+00:00",
        )
        with pytest.raises(AttributeError):
            manifest.backup_id = "modified"  # type: ignore[misc]


class TestBackupResult:
    def test_frozen_dataclass(self, tmp_path: Path) -> None:
        result = BackupResult(
            success=True,
            backup_id="test-1",
            timestamp_utc="2026-01-01T00:00:00+00:00",
            backup_dir=str(tmp_path / "backup"),
        )
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]

    def test_error_message_default_empty(self, tmp_path: Path) -> None:
        result = BackupResult(
            success=True,
            backup_id="test-1",
            timestamp_utc="2026-01-01T00:00:00+00:00",
            backup_dir=str(tmp_path / "backup"),
        )
        assert result.error_message == ""

    def test_failed_result(self, tmp_path: Path) -> None:
        result = BackupResult(
            success=False,
            backup_id="test-1",
            timestamp_utc="2026-01-01T00:00:00+00:00",
            backup_dir=str(tmp_path / "backup"),
            error_message="disk full",
        )
        assert result.success is False
        assert result.error_message == "disk full"


class TestBackupManagerCreateBackup:
    def test_sqlite_backup_creates_file(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        assert result.files_backed_up >= 1
        backup_dir = Path(result.backup_dir)
        assert (backup_dir / "manifest.json").exists()

    def test_duckdb_backup_creates_file(self, tmp_path: Path) -> None:
        db_path = _create_duckdb_file(tmp_path / "ohlcv.duckdb")
        config = _make_config(tmp_path, duckdb_paths=[db_path])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        assert result.files_backed_up >= 1

    def test_config_backup_copies_toml_files(self, tmp_path: Path) -> None:
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        _create_toml_file(cfg_dir / "settings.toml")
        _create_toml_file(cfg_dir / "exchanges.toml")
        config = _make_config(tmp_path, config_dirs=[cfg_dir])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        assert result.files_backed_up >= 2
        backup_dir = Path(result.backup_dir)
        assert (backup_dir / "configs" / "settings.toml").exists()
        assert (backup_dir / "configs" / "exchanges.toml").exists()

    def test_state_export_backup(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text('{"positions": {}}', encoding="utf-8")
        config = _make_config(tmp_path, state_path=state_path)
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        backup_dir = Path(result.backup_dir)
        assert (backup_dir / "state_export.json").exists()

    def test_skips_missing_sqlite_gracefully(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, sqlite_paths=[tmp_path / "nonexistent.sqlite3"])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True

    def test_skips_missing_duckdb_gracefully(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, duckdb_paths=[tmp_path / "nonexistent.duckdb"])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True

    def test_skips_missing_config_dir_gracefully(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, config_dirs=[tmp_path / "nonexistent_dir"])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True

    def test_skips_missing_state_path_gracefully(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, state_path=tmp_path / "nonexistent.json")
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True

    def test_full_backup_with_all_sources(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        duckdb_path = _create_duckdb_file(tmp_path / "ohlcv.duckdb")
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        _create_toml_file(cfg_dir / "settings.toml")
        state_path = tmp_path / "state.json"
        state_path.write_text('{"positions": {}}', encoding="utf-8")
        config = _make_config(
            tmp_path,
            sqlite_paths=[db_path],
            duckdb_paths=[duckdb_path],
            config_dirs=[cfg_dir],
            state_path=state_path,
        )
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        assert result.files_backed_up >= 4

    def test_backup_id_format(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.backup_id.startswith("backup_")
        assert result.backup_id.endswith("Z")

    def test_result_is_frozen(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path])
        manager = BackupManager(config)
        result = manager.create_backup()
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]

    def test_create_backup_failure_returns_error(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        manager = BackupManager(config)
        manager._build_manifest = lambda *a: (_ for _ in ()).throw(OSError("disk full"))  # type: ignore[assignment]
        result = manager.create_backup()
        assert result.success is False
        assert "disk full" in result.error_message

    def test_empty_backup(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        assert result.files_backed_up == 0

    def test_config_dir_with_non_toml_files(self, tmp_path: Path) -> None:
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        (cfg_dir / "readme.md").write_text("# readme", encoding="utf-8")
        _create_toml_file(cfg_dir / "settings.toml")
        config = _make_config(tmp_path, config_dirs=[cfg_dir])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        assert result.files_backed_up == 1

    def test_multiple_sqlite_databases(self, tmp_path: Path) -> None:
        db1 = _create_sqlite_db(tmp_path / "audit1.sqlite3")
        db2 = _create_sqlite_db(tmp_path / "audit2.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db1, db2])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        assert result.files_backed_up == 2

    def test_multiple_duckdb_files(self, tmp_path: Path) -> None:
        db1 = _create_duckdb_file(tmp_path / "ohlcv1.duckdb")
        db2 = _create_duckdb_file(tmp_path / "ohlcv2.duckdb")
        config = _make_config(tmp_path, duckdb_paths=[db1, db2])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        assert result.files_backed_up == 2


class TestBackupManagerRestore:
    def _create_backup_for_restore(self, tmp_path: Path) -> tuple[BackupManager, str, Path, Path]:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        _create_toml_file(cfg_dir / "settings.toml", "execution_mode = 'paper'")
        config = _make_config(
            tmp_path,
            sqlite_paths=[db_path],
            config_dirs=[cfg_dir],
        )
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        return manager, result.backup_id, db_path, cfg_dir

    def test_restore_sqlite_data_integrity(self, tmp_path: Path) -> None:
        manager, backup_id, db_path, _ = self._create_backup_for_restore(tmp_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM trade_audit_log WHERE trade_id = 't1'")
        conn.commit()
        conn.close()
        result = manager.restore_backup(backup_id)
        assert result.success is True
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT data FROM trade_audit_log WHERE trade_id = 't1'").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "test-data-1"

    def test_restore_config_files(self, tmp_path: Path) -> None:
        manager, backup_id, _, cfg_dir = self._create_backup_for_restore(tmp_path)
        (cfg_dir / "settings.toml").write_text("execution_mode = 'live'", encoding="utf-8")
        result = manager.restore_backup(backup_id)
        assert result.success is True
        content = (cfg_dir / "settings.toml").read_text(encoding="utf-8")
        assert "paper" in content

    def test_restore_missing_backup_raises(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        manager = BackupManager(config)
        with pytest.raises(ConfigError, match="manifest not found"):
            manager.restore_backup("backup_nonexistent")

    def test_restore_checksum_mismatch_raises(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        backup_dir = Path(result.backup_dir)
        sqlite_backup = list(backup_dir.glob("sqlite_*"))[0]
        sqlite_backup.write_text("corrupted", encoding="utf-8")
        with pytest.raises(ConfigError, match="Checksum mismatch"):
            manager.restore_backup(result.backup_id)

    def test_restore_missing_file_in_backup_raises(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        backup_dir = Path(result.backup_dir)
        sqlite_backup = list(backup_dir.glob("sqlite_*"))[0]
        sqlite_backup.unlink()
        with pytest.raises(ConfigError, match="Backup file missing"):
            manager.restore_backup(result.backup_id)

    def test_restore_duckdb(self, tmp_path: Path) -> None:
        duckdb_path = _create_duckdb_file(tmp_path / "ohlcv.duckdb")
        config = _make_config(tmp_path, duckdb_paths=[duckdb_path])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        duckdb_path.write_text("modified", encoding="utf-8")
        restore_result = manager.restore_backup(result.backup_id)
        assert restore_result.success is True
        assert duckdb_path.read_text(encoding="utf-8") == "duckdb-fixture-content"

    def test_restore_state(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        state_path.write_text('{"positions": {"X": {"qty": 10}}}', encoding="utf-8")
        config = _make_config(tmp_path, state_path=state_path)
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        state_path.write_text('{"positions": {}}', encoding="utf-8")
        restore_result = manager.restore_backup(result.backup_id)
        assert restore_result.success is True
        content = state_path.read_text(encoding="utf-8")
        assert "X" in content

    def test_restore_failure_returns_error_result(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        manifest_path = Path(result.backup_dir) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["sqlite_files"] = [{"source": str(db_path), "dest": "nonexistent_file.sqlite3"}]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        restore_result = manager.restore_backup(result.backup_id)
        assert restore_result.success is False
        assert "error_message" in restore_result.__dict__


class TestBackupManagerListBackups:
    def test_list_returns_empty_when_no_backups(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        manager = BackupManager(config)
        assert manager.list_backups() == []

    def test_list_returns_created_backups(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path])
        manager = BackupManager(config)
        manager.create_backup()
        manager.create_backup()
        backups = manager.list_backups()
        assert len(backups) == 2
        assert backups[0]["files_count"] >= 1

    def test_list_ignores_dirs_without_manifest(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        manager = BackupManager(config)
        (tmp_path / "backups" / "not_a_backup").mkdir(parents=True)
        assert manager.list_backups() == []

    def test_list_returns_sorted_newest_first(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path])
        manager = BackupManager(config)
        manager.create_backup()
        manager.create_backup()
        backups = manager.list_backups()
        assert backups[0]["backup_id"] > backups[1]["backup_id"]

    def test_list_backup_fields(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path])
        manager = BackupManager(config)
        result = manager.create_backup()
        backups = manager.list_backups()
        assert len(backups) == 1
        assert "backup_id" in backups[0]
        assert "timestamp_utc" in backups[0]
        assert "files_count" in backups[0]
        assert backups[0]["backup_id"] == result.backup_id


class TestBackupManagerCleanup:
    def test_cleanup_removes_oldest_backups(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path], retention=2)
        manager = BackupManager(config)
        for _ in range(3):
            manager.create_backup()
        assert len(manager.list_backups()) == 2

    def test_cleanup_returns_zero_when_under_retention(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path], retention=5)
        manager = BackupManager(config)
        manager.create_backup()
        removed = manager.cleanup_old_backups()
        assert removed == 0

    def test_cleanup_returns_zero_when_no_backup_root(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        manager = BackupManager(config)
        assert manager.cleanup_old_backups() == 0

    def test_cleanup_exact_retention_count(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path], retention=2)
        manager = BackupManager(config)
        manager.create_backup()
        manager.create_backup()
        removed = manager.cleanup_old_backups()
        assert removed == 0

    def test_cleanup_with_retention_one(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path], retention=1)
        manager = BackupManager(config)
        manager.create_backup()
        manager.create_backup()
        assert len(manager.list_backups()) == 1


class TestExportTradingState:
    def test_export_creates_json_file(self, tmp_path: Path) -> None:
        positions = {"RELIANCE": (Decimal("10"), Decimal("2500.50"))}
        orders: dict[str, dict[str, Any]] = {
            "ord-1": {"symbol": "RELIANCE", "quantity": Decimal("5")}
        }
        out = tmp_path / "state.json"
        result = export_trading_state(positions, orders, out)
        assert result == out
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "RELIANCE" in data["positions"]
        assert data["positions"]["RELIANCE"]["quantity"] == "10"
        assert "ord-1" in data["pending_orders"]

    def test_export_uses_decimal_strings_not_floats(self, tmp_path: Path) -> None:
        positions = {"TCS": (Decimal("3.141592653"), Decimal("4000.123456"))}
        orders: dict[str, dict[str, Any]] = {}
        out = tmp_path / "state.json"
        export_trading_state(positions, orders, out)
        content = out.read_text(encoding="utf-8")
        assert "3.141592653" in content
        assert "4000.123456" in content

    def test_export_includes_utc_timestamp(self, tmp_path: Path) -> None:
        positions: dict[str, tuple[Decimal, Decimal]] = {}
        orders: dict[str, dict[str, Any]] = {}
        out = tmp_path / "state.json"
        export_trading_state(positions, orders, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "exported_at_utc" in data
        assert data["exported_at_utc"].endswith("+00:00")

    def test_export_creates_parent_dirs(self, tmp_path: Path) -> None:
        out = tmp_path / "nested" / "dir" / "state.json"
        export_trading_state({}, {}, out)
        assert out.exists()

    def test_export_rejects_empty_path(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="cannot be empty"):
            export_trading_state({}, {}, Path("   "))

    def test_export_with_multiple_positions(self, tmp_path: Path) -> None:
        positions = {
            "RELIANCE": (Decimal("10"), Decimal("2500.50")),
            "TCS": (Decimal("5"), Decimal("3500.75")),
            "INFY": (Decimal("100"), Decimal("1500.25")),
        }
        orders: dict[str, dict[str, Any]] = {}
        out = tmp_path / "state.json"
        export_trading_state(positions, orders, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["positions"]) == 3

    def test_export_with_multiple_orders(self, tmp_path: Path) -> None:
        positions: dict[str, tuple[Decimal, Decimal]] = {}
        orders: dict[str, dict[str, Any]] = {
            "ord-1": {"symbol": "RELIANCE", "quantity": Decimal("5"), "price": Decimal("2500")},
            "ord-2": {"symbol": "TCS", "quantity": Decimal("10"), "price": Decimal("3500")},
        }
        out = tmp_path / "state.json"
        export_trading_state(positions, orders, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["pending_orders"]) == 2

    def test_export_order_decimal_conversion(self, tmp_path: Path) -> None:
        positions: dict[str, tuple[Decimal, Decimal]] = {}
        orders: dict[str, dict[str, Any]] = {
            "ord-1": {"symbol": "X", "quantity": Decimal("1.5"), "price": Decimal("99.99")},
        }
        out = tmp_path / "state.json"
        export_trading_state(positions, orders, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["pending_orders"]["ord-1"]["quantity"] == "1.5"
        assert data["pending_orders"]["ord-1"]["price"] == "99.99"

    def test_export_order_missing_quantity_defaults_zero(self, tmp_path: Path) -> None:
        positions: dict[str, tuple[Decimal, Decimal]] = {}
        orders: dict[str, dict[str, Any]] = {
            "ord-1": {"symbol": "X"},
        }
        out = tmp_path / "state.json"
        export_trading_state(positions, orders, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["pending_orders"]["ord-1"]["quantity"] == "0"


class TestLoadTradingState:
    def test_load_roundtrip(self, tmp_path: Path) -> None:
        positions = {"RELIANCE": (Decimal("10"), Decimal("2500.50"))}
        orders: dict[str, dict[str, Any]] = {"ord-1": {"symbol": "RELIANCE", "side": "BUY"}}
        out = tmp_path / "state.json"
        export_trading_state(positions, orders, out)
        loaded_pos, loaded_orders = load_trading_state(out)
        assert loaded_pos["RELIANCE"] == (Decimal("10"), Decimal("2500.50"))
        assert loaded_orders["ord-1"]["symbol"] == "RELIANCE"

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="State file not found"):
            load_trading_state(tmp_path / "nonexistent.json")

    def test_load_invalid_json_raises(self, tmp_path: Path) -> None:
        (tmp_path / "bad.json").write_text("not-json{{{", encoding="utf-8")
        with pytest.raises(ConfigError, match="Failed to read state file"):
            load_trading_state(tmp_path / "bad.json")

    def test_load_empty_positions(self, tmp_path: Path) -> None:
        out = tmp_path / "empty.json"
        export_trading_state({}, {}, out)
        pos, orders = load_trading_state(out)
        assert pos == {}
        assert orders == {}

    def test_load_preserves_decimal_precision(self, tmp_path: Path) -> None:
        positions = {"INFY": (Decimal("0.00000001"), Decimal("1500.987654321"))}
        out = tmp_path / "precise.json"
        export_trading_state(positions, {}, out)
        loaded_pos, _ = load_trading_state(out)
        qty, price = loaded_pos["INFY"]
        assert qty == Decimal("0.00000001")
        assert price == Decimal("1500.987654321")

    def test_load_missing_positions_key(self, tmp_path: Path) -> None:
        out = tmp_path / "no_positions.json"
        out.write_text('{"pending_orders": {}}', encoding="utf-8")
        pos, orders = load_trading_state(out)
        assert pos == {}

    def test_load_missing_pending_orders_key(self, tmp_path: Path) -> None:
        out = tmp_path / "no_orders.json"
        out.write_text('{"positions": {}}', encoding="utf-8")
        pos, orders = load_trading_state(out)
        assert orders == {}

    def test_load_file_read_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="State file not found"):
            load_trading_state(tmp_path / "nonexistent.json")


class TestManifestPersistence:
    def test_manifest_survives_roundtrip(self, tmp_path: Path) -> None:
        db_path = _create_sqlite_db(tmp_path / "audit.sqlite3")
        config = _make_config(tmp_path, sqlite_paths=[db_path])
        manager = BackupManager(config)
        result = manager.create_backup()
        assert result.success is True
        manifest_path = Path(result.backup_dir) / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "backup_id" in data
        assert "checksums" in data
        assert len(data["checksums"]) >= 1

    def test_manifest_missing_keys_raises_on_restore(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups" / "backup_bad"
        backup_dir.mkdir(parents=True)
        (backup_dir / "manifest.json").write_text('{"backup_id": "bad"}', encoding="utf-8")
        config = _make_config(tmp_path)
        manager = BackupManager(config)
        with pytest.raises(ConfigError, match="missing required keys"):
            manager.restore_backup("backup_bad")

    def test_manifest_invalid_json_raises_on_restore(self, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups" / "backup_corrupt"
        backup_dir.mkdir(parents=True)
        (backup_dir / "manifest.json").write_text("not-json{{{", encoding="utf-8")
        config = _make_config(tmp_path)
        manager = BackupManager(config)
        with pytest.raises(ConfigError, match="Failed to read manifest"):
            manager.restore_backup("backup_corrupt")

    def test_manifest_to_dict(self) -> None:
        manifest = BackupManifest(
            backup_id="test-1",
            timestamp_utc="2025-01-01T00:00:00+00:00",
            sqlite_files=({"source": "/a.db", "dest": "a.db"},),
            duckdb_files=(),
            config_files=(),
            state_file={"source": "/s.json", "dest": "state.json"},
            checksums={"a.db": "abc123"},
        )
        d = BackupManager._manifest_to_dict(manifest)
        assert d["backup_id"] == "test-1"
        assert isinstance(d["sqlite_files"], list)
        assert d["state_file"]["source"] == "/s.json"

    def test_load_manifest_directly(self, tmp_path: Path) -> None:
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "backup_id": "test-1",
                    "timestamp_utc": "2025-01-01T00:00:00+00:00",
                    "sqlite_files": [{"source": "/a.db", "dest": "a.db"}],
                    "duckdb_files": [],
                    "config_files": [],
                    "state_file": None,
                    "checksums": {"a.db": "abc123"},
                }
            ),
            encoding="utf-8",
        )
        manifest = BackupManager._load_manifest(manifest_file)
        assert manifest.backup_id == "test-1"
        assert manifest.checksums == {"a.db": "abc123"}
        assert manifest.state_file is None

    def test_load_manifest_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="Failed to read manifest"):
            BackupManager._load_manifest(tmp_path / "nonexistent.json")

    def test_sqlite_online_backup(self, tmp_path: Path) -> None:
        src = _create_sqlite_db(tmp_path / "src.sqlite3")
        dest = tmp_path / "dest.sqlite3"
        BackupManager._sqlite_online_backup(src, dest)
        assert dest.exists()
        conn = sqlite3.connect(str(dest))
        row = conn.execute("SELECT data FROM trade_audit_log WHERE trade_id = 't1'").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "test-data-1"

    def test_export_state_none_path(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        manager = BackupManager(config)
        backup_dir = tmp_path / "backups" / "test"
        backup_dir.mkdir(parents=True)
        result = manager._export_state(backup_dir, {})
        assert result is None

    def test_export_state_missing_file(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, state_path=tmp_path / "nonexistent.json")
        manager = BackupManager(config)
        backup_dir = tmp_path / "backups" / "test"
        backup_dir.mkdir(parents=True)
        result = manager._export_state(backup_dir, {})
        assert result is None
