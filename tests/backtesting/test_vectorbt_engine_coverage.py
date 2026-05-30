"""Coverage tests for iatb.backtesting.vectorbt_engine - VectorBTEngine and dataclasses."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from iatb.backtesting.vectorbt_engine import (
    BacktestResult,
    MonteCarloResult,
    VectorBTConfig,
    VectorBTEngine,
)
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError


class TestVectorBTConfig:
    def test_defaults(self) -> None:
        config = VectorBTConfig()
        assert config.exchange == Exchange.NSE
        assert config.initial_capital == Decimal("100000")

    def test_zero_capital_raises(self) -> None:
        with pytest.raises(ConfigError, match="initial_capital must be positive"):
            VectorBTConfig(initial_capital=Decimal("0"))

    def test_negative_capital_raises(self) -> None:
        with pytest.raises(ConfigError, match="initial_capital must be positive"):
            VectorBTConfig(initial_capital=Decimal("-100"))

    def test_negative_slippage_raises(self) -> None:
        with pytest.raises(ConfigError, match="slippage_pct cannot be negative"):
            VectorBTConfig(slippage_pct=Decimal("-0.1"))

    def test_negative_commission_raises(self) -> None:
        with pytest.raises(ConfigError, match="commission_pct cannot be negative"):
            VectorBTConfig(commission_pct=Decimal("-0.1"))

    def test_composite_score_below_zero_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_composite_score"):
            VectorBTConfig(min_composite_score=Decimal("-0.1"))

    def test_composite_score_above_one_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_composite_score"):
            VectorBTConfig(min_composite_score=Decimal("1.1"))

    def test_zero_simulations_raises(self) -> None:
        with pytest.raises(ConfigError, match="num_simulations must be positive"):
            VectorBTConfig(num_simulations=0)

    def test_valid_boundary_values(self) -> None:
        config = VectorBTConfig(
            min_composite_score=Decimal("0"), min_exit_probability=Decimal("1")
        )
        assert config.min_composite_score == Decimal("0")


class TestVectorBTEngineLoaders:
    def test_load_vectorbt_missing_raises(self) -> None:
        with patch(
            "iatb.backtesting.vectorbt_engine.importlib.import_module",
            side_effect=ModuleNotFoundError,
        ):
            with pytest.raises(ConfigError, match="vectorbt dependency"):
                VectorBTEngine._load_vectorbt()

    def test_load_pandas_ta_missing_raises(self) -> None:
        with patch(
            "iatb.backtesting.vectorbt_engine.importlib.import_module",
            side_effect=ModuleNotFoundError,
        ):
            with pytest.raises(ConfigError, match="pandas-ta-classic"):
                VectorBTEngine._load_pandas_ta()


class TestBacktestResult:
    def test_creation(self) -> None:
        result = BacktestResult(
            total_return=Decimal("0.1"),
            cagr=Decimal("0.08"),
            sharpe_ratio=Decimal("1.5"),
            max_drawdown=Decimal("-0.05"),
            win_rate=Decimal("0.6"),
            profit_factor=Decimal("1.8"),
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            avg_win=Decimal("500"),
            avg_loss=Decimal("-300"),
            total_costs=Decimal("100"),
            stt_total=Decimal("30"),
            sebi_total=Decimal("5"),
            exchange_txn_total=Decimal("10"),
            stamp_duty_total=Decimal("3"),
            gst_total=Decimal("2"),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            num_days=90,
            avg_composite_score=Decimal("0.7"),
            avg_exit_probability=Decimal("0.6"),
        )
        assert result.total_return == Decimal("0.1")


class TestMonteCarloResult:
    def test_creation(self) -> None:
        result = MonteCarloResult(
            mean_final_equity=Decimal("110000"),
            median_final_equity=Decimal("105000"),
            std_final_equity=Decimal("5000"),
            prob_profit=Decimal("0.7"),
            prob_5pct_return=Decimal("0.4"),
            prob_10pct_return=Decimal("0.2"),
            worst_case_equity=Decimal("90000"),
            best_case_equity=Decimal("130000"),
            p5_equity=Decimal("95000"),
            p25_equity=Decimal("100000"),
            p75_equity=Decimal("115000"),
            p95_equity=Decimal("125000"),
        )
        assert result.prob_profit == Decimal("0.7")
