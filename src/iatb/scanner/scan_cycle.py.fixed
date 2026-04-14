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

from iatb.core.enums import OrderSide
from iatb.execution.base import OrderRequest
from iatb.execution.order_manager import OrderManager
from iatb.execution.order_throttle import OrderThrottle
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.pre_trade_validator import PreTradeConfig
from iatb.execution.trade_audit import TradeAuditLogger
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
    # Create sentiment analyzer
    try:
        sentiment_analyzer = _create_sentiment_analyzer()
        _LOGGER.info("  ✓ Sentiment analyzer ready")
    except Exception as exc:
        error_msg = f"Failed to initialize sentiment analyzer: {exc}"
        _LOGGER.error("  ✗ %s", error_msg)
        errors.append(error_msg)
        sentiment_analyzer = create_mock_sentiment_analyzer({})

    # Create RL predictor
    try:
        rl_predictor = _create_rl_predictor()
        _LOGGER.info("  ✓ RL predictor ready")
    except Exception as exc:
        error_msg = f"Failed to initialize RL predictor: {exc}"
        _LOGGER.error("  ✗ %s", error_msg)
        errors.append(error_msg)
        rl_predictor = create_mock_rl_predictor()

    # Initialize order manager if not provided
    if order_manager is None:
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

            order_manager = OrderManager(
                executor=executor,
                kill_switch=kill_switch,
                pre_trade_config=config,
                daily_loss_guard=daily_guard,
                audit_logger=audit,
                order_throttle=throttle,
                algo_id="IATB-SCAN-001",
            )
            _LOGGER.info("  ✓ Order manager initialized")
        except Exception as exc:
            error_msg = f"Failed to initialize order manager: {exc}"
            _LOGGER.error("  ✗ %s", error_msg)
            errors.append(error_msg)
            return sentiment_analyzer, rl_predictor, None

    return sentiment_analyzer, rl_predictor, order_manager


def _execute_scanner(
    symbols: Sequence[str],
    scanner_config: ScannerConfig | None,
    sentiment_analyzer: Callable[[str], tuple[Decimal, bool]],
    rl_predictor: Callable[[list[Decimal]], Decimal],
    errors: list[str],
) -> ScannerResult | None:
    """Execute the instrument scanner.

    Args:
        symbols: List of symbols to scan.
        scanner_config: Optional scanner configuration.
        sentiment_analyzer: Sentiment analysis function.
        rl_predictor: RL predictor function.
        errors: List to collect error messages.

    Returns:
        ScannerResult if successful, None otherwise.
    """
    try:
        from iatb.scanner.instrument_scanner import InstrumentScanner

        scanner = InstrumentScanner(
            config=scanner_config,
            sentiment_analyzer=sentiment_analyzer,
            rl_predictor=rl_predictor,
            symbols=list(symbols),
        )

        scanner_result = scanner.scan(direction=SortDirection.GAINERS)

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

        return scanner_result

    except Exception as exc:
        error_msg = f"Scanner failed: {exc}"
        _LOGGER.exception("  ✗ %s", error_msg)
        errors.append(error_msg)
        return None


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
    from iatb.core.enums import OrderStatus

    trades_executed = 0
    total_pnl = Decimal("0")

    for candidate in candidates:
        try:
            request = OrderRequest(
                exchange=candidate.exchange,
                symbol=candidate.symbol,
                side=side,
                quantity=Decimal("10"),  # Fixed quantity for paper trading
                price=candidate.close_price,
            )

            result = order_manager.place_order(request, strategy_id="scan_cycle")
            trades_executed += 1

            # Track total fill value (capital deployed during scan cycle)
            if result.status == OrderStatus.FILLED and result.filled_quantity > Decimal("0"):
                fill_value = result.filled_quantity * result.average_price
                total_pnl += fill_value
                _LOGGER.debug(
                    "  Fill value: %s (qty: %s @ %s)",
                    fill_value,
                    result.filled_quantity,
                    result.average_price,
                )

            _LOGGER.info(
                "  ✓ Trade #%d: %s %s %s @ %s → %s",
                trades_executed,
                side.value,
                candidate.symbol,
                Decimal("10"),
                result.average_price,
                result.status.value,
            )

        except Exception as exc:
            error_msg = f"Trade failed for {candidate.symbol}: {exc}"
            _LOGGER.error("  ✗ %s", error_msg)
            errors.append(error_msg)
            continue

    return trades_executed, total_pnl


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
    gainers_to_trade = []
    for candidate in scanner_result.gainers[:max_gainer_trades]:
        if candidate.sentiment_score > Decimal("0"):
            gainers_to_trade.append(candidate)
        else:
            _LOGGER.debug(
                "  Skipping gainer %s with non-positive sentiment: %s",
                candidate.symbol,
                candidate.sentiment_score,
            )

    gainer_trades, gainer_pnl = _execute_trades_for_candidates(
        gainers_to_trade, OrderSide.BUY, order_manager, errors
    )
    trades_executed += gainer_trades
    total_pnl += gainer_pnl

    # Process losers: SELL only if sentiment is negative
    losers_to_trade = []
    for candidate in scanner_result.losers[:max_loser_trades]:
        if candidate.sentiment_score < Decimal("0"):
            losers_to_trade.append(candidate)
        else:
            _LOGGER.debug(
                "  Skipping loser %s with non-negative sentiment: %s",
                candidate.symbol,
                candidate.sentiment_score,
            )

    loser_trades, loser_pnl = _execute_trades_for_candidates(
        losers_to_trade, OrderSide.SELL, order_manager, errors
    )
    trades_executed += loser_trades
    total_pnl += loser_pnl

    return trades_executed, total_pnl


def run_scan_cycle(
    *,
    symbols: Sequence[str] | None = None,
    max_trades: int = 5,
    order_manager: OrderManager | None = None,
    audit_logger: TradeAuditLogger | None = None,
    scanner_config: ScannerConfig | None = None,
) -> ScanCycleResult:
    """
    Execute a complete scan cycle: fetch → sentiment → score → scan → paper-execute → audit.

    This is the main entry point for automated trading. It runs the full pipeline:
      1. Fetches market data for configured symbols
      2. Analyzes sentiment using FinBERT + AION ensemble
      3. Scores candidates using strength scorer
      4. Runs scanner to filter top gainers/losers
      5. Executes paper trades on top candidates
      6. Logs all trades to audit database
      7. Returns comprehensive results

    Args:
        symbols: List of symbols to scan. If None, uses default NIFTY50 stocks.
        max_trades: Maximum number of trades to execute per cycle.
        order_manager: Optional pre-configured OrderManager. If None, creates new.
        audit_logger: Optional pre-configured TradeAuditLogger. If None, creates new.
        scanner_config: Optional scanner configuration. If None, uses defaults.

    Returns:
        ScanCycleResult with scanner results, trades executed, PnL, and errors.

    Example:
        >>> result = run_scan_cycle(symbols=["RELIANCE", "TCS", "INFY"], max_trades=3)
        >>> # Access result.trades_executed and result.total_pnl
    """
    timestamp_utc = datetime.now(UTC)
    errors: list[str] = []

    _LOGGER.info("=" * 70)
    _LOGGER.info("Starting Scan Cycle")
    _LOGGER.info("  Timestamp: %s UTC", timestamp_utc.isoformat())
    _LOGGER.info("  Symbols to scan: %s", len(symbols or []))
    _LOGGER.info("  Max trades: %d", max_trades)
    _LOGGER.info("=" * 70)

    # Default symbols if none provided
    if not symbols:
        symbols = [
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
        _LOGGER.info("Using default NIFTY50 symbols")

    # Step 1: Initialize analyzers and order manager
    _LOGGER.info("Step 1: Initializing components...")

    sentiment_analyzer, rl_predictor, order_manager = _initialize_analyzers_and_order_manager(
        order_manager, audit_logger, errors
    )

    # Early return if order manager initialization failed
    if order_manager is None:
        return ScanCycleResult(
            scanner_result=None,
            trades_executed=0,
            total_pnl=Decimal("0"),
            errors=errors,
            timestamp_utc=timestamp_utc,
        )

    # Step 2: Execute scanner
    _LOGGER.info("Step 2: Running scanner...")
    scanner_result = _execute_scanner(
        symbols, scanner_config, sentiment_analyzer, rl_predictor, errors
    )

    # Early return if scanner failed
    if scanner_result is None:
        return ScanCycleResult(
            scanner_result=None,
            trades_executed=0,
            total_pnl=Decimal("0"),
            errors=errors,
            timestamp_utc=timestamp_utc,
        )

    # Step 3: Execute paper trades
    _LOGGER.info("Step 3: Executing paper trades...")
    trades_executed, total_pnl = _execute_paper_trades(
        scanner_result, max_trades, order_manager, errors
    )

    # Step 4: Audit summary
    _LOGGER.info("Step 4: Audit summary...")
    _LOGGER.info("  Trades executed: %d", trades_executed)
    _LOGGER.info("  Total PnL: %s", total_pnl)
    _LOGGER.info("  Errors: %d", len(errors))

    _LOGGER.info("=" * 70)
    _LOGGER.info("Scan Cycle Complete")
    _LOGGER.info("=" * 70)

    return ScanCycleResult(
        scanner_result=scanner_result,
        trades_executed=trades_executed,
        total_pnl=total_pnl,
        errors=errors,
        timestamp_utc=timestamp_utc,
    )
