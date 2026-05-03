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
    _action_to_score,
    _derive_confidence,
    _drawdown_factor,
    _estimate_drawdown,
    _estimate_win_rate,
    _graduated_overfit_penalty,
    _safe_mean,
    _sigmoid_normalize,
    _validate_conclusion,
    compute_drl_signal,
    compute_drl_signal_from_agent,
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

    def test_compute_drl_signal_robust_flag_true_when_both_robust(self) -> None:
        """Test that robust flag is True when MC robust and no overfit."""
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
        assert output.robust is True

    def test_compute_drl_signal_robust_flag_false_when_mc_not_robust(self) -> None:
        """Test that robust flag is False when MC not robust."""
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
        output = compute_drl_signal(conclusion, datetime.now(UTC))
        assert output.robust is False

    def test_compute_drl_signal_robust_flag_false_when_overfit_detected(self) -> None:
        """Test that robust flag is False when overfit detected."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=True,
            mean_overfit_ratio=Decimal("2.5"),
            timestamp_utc=datetime.now(UTC),
        )
        output = compute_drl_signal(conclusion, datetime.now(UTC))
        assert output.robust is False

    def test_compute_drl_signal_metadata_contains_all_fields(self) -> None:
        """Test that metadata contains all expected fields."""
        conclusion = BacktestConclusion(
            instrument_symbol="RELIANCE",
            out_of_sample_sharpe=Decimal("2.5"),
            max_drawdown_pct=Decimal("8.5"),
            win_rate=Decimal("0.65"),
            total_trades=150,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.1"),
            timestamp_utc=datetime.now(UTC),
        )
        output = compute_drl_signal(conclusion, datetime.now(UTC))

        expected_keys = {
            "oos_sharpe",
            "max_drawdown_pct",
            "win_rate",
            "total_trades",
            "mc_robust",
            "wf_overfit",
        }
        assert set(output.metadata.keys()) == expected_keys
        assert output.metadata["oos_sharpe"] == "2.5"
        assert output.metadata["max_drawdown_pct"] == "8.5"
        assert output.metadata["win_rate"] == "0.65"
        assert output.metadata["total_trades"] == "150"
        assert output.metadata["mc_robust"] == "1"
        assert output.metadata["wf_overfit"] == "0"

    def test_compute_drl_signal_applies_temporal_decay(self) -> None:
        """Test that signal score decays over time."""
        from datetime import timedelta

        # Old conclusion (30 days ago)
        old_time = datetime.now(UTC) - timedelta(days=30)
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("2.0"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.7"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=old_time,
        )
        output = compute_drl_signal(conclusion, datetime.now(UTC))
        # Score should be significantly reduced due to decay
        assert output.score < Decimal("0.5")

    def test_compute_drl_signal_no_decay_when_recent(self) -> None:
        """Test that recent signal has minimal decay."""
        from datetime import timedelta

        # Recent conclusion (1 hour ago)
        recent_time = datetime.now(UTC) - timedelta(hours=1)
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("2.0"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.7"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=recent_time,
        )
        output = compute_drl_signal(conclusion, datetime.now(UTC))
        # Recent signal should have good score (minimal decay)
        assert output.score > Decimal("0.5")

    def test_compute_drl_signal_zero_sharpe(self) -> None:
        """Test zero Sharpe ratio."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("0"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.5"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.2"),
            timestamp_utc=datetime.now(UTC),
        )
        output = compute_drl_signal(conclusion, datetime.now(UTC))
        # Zero Sharpe: sigmoid(0)=0.5, robust=1.0, drawdown=0.75, score=0.5*1.0*0.75=0.375
        assert output.score == Decimal("0.3750")

    def test_compute_drl_signal_very_high_sharpe(self) -> None:
        """Test very high Sharpe ratio."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("10"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.8"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.0"),
            timestamp_utc=datetime.now(UTC),
        )
        output = compute_drl_signal(conclusion, datetime.now(UTC))
        # High Sharpe gives good score
        assert output.score > Decimal("0.6")

    def test_derive_confidence_overfit_halves(self) -> None:
        """Test that overfit detection halves confidence."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=True,
            mean_overfit_ratio=Decimal("2.5"),
            timestamp_utc=datetime.now(UTC),
        )
        confidence = _derive_confidence(conclusion, Decimal("1.0"))
        # Confidence should be halved due to overfit
        assert confidence < Decimal("0.6")

    def test_derive_confidence_both_not_robust_quarters(self) -> None:
        """Test that both not robust quarters confidence."""
        conclusion = BacktestConclusion(
            instrument_symbol="TEST",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=100,
            monte_carlo_robust=False,
            walk_forward_overfit_detected=True,
            mean_overfit_ratio=Decimal("2.5"),
            timestamp_utc=datetime.now(UTC),
        )
        confidence = _derive_confidence(conclusion, Decimal("1.0"))
        # Confidence should be quartered (0.5 * 0.5)
        assert confidence < Decimal("0.3")

    def test_derive_confidence_applies_decay(self) -> None:
        """Test that confidence is affected by decay."""
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
        confidence_with_decay = _derive_confidence(conclusion, Decimal("0.5"))
        confidence_no_decay = _derive_confidence(conclusion, Decimal("1.0"))
        assert confidence_with_decay < confidence_no_decay


class TestComputeDRLSignalFromAgent:
    """Test DRL signal computation from RL agent."""

    def test_action_to_score_mapping(self) -> None:
        """Test action to score mapping."""

        # HOLD -> 0.2
        assert _action_to_score(0) == Decimal("0.2")
        # BUY -> 0.8
        assert _action_to_score(1) == Decimal("0.8")
        # SELL -> 0.2
        assert _action_to_score(2) == Decimal("0.2")
        # Invalid action -> raises ConfigError
        with pytest.raises(ConfigError):
            _action_to_score(3)

    def test_compute_drl_signal_from_agent_with_model(self) -> None:
        """Test DRL signal computation when agent has a trained model."""
        from unittest.mock import Mock

        # Mock RLAgent with model
        mock_agent = Mock()
        mock_agent.has_model = True
        mock_agent.predict_with_confidence.return_value = (
            1,
            Decimal("0.9"),
        )  # BUY with high confidence

        observation = [Decimal("0.5"), Decimal("0.3")]
        current_utc = datetime.now(UTC)

        result = compute_drl_signal_from_agent(mock_agent, observation, current_utc)

        # Verify agent method was called
        mock_agent.predict_with_confidence.assert_called_once_with(observation)

        # Verify result
        assert isinstance(result, DRLSignalOutput)
        # BUY action (0.8) with high confidence (0.9) should give score close to 0.8
        # score = base_score * confidence + 0.5 * (1 - confidence)
        # score = 0.8 * 0.9 + 0.5 * 0.1 = 0.72 + 0.05 = 0.77
        assert result.score > Decimal("0.7")
        assert result.score < Decimal("0.8")
        assert result.confidence == Decimal("0.9")
        assert result.robust is False  # From agent source
        assert result.metadata["source"] == "rl_agent"
        assert result.metadata["action"] == "1"

    def test_compute_drl_signal_from_agent_without_model_fallback(self) -> None:
        """Test fallback to backtest conclusion when agent has no model."""
        from unittest.mock import Mock

        # Mock RLAgent without model
        mock_agent = Mock()
        mock_agent.has_model = False

        # Create a valid backtest conclusion
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

        observation = [Decimal("0.5"), Decimal("0.3")]
        current_utc = datetime.now(UTC)

        # Import the function we're testing
        from iatb.selection.drl_signal import compute_drl_signal, compute_drl_signal_from_agent

        result = compute_drl_signal_from_agent(mock_agent, observation, current_utc, conclusion)

        # Should fall back to regular compute_drl_signal
        assert isinstance(result, DRLSignalOutput)
        expected = compute_drl_signal(conclusion, current_utc)
        assert result == expected

    def test_compute_drl_signal_from_agent_without_model_no_fallback_raises(self) -> None:
        """Test that missing conclusion when no model raises error."""
        from unittest.mock import Mock

        # Mock RLAgent without model
        mock_agent = Mock()
        mock_agent.has_model = False

        observation = [Decimal("0.5"), Decimal("0.3")]
        current_utc = datetime.now(UTC)

        # Import the function we're testing
        from iatb.selection.drl_signal import compute_drl_signal_from_agent

        # Should raise ConfigError when no conclusion provided for fallback
        with pytest.raises(
            ConfigError,
            match="Fallback to backtest conclusion requires conclusion",
        ):
            compute_drl_signal_from_agent(mock_agent, observation, current_utc)
