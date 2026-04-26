"""Tests for backtesting.vectorbt_engine module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from iatb.backtesting.vectorbt_engine import (
    BacktestResult,
    VectorBTConfig,
    VectorBTEngine,
)
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError


def _make_timestamps(n: int, start: datetime | None = None) -> list[datetime]:
    base = start or datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
    return [base + timedelta(minutes=i * 5) for i in range(n)]


def _make_config(**kwargs: Any) -> VectorBTConfig:
    defaults = {
        "exchange": Exchange.NSE,
        "segment": "equity_intraday",
        "initial_capital": Decimal("100000"),
        "slippage_pct": Decimal("0.05"),
        "commission_pct": Decimal("0.05"),
        "min_composite_score": Decimal("0.5"),
        "min_exit_probability": Decimal("0.5"),
        "train_pct": Decimal("0.6"),
        "test_pct": Decimal("0.4"),
        "num_simulations": 10,
    }
    defaults.update(kwargs)
    return VectorBTConfig(**defaults)


class TestVectorBTConfig:
    def test_default_config(self) -> None:
        config = VectorBTConfig()
        assert config.initial_capital == Decimal("100000")

    def test_zero_initial_capital(self) -> None:
        with pytest.raises(ConfigError, match="initial_capital must be positive"):
            VectorBTConfig(initial_capital=Decimal("0"))

    def test_negative_slippage(self) -> None:
        with pytest.raises(ConfigError, match="slippage_pct cannot be negative"):
            VectorBTConfig(slippage_pct=Decimal("-0.1"))

    def test_negative_commission(self) -> None:
        with pytest.raises(ConfigError, match="commission_pct cannot be negative"):
            VectorBTConfig(commission_pct=Decimal("-0.1"))

    def test_composite_score_out_of_range(self) -> None:
        with pytest.raises(ConfigError, match="min_composite_score must be in"):
            VectorBTConfig(min_composite_score=Decimal("1.5"))

    def test_train_pct_boundary(self) -> None:
        with pytest.raises(ConfigError, match="train_pct must be in"):
            VectorBTConfig(train_pct=Decimal("0"))

    def test_train_pct_upper(self) -> None:
        with pytest.raises(ConfigError, match="train_pct must be in"):
            VectorBTConfig(train_pct=Decimal("1"))

    def test_test_pct_boundary(self) -> None:
        with pytest.raises(ConfigError, match="test_pct must be in"):
            VectorBTConfig(test_pct=Decimal("0"))

    def test_num_simulations_zero(self) -> None:
        with pytest.raises(ConfigError, match="num_simulations must be positive"):
            VectorBTConfig(num_simulations=0)

    def test_valid_custom_config(self) -> None:
        config = VectorBTConfig(
            initial_capital=Decimal("500000"),
            num_simulations=500,
        )
        assert config.initial_capital == Decimal("500000")
        assert config.num_simulations == 500


class TestVectorBTEngine:
    @pytest.fixture
    def engine(self) -> VectorBTEngine:
        mock_vbt = MagicMock()
        mock_pandas_ta = MagicMock()
        mock_qs = MagicMock()
        with (
            patch(
                "iatb.backtesting.vectorbt_engine.VectorBTEngine._load_vectorbt",
                return_value=mock_vbt,
            ),
            patch(
                "iatb.backtesting.vectorbt_engine.VectorBTEngine._load_pandas_ta",
                return_value=mock_pandas_ta,
            ),
            patch(
                "iatb.backtesting.vectorbt_engine.VectorBTEngine._load_quantstats",
                return_value=mock_qs,
            ),
        ):
            config = _make_config(num_simulations=10)
            return VectorBTEngine(config=config)

    def test_engine_init(self, engine: VectorBTEngine) -> None:
        assert engine._config.initial_capital == Decimal("100000")

    def test_run_backtest_too_few_prices(self, engine: VectorBTEngine) -> None:
        with pytest.raises(ConfigError, match="at least two points"):
            engine.run_backtest([Decimal("100")], _make_timestamps(1))

    def test_run_backtest_length_mismatch(self, engine: VectorBTEngine) -> None:
        with pytest.raises(ConfigError, match="same length"):
            engine.run_backtest(
                [Decimal("100"), Decimal("101")],
                _make_timestamps(3),
            )

    def test_run_backtest_scores_length_mismatch(self, engine: VectorBTEngine) -> None:
        with pytest.raises(ConfigError, match="composite_scores must match"):
            engine.run_backtest(
                [Decimal("100"), Decimal("101")],
                _make_timestamps(2),
                composite_scores=[Decimal("0.5")],
            )

    def test_run_backtest_probs_length_mismatch(self, engine: VectorBTEngine) -> None:
        with pytest.raises(ConfigError, match="exit_probabilities must match"):
            engine.run_backtest(
                [Decimal("100"), Decimal("101")],
                _make_timestamps(2),
                exit_probabilities=[Decimal("0.5")],
            )

    def test_run_backtest_no_valid_sessions(self, engine: VectorBTEngine) -> None:
        with patch("iatb.backtesting.vectorbt_engine.create_mis_session_mask", return_value=set()):
            with pytest.raises(ConfigError, match="No valid trading sessions"):
                engine.run_backtest(
                    [Decimal("100"), Decimal("101")],
                    _make_timestamps(2),
                )

    def test_run_backtest_empty_trades(self, engine: VectorBTEngine) -> None:
        ts = _make_timestamps(20)
        prices = [Decimal("100") + Decimal(i) for i in range(20)]
        with patch(
            "iatb.backtesting.vectorbt_engine.create_mis_session_mask", return_value={ts[0].date()}
        ):
            result = engine.run_backtest(prices, ts)
            assert isinstance(result, BacktestResult)
            assert result.total_trades == 0

    def test_run_backtest_with_signals(self, engine: VectorBTEngine) -> None:
        ts = _make_timestamps(20)
        prices = [Decimal("100") + Decimal(i) for i in range(20)]
        scores = [Decimal("0.8") if 3 <= i <= 8 else Decimal("0.1") for i in range(20)]
        probs = [Decimal("0.8") if 3 <= i <= 8 else Decimal("0.1") for i in range(20)]
        with patch(
            "iatb.backtesting.vectorbt_engine.create_mis_session_mask", return_value={ts[0].date()}
        ):
            result = engine.run_backtest(prices, ts, scores, probs)
            assert isinstance(result, BacktestResult)

    def test_calculate_degradation_positive(self, engine: VectorBTEngine) -> None:
        result = engine._calculate_degradation(Decimal("0.5"), Decimal("0.3"))
        assert result == Decimal("0.2")

    def test_calculate_degradation_zero_train(self, engine: VectorBTEngine) -> None:
        result = engine._calculate_degradation(Decimal("0"), Decimal("0.1"))
        assert result == Decimal("0")

    def test_calculate_degradation_negative(self, engine: VectorBTEngine) -> None:
        result = engine._calculate_degradation(Decimal("0.3"), Decimal("0.5"))
        assert result == Decimal("-0.2")

    def test_build_equity_curve(self, engine: VectorBTEngine) -> None:
        trades = [
            {"net_pnl": Decimal("100")},
            {"net_pnl": Decimal("-50")},
        ]
        curve = engine._build_equity_curve(trades)
        assert curve == [Decimal("100000"), Decimal("100100"), Decimal("100050")]

    def test_calculate_max_drawdown(self, engine: VectorBTEngine) -> None:
        curve = [Decimal("100"), Decimal("110"), Decimal("90"), Decimal("100")]
        dd = engine._calculate_max_drawdown(curve)
        assert dd > Decimal("0")

    def test_calculate_max_drawdown_empty(self, engine: VectorBTEngine) -> None:
        assert engine._calculate_max_drawdown([]) == Decimal("0")

    def test_calculate_max_drawdown_no_drawdown(self, engine: VectorBTEngine) -> None:
        curve = [Decimal("100"), Decimal("110"), Decimal("120")]
        assert engine._calculate_max_drawdown(curve) == Decimal("0")

    def test_shuffle_returns(self, engine: VectorBTEngine) -> None:
        prices = [Decimal("100"), Decimal("105"), Decimal("103"), Decimal("108")]
        result = engine._shuffle_returns(prices)
        assert len(result) == 3

    def test_apply_shuffled_returns_empty(self, engine: VectorBTEngine) -> None:
        result = engine._apply_shuffled_returns([Decimal("100")], [])
        assert result == [Decimal("100")]

    def test_apply_shuffled_returns_basic(self, engine: VectorBTEngine) -> None:
        original = [Decimal("100"), Decimal("105"), Decimal("103")]
        shuffled = [Decimal("0.05"), Decimal("-0.019")]
        result = engine._apply_shuffled_returns(original, shuffled)
        assert len(result) == 3
        assert result[0] == Decimal("100")

    def test_create_session_mask_empty(self, engine: VectorBTEngine) -> None:
        assert engine._create_session_mask([]) == []

    def test_apply_session_mask(self, engine: VectorBTEngine) -> None:
        prices = [Decimal("100"), Decimal("101"), Decimal("102")]
        ts = _make_timestamps(3)
        scores = [Decimal("0.5")] * 3
        probs = [Decimal("0.5")] * 3
        mask = [True, False, True]
        result = engine._apply_session_mask(prices, ts, scores, probs, mask)
        assert len(result["prices"]) == 2

    def test_generate_signals(self, engine: VectorBTEngine) -> None:
        data = {
            "scores": [Decimal("0.8"), Decimal("0.3"), Decimal("0.9")],
            "probs": [Decimal("0.8"), Decimal("0.3"), Decimal("0.9")],
        }
        signals = engine._generate_signals(data)
        assert signals == [True, False, True]

    def test_empty_result_structure(self, engine: VectorBTEngine) -> None:
        ts = _make_timestamps(5)
        data = {"prices": [], "timestamps": ts, "scores": [], "probs": []}
        result = engine._empty_result(data)
        assert result.total_trades == 0
        assert result.total_return == Decimal("0")

    def test_walk_forward_too_few_prices(self, engine: VectorBTEngine) -> None:
        with pytest.raises(ConfigError, match="at least 10 points"):
            engine.run_walk_forward(
                [Decimal("100")] * 5,
                _make_timestamps(5),
            )

    def test_calculate_trade_statistics_all_winners(self, engine: VectorBTEngine) -> None:
        trades = [
            {"net_pnl": Decimal("100"), "is_winner": True},
            {"net_pnl": Decimal("50"), "is_winner": True},
        ]
        stats = engine._calculate_trade_statistics(trades)
        assert stats["winning_trades"] == 2
        assert stats["losing_trades"] == 0
        assert stats["win_rate"] == Decimal("1")

    def test_calculate_trade_statistics_all_losers(self, engine: VectorBTEngine) -> None:
        trades = [
            {"net_pnl": Decimal("-100"), "is_winner": False},
            {"net_pnl": Decimal("-50"), "is_winner": False},
        ]
        stats = engine._calculate_trade_statistics(trades)
        assert stats["winning_trades"] == 0
        assert stats["losing_trades"] == 2
        assert stats["profit_factor"] == Decimal("0")

    def test_calculate_sharpe_zero_std(self, engine: VectorBTEngine) -> None:
        trades = [
            {"return_pct": Decimal("0.1")},
            {"return_pct": Decimal("0.1")},
        ]
        assert engine._calculate_sharpe_ratio(trades) == Decimal("0")

    def test_calculate_cagr_single_timestamp(self, engine: VectorBTEngine) -> None:
        data = {"timestamps": [datetime(2026, 1, 1, tzinfo=UTC)]}
        assert engine._calculate_cagr(data, Decimal("0.1")) == Decimal("0")

    def test_calculate_timing_empty(self, engine: VectorBTEngine) -> None:
        data = {"timestamps": []}
        result = engine._calculate_timing(data)
        assert result["num_days"] == 1


class TestBacktestResult:
    def test_backtest_result_creation(self) -> None:
        result = BacktestResult(
            total_return=Decimal("0.1"),
            cagr=Decimal("0.05"),
            sharpe_ratio=Decimal("1.5"),
            max_drawdown=Decimal("0.02"),
            win_rate=Decimal("0.6"),
            profit_factor=Decimal("2.0"),
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            avg_win=Decimal("500"),
            avg_loss=Decimal("200"),
            total_costs=Decimal("100"),
            stt_total=Decimal("30"),
            sebi_total=Decimal("10"),
            exchange_txn_total=Decimal("20"),
            stamp_duty_total=Decimal("15"),
            gst_total=Decimal("25"),
            start_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
            end_date=datetime(2026, 6, 1, tzinfo=UTC).date(),
            num_days=152,
            avg_composite_score=Decimal("0.7"),
            avg_exit_probability=Decimal("0.6"),
        )
        assert result.total_return == Decimal("0.1")
        assert result.total_trades == 10
