"""
Comprehensive coverage tests for drl_signal.py.

Tests DRL signal computation, model inference, and error paths.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.backtesting.event_driven import EventDrivenResult
from iatb.backtesting.monte_carlo import MonteCarloResult
from iatb.backtesting.walk_forward import WalkForwardResult
from iatb.core.exceptions import ConfigError
from iatb.selection.drl_signal import (
    BacktestConclusion,
    DRLSignalOutput,
    _derive_confidence,
    _drawdown_factor,
    _graduated_overfit_penalty,
    _sigmoid_normalize,
    _validate_conclusion,
    build_conclusion,
    compute_drl_signal,
    compute_drl_signal_from_agent,
)


class TestComputeDrlSignal:
    """Test compute_drl_signal function."""

    def test_basic_signal_computation(self) -> None:
        """Test basic DRL signal computation."""
        conclusion = BacktestConclusion(
            instrument_symbol="RELIANCE",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("0.15"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        current_utc = datetime.now(UTC)
        result = compute_drl_signal(conclusion, current_utc)
        assert isinstance(result, DRLSignalOutput)
        assert Decimal("0") <= result.score <= Decimal("1")
        assert Decimal("0") <= result.confidence <= Decimal("1")

    def test_poor_performance(self) -> None:
        """Test with poor performance metrics."""
        conclusion = BacktestConclusion(
            instrument_symbol="TCS",
            out_of_sample_sharpe=Decimal("-0.5"),
            max_drawdown_pct=Decimal("0.30"),
            win_rate=Decimal("0.3"),
            total_trades=50,
            monte_carlo_robust=False,
            walk_forward_overfit_detected=True,
            mean_overfit_ratio=Decimal("5.0"),
            timestamp_utc=datetime.now(UTC),
        )
        current_utc = datetime.now(UTC)
        result = compute_drl_signal(conclusion, current_utc)
        assert isinstance(result, DRLSignalOutput)
        assert result.score < Decimal("0.5")
        assert result.robust is False

    def test_old_timestamp(self) -> None:
        """Test with old timestamp (temporal decay)."""
        from datetime import timedelta

        old_timestamp = datetime.now(UTC) - timedelta(days=30)
        conclusion = BacktestConclusion(
            instrument_symbol="INFY",
            out_of_sample_sharpe=Decimal("1.0"),
            max_drawdown_pct=Decimal("0.10"),
            win_rate=Decimal("0.55"),
            total_trades=80,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.1"),
            timestamp_utc=old_timestamp,
        )
        current_utc = datetime.now(UTC)
        result = compute_drl_signal(conclusion, current_utc)
        assert isinstance(result, DRLSignalOutput)


class TestBuildConclusion:
    """Test build_conclusion function."""

    def test_build_from_results(self) -> None:
        """Test building conclusion from backtest results."""
        walk_forward = MagicMock(spec=WalkForwardResult)
        walk_forward.out_of_sample_sharpe = Decimal("1.2")
        walk_forward.max_drawdown_pct = Decimal("0.15")
        walk_forward.win_rate = Decimal("0.6")
        walk_forward.total_trades = 100
        walk_forward.overfit_ratio = Decimal("1.5")
        walk_forward.folds = [MagicMock()]
        walk_forward.folds[0].out_sample_sharpe = Decimal("1.2")
        walk_forward.overfitting_detected = False

        monte_carlo = MagicMock(spec=MonteCarloResult)
        monte_carlo.robust = True
        monte_carlo.success_rate = Decimal("0.8")

        event_driven = MagicMock(spec=EventDrivenResult)
        event_driven.sharpe_ratio = Decimal("1.1")
        event_driven.total_pnl = Decimal("500")
        event_driven.trades = 50
        event_driven.equity_curve = [Decimal("100"), Decimal("110"), Decimal("105")]

        timestamp = datetime.now(UTC)
        conclusion = build_conclusion(
            symbol="RELIANCE",
            walk_forward=walk_forward,
            monte_carlo=monte_carlo,
            event_driven=event_driven,
            timestamp_utc=timestamp,
        )
        assert isinstance(conclusion, BacktestConclusion)
        assert conclusion.instrument_symbol == "RELIANCE"


class TestGraduatedOverfitPenalty:
    """Test _graduated_overfit_penalty function."""

    def test_no_overfit(self) -> None:
        """Test with no overfit detected."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.0"),
            max_drawdown_pct=Decimal("0.1"),
            win_rate=Decimal("0.5"),
            total_trades=50,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.0"),
            timestamp_utc=datetime.now(UTC),
        )
        penalty = _graduated_overfit_penalty(conclusion)
        assert penalty == Decimal("0")

    def test_mild_overfit(self) -> None:
        """Test with mild overfit."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.0"),
            max_drawdown_pct=Decimal("0.1"),
            win_rate=Decimal("0.5"),
            total_trades=50,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=True,
            mean_overfit_ratio=Decimal("2.1"),
            timestamp_utc=datetime.now(UTC),
        )
        penalty = _graduated_overfit_penalty(conclusion)
        assert penalty < Decimal("0")
        assert penalty > Decimal("-0.5")


class TestDrawdownFactor:
    """Test _drawdown_factor function."""

    def test_low_drawdown(self) -> None:
        """Test with low drawdown."""
        factor = _drawdown_factor(Decimal("0.05"))
        assert factor > Decimal("0.5")

    def test_high_drawdown(self) -> None:
        """Test with high drawdown."""
        factor = _drawdown_factor(Decimal("0.25"))
        assert factor < Decimal("1.0")

    def test_extreme_drawdown(self) -> None:
        """Test with extreme drawdown."""
        factor = _drawdown_factor(Decimal("0.50"))
        assert factor < Decimal("1.0")
        assert factor > Decimal("0")


class TestSigmoidNormalize:
    """Test _sigmoid_normalize function."""

    def test_positive_sharpe(self) -> None:
        """Test with positive Sharpe ratio."""
        result = _sigmoid_normalize(Decimal("1.5"))
        assert Decimal("0") <= result <= Decimal("1")

    def test_negative_sharpe(self) -> None:
        """Test with negative Sharpe ratio."""
        result = _sigmoid_normalize(Decimal("-1.5"))
        assert Decimal("0") <= result <= Decimal("1")

    def test_zero_sharpe(self) -> None:
        """Test with zero Sharpe ratio."""
        result = _sigmoid_normalize(Decimal("0"))
        assert result == Decimal("0.5")


class TestDeriveConfidence:
    """Test _derive_confidence function."""

    def test_high_confidence(self) -> None:
        """Test with high confidence factors."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.0"),
            max_drawdown_pct=Decimal("0.1"),
            win_rate=Decimal("0.5"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.0"),
            timestamp_utc=datetime.now(UTC),
        )
        confidence = _derive_confidence(conclusion, Decimal("1.0"))
        assert confidence > Decimal("0.5")

    def test_low_confidence(self) -> None:
        """Test with low confidence factors."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.0"),
            max_drawdown_pct=Decimal("0.1"),
            win_rate=Decimal("0.5"),
            total_trades=10,
            monte_carlo_robust=False,
            walk_forward_overfit_detected=True,
            mean_overfit_ratio=Decimal("3.0"),
            timestamp_utc=datetime.now(UTC),
        )
        confidence = _derive_confidence(conclusion, Decimal("1.0"))
        assert confidence < Decimal("0.5")


class TestValidateConclusion:
    """Test _validate_conclusion function."""

    def test_valid_conclusion(self) -> None:
        """Test with valid conclusion."""
        conclusion = BacktestConclusion(
            instrument_symbol="RELIANCE",
            out_of_sample_sharpe=Decimal("1.0"),
            max_drawdown_pct=Decimal("0.1"),
            win_rate=Decimal("0.5"),
            total_trades=50,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.0"),
            timestamp_utc=datetime.now(UTC),
        )
        _validate_conclusion(conclusion, datetime.now(UTC))

    def test_invalid_symbol(self) -> None:
        """Test with empty symbol raises error."""
        conclusion = BacktestConclusion(
            instrument_symbol="  ",
            out_of_sample_sharpe=Decimal("1.0"),
            max_drawdown_pct=Decimal("0.1"),
            win_rate=Decimal("0.5"),
            total_trades=50,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.0"),
            timestamp_utc=datetime.now(UTC),
        )
        with pytest.raises(ConfigError):
            _validate_conclusion(conclusion, datetime.now(UTC))

    def test_negative_trades(self) -> None:
        """Test with negative total_trades raises error."""
        conclusion = BacktestConclusion(
            instrument_symbol="RELIANCE",
            out_of_sample_sharpe=Decimal("1.0"),
            max_drawdown_pct=Decimal("0.1"),
            win_rate=Decimal("0.5"),
            total_trades=-1,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.0"),
            timestamp_utc=datetime.now(UTC),
        )
        with pytest.raises(ConfigError):
            _validate_conclusion(conclusion, datetime.now(UTC))


class TestComputeDrlSignalFromAgent:
    """Test compute_drl_signal_from_agent function."""

    def test_agent_computation(self) -> None:
        """Test DRL signal from agent prediction."""
        from unittest.mock import MagicMock

        agent = MagicMock()
        agent.has_model = True
        agent.predict_with_confidence = MagicMock(return_value=(1, Decimal("0.8")))
        observation = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]
        current_utc = datetime.now(UTC)
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.0"),
            max_drawdown_pct=Decimal("0.1"),
            win_rate=Decimal("0.5"),
            total_trades=50,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.0"),
            timestamp_utc=datetime.now(UTC),
        )
        result = compute_drl_signal_from_agent(
            agent, observation, current_utc, conclusion
        )
        assert isinstance(result, DRLSignalOutput)
        assert Decimal("0") <= result.score <= Decimal("1")
