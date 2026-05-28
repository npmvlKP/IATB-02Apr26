"""Supplemental coverage tests for config manager module.

Covers: TOML parse error paths, weights config env overlay, weights config
file not found, weights config reload, regime weights get/set, update_weights_config
write error, _merge_weights_config_updates with None, _serialize_weights_to_toml,
WeightsConfig.get_symbols with unknown exchange.
"""

from pathlib import Path

import pytest
from iatb.core.config_manager import (
    WEIGHTS_CONFIG_ENV_VAR,
    ConfigManager,
    WatchlistConfig,
)
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError


class TestConfigManagerWeightsEnvOverlay:
    def test_weights_env_override(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom_weights = tmp_path / "custom_weights.toml"
        monkeypatch.setenv(WEIGHTS_CONFIG_ENV_VAR, str(custom_weights))
        manager = ConfigManager()
        assert manager._weights_path == custom_weights

    def test_weights_explicit_path_overrides_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        env_path = tmp_path / "env_weights.toml"
        explicit_path = tmp_path / "explicit_weights.toml"
        monkeypatch.setenv(WEIGHTS_CONFIG_ENV_VAR, str(env_path))
        manager = ConfigManager(weights_path=explicit_path)
        assert manager._weights_path == explicit_path

    def test_weights_default_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(WEIGHTS_CONFIG_ENV_VAR, raising=False)
        manager = ConfigManager()
        assert manager._weights_path == Path("config/weights.toml")


class TestConfigManagerWeightsFileNotFound:
    def test_weights_file_not_found_returns_empty(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "nonexistent_weights.toml"
        manager = ConfigManager(weights_path=weights_path)
        assert manager.get_weights_config() == {}


class TestConfigManagerWeightsValidToml:
    def test_load_valid_weights(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text(
            '[weights.BULL]\nsentiment = "0.5"\nstrength = "0.3"\n\n'
            '[weights.BEAR]\nsentiment = "0.7"\nstrength = "0.2"\n'
        )
        manager = ConfigManager(weights_path=weights_path)
        weights = manager.get_weights_config()
        assert "BULL" in weights
        assert weights["BULL"]["sentiment"] == "0.5"
        assert "BEAR" in weights

    def test_load_weights_non_dict_weights_returns_empty(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "bad_weights.toml"
        weights_path.write_text('weights = "not_a_dict"')
        manager = ConfigManager(weights_path=weights_path)
        assert manager.get_weights_config() == {}


class TestConfigManagerReloadWeights:
    def test_reload_weights_config(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text('[weights]\n[weights.BULL]\nsentiment = "0.4"\n')
        manager = ConfigManager(weights_path=weights_path)
        assert "BULL" in manager.get_weights_config()

        weights_path.write_text('[weights]\n[weights.SIDEWAYS]\nstrength = "0.6"\n')
        manager.reload_weights_config()
        weights = manager.get_weights_config()
        assert "SIDEWAYS" in weights


class TestConfigManagerRegimeWeights:
    def test_get_regime_weights_found(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text('[weights.BULL]\nsentiment = "0.5"\n')
        manager = ConfigManager(weights_path=weights_path)
        result = manager.get_regime_weights("BULL")
        assert result is not None
        assert result["sentiment"] == "0.5"

    def test_get_regime_weights_not_found(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text("")
        manager = ConfigManager(weights_path=weights_path)
        assert manager.get_regime_weights("NONEXISTENT") is None

    def test_set_regime_weights(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text("")
        manager = ConfigManager(weights_path=weights_path)
        manager.set_regime_weights("BEAR", {"sentiment": "0.8"})
        assert manager.get_regime_weights("BEAR") == {"sentiment": "0.8"}


class TestConfigManagerUpdateWeightsConfig:
    def test_update_weights_config(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text("")
        manager = ConfigManager(weights_path=weights_path)
        new_weights = manager.update_weights_config(
            {"BEAR": {"sentiment": "0.9", "strength": "0.1"}}
        )
        assert "BEAR" in new_weights
        assert new_weights["BEAR"]["sentiment"] == "0.9"

    def test_update_weights_config_creates_dir(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "subdir" / "weights.toml"
        manager = ConfigManager(weights_path=weights_path)
        manager.update_weights_config({"BULL": {"sentiment": "0.6"}})
        assert weights_path.exists()

    def test_update_weights_config_write_error(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "dir" / "weights.toml"
        weights_path.mkdir(parents=True)
        manager = ConfigManager(weights_path=weights_path)
        with pytest.raises(ConfigError, match="Failed to write"):
            manager.update_weights_config({"BULL": {"sentiment": "0.5"}})


class TestConfigManagerMergeWeightsConfigUpdates:
    def test_merge_with_none_returns_current(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text('[weights.BULL]\nsentiment = "0.4"\n')
        manager = ConfigManager(weights_path=weights_path)
        result = manager._merge_weights_config_updates(None)
        assert "BULL" in result

    def test_merge_with_new_returns_new(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text("")
        manager = ConfigManager(weights_path=weights_path)
        new_weights = {"BEAR": {"sentiment": "0.9"}}
        result = manager._merge_weights_config_updates(new_weights)
        assert result == new_weights


class TestConfigManagerSerializeWeights:
    def test_serialize_weights_to_toml(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text("")
        manager = ConfigManager(weights_path=weights_path)
        result = manager._serialize_weights_to_toml({"BULL": {"sentiment": "0.5"}})
        assert result == {"weights": {"BULL": {"sentiment": "0.5"}}}


class TestConfigManagerTOMLParseError:
    def test_invalid_toml_uses_defaults(self, tmp_path: Path) -> None:
        config_path = tmp_path / "bad.toml"
        config_path.write_text("invalid toml [[[[")
        manager = ConfigManager(config_path=config_path)
        config = manager.get_config()
        assert config.nse == []
        assert config.bse == []

    def test_invalid_weights_toml_uses_defaults(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "bad_weights.toml"
        weights_path.write_text("invalid weights toml [[[[")
        manager = ConfigManager(
            config_path=tmp_path / "ok.toml", weights_path=weights_path
        )
        weights = manager.get_weights_config()
        assert weights == {}


class TestWatchlistConfigUnknownExchange:
    def test_get_symbols_unknown_exchange(self) -> None:
        config = WatchlistConfig(nse=["RELIANCE"])
        result = config.get_symbols(Exchange.CDS)
        assert result == []

    def test_get_symbols_returns_copy(self) -> None:
        config = WatchlistConfig(nse=["RELIANCE", "TCS"])
        symbols = config.get_symbols(Exchange.NSE)
        symbols.append("INFY")
        assert config.get_symbols(Exchange.NSE) == ["RELIANCE", "TCS"]

    def test_get_all_entries(self) -> None:
        config = WatchlistConfig(nse=["RELIANCE"], bse=["BSE100"])
        entries = config.get_all_entries()
        assert len(entries) == 2

    def test_get_all_entries_empty(self) -> None:
        config = WatchlistConfig()
        entries = config.get_all_entries()
        assert entries == []


class TestConfigManagerWatchlistPersistence:
    def test_update_config_writes_toml(self, tmp_path: Path) -> None:
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text("")
        manager = ConfigManager(config_path=config_path)
        manager.update_config(nse=["HDFC", "TCS"], bse=["BAJAJ"])
        manager2 = ConfigManager(config_path=config_path)
        config = manager2.get_config()
        assert "HDFC" in config.nse
        assert "BAJAJ" in config.bse

    def test_update_config_preserves_other_exchanges(self, tmp_path: Path) -> None:
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text("")
        manager = ConfigManager(config_path=config_path)
        manager.update_config(nse=["HDFC"])
        manager.update_config(bse=["BAJAJ"])
        config = manager.get_config()
        assert "BAJAJ" in config.bse

    def test_update_config_creates_parent_dir(self, tmp_path: Path) -> None:
        config_path = tmp_path / "subdir" / "watchlist.toml"
        manager = ConfigManager(config_path=config_path)
        manager.update_config(nse=["RELIANCE"])
        assert config_path.exists()


class TestConfigManagerMergeConfigUpdates:
    def test_merge_none_preserves_current(self, tmp_path: Path) -> None:
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text("")
        manager = ConfigManager(config_path=config_path)
        manager.update_config(nse=["HDFC"])
        result = manager._merge_config_updates(None, None, None, None)
        assert "HDFC" in result.nse

    def test_merge_partial_override(self, tmp_path: Path) -> None:
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text("")
        manager = ConfigManager(config_path=config_path)
        manager.update_config(nse=["HDFC"], bse=["BAJAJ"])
        result = manager._merge_config_updates(
            nse=["TCS"], bse=None, mcx=None, cds=None
        )
        assert "TCS" in result.nse
        assert "BAJAJ" in result.bse


class TestConfigManagerReloadConfig:
    def test_reload_config_picks_up_changes(self, tmp_path: Path) -> None:
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text('[nse]\nsymbols = ["RELIANCE"]\n')
        manager = ConfigManager(config_path=config_path)
        assert "RELIANCE" in manager.get_config().nse

        config_path.write_text('[nse]\nsymbols = ["TCS", "INFY"]\n')
        reloaded = manager.reload_config()
        assert "TCS" in reloaded.nse
        assert "INFY" in reloaded.nse


class TestConfigManagerConfigEnvVar:
    def test_config_env_override(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom_config = tmp_path / "custom_watchlist.toml"
        monkeypatch.setenv("IATB_WATCHLIST_CONFIG_PATH", str(custom_config))
        manager = ConfigManager()
        assert manager._config_path == custom_config

    def test_config_explicit_path_overrides_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        env_path = tmp_path / "env_watchlist.toml"
        explicit_path = tmp_path / "explicit_watchlist.toml"
        monkeypatch.setenv("IATB_WATCHLIST_CONFIG_PATH", str(env_path))
        manager = ConfigManager(config_path=explicit_path)
        assert manager._config_path == explicit_path


class TestConfigManagerSerializeToToml:
    def test_serialize_watchlist(self, tmp_path: Path) -> None:
        config_path = tmp_path / "watchlist.toml"
        config_path.write_text("")
        manager = ConfigManager(config_path=config_path)
        config = WatchlistConfig(nse=["A", "B"], mcx=["C"])
        result = manager._serialize_to_toml(config)
        assert result["nse"]["symbols"] == ["A", "B"]
        assert result["mcx"]["symbols"] == ["C"]


class TestConfigManagerSetRegimeWeightsWriteError:
    def test_set_regime_weights_write_error(self, tmp_path: Path) -> None:
        weights_path = tmp_path / "dir" / "weights.toml"
        weights_path.mkdir(parents=True)
        manager = ConfigManager(weights_path=weights_path)
        with pytest.raises(ConfigError, match="Failed to write"):
            manager.set_regime_weights("BEAR", {"sentiment": "0.9"})
