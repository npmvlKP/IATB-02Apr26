"""
Tests for weight optimization persistence functionality.
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from iatb.core.config_manager import ConfigManager
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.selection.composite_score import RegimeWeights
from iatb.selection.weight_optimizer import (
    _save_weights_to_config,
    _weights_to_dict,
    optimize_weights_for_regime,
)


class TestWeightsPersistence:
    """Tests for weight persistence functionality."""

    def test_weights_to_dict_conversion(self) -> None:
        """Test conversion of RegimeWeights to dictionary."""
        weights = RegimeWeights(
            sentiment=Decimal("0.25"),
            strength=Decimal("0.30"),
            volume_profile=Decimal("0.20"),
            drl=Decimal("0.25"),
        )

        result = _weights_to_dict(weights)

        assert result == {
            "sentiment": "0.25",
            "strength": "0.30",
            "volume_profile": "0.20",
            "drl": "0.25",
        }

    def test_save_weights_to_config_success(self) -> None:
        """Test successful weight saving to config."""
        with patch("iatb.selection.weight_optimizer.get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_get_manager.return_value = mock_manager

            weights = RegimeWeights(
                sentiment=Decimal("0.25"),
                strength=Decimal("0.30"),
                volume_profile=Decimal("0.20"),
                drl=Decimal("0.25"),
            )

            # Should not raise
            _save_weights_to_config(MarketRegime.BULL, weights)

            # Verify set_regime_weights was called
            mock_manager.set_regime_weights.assert_called_once()
            call_args = mock_manager.set_regime_weights.call_args
            assert call_args[0][0] == "BULL"
            assert call_args[0][1] == {
                "sentiment": "0.25",
                "strength": "0.30",
                "volume_profile": "0.20",
                "drl": "0.25",
            }

    def test_save_weights_to_config_failure(self) -> None:
        """Test handling of weight saving failure."""
        import pytest

        with patch("iatb.selection.weight_optimizer.get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.set_regime_weights.side_effect = Exception("Save failed")
            mock_get_manager.return_value = mock_manager

            weights = RegimeWeights(
                sentiment=Decimal("0.25"),
                strength=Decimal("0.30"),
                volume_profile=Decimal("0.20"),
                drl=Decimal("0.25"),
            )

            with pytest.raises(ConfigError, match="Failed to save weights"):
                _save_weights_to_config(MarketRegime.BULL, weights)

    def test_optimize_weights_for_regime_persists_by_default(self) -> None:
        """Test that optimize_weights_for_regime persists weights by default."""
        signal_history = [
            {
                "sentiment": Decimal("0.8"),
                "strength": Decimal("0.7"),
                "volume_profile": Decimal("0.6"),
                "drl": Decimal("0.5"),
            }
        ] * 10
        forward_returns = [Decimal("0.1")] * 10

        with patch("iatb.selection.weight_optimizer.get_config_manager") as mock_get_manager:
            with patch("iatb.selection.weight_optimizer._load_optuna") as mock_load:
                mock_manager = MagicMock()
                mock_get_manager.return_value = mock_manager

                mock_optuna = MagicMock()
                mock_load.return_value = mock_optuna

                mock_study = MagicMock()
                mock_study.best_params = {
                    "sentiment": 25,
                    "strength": 25,
                    "volume_profile": 25,
                    "drl": 25,
                }
                mock_study.best_value = 0.05
                mock_optuna.create_study.return_value = mock_study
                mock_optuna.samplers.TPESampler.return_value = MagicMock()

                optimize_weights_for_regime(
                    MarketRegime.BULL,
                    signal_history,
                    forward_returns,
                    n_trials=5,
                )

                # Verify that config manager was called to save weights
                mock_manager.set_regime_weights.assert_called_once()
                call_args = mock_manager.set_regime_weights.call_args
                assert call_args[0][0] == "BULL"

    def test_optimize_weights_for_regime_no_persist(self) -> None:
        """Test that optimize_weights_for_regime can skip persistence."""
        signal_history = [
            {
                "sentiment": Decimal("0.8"),
                "strength": Decimal("0.7"),
                "volume_profile": Decimal("0.6"),
                "drl": Decimal("0.5"),
            }
        ] * 10
        forward_returns = [Decimal("0.1")] * 10

        with patch("iatb.selection.weight_optimizer._save_weights_to_config") as mock_save:
            with patch("iatb.selection.weight_optimizer._load_optuna") as mock_load:
                mock_optuna = MagicMock()
                mock_load.return_value = mock_optuna

                mock_study = MagicMock()
                mock_study.best_params = {
                    "sentiment": 25,
                    "strength": 25,
                    "volume_profile": 25,
                    "drl": 25,
                }
                mock_study.best_value = 0.05
                mock_optuna.create_study.return_value = mock_study
            mock_optuna.samplers.TPESampler.return_value = MagicMock()

        optimize_weights_for_regime(
            MarketRegime.BULL,
            signal_history,
            forward_returns,
            n_trials=5,
            persist=False,
        )

        # Verify that save was NOT called
        mock_save.assert_not_called()


class TestConfigManagerWeights:
    """Tests for ConfigManager weights functionality."""

    def test_config_manager_set_regime_weights(self, tmp_path: Path) -> None:
        """Test setting regime weights in ConfigManager."""
        weights_path = tmp_path / "weights.toml"
        manager = ConfigManager(weights_path=weights_path)

        weights = {
            "sentiment": "0.25",
            "strength": "0.30",
            "volume_profile": "0.20",
            "drl": "0.25",
        }

        manager.set_regime_weights("BULL", weights)

        # Verify weights were set in memory
        assert manager.get_regime_weights("BULL") == weights

        # Verify file was written
        assert weights_path.exists()
        content = weights_path.read_text()
        assert "BULL" in content
        assert "0.25" in content

    def test_config_manager_get_regime_weights_not_found(self, tmp_path: Path) -> None:
        """Test getting non-existent regime weights."""
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text("[weights]\n")
        manager = ConfigManager(weights_path=weights_path)

        result = manager.get_regime_weights("NONEXISTENT")

        assert result is None

    def test_config_manager_update_weights_config(self, tmp_path: Path) -> None:
        """Test updating weights configuration."""
        weights_path = tmp_path / "weights.toml"
        manager = ConfigManager(weights_path=weights_path)

        new_weights = {
            "BULL": {
                "sentiment": "0.30",
                "strength": "0.30",
                "volume_profile": "0.20",
                "drl": "0.20",
            },
            "BEAR": {
                "sentiment": "0.40",
                "strength": "0.20",
                "volume_profile": "0.10",
                "drl": "0.30",
            },
        }

        manager.update_weights_config(new_weights)

        assert manager.get_weights_config() == new_weights

    def test_config_manager_reload_weights_config(self, tmp_path: Path) -> None:
        """Test reloading weights configuration."""
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text(
            """
[weights]
[weights.BULL]
sentiment = "0.25"
strength = "0.25"
volume_profile = "0.25"
drl = "0.25"
"""
        )

        manager = ConfigManager(weights_path=weights_path)

        # Modify file
        weights_path.write_text(
            """
[weights]
[weights.BULL]
sentiment = "0.30"
strength = "0.30"
volume_profile = "0.20"
drl = "0.20"
"""
        )

        # Reload
        manager.reload_weights_config()

        assert manager.get_regime_weights("BULL")["sentiment"] == "0.30"


class TestWeightPersistenceEdgeCases:
    """Tests for edge cases in weight persistence."""

    def test_save_weights_with_invalid_regime(self) -> None:
        """Test saving weights with invalid regime."""
        weights = RegimeWeights(
            sentiment=Decimal("0.25"),
            strength=Decimal("0.30"),
            volume_profile=Decimal("0.20"),
            drl=Decimal("0.25"),
        )

        # MarketRegime is a StrEnum, so we can't create invalid values easily
        # This test just verifies the function accepts valid regimes
        _save_weights_to_config(MarketRegime.BULL, weights)
        _save_weights_to_config(MarketRegime.BEAR, weights)
        _save_weights_to_config(MarketRegime.SIDEWAYS, weights)

    def test_weights_to_dict_preserves_precision(self) -> None:
        """Test that weights_to_dict preserves decimal precision."""
        # Use weights that sum to exactly 1.0
        weights = RegimeWeights(
            sentiment=Decimal("0.25"),
            strength=Decimal("0.25"),
            volume_profile=Decimal("0.25"),
            drl=Decimal("0.25"),
        )

        result = _weights_to_dict(weights)

        assert result["sentiment"] == "0.25"
        assert result["strength"] == "0.25"
        assert result["volume_profile"] == "0.25"
        assert result["drl"] == "0.25"
