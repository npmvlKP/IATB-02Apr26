"""
Scan cycle implementation for automated trading pipeline.

This module provides the main run_scan_cycle() function that orchestrates:
  1. Market data fetch
  2. Sentiment analysis
  3. Strength scoring
  4. Scanner execution
  5. Paper trade execution
  6. Audit logging
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from iatb.core.enums import Exchange, OrderSide
from iatb.core.exceptions import ConfigError
from iatb.core.pipeline_health import (
    PipelineHealthMonitor,
    PipelineRun,
    PipelineStage,
)
from iatb.data.base import DataProvider
from iatb.data.kite_provider import KiteProvider
from iatb.execution.base import OrderRequest
from iatb.execution.order_manager import OrderManager
from iatb.execution.order_throttle import OrderThrottle
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.pre_trade_validator import PreTradeConfig
from iatb.execution.trade_audit import TradeAuditLogger
from iatb.market_strength.regime_detector import RegimeDetector
from iatb.market_strength.strength_scorer import StrengthScorer
from iatb.ml.readiness import check_ml_readiness
from iatb.risk.daily_loss_guard import DailyLossGuard
from iatb.risk.kill_switch import KillSwitch
from iatb.scanner.instrument_scanner import ScannerConfig, ScannerResult, SortDirection
from iatb.selection.instrument_scorer import InstrumentScorer
from iatb.selection.ranking import RankingConfig
from iatb.sentiment.aggregator import SentimentAggregator
from iatb.sentiment.aion_analyzer import AionAnalyzer
from iatb.sentiment.finbert_analyzer import FinbertAnalyzer

_LOGGER = logging.getLogger(__name__)

_module_health_monitor = PipelineHealthMonitor()
_module_pipeline_counter = 0

_cached_symbols: list[str] | None = None


def _load_symbols_from_config() -> list[str] | None:
    """Load symbols from config/watchlist.toml.

    Attempts to load NSE symbols from the watchlist configuration.
    Falls back to None if config is unavailable or empty.

    Returns:
        List of symbols from config, or None if unavailable.
    """
    try:
        from iatb.core.config_manager import get_config_manager

        config_manager = get_config_manager()
        config = config_manager.get_config()

        # Get NSE symbols (default exchange for scanner)
        nse_symbols = config.get_symbols(exchange=Exchange.NSE)

        if nse_symbols:
            _LOGGER.info(
                "Loaded %d symbols from config/watchlist.toml [NSE]",
                len(nse_symbols),
                extra={"symbol_count": len(nse_symbols)},
            )
            return nse_symbols
        else:
            _LOGGER.warning(
                "No NSE symbols found in config/watchlist.toml",
                extra={"config_path": "config/watchlist.toml"},
            )
            return None

    except ConfigError as exc:
        _LOGGER.warning(
            "Failed to load config/watchlist.toml: %s. Will use defaults.",
            exc,
        )
        return None
    except Exception as exc:
        _LOGGER.exception(
            "Unexpected error loading config/watchlist.toml: %s. Will use defaults.",
            exc,
        )
        return None


def refresh_symbols() -> list[str] | None:
    """Refresh the symbol cache from config.

    Hot-reloads symbols from config/watchlist.toml at runtime.
    Clears the module-level cache and reloads from config.

    Returns:
        List of refreshed symbols, or None if config unavailable.
    """
    global _cached_symbols
    _cached_symbols = None

    symbols = _load_symbols_from_config()
    if symbols:
        _cached_symbols = symbols
        _LOGGER.info(
            "Refreshed symbol cache: %d symbols",
            len(symbols),
        )
    else:
        _LOGGER.info("Refreshed symbol cache: using defaults (config unavailable)")

    return symbols


def _check_ml_readiness_and_log(errors: list[str]) -> None:
    """Check ML model readiness and log status.

    This performs health checks on all ML models to detect Windows DLL issues
    or other problems early, enabling graceful degradation.

    Args:
        errors: List to collect error messages.
    """
    _LOGGER.info("Step 0: Checking ML model readiness...")
    check_ml_readiness(errors)
    if not errors:
        _LOGGER.info("  ✓ ML readiness check complete")
    else:
        _LOGGER.warning("  ⚠ ML readiness check found %d issue(s)", len(errors))


class ScanCycleResult:
    """Result of a complete scan cycle."""

    def __init__(
        self,
        scanner_result: ScannerResult | None,
        trades_executed: int,
        total_pnl: Decimal,
        errors: list[str],
        timestamp_utc: datetime,
        pipeline_id: str | None = None,
    ) -> None:
        self.scanner_result = scanner_result
        self.trades_executed = trades_executed
        self.total_pnl = total_pnl
        self.errors = errors
        self.timestamp_utc = timestamp_utc
        self.pipeline_id = pipeline_id


def _create_sentiment_aggregator() -> SentimentAggregator | None:
    """Create SentimentAggregator instance for scanner.

    Returns:
        SentimentAggregator instance or None if initialization fails.
    """
    try:
        aggregator = SentimentAggregator(
            finbert=FinbertAnalyzer(),
            aion=AionAnalyzer(),
        )
        _LOGGER.info("Sentiment aggregator initialized with FinBERT + AION")
        return aggregator
    except Exception as exc:
        _LOGGER.warning("Sentiment aggregator failed to initialize: %s", exc)
        return None


def _create_strength_scorer() -> StrengthScorer:
    """Create StrengthScorer instance for market strength evaluation.

    Returns:
        StrengthScorer instance with caching enabled.
    """
    return StrengthScorer(cache_enabled=True)


def _create_regime_detector() -> RegimeDetector:
    """Create RegimeDetector instance for market regime detection.

    Returns:
        RegimeDetector instance.
    """
    return RegimeDetector()


def _create_instrument_scorer() -> InstrumentScorer:
    """Create InstrumentScorer instance for composite scoring.

    Returns:
        InstrumentScorer instance with default configuration.
    """
    return InstrumentScorer(ranking_config=RankingConfig())


def _initialize_sentiment_aggregator(errors: list[str]) -> SentimentAggregator | None:
    """Initialize sentiment aggregator.

    Args:
        errors: List to collect error messages.

    Returns:
        SentimentAggregator instance or None.
    """
    try:
        aggregator = _create_sentiment_aggregator()
        if aggregator is not None:
            _LOGGER.info("  ✓ Sentiment aggregator ready")
        return aggregator
    except Exception as exc:
        error_msg = f"Failed to initialize sentiment aggregator: {exc}"
        _LOGGER.error("  ✗ %s", error_msg)
        errors.append(error_msg)
        return None


def _initialize_strength_scorer(errors: list[str]) -> StrengthScorer:
    """Initialize strength scorer for market strength evaluation.

    Args:
        errors: List to collect error messages.

    Returns:
        StrengthScorer instance.
    """
    try:
        scorer = _create_strength_scorer()
        _LOGGER.info("  ✓ Strength scorer ready")
        return scorer
    except Exception as exc:
        error_msg = f"Failed to initialize strength scorer: {exc}"
        _LOGGER.error("  ✗ %s", error_msg)
        errors.append(error_msg)
        return StrengthScorer(cache_enabled=False)


def _create_order_manager(
    audit_logger: TradeAuditLogger | None,
    errors: list[str],
) -> OrderManager | None:
    """Create and configure order manager.

    Args:
        audit_logger: Optional pre-configured TradeAuditLogger.
        errors: List to collect error messages.

    Returns:
        OrderManager instance or None if initialization fails.
    """
    try:
        executor = PaperExecutor()
        kill_switch = KillSwitch(executor)
        config = PreTradeConfig(
            max_order_quantity=Decimal("100"),
            max_order_value=Decimal("500000"),
            max_price_deviation_pct=Decimal("0.05"),
            max_position_per_symbol=Decimal("200"),
            max_portfolio_exposure=Decimal("1000000"),
        )
        daily_guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("1000000"),
            kill_switch=kill_switch,
        )
        audit = audit_logger or TradeAuditLogger(Path("data/audit/trades.sqlite"))
        throttle = OrderThrottle(max_ops=10)

        manager = OrderManager(
            executor=executor,
            kill_switch=kill_switch,
            pre_trade_config=config,
            daily_loss_guard=daily_guard,
            audit_logger=audit,
            order_throttle=throttle,
            algo_id="IATB-SCAN-001",
        )
        _LOGGER.info("  ✓ Order manager initialized")
        return manager
    except Exception as exc:
        error_msg = f"Failed to initialize order manager: {exc}"
        _LOGGER.error("  ✗ %s", error_msg)
        errors.append(error_msg)
        return None


def _initialize_data_provider(
    data_provider: DataProvider | None,
    errors: list[str],
) -> DataProvider | None:
    """Initialize or validate data provider.

    Args:
        data_provider: Optional pre-configured DataProvider.
        errors: List to collect error messages.

    Returns:
        Configured DataProvider or None if initialization fails.
    """
    if data_provider is not None:
        _LOGGER.info("  ✓ Using provided data provider: %s", type(data_provider).__name__)
        return data_provider

    # Try to create KiteProvider from environment variables
    try:
        provider = KiteProvider.from_env()
        _LOGGER.info("  ✓ KiteProvider initialized from environment")
        return provider
    except ConfigError as exc:
        error_msg = f"KiteProvider initialization failed: {exc}"
        _LOGGER.warning("  ⚠ %s", error_msg)
        _LOGGER.warning("  ⚠ Scanner will require custom_data or explicit data_provider")
        errors.append(error_msg)
        return None


def _initialize_analyzers_and_order_manager(
    order_manager: OrderManager | None,
    audit_logger: TradeAuditLogger | None,
    errors: list[str],
) -> tuple[
    SentimentAggregator | None,
    RegimeDetector,
    InstrumentScorer,
    StrengthScorer,
    OrderManager | None,
]:
    """Initialize sentiment aggregator, regime detector, instrument scorer,
    strength scorer, and order manager.

    Args:
        order_manager: Optional pre-configured OrderManager.
        audit_logger: Optional pre-configured TradeAuditLogger.
        errors: List to collect error messages.

    Returns:
        Tuple of (sentiment_aggregator, regime_detector, instrument_scorer,
        strength_scorer, order_manager).
        Returns None for order_manager if initialization fails.
    """
    sentiment_aggregator = _initialize_sentiment_aggregator(errors)
    regime_detector = _create_regime_detector()
    instrument_scorer = _create_instrument_scorer()
    strength_scorer = _initialize_strength_scorer(errors)

    if order_manager is None:
        order_manager = _create_order_manager(audit_logger, errors)
        if order_manager is None:
            return sentiment_aggregator, regime_detector, instrument_scorer, strength_scorer, None

    return sentiment_aggregator, regime_detector, instrument_scorer, strength_scorer, order_manager


def _create_scanner(
    scanner_config: ScannerConfig | None,
    sentiment_aggregator: SentimentAggregator | None,
    regime_detector: RegimeDetector,
    instrument_scorer: InstrumentScorer,
    strength_scorer: StrengthScorer,
    data_provider: DataProvider | None,
    symbols: Sequence[str],
) -> Any:
    """Create InstrumentScanner instance.

    Args:
        scanner_config: Scanner configuration.
        sentiment_aggregator: SentimentAggregator instance.
        regime_detector: RegimeDetector instance.
        instrument_scorer: InstrumentScorer for composite scoring.
        strength_scorer: StrengthScorer for market strength evaluation.
        data_provider: DataProvider for market data.
        symbols: List of symbols to scan.

    Returns:
        InstrumentScanner instance.
    """
    from iatb.scanner.instrument_scanner import InstrumentScanner

    return InstrumentScanner(
        config=scanner_config,
        data_provider=data_provider,
        strength_scorer=strength_scorer,
        sentiment_aggregator=sentiment_aggregator,
        regime_detector=regime_detector,
        instrument_scorer=instrument_scorer,
        symbols=list(symbols),
    )


def _log_scan_results(scanner_result: ScannerResult) -> None:
    """Log scan execution results.

    Args:
        scanner_result: Scanner result to log.
    """
    _LOGGER.info(
        "  ✓ Scan complete: %d gainers, %d losers",
        len(scanner_result.gainers),
        len(scanner_result.losers),
    )
    _LOGGER.info(
        "  Total scanned: %d, Filtered: %d",
        scanner_result.total_scanned,
        scanner_result.filtered_count,
    )


def _execute_scanner(
    symbols: Sequence[str],
    scanner_config: ScannerConfig | None,
    sentiment_aggregator: SentimentAggregator | None,
    regime_detector: RegimeDetector,
    instrument_scorer: InstrumentScorer,
    strength_scorer: StrengthScorer,
    data_provider: DataProvider | None,
    errors: list[str],
) -> ScannerResult | None:
    """Execute the instrument scanner.

    Args:
        symbols: List of symbols to scan.
        scanner_config: Optional scanner configuration.
        sentiment_aggregator: SentimentAggregator instance.
        regime_detector: RegimeDetector instance.
        instrument_scorer: InstrumentScorer for composite scoring.
        strength_scorer: StrengthScorer for market strength evaluation.
        data_provider: DataProvider for market data.
        errors: List to collect error messages.

    Returns:
        ScannerResult if successful, None otherwise.
    """
    try:
        scanner = _create_scanner(
            scanner_config,
            sentiment_aggregator,
            regime_detector,
            instrument_scorer,
            strength_scorer,
            data_provider,
            symbols,
        )
        scanner_result: ScannerResult = scanner.scan(direction=SortDirection.GAINERS)
        _log_scan_results(scanner_result)
        return scanner_result
    except Exception as exc:
        error_msg = f"Scanner failed: {exc}"
        _LOGGER.exception("  ✗ %s", error_msg)
        errors.append(error_msg)
        return None


def _calculate_fill_pnl(result: Any) -> tuple[Decimal, bool]:
    """Calculate PnL from filled order.

    Args:
        result: Order result from order manager.

    Returns:
        Tuple of (pnl_value, was_filled).
    """
    from iatb.core.enums import OrderStatus

    if result.status == OrderStatus.FILLED and result.filled_quantity > Decimal("0"):
        fill_value = result.filled_quantity * result.average_price
        _LOGGER.debug(
            "  Fill value: %s (qty: %s @ %s)",
            fill_value,
            result.filled_quantity,
            result.average_price,
        )
        return fill_value, True
    return Decimal("0"), False


def _log_trade_execution(
    trade_count: int,
    side: OrderSide,
    symbol: str,
    price: Decimal,
    status: str,
) -> None:
    """Log trade execution details.

    Args:
        trade_count: Trade number.
        side: Order side.
        symbol: Symbol traded.
        price: Average fill price.
        status: Order status.
    """
    _LOGGER.info(
        "  ✓ Trade #%d: %s %s %s @ %s → %s",
        trade_count,
        side.value,
        symbol,
        Decimal("10"),
        price,
        status,
    )


def _execute_single_trade(
    candidate: Any,
    side: OrderSide,
    order_manager: OrderManager,
    errors: list[str],
    trade_count: int,
) -> tuple[int, Decimal]:
    """Execute a single trade for a candidate.

    Args:
        candidate: ScannerCandidate object.
        side: Order side (BUY or SELL).
        order_manager: OrderManager instance.
        errors: List to collect error messages.
        trade_count: Current trade count for logging.

    Returns:
        Tuple of (updated_trade_count, pnl_contribution).
    """
    try:
        request = OrderRequest(
            exchange=candidate.exchange,
            symbol=candidate.symbol,
            side=side,
            quantity=Decimal("10"),  # Fixed quantity for paper trading
            price=candidate.close_price,
        )

        result = order_manager.place_order(request, strategy_id="scan_cycle")
        trade_count += 1

        pnl, was_filled = _calculate_fill_pnl(result)
        _log_trade_execution(
            trade_count, side, candidate.symbol, result.average_price, result.status.value
        )

        return trade_count, pnl

    except Exception as exc:
        error_msg = f"Trade failed for {candidate.symbol}: {exc}"
        _LOGGER.error("  ✗ %s", error_msg)
        errors.append(error_msg)
        return trade_count, Decimal("0")


def _execute_trades_for_candidates(
    candidates: list[Any],
    side: OrderSide,
    order_manager: OrderManager,
    errors: list[str],
) -> tuple[int, Decimal]:
    """Execute trades for a list of candidates.

    Args:
        candidates: List of ScannerCandidate objects.
        side: Order side (BUY or SELL).
        order_manager: OrderManager instance.
        errors: List to collect error messages.

    Returns:
        Tuple of (trades_executed, total_pnl).
    """
    trades_executed = 0
    total_pnl = Decimal("0")

    for candidate in candidates:
        trades_executed, pnl = _execute_single_trade(
            candidate, side, order_manager, errors, trades_executed
        )
        total_pnl += pnl

    return trades_executed, total_pnl


def _filter_candidates_by_sentiment(
    candidates: list[Any],
    min_score: Decimal,
    max_count: int,
    side: OrderSide,
) -> list[Any]:
    """Filter candidates by sentiment score.

    Args:
        candidates: List of ScannerCandidate objects.
        min_score: Minimum sentiment score threshold.
        max_count: Maximum number of candidates to return.
        side: Order side (BUY or SELL).

    Returns:
        Filtered list of candidates.
    """
    filtered = []
    for candidate in candidates[:max_count]:
        if (side == OrderSide.BUY and candidate.sentiment_score > min_score) or (
            side == OrderSide.SELL and candidate.sentiment_score < min_score
        ):
            filtered.append(candidate)
        else:
            _LOGGER.debug(
                "  Skipping %s %s with sentiment: %s",
                "gainer" if side == OrderSide.BUY else "loser",
                candidate.symbol,
                candidate.sentiment_score,
            )
    return filtered


def _execute_paper_trades(
    scanner_result: ScannerResult,
    max_trades: int,
    order_manager: OrderManager,
    errors: list[str],
) -> tuple[int, Decimal]:
    """Execute paper trades on scanner results.

    Args:
        scanner_result: ScannerResult from scan execution.
        max_trades: Maximum number of trades to execute.
        order_manager: OrderManager instance.
        errors: List to collect error messages.

    Returns:
        Tuple of (total_trades_executed, total_pnl).
    """
    trades_executed = 0
    total_pnl = Decimal("0")

    # Allocate trades proportionally between gainers and losers
    max_gainer_trades = (max_trades + 1) // 2  # Ceiling division
    max_loser_trades = max_trades // 2

    # Process gainers: BUY only if sentiment is positive
    gainers_to_trade = _filter_candidates_by_sentiment(
        scanner_result.gainers, Decimal("0"), max_gainer_trades, OrderSide.BUY
    )

    gainer_trades, gainer_pnl = _execute_trades_for_candidates(
        gainers_to_trade, OrderSide.BUY, order_manager, errors
    )
    trades_executed += gainer_trades
    total_pnl += gainer_pnl

    # Process losers: SELL only if sentiment is negative
    losers_to_trade = _filter_candidates_by_sentiment(
        scanner_result.losers, Decimal("0"), max_loser_trades, OrderSide.SELL
    )

    loser_trades, loser_pnl = _execute_trades_for_candidates(
        losers_to_trade, OrderSide.SELL, order_manager, errors
    )
    trades_executed += loser_trades
    total_pnl += loser_pnl

    return trades_executed, total_pnl


def _get_default_symbols() -> list[str]:
    """Get default list of NIFTY50 symbols to scan.

    Returns:
        List of default symbols.
    """
    return [
        "RELIANCE",
        "TCS",
        "INFY",
        "HDFCBANK",
        "ICICIBANK",
        "SBIN",
        "BHARTIARTL",
        "ITC",
        "KOTAKBANK",
        "LT",
    ]


def _log_scan_cycle_start(
    timestamp_utc: datetime,
    symbols: Sequence[str] | None,
    max_trades: int,
) -> None:
    """Log scan cycle start information.

    Args:
        timestamp_utc: Current UTC timestamp.
        symbols: List of symbols to scan.
        max_trades: Maximum number of trades.
    """
    _LOGGER.info("=" * 70)
    _LOGGER.info("Starting Scan Cycle")
    _LOGGER.info("  Timestamp: %s UTC", timestamp_utc.isoformat())
    _LOGGER.info("  Symbols to scan: %s", len(symbols or []))
    _LOGGER.info("  Max trades: %d", max_trades)
    _LOGGER.info("=" * 70)


def _log_scan_cycle_complete(
    trades_executed: int,
    total_pnl: Decimal,
    error_count: int,
) -> None:
    """Log scan cycle completion summary.

    Args:
        trades_executed: Number of trades executed.
        total_pnl: Total PnL from trades.
        error_count: Number of errors encountered.
    """
    _LOGGER.info("Step 4: Audit summary...")
    _LOGGER.info("  Trades executed: %d", trades_executed)
    _LOGGER.info("  Total PnL: %s", total_pnl)
    _LOGGER.info("  Errors: %d", error_count)
    _LOGGER.info("=" * 70)
    _LOGGER.info("Scan Cycle Complete")
    _LOGGER.info("=" * 70)


def _prepare_scan_symbols(symbols: Sequence[str] | None) -> Sequence[str]:
    """Prepare symbols for scanning, using config or defaults if none provided.

    Priority order:
    1. Explicitly provided symbols (non-empty list)
    2. Fresh load from config/watchlist.toml (if empty list provided, forces reload)
    3. Cached symbols from config/watchlist.toml
    4. Default NIFTY50 symbols (fallback)

    Args:
        symbols: Optional list of symbols. Empty list forces reload from config.

    Returns:
        List of symbols to scan.
    """
    global _cached_symbols

    # Handle explicitly provided symbols (non-empty list)
    if symbols:
        _LOGGER.info("Using %d explicitly provided symbols", len(symbols))
        return symbols

    # Check cache first (only if symbols is None)
    if _cached_symbols is not None:
        _LOGGER.info("Using %d cached symbols from config", len(_cached_symbols))
        return _cached_symbols

    # Cache is empty, try to load from config
    config_symbols = _load_symbols_from_config()
    if config_symbols:
        _cached_symbols = config_symbols
        _LOGGER.info("Using %d symbols loaded from config/watchlist.toml", len(config_symbols))
        return config_symbols

    # Config loading failed, clear cache to force fresh reload next time
    _cached_symbols = None

    # Fallback to defaults
    default_symbols = _get_default_symbols()
    _LOGGER.info("Using default NIFTY50 symbols (config unavailable)")
    return default_symbols


def _initialize_scan_components(
    order_manager: OrderManager | None,
    audit_logger: TradeAuditLogger | None,
    data_provider: DataProvider | None,
    errors: list[str],
) -> tuple[
    SentimentAggregator | None,
    RegimeDetector,
    InstrumentScorer,
    StrengthScorer,
    OrderManager | None,
    DataProvider | None,
]:
    """Initialize all scan cycle components.

    Args:
        order_manager: Optional pre-configured OrderManager.
        audit_logger: Optional pre-configured TradeAuditLogger.
        data_provider: Optional pre-configured DataProvider.
        errors: List to collect error messages.

    Returns:
        Tuple of (sentiment_aggregator, regime_detector, instrument_scorer,
        strength_scorer, order_manager, data_provider).
    """
    _LOGGER.info("Step 1: Initializing components...")

    (
        sentiment_aggregator,
        regime_detector,
        instrument_scorer,
        strength_scorer,
        order_manager,
    ) = _initialize_analyzers_and_order_manager(
        order_manager,
        audit_logger,
        errors,
    )

    data_provider = _initialize_data_provider(data_provider, errors)

    return (
        sentiment_aggregator,
        regime_detector,
        instrument_scorer,
        strength_scorer,
        order_manager,
        data_provider,
    )


def _create_early_return_result(
    errors: list[str],
    timestamp_utc: datetime,
) -> ScanCycleResult:
    """Create early return result for failed initialization.

    Args:
        errors: List of error messages.
        timestamp_utc: UTC timestamp.

    Returns:
        ScanCycleResult with failure state.
    """
    return ScanCycleResult(
        scanner_result=None,
        trades_executed=0,
        total_pnl=Decimal("0"),
        errors=errors,
        timestamp_utc=timestamp_utc,
    )


def _run_scanner_step(
    symbols: Sequence[str],
    scanner_config: ScannerConfig | None,
    sentiment_aggregator: SentimentAggregator | None,
    regime_detector: RegimeDetector,
    instrument_scorer: InstrumentScorer,
    strength_scorer: StrengthScorer,
    data_provider: DataProvider | None,
    errors: list[str],
) -> ScannerResult | None:
    """Execute scanner step of the pipeline.

    Args:
        symbols: List of symbols to scan.
        scanner_config: Scanner configuration.
        sentiment_aggregator: SentimentAggregator instance.
        regime_detector: RegimeDetector instance.
        instrument_scorer: InstrumentScorer for composite scoring.
        strength_scorer: StrengthScorer for market strength evaluation.
        data_provider: DataProvider for market data.
        errors: List to collect error messages.

    Returns:
        ScannerResult if successful, None otherwise.
    """
    _LOGGER.info("Step 2: Running scanner...")
    return _execute_scanner(
        symbols,
        scanner_config,
        sentiment_aggregator,
        regime_detector,
        instrument_scorer,
        strength_scorer,
        data_provider,
        errors,
    )


def _run_trade_execution_step(
    scanner_result: ScannerResult,
    max_trades: int,
    order_manager: OrderManager | None,
    errors: list[str],
) -> tuple[int, Decimal]:
    """Execute trade execution step of the pipeline.

    Args:
        scanner_result: Scanner result from scan step.
        max_trades: Maximum trades to execute.
        order_manager: OrderManager instance.
        errors: List to collect error messages.

    Returns:
        Tuple of (trades_executed, total_pnl).
    """
    _LOGGER.info("Step 3: Executing paper trades...")
    if order_manager is None:
        _LOGGER.warning("  ⚠ Order manager not available, skipping trade execution")
        return 0, Decimal("0")
    return _execute_paper_trades(scanner_result, max_trades, order_manager, errors)


def _execute_scan_pipeline(
    symbols: Sequence[str],
    scanner_config: ScannerConfig | None,
    sentiment_aggregator: SentimentAggregator | None,
    regime_detector: RegimeDetector,
    instrument_scorer: InstrumentScorer,
    strength_scorer: StrengthScorer,
    order_manager: OrderManager | None,
    data_provider: DataProvider | None,
    max_trades: int,
    errors: list[str],
) -> tuple[ScannerResult | None, int, Decimal]:
    """Execute the main scan and trade pipeline.

    Args:
        symbols: List of symbols to scan.
        scanner_config: Scanner configuration.
        sentiment_aggregator: SentimentAggregator instance.
        regime_detector: RegimeDetector instance.
        instrument_scorer: InstrumentScorer for composite scoring.
        strength_scorer: StrengthScorer for market strength evaluation.
        order_manager: OrderManager instance (optional for scanning only).
        data_provider: DataProvider for market data.
        max_trades: Maximum trades to execute.
        errors: List of collect error messages.

    Returns:
        Tuple of (scanner_result, trades_executed, total_pnl).
    """
    scanner_result = _run_scanner_step(
        symbols,
        scanner_config,
        sentiment_aggregator,
        regime_detector,
        instrument_scorer,
        strength_scorer,
        data_provider,
        errors,
    )
    if scanner_result is None:
        return None, 0, Decimal("0")
    trades_executed, total_pnl = _run_trade_execution_step(
        scanner_result, max_trades, order_manager, errors
    )
    return scanner_result, trades_executed, total_pnl


def _initialize_scan_cycle_logging(
    timestamp_utc: datetime, symbols: Sequence[str] | None, max_trades: int, errors: list[str]
) -> None:
    """Initialize logging for scan cycle.

    Args:
        timestamp_utc: UTC timestamp.
        symbols: Symbols to scan.
        max_trades: Maximum trades.
        errors: List to collect errors.
    """
    _log_scan_cycle_start(timestamp_utc, symbols, max_trades)
    _check_ml_readiness_and_log(errors)


def _initialize_scan_cycle(
    symbols: Sequence[str] | None,
    max_trades: int,
    order_manager: OrderManager | None,
    audit_logger: TradeAuditLogger | None,
    data_provider: DataProvider | None,
    scanner_config: ScannerConfig | None,
) -> tuple[
    datetime,
    Sequence[str],
    SentimentAggregator | None,
    RegimeDetector,
    InstrumentScorer,
    StrengthScorer,
    OrderManager | None,
    DataProvider | None,
    list[str],
]:
    """Initialize scan cycle components and prepare symbols.

    Args:
        symbols: Optional list of symbols.
        max_trades: Maximum trades.
        order_manager: Optional OrderManager.
        audit_logger: Optional TradeAuditLogger.
        data_provider: Optional DataProvider.
        scanner_config: Scanner configuration.

    Returns:
        Tuple of (timestamp, symbols, sentiment_aggregator, regime_detector,
        instrument_scorer, strength_scorer, order_manager, data_provider, errors).
    """
    timestamp_utc = datetime.now(UTC)
    errors: list[str] = []
    _initialize_scan_cycle_logging(timestamp_utc, symbols, max_trades, errors)
    symbols = _prepare_scan_symbols(symbols)
    comps = _initialize_scan_components(order_manager, audit_logger, data_provider, errors)
    return (
        timestamp_utc,
        symbols,
        comps[0],
        comps[1],
        comps[2],
        comps[3],
        comps[4],
        comps[5],
        errors,
    )


def _create_final_result(
    scanner_result: ScannerResult,
    trades_executed: int,
    total_pnl: Decimal,
    errors: list[str],
    timestamp_utc: datetime,
) -> ScanCycleResult:
    """Create final scan cycle result.

    Args:
        scanner_result: Scanner result.
        trades_executed: Number of trades.
        total_pnl: Total PnL.
        errors: Error list.
        timestamp_utc: UTC timestamp.

    Returns:
        ScanCycleResult.
    """
    _log_scan_cycle_complete(trades_executed, total_pnl, len(errors))
    return ScanCycleResult(
        scanner_result=scanner_result,
        trades_executed=trades_executed,
        total_pnl=total_pnl,
        errors=errors,
        timestamp_utc=timestamp_utc,
    )


def _check_order_manager_and_return_early_if_needed(
    order_manager: OrderManager | None,
    errors: list[str],
    timestamp_utc: datetime,
) -> bool:
    """Check if order manager exists.

    Args:
        order_manager: OrderManager instance or None.
        errors: List of error messages.
        timestamp_utc: UTC timestamp.

    Returns:
        True if early return is needed (order_manager is None).
    """
    if order_manager is None:
        _create_early_return_result(errors, timestamp_utc)
        return True
    return False


def _handle_scan_result_or_early_return(
    scanner_result: ScannerResult | None,
    trades_executed: int,
    total_pnl: Decimal,
    errors: list[str],
    timestamp_utc: datetime,
) -> ScanCycleResult:
    """Handle scan result, returning early result if scan failed.

    Args:
        scanner_result: Scanner result or None if failed.
        trades_executed: Number of trades executed.
        total_pnl: Total PnL from trades.
        errors: List of error messages.
        timestamp_utc: UTC timestamp.

    Returns:
        ScanCycleResult with final or early return state.
    """
    if scanner_result is None:
        return _create_early_return_result(errors, timestamp_utc)
    return _create_final_result(scanner_result, trades_executed, total_pnl, errors, timestamp_utc)


def _execute_full_scan_cycle(  # noqa: G10
    timestamp_utc: datetime,
    symbols: Sequence[str],
    sentiment_aggregator: SentimentAggregator | None,
    regime_detector: RegimeDetector,
    instrument_scorer: InstrumentScorer,
    strength_scorer: StrengthScorer,
    order_manager: OrderManager | None,
    data_provider: DataProvider | None,
    max_trades: int,
    scanner_config: ScannerConfig | None,
    errors: list[str],
) -> ScanCycleResult:
    """Execute the full scan cycle after initialization.

    Args:
        timestamp_utc: UTC timestamp.
        symbols: List of symbols to scan.
        sentiment_aggregator: SentimentAggregator instance.
        regime_detector: RegimeDetector instance.
        instrument_scorer: InstrumentScorer for composite scoring.
        strength_scorer: StrengthScorer for market strength evaluation.
        order_manager: OrderManager instance.
        data_provider: DataProvider for market data.
        max_trades: Maximum trades to execute.
        scanner_config: Scanner configuration.
        errors: List of error messages.

    Returns:
        ScanCycleResult with results, trades, PnL, errors.
    """
    if _check_order_manager_and_return_early_if_needed(order_manager, errors, timestamp_utc):
        return _create_early_return_result(errors, timestamp_utc)

    scanner_result, trades_executed, total_pnl = _execute_scan_pipeline(
        symbols,
        scanner_config,
        sentiment_aggregator,
        regime_detector,
        instrument_scorer,
        strength_scorer,
        order_manager,
        data_provider,
        max_trades,
        errors,
    )

    return _handle_scan_result_or_early_return(
        scanner_result, trades_executed, total_pnl, errors, timestamp_utc
    )


def _run_scan_cycle_with_params(
    symbols: Sequence[str] | None,
    max_trades: int,
    order_manager: OrderManager | None,
    audit_logger: TradeAuditLogger | None,
    data_provider: DataProvider | None,
    scanner_config: ScannerConfig | None,
) -> ScanCycleResult:
    """Run scan cycle with provided parameters.

    Args:
        symbols: Symbols to scan.
        max_trades: Maximum trades.
        order_manager: Optional OrderManager.
        audit_logger: Optional TradeAuditLogger.
        data_provider: Optional DataProvider.
        scanner_config: Scanner configuration.

    Returns:
        ScanCycleResult with results.
    """
    (
        timestamp_utc,
        symbols,
        sentiment_aggregator,
        regime_detector,
        instrument_scorer,
        strength_scorer,
        order_manager,
        data_provider,
        errors,
    ) = _initialize_scan_cycle(
        symbols, max_trades, order_manager, audit_logger, data_provider, scanner_config
    )

    return _execute_full_scan_cycle(
        timestamp_utc,
        symbols,
        sentiment_aggregator,
        regime_detector,
        instrument_scorer,
        strength_scorer,
        order_manager,
        data_provider,
        max_trades,
        scanner_config,
        errors,
    )


def _generate_pipeline_id() -> str:
    """Generate a unique pipeline run ID."""
    global _module_pipeline_counter
    _module_pipeline_counter += 1
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"scan-{ts}-{_module_pipeline_counter:04d}"


def get_pipeline_health_monitor() -> PipelineHealthMonitor:
    """Get the module-level pipeline health monitor.

    Returns:
        Shared PipelineHealthMonitor instance for scan cycles.
    """
    return _module_health_monitor


def _run_timed_stage(
    pipeline_run: PipelineRun,
    stage: PipelineStage,
    stage_fn: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute a pipeline stage function with timing and health tracking.

    Args:
        pipeline_run: Active pipeline run for recording.
        stage: Pipeline stage enum value.
        stage_fn: Callable to execute.
        *args: Positional arguments for stage_fn.
        **kwargs: Keyword arguments for stage_fn.

    Returns:
        Return value of stage_fn.
    """
    start = datetime.now(UTC)
    try:
        result = stage_fn(*args, **kwargs)
        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        pipeline_run.record_stage(stage, success=True, duration_ms=duration_ms)
        return result
    except Exception as exc:
        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        pipeline_run.record_stage(stage, success=False, duration_ms=duration_ms, error=str(exc))
        raise


def run_scan_cycle(
    *,
    symbols: Sequence[str] | None = None,
    max_trades: int = 5,
    order_manager: OrderManager | None = None,
    audit_logger: TradeAuditLogger | None = None,
    data_provider: DataProvider | None = None,
    scanner_config: ScannerConfig | None = None,
    health_monitor: PipelineHealthMonitor | None = None,
) -> ScanCycleResult:
    """Execute scan cycle: fetch -> sentiment -> score -> scan -> paper-execute -> audit.

    Pipeline: fetch data -> sentiment -> score -> filter -> paper-execute -> audit.
    Args are optional; defaults pulled from env/config when not provided.
    Returns ScanCycleResult with results, trades, PnL, errors.
    """
    monitor = health_monitor or _module_health_monitor
    pipeline_id = _generate_pipeline_id()
    pipeline_run = monitor.start_run(pipeline_id)

    try:
        result = _run_scan_cycle_with_params(
            symbols, max_trades, order_manager, audit_logger, data_provider, scanner_config
        )
        result.pipeline_id = pipeline_id
        pipeline_run.finish()
        return result
    except Exception as exc:
        pipeline_run.record_stage(
            PipelineStage.COMPLETE,
            success=False,
            duration_ms=0,
            error=str(exc),
        )
        pipeline_run.finish()
        raise
