"""
Tests for DRL signal computation.
"""

import random
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pytest
from iatb.backtesting.event_driven import EventDrivenResult
from iatb.core.exceptions import ConfigError
from iatb.selection.drl_signal import (
    BacktestConclusion,
    DRLSignalOutput,
    _derive_confidence,
    _drawdown_factor,
    _estimate_drawdown,
    _estimate_win_rate,
    _graduated_overfit_penalty,
    _safe_mean,
    _sigmoid_normalize,
    _validate_conclusion,
    compute_drl_signal,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)


class TestValidateConclusion:
    """Test BacktestConclusion validation."""

    def test_validate_conclusion_non_utc_timestamp_raises(self) -> None:
        """Test that non-UTC timestamp raises error."""
        import pytz

        # Create a non-UTC datetime (e.g., IST timezone)
        ist = pytz.timezone("Asia/Kolkata")
        non_utc_dt = datetime.now(ist)

        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=non_utc_dt,  # Non-UTC
        )
        with pytest.raises(ConfigError, match="timestamp_utc must be UTC"):
            _validate_conclusion(conclusion, datetime.now(UTC))

    def test_validate_conclusion_non_utc_current_raises(self) -> None:
        """Test that non-UTC current time raises error."""
        import pytz

        # Create a non-UTC datetime (e.g., IST timezone)
        ist = pytz.timezone("Asia/Kolkata")
        non_utc_dt = datetime.now(ist)

        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        with pytest.raises(ConfigError, match="current_utc must be UTC"):
            _validate_conclusion(conclusion, non_utc_dt)

    def test_validate_conclusion_empty_symbol_raises(self) -> None:
        """Test that empty symbol raises error."""
        conclusion = BacktestConclusion(
            instrument_symbol="   ",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        with pytest.raises(ConfigError, match="instrument_symbol cannot be empty"):
            _validate_conclusion(conclusion, datetime.now(UTC))

    def test_validate_conclusion_negative_trades_raises(self) -> None:
        """Test that negative trades raises error."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=-1,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        with pytest.raises(ConfigError, match="total_trades cannot be negative"):
            _validate_conclusion(conclusion, datetime.now(UTC))

    def test_validate_conclusion_invalid_win_rate_raises(self) -> None:
        """Test that invalid win rate raises error."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("1.5"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        with pytest.raises(ConfigError, match="win_rate must be in \\[0, 1\\]"):
            _validate_conclusion(conclusion, datetime.now(UTC))

    def test_validate_conclusion_negative_drawdown_raises(self) -> None:
        """Test that negative drawdown raises error."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("-5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        with pytest.raises(ConfigError, match="max_drawdown_pct cannot be negative"):
            _validate_conclusion(conclusion, datetime.now(UTC))

    def test_validate_conclusion_negative_overfit_ratio_raises(self) -> None:
        """Test that negative overfit ratio raises error."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("-1"),
            timestamp_utc=datetime.now(UTC),
        )
        with pytest.raises(ConfigError, match="mean_overfit_ratio cannot be negative"):
            _validate_conclusion(conclusion, datetime.now(UTC))


class TestSigmoidNormalize:
    """Test Sharpe ratio normalization."""

    def test_sigmoid_normalize_zero_sharpe(self) -> None:
        """Test normalization of zero Sharpe."""
        result = _sigmoid_normalize(Decimal("0"))
        assert result == Decimal("0.5")

    def test_sigmoid_normalize_positive_sharpe(self) -> None:
        """Test normalization of positive Sharpe."""
        result = _sigmoid_normalize(Decimal("2"))
        assert result > Decimal("0.5")
        assert result <= Decimal("1")

    def test_sigmoid_normalize_negative_sharpe(self) -> None:
        """Test normalization of negative Sharpe."""
        result = _sigmoid_normalize(Decimal("-2"))
        assert result < Decimal("0.5")
        assert result >= Decimal("0")

    def test_sigmoid_normalize_large_sharpe_clamps(self) -> None:
        """Test that very large Sharpe clamps to 1."""
        result = _sigmoid_normalize(Decimal("100"))
        assert result == Decimal("1")

    def test_sigmoid_normalize_very_negative_sharpe_clamps(self) -> None:
        """Test that very negative Sharpe clamps to near 0."""
        result = _sigmoid_normalize(Decimal("-100"))
        # Due to floating point precision, may be extremely small but not exactly 0
        assert result < Decimal("0.001")


class TestGraduatedOverfitPenalty:
    """Test overfit penalty computation."""

    def test_overfit_penalty_no_overfit_zero_penalty(self) -> None:
        """Test that no overfit results in zero penalty."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        penalty = _graduated_overfit_penalty(conclusion)
        assert penalty == Decimal("0")

    def test_overfit_penalty_mild_overfit(self) -> None:
        """Test mild overfit penalty."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=True,
            mean_overfit_ratio=Decimal("2.1"),
            timestamp_utc=datetime.now(UTC),
        )
        penalty = _graduated_overfit_penalty(conclusion)
        assert penalty < Decimal("0")
        assert penalty > Decimal("-0.1")

    def test_overfit_penalty_severe_overfit(self) -> None:
        """Test severe overfit penalty."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=True,
            mean_overfit_ratio=Decimal("10"),
            timestamp_utc=datetime.now(UTC),
        )
        penalty = _graduated_overfit_penalty(conclusion)
        assert penalty <= Decimal("-0.5")  # Max penalty


class TestDrawdownFactor:
    """Test drawdown factor computation."""

    def test_drawdown_factor_zero_drawdown(self) -> None:
        """Test that zero drawdown gives factor of 1."""
        factor = _drawdown_factor(Decimal("0"))
        assert factor == Decimal("1")

    def test_drawdown_factor_ten_percent(self) -> None:
        """Test 10% drawdown."""
        factor = _drawdown_factor(Decimal("10"))
        assert factor == Decimal("0.5")

    def test_drawdown_factor_twenty_percent_zeroes(self) -> None:
        """Test that 20% drawdown zeroes the signal."""
        factor = _drawdown_factor(Decimal("20"))
        assert factor == Decimal("0")

    def test_drawdown_factor_over_twenty_percent_clamps(self) -> None:
        """Test that >20% drawdown clamps to 0."""
        factor = _drawdown_factor(Decimal("25"))
        assert factor == Decimal("0")


class TestDeriveConfidence:
    """Test confidence derivation."""

    def test_derive_confidence_high_trades_robust(self) -> None:
        """Test high confidence with many trades and robust signals."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=150,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        confidence = _derive_confidence(conclusion, Decimal("1.0"))
        assert confidence > Decimal("0.5")
        assert confidence <= Decimal("1")

    def test_derive_confidence_low_trades(self) -> None:
        """Test low confidence with few trades."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=10,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        confidence = _derive_confidence(conclusion, Decimal("1.0"))
        assert confidence < Decimal("0.2")

    def test_derive_confidence_not_robust_halves(self) -> None:
        """Test that non-robust MC halves confidence."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=False,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        confidence = _derive_confidence(conclusion, Decimal("1.0"))
        assert confidence < Decimal("0.6")


class TestSafeMean:
    """Test safe mean computation."""

    def test_safe_mean_empty_list(self) -> None:
        """Test that empty list returns 0."""
        result = _safe_mean([])
        assert result == Decimal("0")

    def test_safe_mean_single_value(self) -> None:
        """Test mean of single value."""
        result = _safe_mean([Decimal("5")])
        assert result == Decimal("5")

    def test_safe_mean_multiple_values(self) -> None:
        """Test mean of multiple values."""
        result = _safe_mean([Decimal("1"), Decimal("2"), Decimal("3")])
        assert result == Decimal("2")


class TestEstimateWinRate:
    """Test win rate estimation."""

    def test_estimate_win_rate_zero_trades(self) -> None:
        """Test that zero trades returns 0."""
        result = _estimate_win_rate(Decimal("1000"), 0)
        assert result == Decimal("0")

    def test_estimate_win_rate_negative_trades(self) -> None:
        """Test that negative trades returns 0."""
        result = _estimate_win_rate(Decimal("1000"), -5)
        assert result == Decimal("0")

    def test_estimate_win_rate_positive_pnl(self) -> None:
        """Test positive PnL increases win rate."""
        result = _estimate_win_rate(Decimal("1000"), 10)
        assert result > Decimal("0.5")

    def test_estimate_win_rate_negative_pnl(self) -> None:
        """Test negative PnL decreases win rate."""
        result = _estimate_win_rate(Decimal("-1000"), 10)
        assert result < Decimal("0.5")


class TestEstimateDrawdown:
    """Test drawdown estimation."""

    def test_estimate_drawdown_empty_curve(self) -> None:
        """Test empty curve returns 0."""
        result = _estimate_drawdown(
            EventDrivenResult(equity_curve=[], total_pnl=Decimal("0"), trades=0),
        )
        assert result == Decimal("0")

    def test_estimate_drawdown_single_value(self) -> None:
        """Test single value returns 0."""
        result = _estimate_drawdown(
            EventDrivenResult(
                equity_curve=[Decimal("1000")],
                total_pnl=Decimal("0"),
                trades=0,
            ),
        )
        assert result == Decimal("0")

    def test_estimate_drawdown_declining_curve(self) -> None:
        """Test declining curve calculates drawdown."""
        curve = [Decimal("1000"), Decimal("900"), Decimal("800"), Decimal("700")]
        result = _estimate_drawdown(
            EventDrivenResult(equity_curve=curve, total_pnl=Decimal("0"), trades=0),
        )
        assert result == Decimal("30")  # (1000-700)/1000*100

    def test_estimate_drawdown_with_recovery(self) -> None:
        """Test drawdown with recovery."""
        curve = [Decimal("1000"), Decimal("800"), Decimal("900"), Decimal("1100")]
        result = _estimate_drawdown(
            EventDrivenResult(equity_curve=curve, total_pnl=Decimal("0"), trades=0),
        )
        # Max drawdown is 20% (1000->800), not affected by recovery
        assert result == Decimal("20")


class TestBuildConclusion:
    """Test BacktestConclusion building."""

    # Note: build_conclusion tests skipped due to complex dependencies
    # The function is tested through integration tests in other modules


class TestComputeDRLSignal:
    """Test main DRL signal computation."""

    def test_compute_drl_signal_validates(self) -> None:
        """Test that computation validates input."""
        import pytz

        # Create a non-UTC datetime (e.g., IST timezone)
        ist = pytz.timezone("Asia/Kolkata")
        non_utc_dt = datetime.now(ist)

        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=non_utc_dt,
        )
        with pytest.raises(ConfigError, match="timestamp_utc must be UTC"):
            compute_drl_signal(conclusion, datetime.now(UTC))

    def test_compute_drl_signal_returns_output(self) -> None:
        """Test that computation returns DRLSignalOutput."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        output = compute_drl_signal(conclusion, datetime.now(UTC))

        assert isinstance(output, DRLSignalOutput)
        assert 0 <= output.score <= 1
        assert 0 <= output.confidence <= 1
        assert isinstance(output.robust, bool)
        assert "oos_sharpe" in output.metadata
        assert "win_rate" in output.metadata
