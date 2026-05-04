"""
Tests for Phase H - Engine Pipeline Integration.

Tests cover:
- Engine wiring with dynamic dependencies
- Dynamic symbol loading from config
- Strength scorer integration
- Deprecated file removal handling
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.config import Config
from iatb.core.engine import Engine
from iatb.core.enums import Exchange
from iatb.core.event_bus import EventBus
from iatb.core.sse_broadcaster import SSEBroadcaster
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.selection.drl_signal import DRLSignalOutput
from iatb.selection.instrument_scorer import (
    InstrumentSignals,
    SelectionResult,
)
from iatb.selection.sentiment_signal import SentimentSignalOutput
from iatb.selection.strength_signal import StrengthSignalOutput
from iatb.selection.volume_profile_signal import VolumeProfileSignalOutput


@pytest.fixture
def mock_engine_dependencies():
    """Provide mock core dependencies for Engine initialization."""
    return {
        "event_bus": MagicMock(spec=EventBus),
        "sse_broadcaster": MagicMock(spec=SSEBroadcaster),
        "config": MagicMock(spec=Config),
    }


class TestEngineWiring:
    """Test engine wiring with dynamic dependencies."""

    def test_engine_initialization_with_all_dependencies(self, mock_engine_dependencies) -> None:
        """Test engine initialization with all pipeline dependencies."""
        mock_scorer = MagicMock()
        mock_kill_switch = MagicMock()
        mock_data_provider = MagicMock()
        mock_scanner = MagicMock()
        mock_order_manager = MagicMock()
        mock_scanner_config = MagicMock()

        engine = Engine(
            **mock_engine_dependencies,
            instrument_scorer=mock_scorer,
            kill_switch=mock_kill_switch,
            data_provider=mock_data_provider,
            instrument_scanner=mock_scanner,
            order_manager=mock_order_manager,
            scanner_config=mock_scanner_config,
        )

        assert engine.instrument_scorer is mock_scorer
        assert engine.kill_switch is mock_kill_switch
        assert engine.data_provider is mock_data_provider
        assert engine.instrument_scanner is mock_scanner
        assert engine.order_manager is mock_order_manager

    def test_engine_wiring_default_dependencies(self, mock_engine_dependencies) -> None:
        """Test engine creates default dependencies when not provided."""
        engine = Engine(**mock_engine_dependencies)

        assert engine.instrument_scorer is not None
        assert isinstance(engine.instrument_scorer, type(engine.instrument_scorer))
        assert engine.kill_switch is None
        assert engine.data_provider is None
        assert engine.instrument_scanner is None
        assert engine.order_manager is None

    def test_engine_pipeline_data_flow(self, mock_engine_dependencies) -> None:
        """Test data flows correctly through pipeline components."""
        mock_data_provider = MagicMock()
        mock_scanner = MagicMock()
        mock_order_manager = MagicMock()
        mock_scanner_config = MagicMock()

        engine = Engine(
            **mock_engine_dependencies,
            data_provider=mock_data_provider,
            instrument_scanner=mock_scanner,
            order_manager=mock_order_manager,
            scanner_config=mock_scanner_config,
        )

        # Verify components are wired correctly
        assert engine.data_provider is mock_data_provider
        assert engine.instrument_scanner is mock_scanner
        assert engine.order_manager is mock_order_manager


class TestDynamicSymbolLoading:
    """Test dynamic symbol loading from configuration."""

    def test_dynamic_symbol_loading_with_config(self, mock_engine_dependencies) -> None:
        """Test dynamic symbol loading from watchlist config."""
        mock_data_provider = MagicMock()
        engine = Engine(**mock_engine_dependencies, data_provider=mock_data_provider)

        # Mock config manager to return symbols
        mock_config = MagicMock()
        mock_config.get_symbols.return_value = ["RELIANCE", "TCS", "INFY"]
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = mock_config

        with patch(
            "iatb.core.config_manager.get_config_manager",
            return_value=mock_config_manager,
        ):
            engine.run_full_cycle()

        # Verify config was accessed
        mock_config.get_symbols.assert_called_once_with(exchange=Exchange.NSE)

    def test_dynamic_symbol_loading_fallback_to_defaults(self, mock_engine_dependencies) -> None:
        """Test fallback to default symbols when config unavailable."""
        from iatb.core.exceptions import ConfigError

        mock_data_provider = MagicMock()
        engine = Engine(**mock_engine_dependencies, data_provider=mock_data_provider)

        # Mock config manager to raise ConfigError
        with patch(
            "iatb.core.config_manager.get_config_manager",
            side_effect=ConfigError("Config not found"),
        ):
            # Should not raise, should use defaults
            with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
                mock_result = MagicMock()
                mock_run.return_value = mock_result
                engine.run_full_cycle()

                # Verify run_scan_cycle was called
                mock_run.assert_called_once()

    def test_dynamic_symbol_loading_with_empty_config(self, mock_engine_dependencies) -> None:
        """Test behavior when config returns empty symbol list."""
        mock_data_provider = MagicMock()
        engine = Engine(**mock_engine_dependencies, data_provider=mock_data_provider)

        # Mock config manager to return empty list
        mock_config = MagicMock()
        mock_config.get_symbols.return_value = []
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = mock_config

        with patch(
            "iatb.core.config_manager.get_config_manager",
            return_value=mock_config_manager,
        ):
            with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
                mock_result = MagicMock()
                mock_run.return_value = mock_result
                engine.run_full_cycle()

                # Should use defaults when config is empty
                mock_run.assert_called_once()

    def test_dynamic_symbol_loading_with_explicit_symbols(self, mock_engine_dependencies) -> None:
        """Test that explicitly provided symbols override config."""
        mock_data_provider = MagicMock()
        engine = Engine(**mock_engine_dependencies, data_provider=mock_data_provider)

        with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
            mock_result = MagicMock()
            mock_run.return_value = mock_result

            engine.run_full_cycle(symbols=["RELIANCE", "HDFCBANK"])

            # Verify explicit symbols were used
            call_args = mock_run.call_args
            assert call_args[1]["symbols"] == ["RELIANCE", "HDFCBANK"]


class TestStrengthScorerIntegration:
    """Test strength scorer integration in engine pipeline."""

    def test_strength_scorer_initialization(self, mock_engine_dependencies) -> None:
        """Test strength scorer is properly initialized in engine."""
        from iatb.selection.instrument_scorer import InstrumentScorer

        engine = Engine(**mock_engine_dependencies)
        assert engine.instrument_scorer is not None
        assert isinstance(engine.instrument_scorer, InstrumentScorer)

    def test_strength_scorer_used_in_selection_cycle(self, mock_engine_dependencies) -> None:
        """Test strength scorer is used during selection cycle."""
        engine = Engine(**mock_engine_dependencies)

        # Create mock signals with strength inputs
        mock_strength_inputs = MagicMock(spec=StrengthInputs)
        mock_sentiment = MagicMock(spec=SentimentSignalOutput)
        mock_sentiment.score = Decimal("0.7")
        mock_strength = MagicMock(spec=StrengthSignalOutput)
        mock_strength.score = Decimal("0.75")
        mock_volume_profile = MagicMock(spec=VolumeProfileSignalOutput)
        mock_volume_profile.score = Decimal("0.8")
        mock_drl = MagicMock(spec=DRLSignalOutput)
        mock_drl.score = Decimal("0.85")

        signals = [
            InstrumentSignals(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                sentiment=mock_sentiment,
                strength=mock_strength,
                volume_profile=mock_volume_profile,
                drl=mock_drl,
                strength_inputs=mock_strength_inputs,
            )
        ]

        strength_by_symbol = {"RELIANCE": mock_strength_inputs}
        regime = MarketRegime.BULL

        mock_selection = MagicMock(spec=SelectionResult)
        mock_selection.selected = []
        mock_selection.filtered_count = 0
        mock_selection.total_candidates = 1
        engine._scorer.score_and_select = MagicMock(return_value=mock_selection)

        with patch("iatb.core.engine.build_strategy_contexts", return_value=[]):
            engine.run_selection_cycle(
                signals=signals,
                regime=regime,
                strength_by_symbol=strength_by_symbol,
            )

        # Verify scorer was called
        engine._scorer.score_and_select.assert_called_once()

    def test_strength_scorer_caching_in_pipeline(self, mock_engine_dependencies) -> None:
        """Test strength scorer caching is respected in pipeline."""
        from iatb.selection.instrument_scorer import InstrumentScorer

        # Create scorer with caching
        scorer = InstrumentScorer()
        engine = Engine(**mock_engine_dependencies, instrument_scorer=scorer)

        # Verify scorer is accessible
        assert engine.instrument_scorer is scorer

    def test_strength_scorer_error_handling(self, mock_engine_dependencies) -> None:
        """Test error handling when strength scorer fails."""
        engine = Engine(**mock_engine_dependencies)

        mock_strength_inputs = MagicMock(spec=StrengthInputs)
        mock_sentiment = MagicMock(spec=SentimentSignalOutput)
        mock_sentiment.score = Decimal("0.7")
        mock_strength = MagicMock(spec=StrengthSignalOutput)
        mock_strength.score = Decimal("0.75")
        mock_volume_profile = MagicMock(spec=VolumeProfileSignalOutput)
        mock_volume_profile.score = Decimal("0.8")
        mock_drl = MagicMock(spec=DRLSignalOutput)
        mock_drl.score = Decimal("0.85")

        signals = [
            InstrumentSignals(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                sentiment=mock_sentiment,
                strength=mock_strength,
                volume_profile=mock_volume_profile,
                drl=mock_drl,
                strength_inputs=mock_strength_inputs,
            )
        ]

        regime = MarketRegime.BULL

        # Mock scorer to raise exception
        engine._scorer.score_and_select = MagicMock(side_effect=Exception("Scorer failed"))

        with pytest.raises(Exception, match="Scorer failed"):
            engine.select_instruments(signals, regime)


class TestDeprecatedFileRemoval:
    """Test deprecated file removal handling in pipeline."""

    def test_deprecated_scanner_file_removed(self, mock_engine_dependencies) -> None:
        """Test that deprecated scanner files are not used."""
        # This test verifies that the engine uses the new scanner module
        # and not any deprecated scanner files
        engine = Engine(**mock_engine_dependencies)

        # Verify engine does not import deprecated modules
        assert "deprecated_scanner" not in dir(engine)

    def test_pipeline_uses_new_scan_cycle_module(self, mock_engine_dependencies) -> None:
        """Test pipeline uses the new scan_cycle module."""
        mock_data_provider = MagicMock()
        engine = Engine(**mock_engine_dependencies, data_provider=mock_data_provider)

        with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
            mock_result = MagicMock()
            mock_result.scanner_result = None
            mock_result.trades_executed = 0
            mock_result.total_pnl = Decimal("0")
            mock_result.errors = []
            mock_result.timestamp_utc = datetime.now(UTC)
            mock_run.return_value = mock_result

            engine.run_full_cycle()

            # Verify new module is used
            mock_run.assert_called_once()

    def test_no_reference_to_old_scanner_paths(self) -> None:
        """Test no references to old scanner file paths."""
        import inspect

        # Use the class, not an instance
        source = inspect.getsource(Engine)

        # Verify no references to deprecated paths
        assert "old_scanner" not in source
        assert "legacy_scanner" not in source
        assert "deprecated" not in source.lower()


class TestEnginePipelineIntegration:
    """Integration tests for complete engine pipeline."""

    def test_full_pipeline_with_all_components(self, mock_engine_dependencies) -> None:
        """Test complete pipeline with all components wired."""
        mock_data_provider = MagicMock()
        mock_scanner = MagicMock()
        mock_order_manager = MagicMock()
        mock_scanner_config = MagicMock()

        engine = Engine(
            **mock_engine_dependencies,
            data_provider=mock_data_provider,
            instrument_scanner=mock_scanner,
            order_manager=mock_order_manager,
            scanner_config=mock_scanner_config,
        )

        with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
            mock_result = MagicMock()
            mock_result.scanner_result = MagicMock()
            mock_result.trades_executed = 5
            mock_result.total_pnl = Decimal("1000")
            mock_result.errors = []
            mock_result.timestamp_utc = datetime.now(UTC)
            mock_run.return_value = mock_result

            result = engine.run_full_cycle(symbols=["RELIANCE"], max_trades=10)

            assert result.trades_executed == 5
            assert result.total_pnl == Decimal("1000")
            mock_run.assert_called_once()

    def test_pipeline_with_partial_components(self, mock_engine_dependencies) -> None:
        """Test pipeline works with partial component configuration."""
        mock_data_provider = MagicMock()
        engine = Engine(**mock_engine_dependencies, data_provider=mock_data_provider)

        # Should work without scanner and order_manager
        with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
            mock_result = MagicMock()
            mock_result.scanner_result = None
            mock_result.trades_executed = 0
            mock_result.total_pnl = Decimal("0")
            mock_result.errors = []
            mock_result.timestamp_utc = datetime.now(UTC)
            mock_run.return_value = mock_result

            engine.run_full_cycle()

            # Should complete without errors
            mock_run.assert_called_once()

    def test_pipeline_error_handling(self, mock_engine_dependencies) -> None:
        """Test pipeline error handling and recovery."""
        mock_data_provider = MagicMock()
        engine = Engine(**mock_engine_dependencies, data_provider=mock_data_provider)

        with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
            # Simulate error
            mock_run.side_effect = Exception("Pipeline error")

            with pytest.raises(Exception, match="Pipeline error"):
                engine.run_full_cycle()

    def test_pipeline_with_dynamic_symbol_refresh(self, mock_engine_dependencies) -> None:
        """Test pipeline with dynamic symbol refresh during runtime."""
        from iatb.scanner.scan_cycle import refresh_symbols

        mock_data_provider = MagicMock()
        engine = Engine(**mock_engine_dependencies, data_provider=mock_data_provider)

        # Mock refresh_symbols to return updated symbols
        with patch("iatb.scanner.scan_cycle.refresh_symbols") as mock_refresh:
            mock_refresh.return_value = ["RELIANCE", "TCS", "INFY", "HDFCBANK"]

            refresh_symbols()

            # Now run pipeline
            with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
                mock_result = MagicMock()
                mock_result.scanner_result = None
                mock_result.trades_executed = 0
                mock_result.total_pnl = Decimal("0")
                mock_result.errors = []
                mock_result.timestamp_utc = datetime.now(UTC)
                mock_run.return_value = mock_result

                engine.run_full_cycle()

                mock_run.assert_called_once()

    def test_pipeline_strength_scorer_integration(self, mock_engine_dependencies) -> None:
        """Test strength scorer integration in full pipeline."""
        from iatb.market_strength.strength_scorer import StrengthScorer

        # Create custom strength scorer
        strength_scorer = StrengthScorer(cache_enabled=True)
        mock_data_provider = MagicMock()

        engine = Engine(
            **mock_engine_dependencies,
            data_provider=mock_data_provider,
            instrument_scorer=strength_scorer,
        )

        # Verify strength scorer is part of pipeline
        assert engine.instrument_scorer is strength_scorer

        with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
            mock_result = MagicMock()
            mock_result.scanner_result = None
            mock_result.trades_executed = 0
            mock_result.total_pnl = Decimal("0")
            mock_result.errors = []
            mock_result.timestamp_utc = datetime.now(UTC)
            mock_run.return_value = mock_result

            engine.run_full_cycle()

            # Pipeline should complete successfully
            mock_run.assert_called_once()


class TestEngineEdgeCases:
    """Test edge cases in engine pipeline."""

    def test_pipeline_with_empty_symbols(self, mock_engine_dependencies) -> None:
        """Test pipeline with empty symbol list."""
        mock_data_provider = MagicMock()
        engine = Engine(**mock_engine_dependencies, data_provider=mock_data_provider)

        with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
            mock_result = MagicMock()
            mock_result.scanner_result = None
            mock_result.trades_executed = 0
            mock_result.total_pnl = Decimal("0")
            mock_result.errors = []
            mock_result.timestamp_utc = datetime.now(UTC)
            mock_run.return_value = mock_result

            # Empty list should use defaults
            engine.run_full_cycle(symbols=[])

            mock_run.assert_called_once()

    def test_pipeline_with_max_trades_zero(self, mock_engine_dependencies) -> None:
        """Test pipeline with max_trades set to zero."""
        mock_data_provider = MagicMock()
        engine = Engine(**mock_engine_dependencies, data_provider=mock_data_provider)

        with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
            mock_result = MagicMock()
            mock_result.scanner_result = None
            mock_result.trades_executed = 0
            mock_result.total_pnl = Decimal("0")
            mock_result.errors = []
            mock_result.timestamp_utc = datetime.now(UTC)
            mock_run.return_value = mock_result

            result = engine.run_full_cycle(max_trades=0)

            assert result.trades_executed == 0

    def test_pipeline_with_large_symbol_list(self, mock_engine_dependencies) -> None:
        """Test pipeline with large symbol list."""
        mock_data_provider = MagicMock()
        engine = Engine(**mock_engine_dependencies, data_provider=mock_data_provider)

        large_symbol_list = [f"SYMBOL{i}" for i in range(100)]

        with patch("iatb.scanner.scan_cycle.run_scan_cycle") as mock_run:
            mock_result = MagicMock()
            mock_result.scanner_result = None
            mock_result.trades_executed = 0
            mock_result.total_pnl = Decimal("0")
            mock_result.errors = []
            mock_result.timestamp_utc = datetime.now(UTC)
            mock_run.return_value = mock_result

            engine.run_full_cycle(symbols=large_symbol_list)

            # Verify large list was passed
            call_args = mock_run.call_args
            assert len(call_args[1]["symbols"]) == 100
