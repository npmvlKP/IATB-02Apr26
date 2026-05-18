"""
Comprehensive coverage tests for drl_signal.py.

Tests DRL backtest conclusion signal for instrument selection.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.backtesting.event_driven import EventDrivenResult
from iatb.backtesting.monte_carlo import MonteCarloResult
from iatb.backtesting.walk_forward import WalkForwardFold, WalkForwardResult
from iatb.core.exceptions import ConfigError
from iatb.selection.drl_signal import (
    BacktestConclusion,
    DRLSignalOutput,
    _action_to_score,
    _drawdown_factor,
    _sigmoid_normalize,
    build_conclusion,
    compute_drl_signal,
)


class TestBacktestConclusion:
    """Test backtest conclusion dataclass."""

    def test_create_conclusion(self):
        """Test creating backtest conclusion."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("10"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )

        assert conclusion.instrument_symbol == "TEST"
        assert conclusion.monte_carlo_robust is True


class TestDRLSignalOutput:
    """Test DRL signal output dataclass."""

    def test_create_output(self):
        """Test creating DRL signal output."""
        output = DRLSignalOutput(
            score=Decimal("0.8"),
            confidence=Decimal("0.7"),
            robust=True,
            metadata={"key": "value"},
        )

        assert output.score == Decimal("0.8")
        assert output.robust is True


class TestComputeDRLSignal:
    """Test DRL signal computation."""

    def test_compute_signal_strong_sharpe(self):
        """Test computing signal with strong Sharpe ratio."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("2.0"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.7"),
            total_trades=150,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.1"),
            timestamp_utc=datetime.now(UTC),
        )

        result = compute_drl_signal(conclusion, datetime.now(UTC))

        assert isinstance(result, DRLSignalOutput)
        assert result.score > Decimal("0.5")
        assert result.robust is True

    def test_compute_signal_with_overfit_penalty(self):
        """Test computing signal with overfit penalty."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("2.0"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.7"),
            total_trades=150,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=True,
            mean_overfit_ratio=Decimal("4.0"),
            timestamp_utc=datetime.now(UTC),
        )

        result = compute_drl_signal(conclusion, datetime.now(UTC))

        assert isinstance(result, DRLSignalOutput)
        assert result.robust is False

    def test_compute_signal_high_drawdown(self):
        """Test computing signal with high drawdown."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("2.0"),
            max_drawdown_pct=Decimal("25"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.1"),
            timestamp_utc=datetime.now(UTC),
        )

        result = compute_drl_signal(conclusion, datetime.now(UTC))

        assert isinstance(result, DRLSignalOutput)
        assert result.score < Decimal("0.5")


class TestBuildConclusion:
    """Test building backtest conclusion from upstream results."""

    def test_build_conclusion_from_results(self):
        """Test building conclusion from backtest results."""
        symbol = "TEST"
        walk_forward = WalkForwardResult(
            folds=[
                WalkForwardFold(
                    fold_index=0,
                    in_sample_sharpe=Decimal("1.5"),
                    out_sample_sharpe=Decimal("1.2"),
                    overfit_ratio=Decimal("1.25"),
                    overfit_flag=False,
                )
            ],
            overfitting_detected=False,
            sampler_name="test_sampler",
        )
        monte_carlo = MonteCarloResult(
            base_sharpe=Decimal("2.0"),
            percentile_5_sharpe=Decimal("1.5"),
            robust=True,
            permutations=1000,
        )
        event_driven = EventDrivenResult(
            equity_curve=[Decimal("10000"), Decimal("10500"), Decimal("11000")],
            total_pnl=Decimal("1000"),
            trades=50,
        )
        timestamp_utc = datetime.now(UTC)

        conclusion = build_conclusion(
            symbol, walk_forward, monte_carlo, event_driven, timestamp_utc
        )

        assert conclusion.instrument_symbol == symbol
        assert conclusion.total_trades == 50
        assert conclusion.monte_carlo_robust is True

    def test_build_conclusion_empty_symbol_raises_error(self):
        """Test that empty symbol raises ConfigError."""
        walk_forward = WalkForwardResult(
            folds=[], overfitting_detected=False, sampler_name="test_sampler"
        )
        monte_carlo = MonteCarloResult(
            base_sharpe=Decimal("2.0"),
            percentile_5_sharpe=Decimal("1.5"),
            robust=True,
            permutations=1000,
        )
        event_driven = EventDrivenResult(
            equity_curve=[],
            total_pnl=Decimal("0"),
            trades=0,
        )

        with pytest.raises(ConfigError, match="symbol cannot be empty"):
            build_conclusion(
                "", walk_forward, monte_carlo, event_driven, datetime.now(UTC)
            )


class TestSigmoidNormalize:
    """Test sigmoid normalization."""

    def test_normalize_positive_sharpe(self):
        """Test normalizing positive Sharpe ratio."""
        result = _sigmoid_normalize(Decimal("2.0"))
        assert Decimal("0") <= result <= Decimal("1")

    def test_normalize_negative_sharpe(self):
        """Test normalizing negative Sharpe ratio."""
        result = _sigmoid_normalize(Decimal("-1.0"))
        assert Decimal("0") <= result <= Decimal("1")

    def test_normalize_zero_sharpe(self):
        """Test normalizing zero Sharpe ratio."""
        result = _sigmoid_normalize(Decimal("0"))
        assert Decimal("0") <= result <= Decimal("1")


class TestDrawdownFactor:
    """Test drawdown factor calculation."""

    def test_drawdown_factor_zero(self):
        """Test drawdown factor with zero drawdown."""
        result = _drawdown_factor(Decimal("0"))
        assert result == Decimal("1")

    def test_drawdown_factor_moderate(self):
        """Test drawdown factor with moderate drawdown."""
        result = _drawdown_factor(Decimal("10"))
        assert Decimal("0.5") <= result <= Decimal("1")

    def test_drawdown_factor_max(self):
        """Test drawdown factor at maximum threshold."""
        result = _drawdown_factor(Decimal("20"))
        assert result <= Decimal("1")


class TestActionToScore:
    """Test action to score mapping."""

    def test_action_hold(self):
        """Test HOLD action score."""
        result = _action_to_score(0)
        assert result == Decimal("0.2")

    def test_action_buy(self):
        """Test BUY action score."""
        result = _action_to_score(1)
        assert result == Decimal("0.8")

    def test_action_sell(self):
        """Test SELL action score."""
        result = _action_to_score(2)
        assert result == Decimal("0.2")

    def test_invalid_action_raises_error(self):
        """Test that invalid action raises ConfigError."""
        with pytest.raises(ConfigError, match="invalid action"):
            _action_to_score(3)
