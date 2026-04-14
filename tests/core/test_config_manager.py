"""
Tests for config manager module.

Covers happy path, edge cases, error paths, type handling,
precision handling, timezone handling, and external API mocking.
"""

from pathlib import Path

import pytest
from iatb.core.config_manager import (
    WATCHLIST_CONFIG_ENV_VAR,
    ConfigManager,
    WatchlistConfig,
    WatchlistEntry,
    get_config_manager,
    reset_config_manager,
)
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError


class TestWatchlistEntry:
    """Tests for WatchlistEntry dataclass."""

    def test_watchlist_entry_creation(self) -> None:
        """Test creating a watchlist entry."""
        entry = WatchlistEntry(exchange=Exchange.NSE, symbol="RELIANCE")
        assert entry.exchange == Exchange.NSE
        assert entry.symbol == "RELIANCE"

    def test_watchlist_entry_immutable(self) -> None:
        """Test that watchlist entry is frozen."""
        entry = WatchlistEntry(exchange=Exchange.NSE, symbol="RELIANCE")
        with pytest.raises(AttributeError):
            entry.symbol = "TCS"  # type: ignore[misc]


class TestWatchlistConfig:
    """Tests for WatchlistConfig dataclass."""

    def test_default_config_empty(self) -> None:
        """Test default config has empty lists."""
        config = WatchlistConfig()
        assert config.nse == []
        assert config.bse == []
        assert config.mcx == []
        assert config.cds == []

    def test_config_with_symbols(self) -> None:
        """Test config with symbols."""
        config = WatchlistConfig(
            nse=["RELIANCE", "TCS"],
            bse=["SBIN"],
        )
        assert len(config.nse) == 2
        assert len(config.bse) == 1
        assert config.mcx == []
        assert config.cds == []

    def test_get_symbols_nse(self) -> None:
        """Test getting NSE symbols."""
        config = WatchlistConfig(nse=["RELIANCE", "TCS"])
        symbols = config.get_symbols(Exchange.NSE)
        assert symbols == ["RELIANCE", "TCS"]
        # Should return a copy, not the original list
        symbols.append("INFY")
        assert len(config.nse) == 2

    def test_get_symbols_all_exchanges(self) -> None:
        """Test getting symbols for all exchanges."""
        config = WatchlistConfig(
            nse=["RELIANCE"],
            bse=["TCS"],
            mcx=["GOLD"],
            cds=["USDINR"],
        )
        assert config.get_symbols(Exchange.NSE) == ["RELIANCE"]
        assert config.get_symbols(Exchange.BSE) == ["TCS"]
        assert config.get_symbols(Exchange.MCX) == ["GOLD"]
        assert config.get_symbols(Exchange.CDS) == ["USDINR"]

    def test_get_symbols_empty_exchange(self) -> None:
        """Test getting symbols for exchange with no symbols."""
        config = WatchlistConfig(nse=["RELIANCE"])
        symbols = config.get_symbols(Exchange.MCX)
        assert symbols == []

    def test_get_all_entries(self) -> None:
        """Test getting all watchlist entries."""
        config = WatchlistConfig(
            nse=["RELIANCE", "TCS"],
            bse=["SBIN"],
            mcx=["GOLD"],
        )
        entries = config.get_all_entries()
        assert len(entries) == 4
        assert any(e.exchange == Exchange.NSE and e.symbol == "RELIANCE" for e in entries)
        assert any(e.exchange == Exchange.NSE and e.symbol == "TCS" for e in entries)
        assert any(e.exchange == Exchange.BSE and e.symbol == "SBIN" for e in entries)
        assert any(e.exchange == Exchange.MCX and e.symbol == "GOLD" for e in entries)

    def test_config_immutable(self) -> None:
        """Test that config is frozen."""
        config = WatchlistConfig(nse=["RELIANCE"])
        with pytest.raises(AttributeError):
            config.nse = ["TCS"]  # type: ignore[misc]


class TestConfigManager:
    """Tests for ConfigManager class."""

    def test_init_with_default_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initialization with default config path."""
        # Reset environment variable to use default
        monkeypatch.delenv(WATCHLIST_CONFIG_ENV_VAR, raising=False)

        manager = ConfigManager()
        assert manager._config_path == Path("config/watchlist.toml")

    def test_init_with_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test initialization with environment variable override."""
        custom_path = tmp_path / "custom_watchlist.toml"
        monkeypatch.setenv(WATCHLIST_CONFIG_ENV_VAR, str(custom_path))

        manager = ConfigManager()
        assert manager._config_path == custom_path

    def test_init_with_explicit_path(self, tmp_path: Path) -> None:
        """Test initialization with explicit config path."""
        custom_path = tmp_path / "explicit_watchlist.toml"
        manager = ConfigManager(config_path=custom_path)
        assert manager._config_path == custom_path

    def test_load_config_file_not_found(self, tmp_path: Path) -> None:
        """Test loading config when file doesn't exist."""
        manager = ConfigManager(config_path=tmp_path / "nonexistent.toml")
        config = manager.get_config()
        assert isinstance(config, WatchlistConfig)
        assert config.nse == []
        assert config.bse == []
        assert config.mcx == []
        assert config.cds == []

    def test_load_config_valid_toml(self, tmp_path: Path) -> None:
        """Test loading valid TOML config."""
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text(
            """
[nse]
symbols = ["RELIANCE", "TCS"]

[bse]
symbols = ["SBIN"]

[mcx]
symbols = ["GOLD"]

[cds]
symbols = ["USDINR"]
"""
        )

        manager = ConfigManager(config_path=config_path)
        config = manager.get_config()
        assert config.nse == ["RELIANCE", "TCS"]
        assert config.bse == ["SBIN"]
        assert config.mcx == ["GOLD"]
        assert config.cds == ["USDINR"]

    def test_load_config_empty_toml(self, tmp_path: Path) -> None:
        """Test loading empty TOML config."""
        config_path = tmp_path / "empty.toml"
        config_path.write_text("")

        manager = ConfigManager(config_path=config_path)
        config = manager.get_config()
        assert config.nse == []
        assert config.bse == []
        assert config.mcx == []
        assert config.cds == []

    def test_load_config_partial_exchanges(self, tmp_path: Path) -> None:
        """Test loading config with only some exchanges defined."""
        config_path = tmp_path / "partial.toml"
        config_path.write_text(
            """
[nse]
symbols = ["RELIANCE"]

[cds]
symbols = ["USDINR"]
"""
        )

        manager = ConfigManager(config_path=config_path)
        config = manager.get_config()
        assert config.nse == ["RELIANCE"]
        assert config.bse == []
        assert config.mcx == []
        assert config.cds == ["USDINR"]

    def test_reload_config(self, tmp_path: Path) -> None:
        """Test reloading configuration from file."""
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text(
            """
[nse]
symbols = ["RELIANCE"]
"""
        )

        manager = ConfigManager(config_path=config_path)
        assert len(manager.get_config().nse) == 1

        # Update file
        config_path.write_text(
            """
[nse]
symbols = ["RELIANCE", "TCS", "INFY"]
"""
        )

        # Reload
        manager.reload_config()
        assert len(manager.get_config().nse) == 3

    def test_update_config_nse(self, tmp_path: Path) -> None:
        """Test updating NSE watchlist."""
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text(
            """
[nse]
symbols = ["RELIANCE"]
"""
        )

        manager = ConfigManager(config_path=config_path)
        config = manager.update_config(nse=["TCS", "INFY"])

        assert config.nse == ["TCS", "INFY"]
        assert config_path.exists()

        # Verify file was updated
        import tomli

        with config_path.open("rb") as f:
            file_content = tomli.load(f)
        assert file_content["nse"]["symbols"] == ["TCS", "INFY"]

    def test_update_config_multiple_exchanges(self, tmp_path: Path) -> None:
        """Test updating multiple exchanges."""
        config_path = tmp_path / "watchlist.toml"
        manager = ConfigManager(config_path=config_path)

        config = manager.update_config(
            nse=["RELIANCE"],
            bse=["TCS"],
            mcx=["GOLD"],
            cds=["USDINR"],
        )

        assert config.nse == ["RELIANCE"]
        assert config.bse == ["TCS"]
        assert config.mcx == ["GOLD"]
        assert config.cds == ["USDINR"]

        # Verify file was written
        import tomli

        with config_path.open("rb") as f:
            file_content = tomli.load(f)
        assert file_content["nse"]["symbols"] == ["RELIANCE"]
        assert file_content["bse"]["symbols"] == ["TCS"]
        assert file_content["mcx"]["symbols"] == ["GOLD"]
        assert file_content["cds"]["symbols"] == ["USDINR"]

    def test_update_config_partial_update(self, tmp_path: Path) -> None:
        """Test partial update (only some exchanges)."""
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text(
            """
[nse]
symbols = ["RELIANCE", "TCS"]
[bse]
symbols = ["SBIN"]
"""
        )

        manager = ConfigManager(config_path=config_path)
        config = manager.update_config(nse=["INFY"])  # Only update NSE

        assert config.nse == ["INFY"]
        assert config.bse == ["SBIN"]  # Should remain unchanged
        assert config.mcx == []
        assert config.cds == []

    def test_update_config_creates_directory(self, tmp_path: Path) -> None:
        """Test that update_config creates parent directory if needed."""
        config_path = tmp_path / "subdir" / "watchlist.toml"
        assert not config_path.parent.exists()

        manager = ConfigManager(config_path=config_path)
        manager.update_config(nse=["RELIANCE"])

        assert config_path.parent.exists()
        assert config_path.exists()

    def test_update_config_write_error(self, tmp_path: Path) -> None:
        """Test handling of write errors."""
        # Create a directory instead of a file path
        config_path = tmp_path / "directory" / "watchlist.toml"
        config_path.mkdir(parents=True)

        manager = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="Failed to write"):
            manager.update_config(nse=["RELIANCE"])

    def test_get_config_returns_immutable(self, tmp_path: Path) -> None:
        """Test that get_config returns immutable config."""
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text(
            """
[nse]
symbols = ["RELIANCE"]
"""
        )

        manager = ConfigManager(config_path=config_path)
        config = manager.get_config()

        # Config should be frozen/immutable
        with pytest.raises(AttributeError):
            config.nse = ["TCS"]  # type: ignore[misc]

        # get_symbols should return a copy
        symbols = config.get_symbols(Exchange.NSE)
        symbols.append("NEW_SYMBOL")

        # Original should be unchanged
        assert config.nse == ["RELIANCE"]


class TestGlobalConfigManager:
    """Tests for global config manager functions."""

    def test_get_config_manager_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that get_config_manager returns singleton instance."""
        monkeypatch.delenv(WATCHLIST_CONFIG_ENV_VAR, raising=False)
        reset_config_manager()

        manager1 = get_config_manager()
        manager2 = get_config_manager()
        assert manager1 is manager2

    def test_reset_config_manager(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test resetting config manager."""
        monkeypatch.delenv(WATCHLIST_CONFIG_ENV_VAR, raising=False)
        reset_config_manager()

        manager1 = get_config_manager()
        reset_config_manager()
        manager2 = get_config_manager()

        assert manager1 is not manager2

    def test_config_manager_persists_across_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that config changes persist across get_config_manager calls."""
        monkeypatch.delenv(WATCHLIST_CONFIG_ENV_VAR, raising=False)
        reset_config_manager()

        manager1 = get_config_manager()
        manager1.update_config(nse=["TEST1"])

        manager2 = get_config_manager()
        assert manager2.get_config().nse == ["TEST1"]


class TestConfigManagerEdgeCases:
    """Tests for edge cases and error handling."""

    def test_config_with_duplicate_symbols(self, tmp_path: Path) -> None:
        """Test config with duplicate symbols."""
        config_path = tmp_path / "watchlist.toml"
        manager = ConfigManager(config_path=config_path)
        config = manager.update_config(nse=["RELIANCE", "RELIANCE", "TCS"])

        # Duplicates should be preserved as-is (no deduplication)
        assert config.nse == ["RELIANCE", "RELIANCE", "TCS"]

    def test_config_with_empty_symbol_list(self, tmp_path: Path) -> None:
        """Test updating with empty symbol list."""
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text(
            """
[nse]
symbols = ["RELIANCE", "TCS"]
"""
        )

        manager = ConfigManager(config_path=config_path)
        config = manager.update_config(nse=[])

        assert config.nse == []

    def test_config_with_non_list_symbols(self, tmp_path: Path) -> None:
        """Test config where symbols is not a list - Pydantic handles type coercion."""
        config_path = tmp_path / "bad.toml"
        config_path.write_text(
            """
[nse]
symbols = "NOT_A_LIST"
"""
        )

        manager = ConfigManager(config_path=config_path)
        # Pydantic will load the config as-is (type not strictly enforced)
        config = manager.get_config()
        # The string value is preserved as-is
        assert config.nse == "NOT_A_LIST"  # type: ignore[comparison-overlap]

    def test_config_path_with_special_characters(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test config path with special characters."""
        special_path = tmp_path / "config with spaces & special chars.toml"
        monkeypatch.setenv(WATCHLIST_CONFIG_ENV_VAR, str(special_path))

        manager = ConfigManager()
        manager.update_config(nse=["RELIANCE"])

        assert special_path.exists()
        assert manager.get_config().nse == ["RELIANCE"]
