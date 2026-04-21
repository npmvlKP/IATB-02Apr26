"""
Tests for engine orchestrator.
"""

import asyncio
import random
from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch
from iatb.core.engine import Engine
from iatb.core.event_bus import EventBus
from iatb.core.exceptions import EngineError

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class TestEngineLifecycle:
    """Test engine lifecycle."""

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        """Test starting and stopping engine."""
        engine = Engine()
        assert not engine.is_running

        await engine.start()
        assert engine.is_running

        await engine.stop()
        assert not engine.is_running

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        """Test that start can be called multiple times."""
        engine = Engine()
        await engine.start()
        await engine.start()  # Should not raise
        assert engine.is_running
        await engine.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        """Test that stop can be called multiple times."""
        engine = Engine()
        await engine.start()
        await engine.stop()
        await engine.stop()  # Should not raise
        assert not engine.is_running


class TestEngineEventBus:
    """Test engine event bus integration."""

    @pytest.mark.asyncio
    async def test_event_bus_property(self) -> None:
        """Test that engine has event bus."""
        engine = Engine()
        assert isinstance(engine.event_bus, EventBus)

    @pytest.mark.asyncio
    async def test_event_bus_started_on_engine_start(self) -> None:
        """Test that event bus starts when engine starts."""
        engine = Engine()
        assert not engine.event_bus._running

        await engine.start()
        assert engine.event_bus._running

        await engine.stop()


class TestEngineTasks:
    """Test engine task management."""

    @pytest.mark.asyncio
    async def test_run_task(self) -> None:
        """Test running a task in engine."""
        engine = Engine()
        await engine.start()

        task_completed = False

        async def dummy_task() -> None:
            nonlocal task_completed
            await asyncio.sleep(0.01)
            task_completed = True

        await engine.run_task(dummy_task())
        await asyncio.sleep(0.02)  # Wait for task to complete

        assert task_completed
        await engine.stop()

    @pytest.mark.asyncio
    async def test_run_task_not_running_raises_error(self) -> None:
        """Test that running task when engine not started raises error."""
        engine = Engine()

        async def dummy_task() -> None:
            pass

        coro = dummy_task()
        with pytest.raises(EngineError, match="Engine not running"):
            await engine.run_task(coro)

    @pytest.mark.asyncio
    async def test_tasks_cancelled_on_stop(self) -> None:
        """Test that tasks are cancelled when engine stops."""
        engine = Engine()
        await engine.start()

        task_cancelled = False

        async def long_running_task() -> None:
            nonlocal task_cancelled
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                task_cancelled = True
                raise

        await engine.run_task(long_running_task())
        await asyncio.sleep(0.01)  # Let task start

        await engine.stop()
        await asyncio.sleep(0.01)  # Let cancellation propagate

        assert task_cancelled

    @pytest.mark.asyncio
    async def test_multiple_tasks(self) -> None:
        """Test running multiple tasks."""
        engine = Engine()
        await engine.start()

        completed_tasks = []

        async def task(n: int) -> None:
            await asyncio.sleep(0.01)
            completed_tasks.append(n)

        for i in range(3):
            await engine.run_task(task(i))

        await asyncio.sleep(0.02)  # Wait for all tasks

        assert len(completed_tasks) == 3
        await engine.stop()


class TestEngineProperties:
    """Test engine properties."""

    def test_instrument_scorer_property(self) -> None:
        """Test instrument_scorer property."""
        from iatb.selection.instrument_scorer import InstrumentScorer

        scorer = InstrumentScorer()
        engine = Engine(instrument_scorer=scorer)

        assert engine.instrument_scorer is scorer

    def test_default_instrument_scorer(self) -> None:
        """Test that engine creates default scorer if none provided."""
        engine = Engine()
        assert engine.instrument_scorer is not None

    def test_kill_switch_property_none(self) -> None:
        """Test kill_switch property when not configured."""
        engine = Engine()
        assert engine.kill_switch is None

    def test_engage_kill_switch_without_config_raises_error(self) -> None:
        """Test engaging kill switch when not configured raises error."""
        engine = Engine()

        with pytest.raises(EngineError, match="no kill switch configured"):
            engine.engage_kill_switch("Test reason")

    def test_disengage_kill_switch_without_config_raises_error(self) -> None:
        """Test disengaging kill switch when not configured raises error."""
        engine = Engine()

        with pytest.raises(EngineError, match="no kill switch configured"):
            engine.disengage_kill_switch()


class TestEngineSelectionCycle:
    """Test engine selection cycle functionality."""

    def test_select_instruments_calls_scorer(self) -> None:
        """Test that select_instruments delegates to scorer."""
        from iatb.core.enums import Exchange
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.selection.instrument_scorer import InstrumentSignals, SelectionResult

        engine = Engine()

        # Create mock signals with correct structure
        from iatb.market_strength.strength_scorer import StrengthInputs
        from iatb.selection.drl_signal import DRLSignalOutput
        from iatb.selection.sentiment_signal import SentimentSignalOutput
        from iatb.selection.strength_signal import StrengthSignalOutput
        from iatb.selection.volume_profile_signal import VolumeProfileSignalOutput

        mock_sentiment = MagicMock(spec=SentimentSignalOutput)
        mock_sentiment.score = Decimal("0.6")
        mock_sentiment.confidence = Decimal("0.8")

        mock_strength = MagicMock(spec=StrengthSignalOutput)
        mock_strength.score = Decimal("0.75")
        mock_strength.confidence = Decimal("0.7")

        mock_volume_profile = MagicMock(spec=VolumeProfileSignalOutput)
        mock_volume_profile.score = Decimal("0.7")
        mock_volume_profile.confidence = Decimal("0.75")

        mock_drl = MagicMock(spec=DRLSignalOutput)
        mock_drl.score = Decimal("0.8")
        mock_drl.confidence = Decimal("0.9")

        mock_strength_inputs = MagicMock(spec=StrengthInputs)

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
        correlations = {}

        # Mock the scorer's return value
        mock_result = MagicMock(spec=SelectionResult)
        mock_result.selected = []
        mock_result.filtered_count = 0
        mock_result.total_candidates = 1
        engine._scorer.score_and_select = MagicMock(return_value=mock_result)

        result = engine.select_instruments(signals, regime, correlations)

        assert result == mock_result
        engine._scorer.score_and_select.assert_called_once_with(signals, regime, correlations)

    def test_run_selection_cycle_full_pipeline(self) -> None:
        """Test full selection cycle pipeline."""
        from iatb.core.enums import Exchange, OrderSide
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

        engine = Engine()

        # Create mock signals with correct structure
        mock_sentiment = MagicMock(spec=SentimentSignalOutput)
        mock_sentiment.score = Decimal("0.6")
        mock_sentiment.confidence = Decimal("0.8")

        mock_strength = MagicMock(spec=StrengthSignalOutput)
        mock_strength.score = Decimal("0.75")
        mock_strength.confidence = Decimal("0.7")

        mock_volume_profile = MagicMock(spec=VolumeProfileSignalOutput)
        mock_volume_profile.score = Decimal("0.7")
        mock_volume_profile.confidence = Decimal("0.75")

        mock_drl = MagicMock(spec=DRLSignalOutput)
        mock_drl.score = Decimal("0.8")
        mock_drl.confidence = Decimal("0.9")

        mock_strength_inputs = MagicMock(spec=StrengthInputs)

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

        # Create strength inputs
        strength_by_symbol = {"RELIANCE": MagicMock(spec=StrengthInputs)}

        regime = MarketRegime.BULL
        side = OrderSide.BUY

        # Mock the scorer's return value
        mock_selection = MagicMock(spec=SelectionResult)
        mock_selection.selected = []
        mock_selection.filtered_count = 0
        mock_selection.total_candidates = 1
        engine._scorer.score_and_select = MagicMock(return_value=mock_selection)

        # Mock build_strategy_contexts
        mock_contexts = [MagicMock()]
        with patch(
            "iatb.core.engine.build_strategy_contexts",
            return_value=mock_contexts,
        ) as mock_build:
            result = engine.run_selection_cycle(
                signals=signals,
                regime=regime,
                strength_by_symbol=strength_by_symbol,
                side=side,
            )

        assert result == mock_contexts
        engine._scorer.score_and_select.assert_called_once()
        mock_build.assert_called_once()

    def test_run_selection_cycle_async(self) -> None:
        """Test async variant of selection cycle."""
        import asyncio

        from iatb.core.enums import Exchange, OrderSide
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

        async def async_test() -> None:
            engine = Engine()

            # Create mock signals with correct structure
            mock_sentiment = MagicMock(spec=SentimentSignalOutput)
            mock_sentiment.score = Decimal("0.6")
            mock_sentiment.confidence = Decimal("0.8")

            mock_strength = MagicMock(spec=StrengthSignalOutput)
            mock_strength.score = Decimal("0.75")
            mock_strength.confidence = Decimal("0.7")

            mock_volume_profile = MagicMock(spec=VolumeProfileSignalOutput)
            mock_volume_profile.score = Decimal("0.7")
            mock_volume_profile.confidence = Decimal("0.75")

            mock_drl = MagicMock(spec=DRLSignalOutput)
            mock_drl.score = Decimal("0.8")
            mock_drl.confidence = Decimal("0.9")

            mock_strength_inputs = MagicMock(spec=StrengthInputs)

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

            strength_by_symbol = {"RELIANCE": MagicMock(spec=StrengthInputs)}

            regime = MarketRegime.BULL
            side = OrderSide.BUY

            mock_selection = MagicMock(spec=SelectionResult)
            mock_selection.selected = []
            mock_selection.filtered_count = 0
            mock_selection.total_candidates = 1
            engine._scorer.score_and_select = MagicMock(return_value=mock_selection)

            with patch("iatb.core.engine.build_strategy_contexts") as mock_build:
                mock_contexts = [MagicMock()]
                mock_build.return_value = mock_contexts

                result = await engine.run_selection_cycle_async(
                    signals=signals,
                    regime=regime,
                    strength_by_symbol=strength_by_symbol,
                    side=side,
                )

            assert result == mock_contexts
            engine._scorer.score_and_select.assert_called_once()

        asyncio.run(async_test())

    def test_run_selection_cycle_with_correlations(self) -> None:
        """Test selection cycle with correlation filtering."""
        from iatb.core.enums import Exchange, OrderSide
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

        engine = Engine()

        # Create mock signals for two instruments
        def create_mock_signals(
            symbol: str,
            scores: tuple[Decimal, Decimal, Decimal, Decimal],
        ) -> InstrumentSignals:
            mock_sentiment = MagicMock(spec=SentimentSignalOutput)
            mock_sentiment.score = scores[0]
            mock_sentiment.confidence = Decimal("0.8")

            mock_strength = MagicMock(spec=StrengthSignalOutput)
            mock_strength.score = scores[1]
            mock_strength.confidence = Decimal("0.7")

            mock_volume_profile = MagicMock(spec=VolumeProfileSignalOutput)
            mock_volume_profile.score = scores[2]
            mock_volume_profile.confidence = Decimal("0.75")

            mock_drl = MagicMock(spec=DRLSignalOutput)
            mock_drl.score = scores[3]
            mock_drl.confidence = Decimal("0.9")

            mock_strength_inputs = MagicMock(spec=StrengthInputs)

            return InstrumentSignals(
                symbol=symbol,
                exchange=Exchange.NSE,
                sentiment=mock_sentiment,
                strength=mock_strength,
                volume_profile=mock_volume_profile,
                drl=mock_drl,
                strength_inputs=mock_strength_inputs,
            )

        signals = [
            create_mock_signals(
                "RELIANCE",
                (Decimal("0.8"), Decimal("0.7"), Decimal("0.6"), Decimal("0.75")),
            ),
            create_mock_signals(
                "TCS",
                (Decimal("0.85"), Decimal("0.75"), Decimal("0.65"), Decimal("0.78")),
            ),
        ]

        regime = MarketRegime.BULL
        side = OrderSide.BUY
        correlations = {("RELIANCE", "TCS"): Decimal("0.9")}  # High correlation

        mock_selection = MagicMock(spec=SelectionResult)
        mock_selection.selected = []
        mock_selection.filtered_count = 2
        mock_selection.total_candidates = 2
        engine._scorer.score_and_select = MagicMock(return_value=mock_selection)

        with patch("iatb.core.engine.build_strategy_contexts") as mock_build:
            mock_contexts = [MagicMock()]
            mock_build.return_value = mock_contexts

            result = engine.run_selection_cycle(
                signals=signals,
                regime=regime,
                side=side,
                correlations=correlations,
            )

        assert len(result) == 1
        engine._scorer.score_and_select.assert_called_once_with(signals, regime, correlations)

    def test_run_selection_cycle_empty_signals(self) -> None:
        """Test selection cycle with empty signals."""
        from iatb.market_strength.regime_detector import MarketRegime
        from iatb.selection.instrument_scorer import SelectionResult

        engine = Engine()

        signals: list = []
        regime = MarketRegime.BULL

        mock_selection = MagicMock(spec=SelectionResult)
        mock_selection.selected = []
        mock_selection.filtered_count = 0
        mock_selection.total_candidates = 0
        engine._scorer.score_and_select = MagicMock(return_value=mock_selection)

        with patch("iatb.core.engine.build_strategy_contexts") as mock_build:
            mock_build.return_value = []

            result = engine.run_selection_cycle(signals=signals, regime=regime)

        assert result == []
        engine._scorer.score_and_select.assert_called_once()

    def test_engage_kill_switch_with_config(self) -> None:
        """Test engaging kill switch when configured."""
        from iatb.risk.kill_switch import KillSwitch

        mock_kill_switch = MagicMock(spec=KillSwitch)
        engine = Engine(kill_switch=mock_kill_switch)

        engine.engage_kill_switch("Test reason")

        mock_kill_switch.engage.assert_called_once()
        # Verify the timestamp argument is a datetime
        assert mock_kill_switch.engage.call_args[0][0] == "Test reason"
        assert mock_kill_switch.engage.call_args[0][1] is not None

    def test_disengage_kill_switch_with_config(self) -> None:
        """Test disengaging kill switch when configured."""
        from iatb.risk.kill_switch import KillSwitch

        mock_kill_switch = MagicMock(spec=KillSwitch)
        engine = Engine(kill_switch=mock_kill_switch)

        engine.disengage_kill_switch()

        mock_kill_switch.disengage.assert_called_once()
        # Verify the timestamp argument is a datetime
        assert mock_kill_switch.disengage.call_args[0][0] is not None
