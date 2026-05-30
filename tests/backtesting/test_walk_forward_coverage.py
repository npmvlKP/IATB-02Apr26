"""Coverage tests for iatb.backtesting.walk_forward - WalkForwardOptimizer and helpers."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from iatb.backtesting.walk_forward import (
    WalkForwardFold,
    WalkForwardOptimizer,
    WalkForwardResult,
    _default_sharpe_scorer,
    _overfit_ratio,
    _time_series_splits,
)
from iatb.core.exceptions import ConfigError


class TestWalkForwardFold:
    def test_creation(self) -> None:
        fold = WalkForwardFold(
            fold_index=1,
            in_sample_sharpe=Decimal("1.5"),
            out_sample_sharpe=Decimal("1.0"),
            overfit_ratio=Decimal("1.5"),
            overfit_flag=False,
        )
        assert fold.fold_index == 1
        assert fold.in_sample_sharpe == Decimal("1.5")
        assert fold.overfit_flag is False


class TestWalkForwardResult:
    def test_creation(self) -> None:
        fold = WalkForwardFold(
            fold_index=1,
            in_sample_sharpe=Decimal("1"),
            out_sample_sharpe=Decimal("0.5"),
            overfit_ratio=Decimal("2"),
            overfit_flag=True,
        )
        result = WalkForwardResult(
            folds=[fold],
            overfitting_detected=True,
            sampler_name="TPESampler",
        )
        assert result.overfitting_detected is True
        assert result.sampler_name == "TPESampler"


class TestDefaultSharpeScorer:
    def test_empty_returns_zero(self) -> None:
        assert _default_sharpe_scorer([]) == Decimal("0")

    def test_single_returns_zero(self) -> None:
        assert _default_sharpe_scorer([Decimal("5")]) == Decimal("0")

    def test_constant_returns_zero(self) -> None:
        assert _default_sharpe_scorer([Decimal("5"), Decimal("5")]) == Decimal("0")

    def test_varying_returns_nonzero(self) -> None:
        result = _default_sharpe_scorer([Decimal("1"), Decimal("2")])
        assert isinstance(result, Decimal)


class TestOverfitRatio:
    def test_zero_out_sample(self) -> None:
        result = _overfit_ratio(Decimal("1"), Decimal("0"))
        assert result == Decimal("1") / Decimal("0.0001")

    def test_normal_ratio(self) -> None:
        result = _overfit_ratio(Decimal("2"), Decimal("1"))
        assert result == Decimal("2")


class TestTimeSeriesSplits:
    def test_too_short_raises(self) -> None:
        with pytest.raises(ConfigError, match="returns length too short"):
            _time_series_splits([Decimal("1")] * 3, 5)

    def test_valid_splits(self) -> None:
        splits = _time_series_splits(
            [Decimal(str(i)) for i in range(12)],
            3,
        )
        assert len(splits) == 3
        for in_s, out_s in splits:
            assert len(in_s) > 0
            assert len(out_s) > 0


class TestWalkForwardOptimizer:
    def test_init_defaults(self) -> None:
        opt = WalkForwardOptimizer()
        assert opt._n_splits == 5

    def test_init_n_splits_lt_2_raises(self) -> None:
        with pytest.raises(ConfigError, match="n_splits must be >= 2"):
            WalkForwardOptimizer(n_splits=1)

    def test_run_insufficient_returns_raises(self) -> None:
        opt = WalkForwardOptimizer(n_splits=2)
        with pytest.raises(ConfigError, match="returns length insufficient"):
            opt.run([Decimal("1"), Decimal("2")])

    def test_run_success(self) -> None:
        with patch(
            "iatb.backtesting.walk_forward._initialize_tpe_sampler",
            return_value="TPESampler",
        ):
            opt = WalkForwardOptimizer(n_splits=2)
            returns = [Decimal(str(i % 10)) for i in range(20)]
            result = opt.run(returns)
            assert isinstance(result, WalkForwardResult)
            assert len(result.folds) == 2
            assert result.sampler_name == "TPESampler"

    def test_run_overfitting_detected(self) -> None:
        with patch(
            "iatb.backtesting.walk_forward._initialize_tpe_sampler",
            return_value="TPESampler",
        ):
            opt = WalkForwardOptimizer(n_splits=2)
            returns = [Decimal(str(i % 5)) for i in range(20)]
            result = opt.run(returns)
            assert isinstance(result.overfitting_detected, bool)


class TestInitializeTpeSampler:
    def test_optuna_missing_raises(self) -> None:
        with patch.dict("sys.modules", {"optuna": None}):
            from iatb.backtesting.walk_forward import _initialize_tpe_sampler

            with pytest.raises(ConfigError, match="optuna dependency"):
                _initialize_tpe_sampler()
