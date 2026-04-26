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
        assert not engine.event_bus.is_running

        await engine.start()
        assert engine.event_bus.is_running

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


class TestEngineFullCycle:
    """Test engine run_full_cycle pipeline orchestration."""

    def test_run_full_cycle_delegates_to_scan_cycle(self) -> None:
        """Test that run_full_cycle delegates to run_scan_cycle."""
        from datetime import UTC, datetime

        from iatb.scanner.scan_cycle import ScanCycleResult

        engine = Engine()

        mock_result = ScanCycleResult(
            scanner_result=None,
            trades_executed=0,
            total_pnl=Decimal("0"),
            errors=[],
            timestamp_utc=datetime.now(UTC),
        )

        with patch("iatb.scanner.scan_cycle.run_scan_cycle", return_value=mock_result) as mock_run:
            result = engine.run_full_cycle()

        assert result is mock_result
        mock_run.assert_called_once_with(
            symbols=None,
            max_trades=5,
            order_manager=None,
            data_provider=None,
            scanner_config=None,
        )

    def test_run_full_cycle_passes_dependencies(self) -> None:
        """Test that run_full_cycle passes configured dependencies."""
        from datetime import UTC, datetime

        from iatb.scanner.scan_cycle import ScanCycleResult

        mock_dp = MagicMock()
        mock_om = MagicMock()
        mock_config = MagicMock()

        engine = Engine(
            data_provider=mock_dp,
            order_manager=mock_om,
            scanner_config=mock_config,
        )

        mock_result = ScanCycleResult(
            scanner_result=None,
            trades_executed=0,
            total_pnl=Decimal("0"),
            errors=[],
            timestamp_utc=datetime.now(UTC),
        )

        with patch("iatb.scanner.scan_cycle.run_scan_cycle", return_value=mock_result) as mock_run:
            result = engine.run_full_cycle(
                symbols=["RELIANCE", "TCS"],
                max_trades=3,
            )

        assert result is mock_result
        mock_run.assert_called_once_with(
            symbols=["RELIANCE", "TCS"],
            max_trades=3,
            order_manager=mock_om,
            data_provider=mock_dp,
            scanner_config=mock_config,
        )

    def test_run_full_cycle_with_custom_params(self) -> None:
        """Test run_full_cycle with custom symbols and max_trades."""
        from datetime import UTC, datetime

        from iatb.scanner.scan_cycle import ScanCycleResult

        engine = Engine()

        mock_result = ScanCycleResult(
            scanner_result=None,
            trades_executed=2,
            total_pnl=Decimal("100"),
            errors=[],
            timestamp_utc=datetime.now(UTC),
        )

        with patch("iatb.scanner.scan_cycle.run_scan_cycle", return_value=mock_result) as mock_run:
            result = engine.run_full_cycle(symbols=["INFY"], max_trades=10)

        assert result.trades_executed == 2
        mock_run.assert_called_once_with(
            symbols=["INFY"],
            max_trades=10,
            order_manager=None,
            data_provider=None,
            scanner_config=None,
        )


class TestEngineScanOnly:
    """Test engine run_scan_only method."""

    def test_run_scan_only_with_preconfigured_scanner(self) -> None:
        """Test run_scan_only uses pre-configured scanner."""
        from datetime import UTC, datetime

        from iatb.scanner.instrument_scanner import (
            ScannerResult,
            SortDirection,
        )

        mock_scanner = MagicMock()
        mock_scan_result = ScannerResult(
            gainers=[],
            losers=[],
            total_scanned=0,
            filtered_count=0,
            scan_timestamp_utc=datetime.now(UTC),
        )
        mock_scanner.scan.return_value = mock_scan_result

        engine = Engine(instrument_scanner=mock_scanner)
        result = engine.run_scan_only()

        assert result is mock_scan_result
        mock_scanner.scan.assert_called_once_with(direction=SortDirection.GAINERS)

    def test_run_scan_only_with_direction(self) -> None:
        """Test run_scan_only passes sort direction."""
        from datetime import UTC, datetime

        from iatb.scanner.instrument_scanner import (
            ScannerResult,
            SortDirection,
        )

        mock_scanner = MagicMock()
        mock_scan_result = ScannerResult(
            gainers=[],
            losers=[],
            total_scanned=0,
            filtered_count=0,
            scan_timestamp_utc=datetime.now(UTC),
        )
        mock_scanner.scan.return_value = mock_scan_result

        engine = Engine(instrument_scanner=mock_scanner)
        result = engine.run_scan_only(direction=SortDirection.LOSERS)

        assert result is mock_scan_result
        mock_scanner.scan.assert_called_once_with(direction=SortDirection.LOSERS)

    def test_run_scan_only_creates_scanner_from_data_provider(self) -> None:
        """Test run_scan_only creates scanner when only data_provider set."""
        from datetime import UTC, datetime

        from iatb.scanner.instrument_scanner import ScannerResult

        mock_dp = MagicMock()

        engine = Engine(data_provider=mock_dp)

        mock_scan_result = ScannerResult(
            gainers=[],
            losers=[],
            total_scanned=0,
            filtered_count=0,
            scan_timestamp_utc=datetime.now(UTC),
        )

        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_is_cls:
            mock_instance = MagicMock()
            mock_instance.scan.return_value = mock_scan_result
            mock_is_cls.return_value = mock_instance

            result = engine.run_scan_only(symbols=["RELIANCE"])

        assert result is mock_scan_result
        mock_is_cls.assert_called_once_with(
            config=None,
            data_provider=mock_dp,
            symbols=["RELIANCE"],
        )
        mock_instance.scan.assert_called_once()

    def test_run_scan_only_raises_without_scanner_or_provider(self) -> None:
        """Test run_scan_only raises EngineError without deps."""
        engine = Engine()

        with pytest.raises(EngineError, match="no instrument_scanner or data_provider"):
            engine.run_scan_only()

    def test_run_scan_only_no_symbols_without_scanner(self) -> None:
        """Test run_scan_only passes None symbols when creating scanner."""
        from datetime import UTC, datetime

        from iatb.scanner.instrument_scanner import ScannerResult

        mock_dp = MagicMock()
        engine = Engine(data_provider=mock_dp)

        mock_scan_result = ScannerResult(
            gainers=[],
            losers=[],
            total_scanned=0,
            filtered_count=0,
            scan_timestamp_utc=datetime.now(UTC),
        )

        with patch("iatb.scanner.instrument_scanner.InstrumentScanner") as mock_is_cls:
            mock_instance = MagicMock()
            mock_instance.scan.return_value = mock_scan_result
            mock_is_cls.return_value = mock_instance

            engine.run_scan_only()

        mock_is_cls.assert_called_once_with(
            config=None,
            data_provider=mock_dp,
            symbols=None,
        )


class TestEngineNewProperties:
    """Test new engine pipeline dependency properties."""

    def test_data_provider_property_none(self) -> None:
        """Test data_provider is None when not configured."""
        engine = Engine()
        assert engine.data_provider is None

    def test_data_provider_property_set(self) -> None:
        """Test data_provider returns configured provider."""
        mock_dp = MagicMock()
        engine = Engine(data_provider=mock_dp)
        assert engine.data_provider is mock_dp

    def test_instrument_scanner_property_none(self) -> None:
        """Test instrument_scanner is None when not configured."""
        engine = Engine()
        assert engine.instrument_scanner is None

    def test_instrument_scanner_property_set(self) -> None:
        """Test instrument_scanner returns configured scanner."""
        mock_scanner = MagicMock()
        engine = Engine(instrument_scanner=mock_scanner)
        assert engine.instrument_scanner is mock_scanner

    def test_order_manager_property_none(self) -> None:
        """Test order_manager is None when not configured."""
        engine = Engine()
        assert engine.order_manager is None

    def test_order_manager_property_set(self) -> None:
        """Test order_manager returns configured manager."""
        mock_om = MagicMock()
        engine = Engine(order_manager=mock_om)
        assert engine.order_manager is mock_om

    def test_backward_compat_two_arg_constructor(self) -> None:
        """Test that Engine(instrument_scorer, kill_switch) still works."""
        from iatb.risk.kill_switch import KillSwitch
        from iatb.selection.instrument_scorer import InstrumentScorer

        scorer = InstrumentScorer()
        ks = MagicMock(spec=KillSwitch)
        engine = Engine(instrument_scorer=scorer, kill_switch=ks)

        assert engine.instrument_scorer is scorer
        assert engine.kill_switch is ks
        assert engine.data_provider is None
        assert engine.instrument_scanner is None
        assert engine.order_manager is None
