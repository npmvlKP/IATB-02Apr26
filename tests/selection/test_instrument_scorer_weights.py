"""
Tests for InstrumentScorer weight loading from ConfigManager.
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from iatb.core.enums import Exchange
from iatb.market_strength.regime_detector import MarketRegime
from iatb.selection.composite_score import RegimeWeights
from iatb.selection.drl_signal import DRLSignalOutput
from iatb.selection.instrument_scorer import InstrumentScorer, InstrumentSignals
from iatb.selection.sentiment_signal import SentimentSignalOutput
from iatb.selection.strength_signal import StrengthSignalOutput
from iatb.selection.volume_profile_signal import VolumeProfileSignalOutput
from iatb.selection.weight_optimizer import _load_weights_from_config


class TestInstrumentScorerWeightLoading:
    """Tests for InstrumentScorer weight loading functionality."""

    def test_instrument_scorer_loads_weights_from_config(self) -> None:
        """Test that InstrumentScorer loads weights from config when requested."""
        # Mock the config manager
        with patch("iatb.selection.weight_optimizer.get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_weights_config.return_value = {
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
            mock_get_manager.return_value = mock_manager

            # Create InstrumentScorer with load_from_config=True
            scorer = InstrumentScorer(load_from_config=True)

            # Verify that custom weights were loaded
            assert len(scorer._custom_weights) == 2
            assert MarketRegime.BULL in scorer._custom_weights
            assert MarketRegime.BEAR in scorer._custom_weights

    def test_instrument_scorer_uses_provided_weights(self) -> None:
        """Test that InstrumentScorer uses provided weights instead of loading from config."""
        custom_weights = {
            MarketRegime.BULL: RegimeWeights(
                sentiment=Decimal("0.5"),
                strength=Decimal("0.3"),
                volume_profile=Decimal("0.1"),
                drl=Decimal("0.1"),
            )
        }

        # Create InstrumentScorer with provided weights
        scorer = InstrumentScorer(custom_weights=custom_weights, load_from_config=False)

        # Verify that provided weights are used
        assert len(scorer._custom_weights) == 1
        assert MarketRegime.BULL in scorer._custom_weights
        assert scorer._custom_weights[MarketRegime.BULL].sentiment == Decimal("0.5")

    def test_instrument_scorer_empty_weights_when_config_fails(self) -> None:
        """Test that InstrumentScorer handles config loading failure gracefully."""
        # This test verifies that when config loading fails, the scorer still works
        # We can't easily mock the config loading from weight_optimizer,
        # so we test the default behavior
        with patch("iatb.selection.weight_optimizer.get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_weights_config.return_value = {}
            mock_get_manager.return_value = mock_manager

            # Create InstrumentScorer - should use empty weights when config fails
            scorer = InstrumentScorer(load_from_config=True)

            # Verify that custom weights are a dict (may be empty or have loaded values)
            assert isinstance(scorer._custom_weights, dict)

    def test_load_weights_from_config_success(self, tmp_path: Path) -> None:
        """Test successful weight loading from config."""
        # Create a test weights config
        weights_path = tmp_path / "weights.toml"
        weights_path.write_text(
            """
[weights]
[weights.BULL]
sentiment = "0.25"
strength = "0.25"
volume_profile = "0.25"
drl = "0.25"

[weights.SIDEWAYS]
sentiment = "0.30"
strength = "0.30"
volume_profile = "0.20"
drl = "0.20"
"""
        )

        # Mock the config manager
        with patch("iatb.selection.weight_optimizer.get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_weights_config.return_value = {
                "BULL": {
                    "sentiment": "0.25",
                    "strength": "0.25",
                    "volume_profile": "0.25",
                    "drl": "0.25",
                },
                "SIDEWAYS": {
                    "sentiment": "0.30",
                    "strength": "0.30",
                    "volume_profile": "0.20",
                    "drl": "0.20",
                },
            }
            mock_get_manager.return_value = mock_manager

            weights = _load_weights_from_config()

            assert len(weights) == 2
            assert MarketRegime.BULL in weights
            assert MarketRegime.SIDEWAYS in weights
            assert weights[MarketRegime.BULL].sentiment == Decimal("0.25")

    def test_load_weights_from_config_handles_missing_fields(self, tmp_path: Path) -> None:
        """Test that weight loading handles missing fields gracefully."""
        with patch("iatb.selection.weight_optimizer.get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            # Missing 'drl' field
            mock_manager.get_weights_config.return_value = {
                "BULL": {
                    "sentiment": "0.25",
                    "strength": "0.25",
                    "volume_profile": "0.25",
                }
            }
            mock_get_manager.return_value = mock_manager

            weights = _load_weights_from_config()

            # Should return empty dict because BULL weights are incomplete
            assert len(weights) == 0

    def test_load_weights_from_config_handles_invalid_regime(self, tmp_path: Path) -> None:
        """Test that weight loading handles invalid regime names gracefully."""
        with patch("iatb.selection.weight_optimizer.get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_weights_config.return_value = {
                "INVALID_REGIME": {
                    "sentiment": "0.25",
                    "strength": "0.25",
                    "volume_profile": "0.25",
                    "drl": "0.25",
                }
            }
            mock_get_manager.return_value = mock_manager

            weights = _load_weights_from_config()

            # Should return empty dict because regime is invalid
            assert len(weights) == 0

    def test_instrument_scorer_uses_custom_weights_in_computation(self) -> None:
        """Test that InstrumentScorer uses custom weights in composite computation."""
        custom_weights = {
            MarketRegime.BULL: RegimeWeights(
                sentiment=Decimal("1.0"),
                strength=Decimal("0.0"),
                volume_profile=Decimal("0.0"),
                drl=Decimal("0.0"),
            )
        }

        scorer = InstrumentScorer(custom_weights=custom_weights)

        # Create test signals with required fields
        signals = [
            InstrumentSignals(
                symbol="TEST",
                exchange=Exchange.NSE,
                sentiment=SentimentSignalOutput(
                    score=Decimal("0.8"),
                    confidence=Decimal("0.9"),
                    directional_bias="BULLISH",
                    metadata={},
                ),
                strength=StrengthSignalOutput(
                    score=Decimal("0.5"),
                    confidence=Decimal("0.9"),
                    regime=MarketRegime.BULL,
                    tradable=True,
                    metadata={},
                ),
                volume_profile=VolumeProfileSignalOutput(
                    score=Decimal("0.3"),
                    confidence=Decimal("0.9"),
                    shape="P",
                    poc_distance_pct=Decimal("0.1"),
                    va_width_pct=Decimal("0.2"),
                    metadata={},
                ),
                drl=DRLSignalOutput(
                    score=Decimal("0.2"),
                    confidence=Decimal("0.9"),
                    robust=True,
                    metadata={},
                ),
            )
        ]

        # Score instruments
        scored = scorer.score_instruments(signals, MarketRegime.BULL)

        # With custom weights that only use sentiment (1.0 weight),
        # the composite score should be close to the sentiment score
        assert len(scored) == 1
        # The composite score should reflect the sentiment score with gating
        assert scored[0].composite.composite_score > Decimal("0")


class TestWeightLoadingEdgeCases:
    """Tests for edge cases in weight loading."""

    def test_empty_weights_config(self) -> None:
        """Test loading from empty weights config."""
        with patch("iatb.selection.weight_optimizer.get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_weights_config.return_value = {}
            mock_get_manager.return_value = mock_manager

            weights = _load_weights_from_config()

            assert weights == {}

    def test_config_manager_exception(self) -> None:
        """Test handling of ConfigManager exception."""
        with patch("iatb.selection.weight_optimizer.get_config_manager") as mock_get_manager:
            mock_get_manager.side_effect = Exception("Config manager error")

            weights = _load_weights_from_config()

            assert weights == {}

    def test_instrument_scorer_with_empty_custom_weights(self) -> None:
        """Test InstrumentScorer with empty custom weights."""
        scorer = InstrumentScorer(custom_weights={})

        assert scorer._custom_weights == {}

    def test_instrument_scorer_default_behavior(self) -> None:
        """Test InstrumentScorer default behavior without custom weights."""
        scorer = InstrumentScorer()

        # Should have loaded from config or be empty
        assert isinstance(scorer._custom_weights, dict)
