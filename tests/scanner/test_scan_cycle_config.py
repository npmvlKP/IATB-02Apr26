"""
Tests for Phase H - Scan Cycle Configuration.

Tests cover:
- Scan cycle configuration management
- Dynamic symbol loading and caching
- Component initialization with configuration
- Configuration fallback and error handling
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.scanner.scan_cycle import (
    ScanCycleResult,
    _create_order_manager,
    _create_rl_predictor,
    _create_scanner,
    _create_sentiment_analyzer,
    _create_strength_scorer,
    _execute_paper_trades,
    _filter_candidates_by_sentiment,
    _initialize_data_provider,
    _initialize_rl_predictor,
    _initialize_scan_components,
    _initialize_sentiment_analyzer,
    _initialize_strength_scorer,
    _load_symbols_from_config,
    _prepare_scan_symbols,
    refresh_symbols,
)


class TestSymbolLoadingAndCaching:
    """Test dynamic symbol loading and caching mechanisms."""

    def test_load_symbols_from_config_success(self) -> None:
        """Test successful symbol loading from config."""
        mock_config = MagicMock()
        mock_config.get_symbols.return_value = ["RELIANCE", "TCS", "INFY", "HDFCBANK"]
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = mock_config

        with patch(
            "iatb.scanner.scan_cycle.get_config_manager",
            return_value=mock_config_manager,
        ):
            symbols = _load_symbols_from_config()

        assert symbols == ["RELIANCE", "TCS", "INFY", "HDFCBANK"]
        mock_config.get_symbols.assert_called_once_with(exchange=Exchange.NSE)

    def test_load_symbols_from_config_empty(self) -> None:
        """Test loading symbols when config returns empty list."""
        mock_config = MagicMock()
        mock_config.get_symbols.return_value = []
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = mock_config

        with patch(
            "iatb.scanner.scan_cycle.get_config_manager",
            return_value=mock_config_manager,
        ):
            symbols = _load_symbols_from_config()

        assert symbols is None

    def test_load_symbols_from_config_error(self) -> None:
        """Test loading symbols when config raises ConfigError."""
        with patch(
            "iatb.scanner.scan_cycle.get_config_manager",
            side_effect=ConfigError("Config not found"),
        ):
            symbols = _load_symbols_from_config()

        assert symbols is None

    def test_refresh_symbols_clears_cache(self) -> None:
        """Test that refresh_symbols clears and reloads cache."""
        mock_config = MagicMock()
        mock_config.get_symbols.return_value = ["RELIANCE", "TCS", "INFY"]
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = mock_config

        with patch(
            "iatb.scanner.scan_cycle.get_config_manager",
            return_value=mock_config_manager,
        ):
            symbols = refresh_symbols()

        assert symbols == ["RELIANCE", "TCS", "INFY"]
        mock_config.get_symbols.assert_called_once()

    def test_refresh_symbols_with_config_error(self) -> None:
        """Test refresh_symbols handles config errors gracefully."""
        with patch(
            "iatb.scanner.scan_cycle.get_config_manager",
            side_effect=ConfigError("Config error"),
        ):
            symbols = refresh_symbols()

        assert symbols is None

    def test_prepare_scan_symbols_explicit(self) -> None:
        """Test prepare_scan_symbols uses explicit symbols."""
        symbols = _prepare_scan_symbols(["RELIANCE", "TCS"])

        assert symbols == ["RELIANCE", "TCS"]

    def test_prepare_scan_symbols_cached(self) -> None:
        """Test prepare_scan_symbols uses cached symbols."""
        # Set cache
        import iatb.scanner.scan_cycle as scan_cycle_module

        scan_cycle_module._cached_symbols = ["RELIANCE", "TCS", "INFY"]

        symbols = _prepare_scan_symbols(None)

        assert symbols == ["RELIANCE", "TCS", "INFY"]

        # Reset cache
        scan_cycle_module._cached_symbols = None

    def test_prepare_scan_symbols_load_from_config(self) -> None:
        """Test prepare_scan_symbols loads from config when cache empty."""
        mock_config = MagicMock()
        mock_config.get_symbols.return_value = ["RELIANCE", "TCS"]
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = mock_config

        with patch(
            "iatb.scanner.scan_cycle.get_config_manager",
            return_value=mock_config_manager,
        ):
            symbols = _prepare_scan_symbols(None)

        assert symbols == ["RELIANCE", "TCS"]

    def test_prepare_scan_symbols_fallback_to_defaults(self) -> None:
        """Test prepare_scan_symbols falls back to defaults when config fails."""
        with patch(
            "iatb.scanner.scan_cycle.get_config_manager",
            side_effect=ConfigError("Config error"),
        ):
            symbols = _prepare_scan_symbols(None)

        # Should return default NIFTY50 symbols
        assert len(symbols) == 10
        assert "RELIANCE" in symbols
        assert "TCS" in symbols


class TestComponentInitialization:
    """Test component initialization with configuration."""

    def test_create_sentiment_analyzer_success(self) -> None:
        """Test successful creation of sentiment analyzer."""
        with patch("iatb.scanner.scan_cycle.SentimentAggregator") as mock_aggregator:
            mock_instance = MagicMock()
            mock_aggregator.return_value = mock_instance

            analyzer = _create_sentiment_analyzer()

            assert analyzer is not None
            mock_aggregator.assert_called_once()

    def test_create_sentiment_analyzer_fallback(self) -> None:
        """Test sentiment analyzer falls back to mock on error."""
        with patch("iatb.scanner.scan_cycle.SentimentAggregator", side_effect=Exception("Failed")):
            analyzer = _create_sentiment_analyzer()

            # Should return mock analyzer
            assert analyzer is not None

    def test_create_strength_scorer(self) -> None:
        """Test creation of strength scorer."""
        scorer = _create_strength_scorer()

        assert scorer is not None

    def test_create_rl_predictor(self) -> None:
        """Test creation of RL predictor."""
        predictor = _create_rl_predictor()

        assert predictor is not None

    def test_initialize_sentiment_analyzer(self) -> None:
        """Test initialization of sentiment analyzer with error handling."""
        errors = []

        with patch(
            "iatb.scanner.scan_cycle._create_sentiment_analyzer",
            return_value=lambda x: (Decimal("0.5"), False),
        ):
            analyzer = _initialize_sentiment_analyzer(errors)

        assert analyzer is not None
        assert len(errors) == 0

    def test_initialize_sentiment_analyzer_with_error(self) -> None:
        """Test sentiment analyzer initialization error handling."""
        errors = []

        with patch(
            "iatb.scanner.scan_cycle._create_sentiment_analyzer",
            side_effect=Exception("Failed"),
        ):
            analyzer = _initialize_sentiment_analyzer(errors)

        assert analyzer is not None
        assert len(errors) == 1
        assert "Failed to initialize sentiment analyzer" in errors[0]

    def test_initialize_strength_scorer(self) -> None:
        """Test initialization of strength scorer with error handling."""
        errors = []

        scorer = _initialize_strength_scorer(errors)

        assert scorer is not None
        assert len(errors) == 0

    def test_initialize_strength_scorer_with_error(self) -> None:
        """Test strength scorer initialization error handling."""
        errors = []

        with patch(
            "iatb.scanner.scan_cycle._create_strength_scorer",
            side_effect=Exception("Failed"),
        ):
            scorer = _initialize_strength_scorer(errors)

        assert scorer is not None
        assert len(errors) == 1
        assert "Failed to initialize strength scorer" in errors[0]

    def test_initialize_rl_predictor(self) -> None:
        """Test initialization of RL predictor with error handling."""
        errors = []

        predictor = _initialize_rl_predictor(errors)

        assert predictor is not None
        assert len(errors) == 0

    def test_initialize_rl_predictor_with_error(self) -> None:
        """Test RL predictor initialization error handling."""
        errors = []

        with patch(
            "iatb.scanner.scan_cycle._create_rl_predictor",
            side_effect=Exception("Failed"),
        ):
            predictor = _initialize_rl_predictor(errors)

        assert predictor is not None
        assert len(errors) == 1
        assert "Failed to initialize RL predictor" in errors[0]

    def test_create_order_manager(self) -> None:
        """Test creation of order manager."""
        errors = []

        order_manager = _create_order_manager(None, errors)

        assert order_manager is not None
        assert len(errors) == 0

    def test_create_order_manager_with_error(self) -> None:
        """Test order manager creation error handling."""
        errors = []

        with patch("iatb.scanner.scan_cycle.PaperExecutor", side_effect=Exception("Failed")):
            order_manager = _create_order_manager(None, errors)

        assert order_manager is None
        assert len(errors) == 1
        assert "Failed to initialize order manager" in errors[0]

    def test_initialize_data_provider_provided(self) -> None:
        """Test data provider initialization when provider is provided."""
        errors = []
        mock_dp = MagicMock()

        result = _initialize_data_provider(mock_dp, errors)

        assert result is mock_dp
        assert len(errors) == 0

    def test_initialize_data_provider_from_env(self) -> None:
        """Test data provider initialization from environment."""
        errors = []

        with patch("iatb.scanner.scan_cycle.KiteProvider.from_env") as mock_from_env:
            mock_dp = MagicMock()
            mock_from_env.return_value = mock_dp

            result = _initialize_data_provider(None, errors)

            assert result is mock_dp
            assert len(errors) == 0

    def test_initialize_data_provider_failure(self) -> None:
        """Test data provider initialization failure handling."""
        errors = []

        with patch(
            "iatb.scanner.scan_cycle.KiteProvider.from_env",
            side_effect=ConfigError("No credentials"),
        ):
            result = _initialize_data_provider(None, errors)

            assert result is None
            assert len(errors) == 1

    def test_initialize_scan_components(self) -> None:
        """Test initialization of all scan components."""
        errors = []

        (
            sentiment_analyzer,
            rl_predictor,
            strength_scorer,
            order_manager,
            data_provider,
        ) = _initialize_scan_components(None, None, None, errors)

        assert sentiment_analyzer is not None
        assert rl_predictor is not None
        assert strength_scorer is not None
        assert order_manager is not None
        assert data_provider is None
        assert len(errors) == 0

    def test_initialize_scan_components_with_errors(self) -> None:
        """Test scan components initialization with errors."""
        errors = []

        with patch("iatb.scanner.scan_cycle.PaperExecutor", side_effect=Exception("Failed")):
            (
                sentiment_analyzer,
                rl_predictor,
                strength_scorer,
                order_manager,
                data_provider,
            ) = _initialize_scan_components(None, None, None, errors)

        assert sentiment_analyzer is not None
        assert rl_predictor is not None
        assert strength_scorer is not None
        assert order_manager is None
        assert len(errors) >= 1


class TestScannerCreation:
    """Test scanner creation with configuration."""

    def test_create_scanner_with_all_dependencies(self) -> None:
        """Test scanner creation with all dependencies."""
        mock_config = MagicMock()
        mock_dp = MagicMock()
        mock_sentiment_analyzer = MagicMock()
        mock_rl_predictor = MagicMock()
        mock_strength_scorer = MagicMock()
        symbols = ["RELIANCE", "TCS"]

        with patch("iatb.scanner.scan_cycle.InstrumentScanner") as mock_scanner_class:
            mock_scanner_instance = MagicMock()
            mock_scanner_class.return_value = mock_scanner_instance

            scanner = _create_scanner(
                mock_config,
                mock_sentiment_analyzer,
                mock_rl_predictor,
                mock_strength_scorer,
                mock_dp,
                symbols,
            )

            assert scanner is not None
            mock_scanner_class.assert_called_once()

    def test_create_scanner_with_minimal_dependencies(self) -> None:
        """Test scanner creation with minimal dependencies."""
        mock_sentiment_analyzer = MagicMock()
        mock_rl_predictor = MagicMock()
        mock_strength_scorer = MagicMock()
        symbols = ["RELIANCE"]

        with patch("iatb.scanner.scan_cycle.InstrumentScanner") as mock_scanner_class:
            mock_scanner_instance = MagicMock()
            mock_scanner_class.return_value = mock_scanner_instance

            scanner = _create_scanner(
                None,
                mock_sentiment_analyzer,
                mock_rl_predictor,
                mock_strength_scorer,
                None,
                symbols,
            )

            assert scanner is not None


class TestTradeExecution:
    """Test trade execution with configuration."""

    def test_filter_candidates_by_sentiment_buy(self) -> None:
        """Test filtering candidates for BUY side."""
        from iatb.core.enums import OrderSide

        # Create mock candidates
        candidates = []
        for score in [Decimal("0.8"), Decimal("0.5"), Decimal("0.9")]:
            candidate = MagicMock()
            candidate.sentiment_score = score
            candidates.append(candidate)

        filtered = _filter_candidates_by_sentiment(candidates, Decimal("0"), 10, OrderSide.BUY)

        # Should filter out negative/zero sentiment for BUY
        assert len(filtered) >= 1

    def test_filter_candidates_by_sentiment_sell(self) -> None:
        """Test filtering candidates for SELL side."""
        from iatb.core.enums import OrderSide

        # Create mock candidates
        candidates = []
        for score in [Decimal("-0.8"), Decimal("0.5"), Decimal("-0.9")]:
            candidate = MagicMock()
            candidate.sentiment_score = score
            candidates.append(candidate)

        filtered = _filter_candidates_by_sentiment(candidates, Decimal("0"), 10, OrderSide.SELL)

        # Should filter out positive sentiment for SELL
        assert len(filtered) >= 1

    def test_filter_candidates_max_count(self) -> None:
        """Test filtering respects max count."""
        from iatb.core.enums import OrderSide

        # Create 10 candidates
        candidates = []
        for _ in range(10):
            candidate = MagicMock()
            candidate.sentiment_score = Decimal("0.8")
            candidates.append(candidate)

        filtered = _filter_candidates_by_sentiment(candidates, Decimal("0"), 3, OrderSide.BUY)

        # Should return at most 3
        assert len(filtered) <= 3

    def test_execute_paper_trades_no_candidates(self) -> None:
        """Test paper trade execution with no candidates."""
        from iatb.scanner.instrument_scanner import ScannerResult

        scanner_result = ScannerResult(
            gainers=[],
            losers=[],
            total_scanned=0,
            filtered_count=0,
            scan_timestamp_utc=datetime.now(UTC),
        )

        mock_order_manager = MagicMock()
        errors = []

        trades, pnl = _execute_paper_trades(scanner_result, 5, mock_order_manager, errors)

        assert trades == 0
        assert pnl == Decimal("0")

    def test_execute_paper_trades_with_sentiment_filter(self) -> None:
        """Test paper trade execution respects sentiment filtering."""
        from iatb.core.enums import Exchange, OrderStatus
        from iatb.scanner.instrument_scanner import ScannerResult

        # Create mock candidates with sentiment
        mock_candidate = MagicMock()
        mock_candidate.exchange = Exchange.NSE
        mock_candidate.symbol = "RELIANCE"
        mock_candidate.close_price = Decimal("2500")
        mock_candidate.sentiment_score = Decimal("0.8")

        scanner_result = ScannerResult(
            gainers=[mock_candidate],
            losers=[],
            total_scanned=1,
            filtered_count=1,
            scan_timestamp_utc=datetime.now(UTC),
        )

        mock_order_manager = MagicMock()
        mock_result = MagicMock()
        mock_result.status = OrderStatus.FILLED
        mock_result.filled_quantity = Decimal("10")
        mock_result.average_price = Decimal("2500")
        mock_order_manager.place_order.return_value = mock_result

        errors = []

        trades, pnl = _execute_paper_trades(scanner_result, 1, mock_order_manager, errors)

        assert trades == 1
        assert pnl > Decimal("0")


class TestScanCycleResult:
    """Test ScanCycleResult class."""

    def test_scan_cycle_result_creation(self) -> None:
        """Test creation of ScanCycleResult."""
        result = ScanCycleResult(
            scanner_result=None,
            trades_executed=5,
            total_pnl=Decimal("1000"),
            errors=["Warning 1"],
            timestamp_utc=datetime.now(UTC),
        )

        assert result.scanner_result is None
        assert result.trades_executed == 5
        assert result.total_pnl == Decimal("1000")
        assert len(result.errors) == 1

    def test_scan_cycle_result_zero_trades(self) -> None:
        """Test ScanCycleResult with zero trades."""
        result = ScanCycleResult(
            scanner_result=None,
            trades_executed=0,
            total_pnl=Decimal("0"),
            errors=[],
            timestamp_utc=datetime.now(UTC),
        )

        assert result.trades_executed == 0
        assert result.total_pnl == Decimal("0")
        assert len(result.errors) == 0


class TestConfigurationFallback:
    """Test configuration fallback mechanisms."""

    def test_fallback_to_defaults_on_config_error(self) -> None:
        """Test fallback to default symbols on configuration error."""
        with patch("iatb.scanner.scan_cycle._load_symbols_from_config", return_value=None):
            symbols = _prepare_scan_symbols(None)

            # Should return default symbols
            assert len(symbols) >= 10
            assert "RELIANCE" in symbols

    def test_fallback_to_mock_sentiment_analyzer(self) -> None:
        """Test fallback to mock sentiment analyzer on initialization error."""
        errors = []

        with patch("iatb.scanner.scan_cycle.SentimentAggregator", side_effect=Exception("Failed")):
            analyzer = _initialize_sentiment_analyzer(errors)

        # Should return mock analyzer
        assert analyzer is not None
        assert len(errors) == 1

    def test_fallback_to_mock_rl_predictor(self) -> None:
        """Test fallback to mock RL predictor on initialization error."""
        errors = []

        with patch(
            "iatb.scanner.scan_cycle._create_rl_predictor",
            side_effect=Exception("Failed"),
        ):
            predictor = _initialize_rl_predictor(errors)

        # Should return mock predictor
        assert predictor is not None
        assert len(errors) == 1

    def test_fallback_strength_scorer_no_cache(self) -> None:
        """Test fallback strength scorer without cache on error."""
        errors = []

        with patch(
            "iatb.scanner.scan_cycle._create_strength_scorer",
            side_effect=Exception("Failed"),
        ):
            scorer = _initialize_strength_scorer(errors)

        # Should return scorer without cache
        assert scorer is not None
        assert len(errors) == 1


class TestConfigurationEdgeCases:
    """Test edge cases in configuration handling."""

    def test_config_with_mixed_exchanges(self) -> None:
        """Test config handling with multiple exchanges."""
        mock_config = MagicMock()
        # Return symbols for NSE
        mock_config.get_symbols.return_value = ["RELIANCE", "TCS"]
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = mock_config

        with patch(
            "iatb.scanner.scan_cycle.get_config_manager",
            return_value=mock_config_manager,
        ):
            symbols = _load_symbols_from_config()

        # Should only return NSE symbols
        assert len(symbols) == 2
        mock_config.get_symbols.assert_called_once_with(exchange=Exchange.NSE)

    def test_config_with_duplicate_symbols(self) -> None:
        """Test config handling with duplicate symbols."""
        mock_config = MagicMock()
        mock_config.get_symbols.return_value = ["RELIANCE", "TCS", "RELIANCE"]
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = mock_config

        with patch(
            "iatb.scanner.scan_cycle.get_config_manager",
            return_value=mock_config_manager,
        ):
            symbols = _load_symbols_from_config()

        # Should return as-is (deduplication is upstream)
        assert len(symbols) == 3

    def test_refresh_symbols_persists_to_cache(self) -> None:
        """Test that refresh_symbols persists to module cache."""
        import iatb.scanner.scan_cycle as scan_cycle_module

        mock_config = MagicMock()
        mock_config.get_symbols.return_value = ["RELIANCE", "TCS", "INFY"]
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = mock_config

        with patch(
            "iatb.scanner.scan_cycle.get_config_manager",
            return_value=mock_config_manager,
        ):
            refresh_symbols()

        # Verify cache is set
        assert scan_cycle_module._cached_symbols == ["RELIANCE", "TCS", "INFY"]

        # Reset cache
        scan_cycle_module._cached_symbols = None

    def test_prepare_symbols_empty_list_uses_defaults(self) -> None:
        """Test that empty symbol list uses defaults."""
        # Clear cache
        import iatb.scanner.scan_cycle as scan_cycle_module

        scan_cycle_module._cached_symbols = None

        with patch("iatb.scanner.scan_cycle._load_symbols_from_config", return_value=None):
            symbols = _prepare_scan_symbols([])

        # Empty list is falsy, should use defaults
        assert len(symbols) >= 10

    def test_initialize_components_partial_failure(self) -> None:
        """Test component initialization with partial failures."""
        errors = []

        # Mock one component to fail
        with patch("iatb.scanner.scan_cycle.PaperExecutor", side_effect=Exception("Failed")):
            (
                sentiment_analyzer,
                rl_predictor,
                strength_scorer,
                order_manager,
                data_provider,
            ) = _initialize_scan_components(None, None, None, errors)

        # Other components should still initialize
        assert sentiment_analyzer is not None
        assert rl_predictor is not None
        assert strength_scorer is not None
        # Order manager should fail
        assert order_manager is None
        assert len(errors) >= 1
