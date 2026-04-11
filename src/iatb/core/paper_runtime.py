"""
Paper trading runtime with continuous work loop.

This runtime:
- Runs continuous scanning cycles
- Executes paper trades
- Maintains paper trading state
- Handles graceful shutdown
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import tomli

from iatb.core.engine import Engine
from iatb.core.enums import Exchange, OrderSide, OrderType
from iatb.core.event_bus import EventBus
from iatb.core.exceptions import ConfigError
from iatb.core.types import (
    create_price,
    create_quantity,
    create_timestamp,
)
from iatb.data.jugaad_provider import JugaadProvider
from iatb.execution.base import OrderRequest
from iatb.execution.paper_executor import PaperExecutor
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    MarketData,
    ScannerCandidate,
    ScannerResult,
)
from iatb.sentiment.aggregator import SentimentAggregator
from iatb.sentiment.news_scraper import NewsScraper
from iatb.storage.audit_logger import AuditLogger
from iatb.storage.sqlite_store import TradeAuditRecord

logger = logging.getLogger(__name__)

DEFAULT_WATCHLIST = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_MAX_CANDIDATES = 5
SETTINGS_PATH = Path("config/settings.toml")


@dataclass(frozen=True)
class ScannerSettings:
    """Scanner configuration from settings.toml."""

    watchlist: list[str]
    scan_interval_seconds: int
    max_candidates: int

    @classmethod
    def load(cls, config_path: Path = SETTINGS_PATH) -> "ScannerSettings":
        """Load scanner settings from TOML config file."""
        try:
            with config_path.open("rb") as f:
                config = tomli.load(f)
        except FileNotFoundError:
            logger.warning(
                "Config file not found, using defaults",
                extra={"config_path": str(config_path)},
            )
            return cls(
                watchlist=DEFAULT_WATCHLIST,
                scan_interval_seconds=DEFAULT_SCAN_INTERVAL,
                max_candidates=DEFAULT_MAX_CANDIDATES,
            )
        except Exception as exc:
            msg = f"Failed to load config from {config_path}: {exc}"
            raise ConfigError(msg) from exc

        scanner_config = config.get("scanner", {})
        return cls(
            watchlist=scanner_config.get("watchlist", DEFAULT_WATCHLIST),
            scan_interval_seconds=scanner_config.get(
                "scan_interval_seconds", DEFAULT_SCAN_INTERVAL
            ),
            max_candidates=scanner_config.get("max_candidates", DEFAULT_MAX_CANDIDATES),
        )


@dataclass(frozen=True)
class ScanContext:
    """Context for a single scan cycle."""

    timestamp_utc: datetime
    market_data: dict[str, MarketData]
    sentiment_scores: dict[str, Decimal]
    strength_scores: dict[str, Decimal]
    scanner_result: ScannerResult
    executed_orders: list[TradeAuditRecord]


class PaperTradingRuntime:
    """Continuous paper trading runtime."""

    def __init__(
        self,
        scan_interval_seconds: float = 60.0,
        audit_db_path: Path | None = None,
        scanner_settings: ScannerSettings | None = None,
    ) -> None:
        """Initialize paper trading runtime.

        Args:
            scan_interval_seconds: Interval between scan cycles
            audit_db_path: Path to audit database
            scanner_settings: Scanner configuration
        """
        self._scan_interval = scan_interval_seconds
        self._audit_db_path = audit_db_path or Path("data/audit/trades.sqlite")
        self._scanner_settings = scanner_settings or ScannerSettings.load()
        self._running = False
        self._stop_event = asyncio.Event()

        # Components
        self._engine = Engine()
        self._paper_executor = PaperExecutor()
        self._audit_logger = AuditLogger(self._audit_db_path)
        self._event_bus = EventBus()
        self._sentiment_aggregator = SentimentAggregator()
        self._strength_scorer = StrengthScorer()

        # Track processed orders for idempotency
        self._processed_keys: set[str] = set()

    async def start(self) -> None:
        """Start paper trading runtime."""
        logger.info("Starting paper trading runtime")
        self._running = True
        self._stop_event.clear()

        # Start components
        await self._engine.start()
        await self._event_bus.start()

        logger.info("Paper trading runtime started - beginning scan loop")

    async def stop(self) -> None:
        """Stop paper trading runtime."""
        logger.info("Stopping paper trading runtime")
        self._running = False
        self._stop_event.set()

        # Stop components
        await self._event_bus.stop()
        await self._engine.stop()

        logger.info("Paper trading runtime stopped")

    async def run_scan_cycle(self) -> None:
        """Run a single scanning and trading cycle."""
        try:
            timestamp = datetime.now(UTC)
            logger.info("Starting scan cycle", extra={"timestamp_utc": timestamp.isoformat()})

            # Check readiness
            if not self._check_readiness():
                logger.warning("System not ready, skipping scan cycle")
                return

            # Fetch market data
            market_data = await self._fetch_market_data()
            if not market_data:
                logger.info("No market data available, skipping cycle")
                return

            # Run sentiment analysis
            sentiment_scores = self._run_sentiment(market_data)

            # Calculate strength scores
            strength_scores = self._calculate_strength(market_data)

            # Run scanner with composite scoring
            scanner_result = self._run_scanner(market_data, sentiment_scores, strength_scores)

            # Execute paper orders for qualified candidates
            executed_orders = self._execute_paper_orders(scanner_result, timestamp)

            # Persist audit logs
            self._persist_audit(executed_orders)

            # Publish results to event bus
            self._publish_results(scanner_result, executed_orders, timestamp)

            logger.info("Scan cycle completed", extra={"timestamp_utc": timestamp.isoformat()})

        except Exception as e:
            logger.error(
                "Error in scan cycle",
                extra={
                    "error": str(e),
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                },
                exc_info=True,
            )

    def _check_readiness(self) -> bool:
        """Verify engine running, exchange open.

        Returns:
            True if system is ready for scanning
        """
        if not self._engine.is_running:
            logger.warning("Engine not running")
            return False

        # For paper trading, we don't need broker authentication
        # Just check if engine is running

        # TODO: Add exchange session check when exchange calendar is integrated
        return True

    async def _fetch_market_data(self) -> dict[str, MarketData]:
        """Fetch market data for watchlist symbols.

        Returns:
            Dictionary mapping symbol to MarketData
        """
        market_data: dict[str, MarketData] = {}

        try:
            # Use JugaadProvider to fetch market data
            provider = JugaadProvider()

            for symbol in self._scanner_settings.watchlist:
                try:
                    # Get ticker snapshot from JugaadProvider
                    ticker = await provider.get_ticker(symbol=symbol, exchange=Exchange.NSE)

                    # Build MarketData from ticker
                    data = self._build_market_data_from_ticker(ticker, symbol)
                    if data:
                        market_data[symbol] = data

                except Exception as exc:
                    logger.warning(
                        "Failed to fetch data for symbol",
                        extra={"symbol": symbol, "error": str(exc)},
                    )
                    continue

            logger.info("Fetched market data", extra={"symbols": list(market_data.keys())})
        except Exception as exc:
            logger.error("Failed to fetch market data", extra={"error": str(exc)}, exc_info=True)

        return market_data

    def _build_market_data_from_ticker(self, ticker: Any, symbol: str) -> MarketData | None:
        """Build MarketData from ticker snapshot.

        Args:
            ticker: Ticker snapshot from JugaadProvider
            symbol: Symbol name

        Returns:
            MarketData object or None
        """
        from iatb.scanner.instrument_scanner import InstrumentCategory

        # Get price and volume from ticker
        close_price = ticker.last if hasattr(ticker, "last") else Decimal("0")
        volume = ticker.volume_24h if hasattr(ticker, "volume_24h") else Decimal("0")

        if close_price == Decimal("0") or volume == Decimal("0"):
            return None

        # Calculate derived fields
        prev_close_price = close_price * Decimal("0.99")  # Approximate 1% change
        avg_volume = volume / Decimal("2")  # Approximate average

        return MarketData(
            symbol=symbol,
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=close_price,
            prev_close_price=prev_close_price,
            volume=volume,
            avg_volume=avg_volume,
            timestamp_utc=datetime.now(UTC),
            high_price=close_price * Decimal("1.01"),
            low_price=close_price * Decimal("0.99"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )

    def _run_sentiment(self, market_data: dict[str, MarketData]) -> dict[str, Decimal]:
        """Run sentiment analysis on fetched news.

        Args:
            market_data: Market data dictionary

        Returns:
            Dictionary mapping symbol to sentiment score
        """
        sentiment_scores: dict[str, Decimal] = {}

        try:
            # Fetch news headlines
            scraper = NewsScraper()
            headlines = scraper.fetch_headlines(max_items_per_feed=3)

            # Match news to symbols and analyze sentiment
            for symbol in market_data:
                data = market_data[symbol]
                # Find news mentioning the symbol
                symbol_headlines = [
                    h.article_text
                    for h in headlines
                    if symbol.lower() in h.title.lower() or symbol.lower() in h.article_text.lower()
                ]

                if symbol_headlines:
                    # Use the most recent headline
                    news_text = symbol_headlines[0][:500]  # Limit to 500 chars
                    result = self._sentiment_aggregator.evaluate_instrument(
                        news_text, data.volume_ratio
                    )
                    sentiment_scores[symbol] = result.composite.score
                else:
                    # No news found, use neutral score
                    sentiment_scores[symbol] = Decimal("0")

        except Exception as exc:
            logger.warning(
                "Failed to run sentiment analysis, using neutral scores",
                extra={"error": str(exc)},
                exc_info=True,
            )
            # Fall back to neutral scores for all symbols
            for symbol in market_data:
                sentiment_scores[symbol] = Decimal("0")

        logger.debug("Sentiment scores computed", extra={"scores": sentiment_scores})
        return sentiment_scores

    def _calculate_strength(self, market_data: dict[str, MarketData]) -> dict[str, Decimal]:
        """Calculate strength scores for each symbol.

        Args:
            market_data: Market data dictionary

        Returns:
            Dictionary mapping symbol to strength score
        """
        strength_scores: dict[str, Decimal] = {}

        for symbol, data in market_data.items():
            try:
                inputs = StrengthInputs(
                    breadth_ratio=data.breadth_ratio,
                    regime=MarketRegime.SIDEWAYS,
                    adx=data.adx,
                    volume_ratio=data.volume_ratio,
                    volatility_atr_pct=data.atr_pct,
                )
                score = self._strength_scorer.score(data.exchange, inputs)
                strength_scores[symbol] = score
            except Exception as exc:
                logger.warning(
                    "Failed to calculate strength",
                    extra={"symbol": symbol, "error": str(exc)},
                )
                strength_scores[symbol] = Decimal("0")

        logger.debug("Strength scores computed", extra={"scores": strength_scores})
        return strength_scores

    def _run_scanner(
        self,
        market_data: dict[str, MarketData],
        sentiment_scores: dict[str, Decimal],
        strength_scores: dict[str, Decimal],
    ) -> ScannerResult:
        """Run scanner with composite scoring.

        Args:
            market_data: Market data dictionary
            sentiment_scores: Sentiment scores dictionary
            strength_scores: Strength scores dictionary

        Returns:
            Scanner result with qualified candidates
        """
        candidates = self._filter_candidates(market_data, sentiment_scores, strength_scores)
        gainers, losers = self._rank_candidates(candidates)

        result = ScannerResult(
            gainers=gainers[: self._scanner_settings.max_candidates],
            losers=losers[: self._scanner_settings.max_candidates],
            total_scanned=len(market_data),
            filtered_count=len(market_data) - len(candidates),
            scan_timestamp_utc=datetime.now(UTC),
        )

        logger.info(
            "Scanner completed",
            extra={
                "gainers": len(result.gainers),
                "losers": len(result.losers),
                "total_scanned": result.total_scanned,
            },
        )

        return result

    def _filter_candidates(
        self,
        market_data: dict[str, MarketData],
        sentiment_scores: dict[str, Decimal],
        strength_scores: dict[str, Decimal],
    ) -> list[ScannerCandidate]:
        """Filter and create scanner candidates.

        Args:
            market_data: Market data dictionary
            sentiment_scores: Sentiment scores dictionary
            strength_scores: Strength scores dictionary

        Returns:
            List of qualified candidates
        """
        from iatb.scanner.instrument_scanner import InstrumentCategory, ScannerCandidate

        candidates: list[ScannerCandidate] = []

        for symbol, data in market_data.items():
            sentiment_score = sentiment_scores.get(symbol, Decimal("0"))
            strength_score = strength_scores.get(symbol, Decimal("0"))
            very_strong = abs(sentiment_score) >= Decimal("0.75")
            volume_ok = data.volume_ratio >= Decimal("2.0")

            try:
                inputs = StrengthInputs(
                    breadth_ratio=data.breadth_ratio,
                    regime=MarketRegime.SIDEWAYS,
                    adx=data.adx,
                    volume_ratio=data.volume_ratio,
                    volatility_atr_pct=data.atr_pct,
                )
                is_tradable = self._strength_scorer.is_tradable(data.exchange, inputs)
            except Exception:
                is_tradable = False

            if very_strong and is_tradable and volume_ok:
                composite_score = (abs(sentiment_score) + strength_score) / Decimal("2")
                candidate = ScannerCandidate(
                    symbol=symbol,
                    exchange=data.exchange,
                    category=InstrumentCategory.STOCK,
                    pct_change=data.pct_change,
                    composite_score=composite_score,
                    sentiment_score=sentiment_score,
                    volume_ratio=data.volume_ratio,
                    exit_probability=Decimal("0.6"),
                    is_tradable=True,
                    regime=MarketRegime.SIDEWAYS,
                    rank=0,
                    timestamp_utc=datetime.now(UTC),
                    metadata={
                        "strength_score": str(strength_score),
                        "very_strong": str(very_strong),
                    },
                )
                candidates.append(candidate)

        return candidates

    def _rank_candidates(
        self, candidates: list[ScannerCandidate]
    ) -> tuple[list[ScannerCandidate], list[ScannerCandidate]]:
        """Rank candidates by composite score.

        Args:
            candidates: List of unranked candidates

        Returns:
            Tuple of (ranked_gainers, ranked_losers)
        """
        gainers = [c for c in candidates if c.pct_change > Decimal("0")]
        losers = [c for c in candidates if c.pct_change < Decimal("0")]
        gainers.sort(key=lambda c: c.composite_score, reverse=True)
        losers.sort(key=lambda c: c.composite_score, reverse=True)

        ranked_gainers = [self._assign_rank(c, idx + 1) for idx, c in enumerate(gainers)]
        ranked_losers = [self._assign_rank(c, idx + 1) for idx, c in enumerate(losers)]

        return ranked_gainers, ranked_losers

    def _assign_rank(
        self, candidate: ScannerCandidate, rank: int
    ) -> ScannerCandidate:
        """Assign rank to a candidate.

        Args:
            candidate: ScannerCandidate
            rank: Rank to assign

        Returns:
            New ScannerCandidate with rank assigned
        """
        from iatb.scanner.instrument_scanner import ScannerCandidate

        return ScannerCandidate(
            symbol=candidate.symbol,
            exchange=candidate.exchange,
            category=candidate.category,
            pct_change=candidate.pct_change,
            composite_score=candidate.composite_score,
            sentiment_score=candidate.sentiment_score,
            volume_ratio=candidate.volume_ratio,
            exit_probability=candidate.exit_probability,
            is_tradable=candidate.is_tradable,
            regime=candidate.regime,
            rank=rank,
            timestamp_utc=candidate.timestamp_utc,
            metadata=candidate.metadata,
        )

    def _execute_paper_orders(
        self, scanner_result: ScannerResult, timestamp: datetime
    ) -> list[TradeAuditRecord]:
        """Execute paper orders for qualified candidates.

        Args:
            scanner_result: Scanner result with candidates
            timestamp: Scan timestamp

        Returns:
            List of executed trade audit records
        """
        executed_orders: list[TradeAuditRecord] = []

        for candidate in scanner_result.gainers + scanner_result.losers:
            idempotency_key = f"{candidate.symbol}_{timestamp.strftime('%Y%m%d%H%M')}"
            if idempotency_key in self._processed_keys:
                logger.debug("Skipping duplicate order", extra={"key": idempotency_key})
                continue

            order_record = self._execute_single_order(candidate, timestamp, idempotency_key)
            if order_record:
                executed_orders.append(order_record)

        return executed_orders

    def _execute_single_order(
        self, candidate: ScannerCandidate, timestamp: datetime, idempotency_key: str
    ) -> TradeAuditRecord | None:
        """Execute a single paper order.

        Args:
            candidate: ScannerCandidate
            timestamp: Scan timestamp
            idempotency_key: Idempotency key for duplicate prevention

        Returns:
            TradeAuditRecord if successful, None otherwise
        """
        try:
            side = OrderSide.BUY if candidate.pct_change > Decimal("0") else OrderSide.SELL
            request = self._create_order_request(candidate, side, timestamp)
            result = self._paper_executor.execute_order(request)
            audit_record = self._create_audit_record(
                candidate, result, side, timestamp, request.metadata
            )

            self._processed_keys.add(idempotency_key)
            logger.info(
                "Paper order executed",
                extra={
                    "order_id": result.order_id,
                    "symbol": candidate.symbol,
                    "side": side.value,
                    "quantity": str(result.filled_quantity),
                    "price": str(result.average_price),
                },
            )
            return audit_record

        except Exception as exc:
            logger.error(
                "Failed to execute paper order",
                extra={"symbol": candidate.symbol, "error": str(exc)},
                exc_info=True,
            )
            return None

    def _create_order_request(
        self, candidate: ScannerCandidate, side: OrderSide, timestamp: datetime
    ) -> OrderRequest:
        """Create order request for candidate.

        Args:
            candidate: ScannerCandidate
            side: OrderSide
            timestamp: Scan timestamp

        Returns:
            OrderRequest
        """
        return OrderRequest(
            exchange=candidate.exchange,
            symbol=candidate.symbol,
            side=side,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET,
            price=None,
            metadata={
                "rank": str(candidate.rank),
                "composite_score": str(candidate.composite_score),
                "sentiment_score": str(candidate.sentiment_score),
                "volume_ratio": str(candidate.volume_ratio),
                "scan_timestamp": timestamp.isoformat(),
            },
        )

    def _create_audit_record(
        self,
        candidate: ScannerCandidate,
        result: Any,
        side: OrderSide,
        timestamp: datetime,
        metadata: dict[str, str],
    ) -> TradeAuditRecord:
        """Create audit record from order result.

        Args:
            candidate: ScannerCandidate
            result: OrderResult
            side: OrderSide
            timestamp: Scan timestamp
            metadata: Order metadata

        Returns:
            TradeAuditRecord
        """
        return TradeAuditRecord(
            trade_id=result.order_id,
            timestamp=create_timestamp(timestamp),
            exchange=candidate.exchange,
            symbol=candidate.symbol,
            side=side,
            quantity=create_quantity(str(result.filled_quantity)),
            price=create_price(str(result.average_price)),
            status=result.status,
            strategy_id="paper-scanner-v1",
            metadata=metadata,
        )

    def _persist_audit(self, executed_orders: list[TradeAuditRecord]) -> None:
        """Persist audit logs for executed orders.

        Args:
            executed_orders: List of executed trade records
        """
        for record in executed_orders:
            try:
                self._audit_logger.log_trade(record)
            except Exception as exc:
                logger.error(
                    "Failed to persist audit log",
                    extra={"trade_id": record.trade_id, "error": str(exc)},
                    exc_info=True,
                )

        logger.info("Audit logs persisted", extra={"count": len(executed_orders)})

    def _publish_results(
        self,
        scanner_result: ScannerResult,
        executed_orders: list[TradeAuditRecord],
        timestamp: datetime,
    ) -> None:
        """Publish scanner results via event bus.

        Args:
            scanner_result: Scanner result with candidates
            executed_orders: List of executed trade records
            timestamp: Scan timestamp
        """
        try:
            event = self._build_event_payload(scanner_result, executed_orders, timestamp)
            asyncio.create_task(self._event_bus.publish("scanner_results", event))
            logger.debug(
                "Results published to event bus",
                extra={"timestamp": timestamp.isoformat()},
            )
        except Exception as exc:
            logger.error(
                "Failed to publish results",
                extra={"error": str(exc)},
                exc_info=True,
            )

    def _build_event_payload(
        self,
        scanner_result: ScannerResult,
        executed_orders: list[TradeAuditRecord],
        timestamp: datetime,
    ) -> dict[str, Any]:
        """Build event payload for publishing.

        Args:
            scanner_result: Scanner result with candidates
            executed_orders: List of executed trade records
            timestamp: Scan timestamp

        Returns:
            Event payload dictionary
        """
        return {
            "type": "scan_cycle_completed",
            "timestamp_utc": timestamp.isoformat(),
            "gainers": [self._format_candidate(c) for c in scanner_result.gainers],
            "losers": [self._format_candidate(c) for c in scanner_result.losers],
            "executed_orders": [self._format_order(r) for r in executed_orders],
            "total_scanned": scanner_result.total_scanned,
            "filtered_count": scanner_result.filtered_count,
        }

    def _format_candidate(self, candidate: ScannerCandidate) -> dict[str, str]:
        """Format candidate for event payload.

        Args:
            candidate: ScannerCandidate

        Returns:
            Formatted candidate dictionary
        """
        return {
            "symbol": candidate.symbol,
            "pct_change": str(candidate.pct_change),
            "composite_score": str(candidate.composite_score),
            "rank": candidate.rank,
        }

    def _format_order(self, order: TradeAuditRecord) -> dict[str, str]:
        """Format order for event payload.

        Args:
            order: TradeAuditRecord

        Returns:
            Formatted order dictionary
        """
        return {
            "trade_id": order.trade_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": str(order.quantity),
            "price": str(order.price),
        }

    async def run_continuous(self) -> None:
        """Run continuous paper trading loop."""
        while self._running and not self._stop_event.is_set():
            try:
                await self.run_scan_cycle()

                # Wait for next cycle or stop signal
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._scan_interval,
                    )
                    # If we get here, stop_event was set
                    break
                except asyncio.TimeoutError:
                    # Timeout is expected - continue to next cycle
                    continue

            except asyncio.CancelledError:
                logger.info("Scan loop cancelled")
                break
            except Exception as e:
                logger.error(
                    "Unexpected error in scan loop",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                # Wait a bit before retrying
                await asyncio.sleep(5)

    async def run(self) -> None:
        """Main entry point - start and run continuously."""
        await self.start()
        try:
            await self.run_continuous()
        finally:
            await self.stop()


async def run_paper_runtime(scan_interval_seconds: float = 60.0) -> None:
    """Convenience function to run paper trading runtime.

    Args:
        scan_interval_seconds: Interval between scan cycles
    """
    runtime = PaperTradingRuntime(scan_interval_seconds=scan_interval_seconds)
    await runtime.run()


def _register_signal_handlers(stop_event: asyncio.Event) -> None:
    """Wire SIGINT/SIGTERM handlers to stop event."""
    import signal

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, OSError):
            pass


async def _main() -> None:
    """Run paper runtime with process signal support."""
    stop_event = asyncio.Event()
    _register_signal_handlers(stop_event)

    # Create and run runtime
    runtime = PaperTradingRuntime()
    await runtime.start()

    try:
        # Run continuous loop with stop_event
        while not stop_event.is_set():
            await runtime.run_scan_cycle()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                continue
    finally:
        await runtime.stop()


def main() -> None:
    """CLI entrypoint for paper trading runtime."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(_main())


if __name__ == "__main__":
    main()
