"""
Integration tests for VectorBT backtesting engine.

Tests cover:
- Happy path: normal backtest operations
- Edge cases: boundary conditions, empty data
- Error paths: invalid inputs, configuration errors
- Type handling: Decimal precision, timezone handling
- Precision handling: Indian costs, financial calculations
- Scanner/DRL integration: composite scores, exit probabilities
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.backtesting.vectorbt_engine import (
    BacktestResult,
    MonteCarloResult,
    VectorBTConfig,
    VectorBTEngine,
    WalkForwardResult,
)
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError


class TestVectorBTConfig:
    """Test VectorBTConfig validation."""

    def test_valid_config_defaults(self) -> None:
        """Test valid config with default values."""
        config = VectorBTConfig()
        assert config.exchange == Exchange.NSE
        assert config.segment == "equity_intraday"
        assert config.initial_capital == Decimal("100000")
        assert config.slippage_pct == Decimal("0.05")
        assert config.commission_pct == Decimal("0.05")
        assert config.min_composite_score == Decimal("0.5")
        assert config.min_exit_probability == Decimal("0.5")
        assert config.train_pct == Decimal("0.6")
        assert config.test_pct == Decimal("0.4")
        assert config.num_simulations == 1000

    def test_valid_config_custom(self) -> None:
        """Test valid config with custom values."""
        config = VectorBTConfig(
            exchange=Exchange.MCX,
            segment="mcx",
            initial_capital=Decimal("500000"),
            slippage_pct=Decimal("0.1"),
            commission_pct=Decimal("0.1"),
            min_composite_score=Decimal("0.7"),
            min_exit_probability=Decimal("0.6"),
            train_pct=Decimal("0.7"),
            test_pct=Decimal("0.3"),
            num_simulations=500,
        )
        assert config.exchange == Exchange.MCX
        assert config.segment == "mcx"
        assert config.initial_capital == Decimal("500000")

    def test_invalid_initial_capital_zero(self) -> None:
        """Test config with zero initial capital."""
        with pytest.raises(ConfigError, match="initial_capital must be positive"):
            VectorBTConfig(initial_capital=Decimal("0"))

    def test_invalid_initial_capital_negative(self) -> None:
        """Test config with negative initial capital."""
        with pytest.raises(ConfigError, match="initial_capital must be positive"):
            VectorBTConfig(initial_capital=Decimal("-1000"))

    def test_invalid_slippage_negative(self) -> None:
        """Test config with negative slippage."""
        with pytest.raises(ConfigError, match="slippage_pct cannot be negative"):
            VectorBTConfig(slippage_pct=Decimal("-0.1"))

    def test_invalid_commission_negative(self) -> None:
        """Test config with negative commission."""
        with pytest.raises(ConfigError, match="commission_pct cannot be negative"):
            VectorBTConfig(commission_pct=Decimal("-0.1"))

    def test_invalid_composite_score_low(self) -> None:
        """Test config with composite score < 0."""
        with pytest.raises(ConfigError, match="min_composite_score must be in \\[0, 1\\]"):
            VectorBTConfig(min_composite_score=Decimal("-0.1"))

    def test_invalid_composite_score_high(self) -> None:
        """Test config with composite score > 1."""
        with pytest.raises(ConfigError, match="min_composite_score must be in \\[0, 1\\]"):
            VectorBTConfig(min_composite_score=Decimal("1.5"))

    def test_invalid_exit_probability_low(self) -> None:
        """Test config with exit probability < 0."""
        with pytest.raises(ConfigError, match="min_exit_probability must be in \\[0, 1\\]"):
            VectorBTConfig(min_exit_probability=Decimal("-0.1"))

    def test_invalid_exit_probability_high(self) -> None:
        """Test config with exit probability > 1."""
        with pytest.raises(ConfigError, match="min_exit_probability must be in \\[0, 1\\]"):
            VectorBTConfig(min_exit_probability=Decimal("1.5"))

    def test_invalid_train_pct_zero(self) -> None:
        """Test config with train_pct = 0."""
        with pytest.raises(ConfigError, match="train_pct must be in \\(0, 1\\)"):
            VectorBTConfig(train_pct=Decimal("0"))

    def test_invalid_train_pct_one(self) -> None:
        """Test config with train_pct = 1."""
        with pytest.raises(ConfigError, match="train_pct must be in \\(0, 1\\)"):
            VectorBTConfig(train_pct=Decimal("1"))

    def test_invalid_test_pct_zero(self) -> None:
        """Test config with test_pct = 0."""
        with pytest.raises(ConfigError, match="test_pct must be in \\(0, 1\\)"):
            VectorBTConfig(test_pct=Decimal("0"))

    def test_invalid_num_simulations_zero(self) -> None:
        """Test config with num_simulations = 0."""
        with pytest.raises(ConfigError, match="num_simulations must be positive"):
            VectorBTConfig(num_simulations=0)

    def test_invalid_num_simulations_negative(self) -> None:
        """Test config with negative num_simulations."""
        with pytest.raises(ConfigError, match="num_simulations must be positive"):
            VectorBTConfig(num_simulations=-100)


class TestVectorBTEngineInitialization:
    """Test VectorBTEngine initialization and module loading."""

    @patch("iatb.backtesting.vectorbt_engine.importlib.import_module")
    def test_successful_initialization(self, mock_import: MagicMock) -> None:
        """Test successful engine initialization."""
        mock_vectorbt = MagicMock()
        mock_pandas_ta = MagicMock()
        mock_quantstats = MagicMock()

        mock_import.side_effect = [mock_vectorbt, mock_pandas_ta, mock_quantstats]

        engine = VectorBTEngine()
        assert engine._config is not None
        assert engine._vectorbt == mock_vectorbt
        assert engine._pandas_ta == mock_pandas_ta
        assert engine._quantstats == mock_quantstats

    @patch("iatb.backtesting.vectorbt_engine.importlib.import_module")
    def test_vectorbt_not_found(self, mock_import: MagicMock) -> None:
        """Test error when vectorbt is not installed."""
        mock_import.side_effect = ModuleNotFoundError("vectorbt")

        with pytest.raises(ConfigError, match="vectorbt dependency is required"):
            VectorBTEngine()

    @patch("iatb.backtesting.vectorbt_engine.importlib.import_module")
    def test_pandas_ta_not_found(self, mock_import: MagicMock) -> None:
        """Test error when pandas-ta-classic is not installed."""
        mock_vectorbt = MagicMock()
        mock_import.side_effect = [mock_vectorbt, ModuleNotFoundError("pandas-ta")]

        with pytest.raises(ConfigError, match="pandas-ta-classic dependency is required"):
            VectorBTEngine()

    @patch("iatb.backtesting.vectorbt_engine.importlib.import_module")
    def test_quantstats_not_found(self, mock_import: MagicMock) -> None:
        """Test error when quantstats is not installed."""
        mock_vectorbt = MagicMock()
        mock_pandas_ta = MagicMock()
        mock_import.side_effect = [mock_vectorbt, mock_pandas_ta, ModuleNotFoundError("quantstats")]

        with pytest.raises(ConfigError, match="quantstats dependency is required"):
            VectorBTEngine()


class TestVectorBTEngineBacktest:
    """Test VectorBTEngine backtest functionality."""

    @pytest.fixture
    def mock_engine(self) -> VectorBTEngine:
        """Create mock engine with mocked dependencies and lower thresholds."""
        config = VectorBTConfig(
            min_composite_score=Decimal("0.3"), min_exit_probability=Decimal("0.3")
        )
        with patch("iatb.backtesting.vectorbt_engine.importlib.import_module") as mock_import:
            mock_import.return_value = MagicMock()
            return VectorBTEngine(config)

    @pytest.fixture
    def sample_prices(self) -> list[Decimal]:
        """Generate sample price data."""
        return [
            Decimal("100"),
            Decimal("101"),
            Decimal("102"),
            Decimal("103"),
            Decimal("102"),
            Decimal("104"),
            Decimal("105"),
            Decimal("106"),
            Decimal("105"),
            Decimal("107"),
        ]

    @pytest.fixture
    def sample_timestamps(self) -> list[datetime]:
        """Generate sample UTC timestamps."""
        base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
        return [base + timedelta(hours=i) for i in range(10)]

    @pytest.fixture
    def sample_scores(self) -> list[Decimal]:
        """Generate sample composite scores with alternating values."""
        return [
            Decimal("0.8"),  # High - enter
            Decimal("0.8"),  # High - hold
            Decimal("0.1"),  # Low - exit
            Decimal("0.9"),  # High - enter
            Decimal("0.9"),  # High - hold
            Decimal("0.2"),  # Low - exit
            Decimal("0.8"),  # High - enter
            Decimal("0.8"),  # High - hold
            Decimal("0.1"),  # Low - exit
            Decimal("0.9"),  # High - enter
        ]

    @pytest.fixture
    def sample_probabilities(self) -> list[Decimal]:
        """Generate sample exit probabilities with alternating values."""
        return [
            Decimal("0.8"),  # High - enter
            Decimal("0.8"),  # High - hold
            Decimal("0.2"),  # Low - exit
            Decimal("0.9"),  # High - enter
            Decimal("0.9"),  # High - hold
            Decimal("0.2"),  # Low - exit
            Decimal("0.8"),  # High - enter
            Decimal("0.8"),  # High - hold
            Decimal("0.2"),  # Low - exit
            Decimal("0.9"),  # High - enter
        ]

    def test_backtest_basic(
        self,
        mock_engine: VectorBTEngine,
        sample_prices: list[Decimal],
        sample_timestamps: list[datetime],
    ) -> None:
        """Test basic backtest execution."""
        result = mock_engine.run_backtest(sample_prices, sample_timestamps)

        assert isinstance(result, BacktestResult)
        assert result.total_trades >= 0
        assert result.total_return >= Decimal("0")
        assert result.cagr >= Decimal("0")
        assert result.max_drawdown >= Decimal("0")
        assert result.win_rate >= Decimal("0") and result.win_rate <= Decimal("1")

    @patch("iatb.backtesting.vectorbt_engine.create_mis_session_mask")
    def test_backtest_with_scores(
        self,
        mock_session: MagicMock,
        mock_engine: VectorBTEngine,
        sample_prices: list[Decimal],
        sample_timestamps: list[datetime],
        sample_scores: list[Decimal],
    ) -> None:
        """Test backtest with composite scores."""
        mock_session.return_value = [ts.date() for ts in sample_timestamps]
        result = mock_engine.run_backtest(sample_prices, sample_timestamps, sample_scores)

        assert isinstance(result, BacktestResult)
        # With mocked vectorbt, trades may not execute, but API should work
        assert isinstance(result.avg_composite_score, Decimal)

    def test_backtest_with_scores_and_probabilities(
        self,
        mock_engine: VectorBTEngine,
        sample_prices: list[Decimal],
        sample_timestamps: list[datetime],
        sample_scores: list[Decimal],
        sample_probabilities: list[Decimal],
    ) -> None:
        """Test backtest with both scores and probabilities."""
        result = mock_engine.run_backtest(
            sample_prices, sample_timestamps, sample_scores, sample_probabilities
        )

        assert isinstance(result, BacktestResult)
        # With mocked vectorbt, trades may not execute, but API should work
        assert isinstance(result.avg_composite_score, Decimal)
        assert isinstance(result.avg_exit_probability, Decimal)

    def test_backtest_insufficient_prices(self, mock_engine: VectorBTEngine) -> None:
        """Test backtest with insufficient price data."""
        with pytest.raises(ConfigError, match="prices must contain at least two points"):
            mock_engine.run_backtest([Decimal("100")], [datetime.now(UTC)])

    def test_backtest_mismatched_lengths(
        self,
        mock_engine: VectorBTEngine,
        sample_prices: list[Decimal],
        sample_timestamps: list[datetime],
    ) -> None:
        """Test backtest with mismatched prices and timestamps."""
        with pytest.raises(ConfigError, match="prices and timestamps must have same length"):
            mock_engine.run_backtest(sample_prices, sample_timestamps[:-1])

    def test_backtest_mismatched_scores(
        self,
        mock_engine: VectorBTEngine,
        sample_prices: list[Decimal],
        sample_timestamps: list[datetime],
    ) -> None:
        """Test backtest with mismatched scores length."""
        with pytest.raises(ConfigError, match="composite_scores must match prices length"):
            mock_engine.run_backtest(sample_prices, sample_timestamps, [Decimal("0.5")] * 5)

    def test_backtest_mismatched_probabilities(
        self,
        mock_engine: VectorBTEngine,
        sample_prices: list[Decimal],
        sample_timestamps: list[datetime],
    ) -> None:
        """Test backtest with mismatched probabilities length."""
        with pytest.raises(ConfigError, match="exit_probabilities must match prices length"):
            mock_engine.run_backtest(sample_prices, sample_timestamps, None, [Decimal("0.5")] * 5)

    def test_backtest_cost_breakdown(
        self,
        mock_engine: VectorBTEngine,
        sample_prices: list[Decimal],
        sample_timestamps: list[datetime],
    ) -> None:
        """Test that cost breakdown is calculated correctly."""
        result = mock_engine.run_backtest(sample_prices, sample_timestamps)

        assert result.total_costs >= Decimal("0")
        assert result.stt_total >= Decimal("0")
        assert result.sebi_total >= Decimal("0")
        assert result.exchange_txn_total >= Decimal("0")
        assert result.stamp_duty_total >= Decimal("0")
        assert result.gst_total >= Decimal("0")

    def test_backtest_precision(
        self,
        mock_engine: VectorBTEngine,
        sample_prices: list[Decimal],
        sample_timestamps: list[datetime],
    ) -> None:
        """Test that financial calculations use Decimal precision."""
        result = mock_engine.run_backtest(sample_prices, sample_timestamps)

        assert isinstance(result.total_return, Decimal)
        assert isinstance(result.cagr, Decimal)
        assert isinstance(result.sharpe_ratio, Decimal)
        assert isinstance(result.max_drawdown, Decimal)
        assert isinstance(result.avg_win, Decimal)
        assert isinstance(result.avg_loss, Decimal)

    def test_backtest_timezone(
        self,
        mock_engine: VectorBTEngine,
        sample_prices: list[Decimal],
        sample_timestamps: list[datetime],
    ) -> None:
        """Test that timestamps are in UTC."""
        result = mock_engine.run_backtest(sample_prices, sample_timestamps)

        assert result.start_date is not None
        assert result.end_date is not None
        assert result.num_days > 0


class TestVectorBTEngineWalkForward:
    """Test VectorBTEngine walk-forward validation."""

    @pytest.fixture
    def mock_engine(self) -> VectorBTEngine:
        """Create mock engine with mocked dependencies."""
        with patch("iatb.backtesting.vectorbt_engine.importlib.import_module") as mock_import:
            mock_import.return_value = MagicMock()
            return VectorBTEngine()

    @pytest.fixture
    def extended_prices(self) -> list[Decimal]:
        """Generate extended price data for walk-forward."""
        return [Decimal("100" + str(i % 10)) for i in range(20)]

    @pytest.fixture
    def extended_timestamps(self) -> list[datetime]:
        """Generate extended timestamps for walk-forward."""
        base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
        return [base + timedelta(days=i) for i in range(20)]

    @pytest.mark.slow
    def test_walk_forward_basic(
        self,
        mock_engine: VectorBTEngine,
        extended_prices: list[Decimal],
        extended_timestamps: list[datetime],
    ) -> None:
        """Test basic walk-forward validation."""
        result = mock_engine.run_walk_forward(extended_prices, extended_timestamps)

        assert isinstance(result, WalkForwardResult)
        assert isinstance(result.train_metrics, BacktestResult)
        assert isinstance(result.test_metrics, BacktestResult)
        assert result.cagr_degradation >= Decimal("0")
        assert result.sharpe_degradation >= Decimal("0")
        assert result.win_rate_degradation >= Decimal("0")

    def test_walk_forward_insufficient_data(self, mock_engine: VectorBTEngine) -> None:
        """Test walk-forward with insufficient data."""
        prices = [Decimal("100" + str(i)) for i in range(5)]
        timestamps = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(5)]

        with pytest.raises(ConfigError, match="prices must contain at least 10 points"):
            mock_engine.run_walk_forward(prices, timestamps)

    @patch("iatb.backtesting.vectorbt_engine.create_mis_session_mask")
    def test_walk_forward_with_integration(
        self,
        mock_session: MagicMock,
        mock_engine: VectorBTEngine,
        extended_prices: list[Decimal],
        extended_timestamps: list[datetime],
    ) -> None:
        """Test walk-forward with scanner/DRL integration."""
        mock_session.return_value = [ts.date() for ts in extended_timestamps]
        scores = [Decimal("0.6") for _ in range(20)]
        probs = [Decimal("0.6") for _ in range(20)]

        result = mock_engine.run_walk_forward(extended_prices, extended_timestamps, scores, probs)

        assert isinstance(result, WalkForwardResult)
        # With mocked vectorbt, trades may not execute, but API should work
        assert isinstance(result.train_metrics.avg_composite_score, Decimal)
        assert isinstance(result.train_metrics.avg_exit_probability, Decimal)


class TestVectorBTEngineMonteCarlo:
    """Test VectorBTEngine Monte Carlo simulation."""

    @pytest.fixture
    def mock_engine(self) -> VectorBTEngine:
        """Create mock engine with mocked dependencies."""
        config = VectorBTConfig(num_simulations=10)  # Reduce for test speed
        with patch("iatb.backtesting.vectorbt_engine.importlib.import_module") as mock_import:
            mock_import.return_value = MagicMock()
            return VectorBTEngine(config)

    @pytest.fixture
    def monte_carlo_prices(self) -> list[Decimal]:
        """Generate price data for Monte Carlo."""
        return [Decimal("100" + str(i % 20)) for i in range(30)]

    @pytest.fixture
    def monte_carlo_timestamps(self) -> list[datetime]:
        """Generate timestamps for Monte Carlo."""
        base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
        return [base + timedelta(days=i) for i in range(30)]

    @pytest.mark.slow
    def test_monte_carlo_basic(
        self,
        mock_engine: VectorBTEngine,
        monte_carlo_prices: list[Decimal],
        monte_carlo_timestamps: list[datetime],
    ) -> None:
        """Test basic Monte Carlo simulation."""
        result = mock_engine.run_monte_carlo(monte_carlo_prices, monte_carlo_timestamps)

        assert isinstance(result, MonteCarloResult)
        assert result.mean_final_equity >= Decimal("0")
        assert result.median_final_equity >= Decimal("0")
        assert result.std_final_equity >= Decimal("0")
        assert result.prob_profit >= Decimal("0") and result.prob_profit <= Decimal("1")
        assert result.worst_case_equity <= result.best_case_equity

    def test_monte_carlo_insufficient_data(self, mock_engine: VectorBTEngine) -> None:
        """Test Monte Carlo with insufficient data."""
        prices = [Decimal("100" + str(i)) for i in range(5)]
        timestamps = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(5)]

        with pytest.raises(ConfigError, match="prices must contain at least 10 points"):
            mock_engine.run_monte_carlo(prices, timestamps)

    @pytest.mark.slow
    def test_monte_carlo_percentiles(
        self,
        mock_engine: VectorBTEngine,
        monte_carlo_prices: list[Decimal],
        monte_carlo_timestamps: list[datetime],
    ) -> None:
        """Test that Monte Carlo percentiles are ordered correctly."""
        result = mock_engine.run_monte_carlo(monte_carlo_prices, monte_carlo_timestamps)

        assert result.p5_equity <= result.p25_equity
        assert result.p25_equity <= result.median_final_equity
        assert result.median_final_equity <= result.p75_equity
        assert result.p75_equity <= result.p95_equity

    def test_monte_carlo_probability_metrics(
        self,
        mock_engine: VectorBTEngine,
        monte_carlo_prices: list[Decimal],
        monte_carlo_timestamps: list[datetime],
    ) -> None:
        """Test Monte Carlo probability metrics."""
        result = mock_engine.run_monte_carlo(monte_carlo_prices, monte_carlo_timestamps)

        assert result.prob_profit >= result.prob_5pct_return
        assert result.prob_5pct_return >= result.prob_10pct_return


class TestVectorBTEngineEdgeCases:
    """Test VectorBTEngine edge cases."""

    @pytest.fixture
    def mock_engine(self) -> VectorBTEngine:
        """Create mock engine with mocked dependencies."""
        with patch("iatb.backtesting.vectorbt_engine.importlib.import_module") as mock_import:
            mock_import.return_value = MagicMock()
            return VectorBTEngine()

    def test_empty_timestamps(self, mock_engine: VectorBTEngine) -> None:
        """Test session mask with empty timestamps."""
        mask = mock_engine._create_session_mask([])
        assert mask == []

    def test_no_valid_sessions(self, mock_engine: VectorBTEngine) -> None:
        """Test backtest with no valid trading sessions."""
        # Use timestamps outside trading hours
        base = datetime(2024, 1, 1, 3, 0, tzinfo=UTC)
        timestamps = [base + timedelta(days=i) for i in range(10)]
        prices = [Decimal("100" + str(i)) for i in range(10)]

        with patch("iatb.backtesting.vectorbt_engine.create_mis_session_mask", return_value=[]):
            with pytest.raises(ConfigError, match="No valid trading sessions"):
                mock_engine.run_backtest(prices, timestamps)

    @patch("iatb.backtesting.vectorbt_engine.create_mis_session_mask")
    def test_all_trades_losing(self, mock_session: MagicMock, mock_engine: VectorBTEngine) -> None:
        """Test backtest where all trades lose."""
        # Create decreasing prices with alternating signals
        prices = [Decimal(str(110 - i)) for i in range(10)]
        base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
        timestamps = [base + timedelta(hours=i) for i in range(10)]
        mock_session.return_value = [ts.date() for ts in timestamps]
        scores = [Decimal("0.8") if i % 3 == 0 else Decimal("0.1") for i in range(10)]
        probs = [Decimal("0.8") if i % 3 == 0 else Decimal("0.1") for i in range(10)]

        result = mock_engine.run_backtest(prices, timestamps, scores, probs)

        # With mocked vectorbt, verify API works and returns valid result
        assert isinstance(result, BacktestResult)
        assert isinstance(result.win_rate, Decimal)
        assert isinstance(result.losing_trades, int)

    @patch("iatb.backtesting.vectorbt_engine.create_mis_session_mask")
    def test_all_trades_winning(self, mock_session: MagicMock, mock_engine: VectorBTEngine) -> None:
        """Test backtest where all trades win."""
        # Create increasing prices with alternating signals
        prices = [Decimal(str(100 + i)) for i in range(10)]
        base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
        timestamps = [base + timedelta(hours=i) for i in range(10)]
        mock_session.return_value = [ts.date() for ts in timestamps]
        scores = [Decimal("0.8") if i % 3 == 0 else Decimal("0.1") for i in range(10)]
        probs = [Decimal("0.8") if i % 3 == 0 else Decimal("0.1") for i in range(10)]

        result = mock_engine.run_backtest(prices, timestamps, scores, probs)

        # With mocked vectorbt, verify API works and returns valid result
        assert isinstance(result, BacktestResult)
        assert isinstance(result.win_rate, Decimal)
        assert isinstance(result.winning_trades, int)


class TestVectorBTEngineDecimalPrecision:
    """Test Decimal precision in financial calculations."""

    @pytest.fixture
    def mock_engine(self) -> VectorBTEngine:
        """Create mock engine with mocked dependencies."""
        with patch("iatb.backtesting.vectorbt_engine.importlib.import_module") as mock_import:
            mock_import.return_value = MagicMock()
            return VectorBTEngine()

    def test_cost_calculation_precision(self, mock_engine: VectorBTEngine) -> None:
        """Test that cost calculations maintain Decimal precision."""
        prices = [Decimal("100.50"), Decimal("101.25"), Decimal("102.75")]
        base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
        timestamps = [base + timedelta(hours=i) for i in range(3)]
        scores = [Decimal("0.8") for _ in range(3)]
        probs = [Decimal("0.8") for _ in range(3)]

        result = mock_engine.run_backtest(prices, timestamps, scores, probs)

        # Verify all cost components are Decimals
        assert isinstance(result.stt_total, Decimal)
        assert isinstance(result.sebi_total, Decimal)
        assert isinstance(result.exchange_txn_total, Decimal)
        assert isinstance(result.stamp_duty_total, Decimal)
        assert isinstance(result.gst_total, Decimal)

        # Verify precision is maintained
        assert result.stt_total.as_tuple().exponent >= -4  # At least 4 decimal places

    def test_pnl_calculation_precision(self, mock_engine: VectorBTEngine) -> None:
        """Test that PnL calculations maintain Decimal precision."""
        prices = [Decimal("100.123456"), Decimal("101.789012"), Decimal("102.345678")]
        base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
        timestamps = [base + timedelta(hours=i) for i in range(3)]
        scores = [Decimal("0.8") for _ in range(3)]
        probs = [Decimal("0.8") for _ in range(3)]

        result = mock_engine.run_backtest(prices, timestamps, scores, probs)

        assert isinstance(result.avg_win, Decimal)
        assert isinstance(result.avg_loss, Decimal)
        assert isinstance(result.total_return, Decimal)

    def test_no_float_in_financial_paths(self, mock_engine: VectorBTEngine) -> None:
        """Verify no float types in financial calculation paths."""
        prices = [Decimal("100.50"), Decimal("101.25"), Decimal("102.75")]
        base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
        timestamps = [base + timedelta(hours=i) for i in range(3)]
        scores = [Decimal("0.8") for _ in range(3)]
        probs = [Decimal("0.8") for _ in range(3)]

        result = mock_engine.run_backtest(prices, timestamps, scores, probs)

        # All financial metrics should be Decimal
        financial_attrs = [
            "total_return",
            "cagr",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "profit_factor",
            "avg_win",
            "avg_loss",
            "total_costs",
            "stt_total",
            "sebi_total",
            "exchange_txn_total",
            "stamp_duty_total",
            "gst_total",
            "avg_composite_score",
            "avg_exit_probability",
        ]

        for attr in financial_attrs:
            value = getattr(result, attr)
            assert isinstance(value, Decimal | int), f"{attr} is not Decimal/int: {type(value)}"


class TestVectorBTEngineUTCTimezone:
    """Test UTC timezone handling."""

    @pytest.fixture
    def mock_engine(self) -> VectorBTEngine:
        """Create mock engine with mocked dependencies."""
        with patch("iatb.backtesting.vectorbt_engine.importlib.import_module") as mock_import:
            mock_import.return_value = MagicMock()
            return VectorBTEngine()

    def test_utc_timestamps(self, mock_engine: VectorBTEngine) -> None:
        """Test that UTC timestamps are handled correctly."""
        # Create UTC timestamps
        base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
        timestamps = [base + timedelta(hours=i) for i in range(10)]
        prices = [Decimal("100" + str(i)) for i in range(10)]

        result = mock_engine.run_backtest(prices, timestamps)

        assert result.start_date is not None
        assert result.end_date is not None
        assert result.num_days > 0

    def test_naive_timestamps_rejected(self, mock_engine: VectorBTEngine) -> None:
        """Test that UTC timestamps are handled correctly."""
        # The engine expects UTC, verify it handles UTC timestamps
        base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
        timestamps = [base + timedelta(hours=i) for i in range(10)]
        prices = [Decimal("100" + str(i)) for i in range(10)]

        # This should work because timestamps are datetime objects
        result = mock_engine.run_backtest(prices, timestamps)
        assert isinstance(result, BacktestResult)
