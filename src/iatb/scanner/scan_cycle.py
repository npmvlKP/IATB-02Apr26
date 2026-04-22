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
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from iatb.core.enums import Exchange, OrderSide
from iatb.core.exceptions import ConfigError
from iatb.data.base import DataProvider
from iatb.data.kite_provider import KiteProvider
from iatb.execution.base import OrderRequest
from iatb.execution.order_manager import OrderManager
from iatb.execution.order_throttle import OrderThrottle
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.pre_trade_validator import PreTradeConfig
from iatb.execution.trade_audit import TradeAuditLogger
from iatb.ml.readiness import check_ml_readiness
from iatb.risk.daily_loss_guard import DailyLossGuard
from iatb.risk.kill_switch import KillSwitch
from iatb.scanner.instrument_scanner import (
    ScannerConfig,
    ScannerResult,
    SortDirection,
    create_mock_rl_predictor,
    create_mock_sentiment_analyzer,
)
from iatb.sentiment.aggregator import SentimentAggregator
from iatb.sentiment.aion_analyzer import AionAnalyzer
from iatb.sentiment.finbert_analyzer import FinbertAnalyzer

_LOGGER = logging.getLogger(__name__)

# Module-level cache for symbols
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
    ) -> None:
        self.scanner_result = scanner_result
        self.trades_executed = trades_executed
        self.total_pnl = total_pnl
        self.errors = errors
        self.timestamp_utc = timestamp_utc


def _create_sentiment_analyzer() -> Callable[[str], tuple[Decimal, bool]]:
    """Create sentiment analyzer function for scanner.

    Returns:
        Function that takes symbol and returns (score, is_very_strong).
    """
    try:
        aggregator = SentimentAggregator(
            finbert=FinbertAnalyzer(),
            aion=AionAnalyzer(),
        )

        def analyzer(symbol: str) -> tuple[Decimal, bool]:
            # For instrument-level sentiment, use a placeholder text
            # In production, this would fetch actual news/data
            sentiment_score, _ = aggregator.analyze(f"{symbol} market analysis")
            is_very_strong = abs(sentiment_score.score) >= Decimal("0.75")
            return sentiment_score.score, is_very_strong

        _LOGGER.info("Sentiment analyzer initialized with FinBERT + AION")
        return analyzer
    except Exception as exc:
        _LOGGER.warning("Sentiment analyzer failed to initialize: %s", exc)
        _LOGGER.info("Using mock sentiment analyzer (will result in no trades)")
        return create_mock_sentiment_analyzer({})


def _create_strength_inputs() -> Any:
    """Create strength inputs for scanner.

    Returns:
        Mock strength inputs function.
    """
    # Placeholder - would integrate with actual strength scorer
    return None


def _create_rl_predictor() -> Callable[[list[Decimal]], Decimal]:
    """Create RL predictor for exit probability.

    Returns:
        Mock RL predictor function.
    """
    return create_mock_rl_predictor(probability=Decimal("0.6"))


def _initialize_sentiment_analyzer(errors: list[str]) -> Callable[[str], tuple[Decimal, bool]]:
    """Initialize sentiment analyzer.

    Args:
        errors: List to collect error messages.

    Returns:
        Sentiment analyzer function.
    """
    try:
        analyzer = _create_sentiment_analyzer()
        _LOGGER.info("  ✓ Sentiment analyzer ready")
        return analyzer
    except Exception as exc:
        error_msg = f"Failed to initialize sentiment analyzer: {exc}"
        _LOGGER.error("  ✗ %s", error_msg)
        errors.append(error_msg)
        return create_mock_sentiment_analyzer({})


def _initialize_rl_predictor(errors: list[str]) -> Callable[[list[Decimal]], Decimal]:
    """Initialize RL predictor.

    Args:
        errors: List to collect error messages.

    Returns:
        RL predictor function.
    """
    try:
        predictor = _create_rl_predictor()
        _LOGGER.info("  ✓ RL predictor ready")
        return predictor
    except Exception as exc:
        error_msg = f"Failed to initialize RL predictor: {exc}"
        _LOGGER.error("  ✗ %s", error_msg)
        errors.append(error_msg)
        return create_mock_rl_predictor()


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
    Callable[[str], tuple[Decimal, bool]],
    Callable[[list[Decimal]], Decimal],
    OrderManager | None,
]:
    """Initialize sentiment analyzer, RL predictor, and order manager.

    Args:
        order_manager: Optional pre-configured OrderManager.
        audit_logger: Optional pre-configured TradeAuditLogger.
        errors: List to collect error messages.

    Returns:
        Tuple of (sentiment_analyzer, rl_predictor, order_manager).
        Returns None for order_manager if initialization fails.
    """
    sentiment_analyzer = _initialize_sentiment_analyzer(errors)
    rl_predictor = _initialize_rl_predictor(errors)

    if order_manager is None:
        order_manager = _create_order_manager(audit_logger, errors)
        if order_manager is None:
            return sentiment_analyzer, rl_predictor, None

    return sentiment_analyzer, rl_predictor, order_manager


def _create_scanner(
    scanner_config: ScannerConfig | None,
    sentiment_analyzer: Callable[[str], tuple[Decimal, bool]],
    rl_predictor: Callable[[list[Decimal]], Decimal],
    data_provider: DataProvider | None,
    symbols: Sequence[str],
) -> Any:
    """Create InstrumentScanner instance.

    Args:
        scanner_config: Scanner configuration.
        sentiment_analyzer: Sentiment analysis function.
        rl_predictor: RL predictor function.
        data_provider: DataProvider for market data.
        symbols: List of symbols to scan.

    Returns:
        InstrumentScanner instance.
    """
    from iatb.scanner.instrument_scanner import InstrumentScanner

    return InstrumentScanner(
        config=scanner_config,
        data_provider=data_provider,
        sentiment_analyzer=sentiment_analyzer,
        rl_predictor=rl_predictor,
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
    sentiment_analyzer: Callable[[str], tuple[Decimal, bool]],
    rl_predictor: Callable[[list[Decimal]], Decimal],
    data_provider: DataProvider | None,
    errors: list[str],
) -> ScannerResult | None:
    """Execute the instrument scanner.

    Args:
        symbols: List of symbols to scan.
        scanner_config: Optional scanner configuration.
        sentiment_analyzer: Sentiment analysis function.
        rl_predictor: RL predictor function.
        data_provider: DataProvider for market data.
        errors: List to collect error messages.

    Returns:
        ScannerResult if successful, None otherwise.
    """
    try:
        scanner = _create_scanner(
            scanner_config, sentiment_analyzer, rl_predictor, data_provider, symbols
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
    1. Explicitly provided symbols
    2. Cached symbols from config/watchlist.toml
    3. Fresh load from config/watchlist.toml
    4. Default NIFTY50 symbols (fallback)

    Args:
        symbols: Optional list of symbols.

    Returns:
        List of symbols to scan.
    """
    if symbols:
        _LOGGER.info("Using %d explicitly provided symbols", len(symbols))
        return symbols

    global _cached_symbols

    # Try to use cached symbols
    if _cached_symbols is not None:
        _LOGGER.info("Using %d cached symbols from config", len(_cached_symbols))
        return _cached_symbols

    # Try to load from config
    config_symbols = _load_symbols_from_config()
    if config_symbols:
        _cached_symbols = config_symbols
        _LOGGER.info("Using %d symbols loaded from config/watchlist.toml", len(config_symbols))
        return config_symbols

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
    Callable[[str], tuple[Decimal, bool]],
    Callable[[list[Decimal]], Decimal],
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
        Tuple of (sentiment_analyzer, rl_predictor, order_manager, data_provider).
    """
    _LOGGER.info("Step 1: Initializing components...")

    sentiment_analyzer, rl_predictor, order_manager = _initialize_analyzers_and_order_manager(
        order_manager, audit_logger, errors
    )

    data_provider = _initialize_data_provider(data_provider, errors)

    return sentiment_analyzer, rl_predictor, order_manager, data_provider


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


def _execute_scan_pipeline(
    symbols: Sequence[str],
    scanner_config: ScannerConfig | None,
    sentiment_analyzer: Callable[[str], tuple[Decimal, bool]],
    rl_predictor: Callable[[list[Decimal]], Decimal],
    order_manager: OrderManager | None,
    data_provider: DataProvider | None,
    max_trades: int,
    errors: list[str],
) -> tuple[ScannerResult | None, int, Decimal]:
    """Execute the main scan and trade pipeline.

    Args:
        symbols: List of symbols to scan.
        scanner_config: Scanner configuration.
        sentiment_analyzer: Sentiment analysis function.
        rl_predictor: RL predictor function.
        order_manager: OrderManager instance (optional for scanning only).
        data_provider: DataProvider for market data.
        max_trades: Maximum trades to execute.
        errors: List to collect error messages.

    Returns:
        Tuple of (scanner_result, trades_executed, total_pnl).
    """
    # Step 2: Execute scanner
    _LOGGER.info("Step 2: Running scanner...")
    scanner_result = _execute_scanner(
        symbols, scanner_config, sentiment_analyzer, rl_predictor, data_provider, errors
    )

    if scanner_result is None:
        return None, 0, Decimal("0")

    # Step 3: Execute paper trades (only if order_manager is available)
    _LOGGER.info("Step 3: Executing paper trades...")
    if order_manager is None:
        _LOGGER.warning("  ⚠ Order manager not available, skipping trade execution")
        return scanner_result, 0, Decimal("0")

    trades_executed, total_pnl = _execute_paper_trades(
        scanner_result, max_trades, order_manager, errors
    )

    return scanner_result, trades_executed, total_pnl


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
    Callable[[str], tuple[Decimal, bool]],
    Callable[[list[Decimal]], Decimal],
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
        Tuple of (timestamp, symbols, sentiment_analyzer, rl_predictor,
        order_manager, data_provider, errors).
    """
    timestamp_utc = datetime.now(UTC)
    errors: list[str] = []

    _log_scan_cycle_start(timestamp_utc, symbols, max_trades)
    _check_ml_readiness_and_log(errors)

    symbols = _prepare_scan_symbols(symbols)
    sentiment_analyzer, rl_predictor, order_manager, data_provider = _initialize_scan_components(
        order_manager, audit_logger, data_provider, errors
    )

    return (
        timestamp_utc,
        symbols,
        sentiment_analyzer,
        rl_predictor,
        order_manager,
        data_provider,
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
) -> ScanCycleResult | None:
    """Check if order manager exists, return early result if not.

    Args:
        order_manager: OrderManager instance or None.
        errors: List of error messages.
        timestamp_utc: UTC timestamp.

    Returns:
        ScanCycleResult if order_manager is None, otherwise None.
    """
    if order_manager is None:
        return _create_early_return_result(errors, timestamp_utc)
    return None


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


def _execute_full_scan_cycle(
    timestamp_utc: datetime,
    symbols: Sequence[str],
    sentiment_analyzer: Callable[[str], tuple[Decimal, bool]],
    rl_predictor: Callable[[list[Decimal]], Decimal],
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
        sentiment_analyzer: Sentiment analysis function.
        rl_predictor: RL predictor function.
        order_manager: OrderManager instance.
        data_provider: DataProvider for market data.
        max_trades: Maximum trades to execute.
        scanner_config: Scanner configuration.
        errors: List of error messages.

    Returns:
        ScanCycleResult with results, trades, PnL, errors.
    """
    early_result = _check_order_manager_and_return_early_if_needed(
        order_manager, errors, timestamp_utc
    )
    if early_result is not None:
        return early_result

    scanner_result, trades_executed, total_pnl = _execute_scan_pipeline(
        symbols,
        scanner_config,
        sentiment_analyzer,
        rl_predictor,
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
        sentiment_analyzer,
        rl_predictor,
        order_manager,
        data_provider,
        errors,
    ) = _initialize_scan_cycle(
        symbols, max_trades, order_manager, audit_logger, data_provider, scanner_config
    )

    return _execute_full_scan_cycle(
        timestamp_utc,
        symbols,
        sentiment_analyzer,
        rl_predictor,
        order_manager,
        data_provider,
        max_trades,
        scanner_config,
        errors,
    )


def run_scan_cycle(
    *,
    symbols: Sequence[str] | None = None,
    max_trades: int = 5,
    order_manager: OrderManager | None = None,
    audit_logger: TradeAuditLogger | None = None,
    data_provider: DataProvider | None = None,
    scanner_config: ScannerConfig | None = None,
) -> ScanCycleResult:
    """Execute scan cycle: fetch → sentiment → score → scan → paper-execute → audit.

    Main entry point for automated trading. Runs full pipeline:
      1. Fetches market data via DataProvider (KiteProvider or custom)
      2. Analyzes sentiment (FinBERT + AION)
      3. Scores candidates
      4. Filters top gainers/losers
      5. Executes paper trades
      6. Logs to audit DB

    Args:
        symbols: Symbols to scan (default: NIFTY50).
        max_trades: Max trades per cycle.
        order_manager: Optional OrderManager.
        audit_logger: Optional TradeAuditLogger.
        data_provider: Optional DataProvider for market data.
            If None, attempts to create KiteProvider from environment variables.
            If environment variables not set, scanner will require custom_data.
        scanner_config: Optional scanner config.

    Returns:
        ScanCycleResult with results, trades, PnL, errors.
    """
    return _run_scan_cycle_with_params(
        symbols, max_trades, order_manager, audit_logger, data_provider, scanner_config
    )
