"""Tests for selection/drl_signal.py — DRL signal computation."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.drl_signal import (
    BacktestConclusion,
    DRLSignalOutput,
    _action_to_score,
    _derive_confidence,
    _drawdown_factor,
    _graduated_overfit_penalty,
    _sigmoid_normalize,
    _validate_conclusion,
    compute_drl_signal,
    compute_drl_signal_from_agent,
)


def _conclusion(
    oos_sharpe: Decimal = Decimal("1.5"),
    mc_robust: bool = True,
    wf_overfit: bool = False,
    overfit_ratio: Decimal = Decimal("1.5"),
    max_dd: Decimal = Decimal("5"),
    win_rate: Decimal = Decimal("0.6"),
    trades: int = 50,
    ts_minutes_ago: int = 10,
) -> BacktestConclusion:
    now = datetime.now(UTC)
    ts = now - timedelta(minutes=ts_minutes_ago)
    return BacktestConclusion(
        instrument_symbol="RELIANCE",
        out_of_sample_sharpe=oos_sharpe,
        max_drawdown_pct=max_dd,
        win_rate=win_rate,
        total_trades=trades,
        monte_carlo_robust=mc_robust,
        walk_forward_overfit_detected=wf_overfit,
        mean_overfit_ratio=overfit_ratio,
        timestamp_utc=ts,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TestValidateConclusion:
    def test_non_utc_timestamp_raises(self) -> None:
        c = BacktestConclusion(
            instrument_symbol="RELIANCE",
            out_of_sample_sharpe=Decimal("1.5"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.6"),
            total_trades=20,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1.5"),
            timestamp_utc=datetime(2024, 1, 1),
        )
        with pytest.raises(ConfigError, match="timestamp_utc must be UTC"):
            _validate_conclusion(c, datetime(2024, 1, 1, tzinfo=UTC))

    def test_non_utc_current_raises(self) -> None:
        c = _conclusion()
        with pytest.raises(ConfigError, match="current_utc must be UTC"):
            _validate_conclusion(c, datetime(2024, 1, 1))

    def test_empty_symbol_raises(self) -> None:
        now = _utc_now()
        c = BacktestConclusion(
            instrument_symbol="  ",
            out_of_sample_sharpe=Decimal("1"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.5"),
            total_trades=10,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1"),
            timestamp_utc=now,
        )
        with pytest.raises(ConfigError, match="instrument_symbol cannot be empty"):
            _validate_conclusion(c, now)

    def test_negative_trades_raises(self) -> None:
        now = _utc_now()
        c = BacktestConclusion(
            instrument_symbol="X",
            out_of_sample_sharpe=Decimal("1"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.5"),
            total_trades=-1,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1"),
            timestamp_utc=now,
        )
        with pytest.raises(ConfigError, match="total_trades cannot be negative"):
            _validate_conclusion(c, now)

    def test_win_rate_out_of_range(self) -> None:
        now = _utc_now()
        c = BacktestConclusion(
            instrument_symbol="X",
            out_of_sample_sharpe=Decimal("1"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("1.5"),
            total_trades=10,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1"),
            timestamp_utc=now,
        )
        with pytest.raises(ConfigError, match="win_rate must be in"):
            _validate_conclusion(c, now)

    def test_negative_drawdown_raises(self) -> None:
        now = _utc_now()
        c = BacktestConclusion(
            instrument_symbol="X",
            out_of_sample_sharpe=Decimal("1"),
            max_drawdown_pct=Decimal("-5"),
            win_rate=Decimal("0.5"),
            total_trades=10,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("1"),
            timestamp_utc=now,
        )
        with pytest.raises(ConfigError, match="max_drawdown_pct cannot be negative"):
            _validate_conclusion(c, now)

    def test_negative_overfit_ratio_raises(self) -> None:
        now = _utc_now()
        c = BacktestConclusion(
            instrument_symbol="X",
            out_of_sample_sharpe=Decimal("1"),
            max_drawdown_pct=Decimal("5"),
            win_rate=Decimal("0.5"),
            total_trades=10,
            monte_carlo_robust=True,
            walk_forward_overfit_detected=False,
            mean_overfit_ratio=Decimal("-1"),
            timestamp_utc=now,
        )
        with pytest.raises(ConfigError, match="mean_overfit_ratio cannot be negative"):
            _validate_conclusion(c, now)


class TestSigmoidNormalize:
    def test_high_sharpe(self) -> None:
        result = _sigmoid_normalize(Decimal("3"))
        assert result > Decimal("0.9")

    def test_low_sharpe(self) -> None:
        result = _sigmoid_normalize(Decimal("-3"))
        assert result < Decimal("0.1")

    def test_zero_sharpe(self) -> None:
        result = _sigmoid_normalize(Decimal("0"))
        assert result == Decimal("0.5")


class TestDrawdownFactor:
    def test_zero_drawdown(self) -> None:
        assert _drawdown_factor(Decimal("0")) == Decimal("1")

    def test_max_drawdown(self) -> None:
        assert _drawdown_factor(Decimal("20")) == Decimal("0")

    def test_moderate_drawdown(self) -> None:
        result = _drawdown_factor(Decimal("10"))
        assert Decimal("0") < result < Decimal("1")


class TestGraduatedOverfitPenalty:
    def test_no_overfit(self) -> None:
        c = _conclusion(wf_overfit=False)
        assert _graduated_overfit_penalty(c) == Decimal("0")

    def test_mild_overfit(self) -> None:
        c = _conclusion(wf_overfit=True, overfit_ratio=Decimal("2.5"))
        result = _graduated_overfit_penalty(c)
        assert Decimal("-0.5") <= result < Decimal("0")

    def test_severe_overfit_capped(self) -> None:
        c = _conclusion(wf_overfit=True, overfit_ratio=Decimal("10"))
        result = _graduated_overfit_penalty(c)
        assert result == Decimal("-0.5")


class TestDeriveConfidence:
    def test_high_trades_robust(self) -> None:
        c = _conclusion(trades=100, mc_robust=True, wf_overfit=False)
        result = _derive_confidence(c, Decimal("1"))
        assert result > Decimal("0")

    def test_low_trades(self) -> None:
        c = _conclusion(trades=5, mc_robust=False, wf_overfit=True)
        result = _derive_confidence(c, Decimal("1"))
        assert result < Decimal("1")


class TestComputeDrlSignal:
    def test_robust_conclusion(self) -> None:
        c = _conclusion(mc_robust=True, wf_overfit=False)
        result = compute_drl_signal(c, _utc_now())
        assert isinstance(result, DRLSignalOutput)
        assert Decimal("0") <= result.score <= Decimal("1")
        assert result.robust is True

    def test_non_robust_conclusion(self) -> None:
        c = _conclusion(mc_robust=False, wf_overfit=True)
        result = compute_drl_signal(c, _utc_now())
        assert result.robust is False

    def test_metadata_populated(self) -> None:
        c = _conclusion()
        result = compute_drl_signal(c, _utc_now())
        assert "oos_sharpe" in result.metadata
        assert "mc_robust" in result.metadata

    def test_high_drawdown_reduces_score(self) -> None:
        c_low = _conclusion(max_dd=Decimal("2"))
        c_high = _conclusion(max_dd=Decimal("18"))
        now = _utc_now()
        result_low = compute_drl_signal(c_low, now)
        result_high = compute_drl_signal(c_high, now)
        assert result_low.score > result_high.score


class TestActionToScore:
    def test_hold(self) -> None:
        assert _action_to_score(0) == Decimal("0.2")

    def test_buy(self) -> None:
        assert _action_to_score(1) == Decimal("0.8")

    def test_sell(self) -> None:
        assert _action_to_score(2) == Decimal("0.2")

    def test_invalid_action(self) -> None:
        with pytest.raises(ConfigError, match="invalid action"):
            _action_to_score(5)


class TestComputeDrlSignalFromAgent:
    def test_agent_with_model(self) -> None:
        agent = MagicMock()
        agent.has_model = True
        agent.predict_with_confidence.return_value = (1, Decimal("0.8"))
        result = compute_drl_signal_from_agent(agent, [Decimal("0.5")], _utc_now())
        assert isinstance(result, DRLSignalOutput)
        assert result.metadata["source"] == "rl_agent"

    def test_agent_no_model_with_conclusion(self) -> None:
        agent = MagicMock()
        agent.has_model = False
        c = _conclusion()
        result = compute_drl_signal_from_agent(
            agent, [Decimal("0.5")], _utc_now(), conclusion=c
        )
        assert isinstance(result, DRLSignalOutput)

    def test_agent_no_model_no_conclusion_raises(self) -> None:
        agent = MagicMock()
        agent.has_model = False
        with pytest.raises(ConfigError, match="Fallback to backtest conclusion"):
            compute_drl_signal_from_agent(agent, [Decimal("0.5")], _utc_now())
