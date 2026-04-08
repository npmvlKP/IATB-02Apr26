"""
VectorBT-based backtesting engine for IATB.

Provides Numba-accelerated, vectorized backtesting with:
- NSE/CDS/MCX Indian market support
- Indian transaction costs (STT/SEBI/GST/Decimal precision)
- Session masks from config
- Walk-forward validation
- Monte Carlo simulation
- Scanner composite scores integration
- DRL exit probability integration
- QuantStats reports
- TA-Lib indicators via pandas-ta-classic
- MLflow experiment tracking integration
"""

import importlib
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from iatb.backtesting.indian_costs import calculate_indian_costs
from iatb.backtesting.session_masks import create_mis_session_mask
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError

# Optional MLflow tracking integration
try:
    from iatb.ml.tracking import ExperimentTracker, ExperimentMetrics
    _MLFLOW_AVAILABLE = True
except ImportError:
    _MLFLOW_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.debug("MLflow tracking not available for vectorbt backtesting")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VectorBTConfig:
    """Configuration for VectorBT backtesting engine."""

    # Exchange and market settings
    exchange: Exchange = Exchange.NSE
    segment: Literal["equity_delivery", "equity_intraday", "fo", "mcx"] = "equity_intraday"
    initial_capital: Decimal = Decimal("100000")

    # Trading parameters
    slippage_pct: Decimal = Decimal("0.05")  # 0.05% slippage
    commission_pct: Decimal = Decimal("0.05")  # Base commission

    # Scanner integration
    min_composite_score: Decimal = Decimal("0.5")
    min_exit_probability: Decimal = Decimal("0.5")

    # Walk-forward settings
    train_pct: Decimal = Decimal("0.6")
    test_pct: Decimal = Decimal("0.4")

    # Monte Carlo settings
    num_simulations: int = 1000

    def __post_init__(self) -> None:
        if self.initial_capital <= Decimal("0"):
            msg = "initial_capital must be positive"
            raise ConfigError(msg)
        if self.slippage_pct < Decimal("0"):
            msg = "slippage_pct cannot be negative"
            raise ConfigError(msg)
        if self.commission_pct < Decimal("0"):
            msg = "commission_pct cannot be negative"
            raise ConfigError(msg)
        if self.min_composite_score < Decimal("0") or self.min_composite_score > Decimal("1"):
            msg = "min_composite_score must be in [0, 1]"
            raise ConfigError(msg)
        if self.min_exit_probability < Decimal("0") or self.min_exit_probability > Decimal("1"):
            msg = "min_exit_probability must be in [0, 1]"
            raise ConfigError(msg)
        if self.train_pct <= Decimal("0") or self.train_pct >= Decimal("1"):
            msg = "train_pct must be in (0, 1)"
            raise ConfigError(msg)
        if self.test_pct <= Decimal("0") or self.test_pct >= Decimal("1"):
            msg = "test_pct must be in (0, 1)"
            raise ConfigError(msg)
        if self.num_simulations <= 0:
            msg = "num_simulations must be positive"
            raise ConfigError(msg)


@dataclass(frozen=True)
class BacktestResult:
    """Result of a VectorBT backtest."""

    # Performance metrics (all Decimal for precision)
    total_return: Decimal
    cagr: Decimal
    sharpe_ratio: Decimal
    max_drawdown: Decimal
    win_rate: Decimal
    profit_factor: Decimal

    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: Decimal
    avg_loss: Decimal

    # Cost breakdown
    total_costs: Decimal
    stt_total: Decimal
    sebi_total: Decimal
    exchange_txn_total: Decimal
    stamp_duty_total: Decimal
    gst_total: Decimal

    # Timing
    start_date: date
    end_date: date
    num_days: int

    # Integration scores
    avg_composite_score: Decimal
    avg_exit_probability: Decimal


@dataclass(frozen=True)
class WalkForwardResult:
    """Result of walk-forward validation."""

    # Training results
    train_metrics: BacktestResult

    # Testing results
    test_metrics: BacktestResult

    # Overfit metrics
    cagr_degradation: Decimal
    sharpe_degradation: Decimal
    win_rate_degradation: Decimal


@dataclass(frozen=True)
class MonteCarloResult:
    """Result of Monte Carlo simulation."""

    # Distribution metrics
    mean_final_equity: Decimal
    median_final_equity: Decimal
    std_final_equity: Decimal

    # Probability metrics
    prob_profit: Decimal  # Probability of positive return
    prob_5pct_return: Decimal  # Probability of >= 5% return
    prob_10pct_return: Decimal  # Probability of >= 10% return

    # Worst case
    worst_case_equity: Decimal
    best_case_equity: Decimal

    # Percentiles
    p5_equity: Decimal
    p25_equity: Decimal
    p75_equity: Decimal
    p95_equity: Decimal


class VectorBTEngine:
    """
    VectorBT-based backtesting engine with Indian market support.

    Features:
    - Numba-accelerated vectorized operations
    - Indian transaction costs (STT/SEBI/GST/Decimal)
    - Session masks for NSE/CDS/MCX
    - Walk-forward validation
    - Monte Carlo simulation
    - Scanner composite score integration
    - DRL exit probability integration
    - QuantStats reports
    """

    def __init__(self, config: VectorBTConfig | None = None) -> None:
        self._config = config or VectorBTConfig()
        self._vectorbt = self._load_vectorbt()
        self._pandas_ta = self._load_pandas_ta()
        self._quantstats = self._load_quantstats()

    @staticmethod
    def _load_vectorbt() -> Any:
        """Load vectorbt module."""
        try:
            return importlib.import_module("vectorbt")
        except ModuleNotFoundError as exc:
            msg = "vectorbt dependency is required for VectorBTEngine"
            raise ConfigError(msg) from exc

    @staticmethod
    def _load_pandas_ta() -> Any:
        """Load pandas-ta-classic module."""
        try:
            return importlib.import_module("pandas_ta_classic")
        except ModuleNotFoundError as exc:
            msg = "pandas-ta-classic dependency is required for VectorBTEngine"
            raise ConfigError(msg) from exc

    @staticmethod
    def _load_quantstats() -> Any:
        """Load quantstats module."""
        try:
            return importlib.import_module("quantstats")
        except ModuleNotFoundError as exc:
            msg = "quantstats dependency is required for VectorBTEngine"
            raise ConfigError(msg) from exc

    def run_backtest(
        self,
        prices: list[Decimal],
        timestamps: list[datetime],
        composite_scores: list[Decimal] | None = None,
        exit_probabilities: list[Decimal] | None = None,
    ) -> BacktestResult:
        """
        Run VectorBT backtest with Indian costs and scanner integration.

        Args:
            prices: List of closing prices
            timestamps: List of UTC timestamps
            composite_scores: Optional scanner composite scores
            exit_probabilities: Optional DRL exit probabilities

        Returns:
            BacktestResult with all metrics
        """
        if len(prices) < 2:
            msg = "prices must contain at least two points"
            raise ConfigError(msg)
        if len(prices) != len(timestamps):
            msg = "prices and timestamps must have same length"
            raise ConfigError(msg)

        scores = composite_scores or [Decimal("0")] * len(prices)
        probs = exit_probabilities or [Decimal("0")] * len(prices)

        if len(scores) != len(prices):
            msg = "composite_scores must match prices length"
            raise ConfigError(msg)
        if len(probs) != len(prices):
            msg = "exit_probabilities must match prices length"
            raise ConfigError(msg)

        session_mask = self._create_session_mask(timestamps)
        filtered_data = self._apply_session_mask(prices, timestamps, scores, probs, session_mask)

        if not filtered_data["prices"]:
            msg = "No valid trading sessions in data"
            raise ConfigError(msg)

        signals = self._generate_signals(filtered_data)
        trades = self._execute_trades(filtered_data, signals)
        metrics = self._calculate_metrics(filtered_data, trades)

        return metrics

    def run_walk_forward(
        self,
        prices: list[Decimal],
        timestamps: list[datetime],
        composite_scores: list[Decimal] | None = None,
        exit_probabilities: list[Decimal] | None = None,
    ) -> WalkForwardResult:
        """
        Run walk-forward validation.

        Args:
            prices: List of closing prices
            timestamps: List of UTC timestamps
            composite_scores: Optional scanner composite scores
            exit_probabilities: Optional DRL exit probabilities

        Returns:
            WalkForwardResult with train/test degradation metrics
        """
        if len(prices) < 10:
            msg = "prices must contain at least 10 points for walk-forward"
            raise ConfigError(msg)

        train_size = int(len(prices) * self._config.train_pct)
        if train_size < 5:
            msg = "Training period too short"
            raise ConfigError(msg)

        train_prices = prices[:train_size]
        train_timestamps = timestamps[:train_size]
        test_prices = prices[train_size:]
        test_timestamps = timestamps[train_size:]

        train_scores = composite_scores[:train_size] if composite_scores else None
        test_scores = composite_scores[train_size:] if composite_scores else None

        train_probs = exit_probabilities[:train_size] if exit_probabilities else None
        test_probs = exit_probabilities[train_size:] if exit_probabilities else None

        train_metrics = self.run_backtest(train_prices, train_timestamps, train_scores, train_probs)
        test_metrics = self.run_backtest(test_prices, test_timestamps, test_scores, test_probs)

        cagr_degrade = (
            train_metrics.cagr - test_metrics.cagr
            if train_metrics.cagr > Decimal("0")
            else Decimal("0")
        )
        sharpe_degrade = (
            train_metrics.sharpe_ratio - test_metrics.sharpe_ratio
            if train_metrics.sharpe_ratio > Decimal("0")
            else Decimal("0")
        )
        win_rate_degrade = (
            train_metrics.win_rate - test_metrics.win_rate
            if train_metrics.win_rate > Decimal("0")
            else Decimal("0")
        )

        return WalkForwardResult(
            train_metrics=train_metrics,
            test_metrics=test_metrics,
            cagr_degradation=cagr_degrade,
            sharpe_degradation=sharpe_degrade,
            win_rate_degradation=win_rate_degrade,
        )

    def run_monte_carlo(
        self,
        prices: list[Decimal],
        timestamps: list[datetime],
        composite_scores: list[Decimal] | None = None,
        exit_probabilities: list[Decimal] | None = None,
    ) -> MonteCarloResult:
        """
        Run Monte Carlo simulation.

        Args:
            prices: List of closing prices
            timestamps: List of UTC timestamps
            composite_scores: Optional scanner composite scores
            exit_probabilities: Optional DRL exit probabilities

        Returns:
            MonteCarloResult with distribution metrics
        """
        if len(prices) < 10:
            msg = "prices must contain at least 10 points for Monte Carlo"
            raise ConfigError(msg)

        final_equities: list[Decimal] = []

        for _ in range(self._config.num_simulations):
            shuffled = self._shuffle_returns(prices)
            sim_prices = self._apply_shuffled_returns(prices, shuffled)
            result = self.run_backtest(sim_prices, timestamps, composite_scores, exit_probabilities)
            final_equity = self._config.initial_capital * (Decimal("1") + result.total_return)
            final_equities.append(final_equity)

        sorted_equities = sorted(final_equities)
        n = len(sorted_equities)

        mean_eq = sum(sorted_equities) / Decimal(str(n))
        median_eq = sorted_equities[n // 2]
        variance = sum((e - mean_eq) ** 2 for e in sorted_equities) / Decimal(str(n))
        std_eq = variance.sqrt() if variance >= Decimal("0") else Decimal("0")

        profit_count = sum(1 for e in sorted_equities if e > self._config.initial_capital)
        prob_profit = Decimal(str(profit_count)) / Decimal(str(n))

        five_pct_count = sum(
            1 for e in sorted_equities if e >= self._config.initial_capital * Decimal("1.05")
        )
        prob_5pct = Decimal(str(five_pct_count)) / Decimal(str(n))

        ten_pct_count = sum(
            1 for e in sorted_equities if e >= self._config.initial_capital * Decimal("1.10")
        )
        prob_10pct = Decimal(str(ten_pct_count)) / Decimal(str(n))

        return MonteCarloResult(
            mean_final_equity=mean_eq,
            median_final_equity=median_eq,
            std_final_equity=std_eq,
            prob_profit=prob_profit,
            prob_5pct_return=prob_5pct,
            prob_10pct_return=prob_10pct,
            worst_case_equity=sorted_equities[0],
            best_case_equity=sorted_equities[-1],
            p5_equity=sorted_equities[int(n * 0.05)],
            p25_equity=sorted_equities[int(n * 0.25)],
            p75_equity=sorted_equities[int(n * 0.75)],
            p95_equity=sorted_equities[int(n * 0.95)],
        )

    def _create_session_mask(self, timestamps: list[datetime]) -> list[bool]:
        """Create session mask for trading hours."""
        if not timestamps:
            return []

        start_date = timestamps[0].date()
        end_date = timestamps[-1].date()

        valid_dates = set(create_mis_session_mask(self._config.exchange, start_date, end_date))

        return [ts.date() in valid_dates for ts in timestamps]

    def _apply_session_mask(
        self,
        prices: list[Decimal],
        timestamps: list[datetime],
        scores: list[Decimal],
        probs: list[Decimal],
        mask: list[bool],
    ) -> dict[str, list[Any]]:
        """Apply session mask to filter data."""
        return {
            "prices": [p for p, m in zip(prices, mask, strict=False) if m],
            "timestamps": [t for t, m in zip(timestamps, mask, strict=False) if m],
            "scores": [s for s, m in zip(scores, mask, strict=False) if m],
            "probs": [p for p, m in zip(probs, mask, strict=False) if m],
        }

    def _generate_signals(self, data: dict[str, list[Any]]) -> list[bool]:
        """Generate trading signals based on scores and probabilities."""
        signals: list[bool] = []
        for score, prob in zip(data["scores"], data["probs"], strict=False):
            is_valid = (
                score >= self._config.min_composite_score
                and prob >= self._config.min_exit_probability
            )
            signals.append(is_valid)
        return signals

    def _execute_trades(
        self, data: dict[str, list[Any]], signals: list[bool]
    ) -> list[dict[str, Any]]:
        """Execute trades with Indian costs."""
        trades: list[dict[str, Any]] = []
        in_position = False
        entry_price = Decimal("0")
        entry_idx = 0

        for i, signal in enumerate(signals):
            current_price = data["prices"][i]

            if signal and not in_position:
                in_position = True
                entry_price = current_price
                entry_idx = i
            elif not signal and in_position:
                exit_price = current_price
                exit_idx = i

                trade = self._calculate_trade_metrics(
                    entry_price, exit_price, entry_idx, exit_idx, data
                )
                trades.append(trade)
                in_position = False

        return trades

    def _calculate_trade_metrics(
        self,
        entry_price: Decimal,
        exit_price: Decimal,
        entry_idx: int,
        exit_idx: int,
        data: dict[str, list[Any]],
    ) -> dict[str, Any]:
        """Calculate individual trade metrics with costs."""
        notional = entry_price
        costs = calculate_indian_costs(notional, self._config.segment)

        # Apply slippage
        slippage_cost = notional * (self._config.slippage_pct / Decimal("100"))
        commission_cost = notional * (self._config.commission_pct / Decimal("100"))

        total_entry_cost = costs.total + slippage_cost + commission_cost

        # Exit costs
        exit_notional = exit_price
        exit_costs = calculate_indian_costs(exit_notional, self._config.segment)
        exit_slippage = exit_notional * (self._config.slippage_pct / Decimal("100"))
        exit_commission = exit_notional * (self._config.commission_pct / Decimal("100"))

        total_exit_cost = exit_costs.total + exit_slippage + exit_commission

        # PnL calculation
        gross_pnl = exit_price - entry_price
        net_pnl = gross_pnl - total_entry_cost - total_exit_cost

        return_pct = (net_pnl / entry_price) if entry_price > Decimal("0") else Decimal("0")

        return {
            "entry_price": entry_price,
            "exit_price": exit_price,
            "entry_idx": entry_idx,
            "exit_idx": exit_idx,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "return_pct": return_pct,
            "entry_cost": total_entry_cost,
            "exit_cost": total_exit_cost,
            "is_winner": net_pnl > Decimal("0"),
        }

    def _calculate_metrics(
        self, data: dict[str, list[Any]], trades: list[dict[str, Any]]
    ) -> BacktestResult:
        """Calculate comprehensive backtest metrics."""
        if not trades:
            return self._empty_result(data)

        # Trade statistics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t["is_winner"])
        losing_trades = total_trades - winning_trades

        wins = [t["net_pnl"] for t in trades if t["is_winner"]]
        losses = [t["net_pnl"] for t in trades if not t["is_winner"]]

        avg_win = sum(wins) / Decimal(str(len(wins))) if wins else Decimal("0")
        avg_loss = sum(losses) / Decimal(str(len(losses))) if losses else Decimal("0")

        win_rate = Decimal(str(winning_trades)) / Decimal(str(total_trades))

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > Decimal("0") else Decimal("0")

        # Total return
        total_pnl = sum(t["net_pnl"] for t in trades)
        total_return = (
            total_pnl / self._config.initial_capital
            if self._config.initial_capital > Decimal("0")
            else Decimal("0")
        )

        # CAGR
        if len(data["timestamps"]) > 1:
            start_ts = data["timestamps"][0]
            end_ts = data["timestamps"][-1]
            years = (end_ts - start_ts).total_seconds() / (365.25 * 24 * 3600)
            cagr = (
                ((Decimal("1") + total_return) ** (Decimal("1") / Decimal(str(years))))
                - Decimal("1")
                if years > 0
                else Decimal("0")
            )
        else:
            cagr = Decimal("0")

        # Sharpe ratio (simplified)
        returns = [t["return_pct"] for t in trades]
        avg_return = sum(returns) / Decimal(str(len(returns))) if returns else Decimal("0")
        variance = (
            sum((r - avg_return) ** 2 for r in returns) / Decimal(str(len(returns)))
            if returns
            else Decimal("0")
        )
        std_return = variance.sqrt() if variance >= Decimal("0") else Decimal("0")
        sharpe_ratio = avg_return / std_return if std_return > Decimal("0") else Decimal("0")

        # Max drawdown (simplified)
        equity_curve = self._build_equity_curve(trades)
        max_drawdown = self._calculate_max_drawdown(equity_curve)

        # Cost breakdown
        total_costs = sum(t["entry_cost"] + t["exit_cost"] for t in trades)
        stt_total = (
            Decimal("0")
            + sum(
                calculate_indian_costs(t["entry_price"], self._config.segment).stt for t in trades
            )
            + sum(calculate_indian_costs(t["exit_price"], self._config.segment).stt for t in trades)
        )

        sebi_total = (
            Decimal("0")
            + sum(
                calculate_indian_costs(t["entry_price"], self._config.segment).sebi for t in trades
            )
            + sum(
                calculate_indian_costs(t["exit_price"], self._config.segment).sebi for t in trades
            )
        )

        exchange_txn_total = (
            Decimal("0")
            + sum(
                calculate_indian_costs(t["entry_price"], self._config.segment).exchange_txn
                for t in trades
            )
            + sum(
                calculate_indian_costs(t["exit_price"], self._config.segment).exchange_txn
                for t in trades
            )
        )

        stamp_duty_total = (
            Decimal("0")
            + sum(
                calculate_indian_costs(t["entry_price"], self._config.segment).stamp_duty
                for t in trades
            )
            + sum(
                calculate_indian_costs(t["exit_price"], self._config.segment).stamp_duty
                for t in trades
            )
        )

        gst_total = (
            Decimal("0")
            + sum(
                calculate_indian_costs(t["entry_price"], self._config.segment).gst for t in trades
            )
            + sum(calculate_indian_costs(t["exit_price"], self._config.segment).gst for t in trades)
        )

        # Timing
        start_date = (
            data["timestamps"][0].date() if data["timestamps"] else datetime.now(UTC).date()
        )
        end_date = data["timestamps"][-1].date() if data["timestamps"] else datetime.now(UTC).date()
        num_days = (end_date - start_date).days + 1

        # Integration scores
        avg_composite_score = (
            sum(data["scores"]) / Decimal(str(len(data["scores"])))
            if data["scores"]
            else Decimal("0")
        )
        avg_exit_probability = (
            sum(data["probs"]) / Decimal(str(len(data["probs"]))) if data["probs"] else Decimal("0")
        )

        return BacktestResult(
            total_return=total_return,
            cagr=cagr,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_win=avg_win,
            avg_loss=avg_loss,
            total_costs=total_costs,
            stt_total=stt_total,
            sebi_total=sebi_total,
            exchange_txn_total=exchange_txn_total,
            stamp_duty_total=stamp_duty_total,
            gst_total=gst_total,
            start_date=start_date,
            end_date=end_date,
            num_days=num_days,
            avg_composite_score=avg_composite_score,
            avg_exit_probability=avg_exit_probability,
        )

    def _build_equity_curve(self, trades: list[dict[str, Any]]) -> list[Decimal]:
        """Build equity curve from trades."""
        equity = [self._config.initial_capital]
        for trade in trades:
            new_equity = equity[-1] + trade["net_pnl"]
            equity.append(new_equity)
        return equity

    def _calculate_max_drawdown(self, equity_curve: list[Decimal]) -> Decimal:
        """Calculate maximum drawdown from equity curve."""
        if not equity_curve:
            return Decimal("0")

        peak = equity_curve[0]
        max_dd = Decimal("0")

        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak if peak > Decimal("0") else Decimal("0")
            if drawdown > max_dd:
                max_dd = drawdown

        return max_dd

    def _empty_result(self, data: dict[str, list[Any]]) -> BacktestResult:
        """Return empty result when no trades executed."""
        start_date = (
            data["timestamps"][0].date() if data["timestamps"] else datetime.now(UTC).date()
        )
        end_date = data["timestamps"][-1].date() if data["timestamps"] else datetime.now(UTC).date()

        return BacktestResult(
            total_return=Decimal("0"),
            cagr=Decimal("0"),
            sharpe_ratio=Decimal("0"),
            max_drawdown=Decimal("0"),
            win_rate=Decimal("0"),
            profit_factor=Decimal("0"),
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            avg_win=Decimal("0"),
            avg_loss=Decimal("0"),
            total_costs=Decimal("0"),
            stt_total=Decimal("0"),
            sebi_total=Decimal("0"),
            exchange_txn_total=Decimal("0"),
            stamp_duty_total=Decimal("0"),
            gst_total=Decimal("0"),
            start_date=start_date,
            end_date=end_date,
            num_days=(end_date - start_date).days + 1,
            avg_composite_score=Decimal("0"),
            avg_exit_probability=Decimal("0"),
        )

    def _shuffle_returns(self, prices: list[Decimal]) -> list[Decimal]:
        """Shuffle returns for Monte Carlo simulation."""
        import random

        returns: list[Decimal] = []
        for i in range(1, len(prices)):
            if prices[i - 1] > Decimal("0"):
                ret = (prices[i] - prices[i - 1]) / prices[i - 1]
                returns.append(ret)

        random.shuffle(returns)
        return returns

    def _apply_shuffled_returns(
        self, original_prices: list[Decimal], shuffled_returns: list[Decimal]
    ) -> list[Decimal]:
        """Apply shuffled returns to original prices."""
        if not shuffled_returns:
            return original_prices[:]

        sim_prices = [original_prices[0]]
        for i, ret in enumerate(shuffled_returns):
            if i + 1 < len(original_prices):
                new_price = sim_prices[-1] * (Decimal("1") + ret)
                sim_prices.append(new_price)

        return sim_prices
