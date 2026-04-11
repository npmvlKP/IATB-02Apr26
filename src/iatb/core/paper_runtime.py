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
from iatb.execution.base import OrderRequest
from iatb.execution.paper_executor import PaperExecutor
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer
from iatb.scanner.instrument_scanner import (
    InstrumentScanner,
    MarketData,
    ScannerResult,
)
from iatb.sentiment.aggregator import SentimentAggregator
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
            market_data = self._fetch_market_data()
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

    def _fetch_market_data(self) -> dict[str, MarketData]:
        """Fetch market data for watchlist symbols.

        Returns:
            Dictionary mapping symbol to MarketData
        """
        market_data: dict[str, MarketData] = {}

        try:
            scanner = InstrumentScanner(
                symbols=self._scanner_settings.watchlist,
            )
            result = scanner.scan()
            for candidate in result.gainers + result.losers:
                data = self._build_market_data_from_candidate(candidate)
                if data:
                    market_data[candidate.symbol] = data

            logger.info("Fetched market data", extra={"symbols": list(market_data.keys())})
        except Exception as exc:
            logger.error("Failed to fetch market data", extra={"error": str(exc)}, exc_info=True)

        return market_data

    def _build_market_data_from_candidate(self, candidate: Any) -> MarketData | None:
        """Build MarketData from scanner candidate.

        Args:
            candidate: Scanner candidate object

        Returns:
            MarketData object or None
        """
        # This is a simplified version - in production, this would
        # use actual OHLCV data from data providers
        from iatb.scanner.instrument_scanner import InstrumentCategory

        return MarketData(
            symbol=candidate.symbol,
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("1000"),
            prev_close_price=Decimal("990"),
            volume=Decimal("1000000"),
            avg_volume=Decimal("500000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("1010"),
            low_price=Decimal("980"),
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

        for symbol in market_data:
            # In production, this would fetch actual news and analyze
            # For now, use a default neutral score
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
        from iatb.scanner.instrument_scanner import InstrumentCategory, ScannerCandidate

        candidates: list[ScannerCandidate] = []

        for symbol, data in market_data.items():
            sentiment_score = sentiment_scores.get(symbol, Decimal("0"))
            strength_score = strength_scores.get(symbol, Decimal("0"))

            # Composite scoring: |sentiment| >= 0.75 AND is_tradable AND volume_ratio >= 2.0
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
                    exit_probability=Decimal("0.6"),  # Default for now
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

        # Rank by composite score
        gainers = [c for c in candidates if c.pct_change > Decimal("0")]
        losers = [c for c in candidates if c.pct_change < Decimal("0")]
        gainers.sort(key=lambda c: c.composite_score, reverse=True)
        losers.sort(key=lambda c: c.composite_score, reverse=True)

        # Assign ranks
        for idx, c in enumerate(gainers):
            gainers[idx] = ScannerCandidate(
                symbol=c.symbol,
                exchange=c.exchange,
                category=c.category,
                pct_change=c.pct_change,
                composite_score=c.composite_score,
                sentiment_score=c.sentiment_score,
                volume_ratio=c.volume_ratio,
                exit_probability=c.exit_probability,
                is_tradable=c.is_tradable,
                regime=c.regime,
                rank=idx + 1,
                timestamp_utc=c.timestamp_utc,
                metadata=c.metadata,
            )
        for idx, c in enumerate(losers):
            losers[idx] = ScannerCandidate(
                symbol=c.symbol,
                exchange=c.exchange,
                category=c.category,
                pct_change=c.pct_change,
                composite_score=c.composite_score,
                sentiment_score=c.sentiment_score,
                volume_ratio=c.volume_ratio,
                exit_probability=c.exit_probability,
                is_tradable=c.is_tradable,
                regime=c.regime,
                rank=idx + 1,
                timestamp_utc=c.timestamp_utc,
                metadata=c.metadata,
            )

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
            # Create idempotency key: symbol+timestamp
            idempotency_key = f"{candidate.symbol}_{timestamp.strftime('%Y%m%d%H%M')}"

            # Skip if already processed
            if idempotency_key in self._processed_keys:
                logger.debug("Skipping duplicate order", extra={"key": idempotency_key})
                continue

            try:
                # Determine order side based on pct_change
                side = OrderSide.BUY if candidate.pct_change > Decimal("0") else OrderSide.SELL

                # Create order request
                request = OrderRequest(
                    exchange=candidate.exchange,
                    symbol=candidate.symbol,
                    side=side,
                    quantity=Decimal("100"),  # Default lot size
                    order_type=OrderType.MARKET,
                    price=None,  # Market order
                    metadata={
                        "rank": str(candidate.rank),
                        "composite_score": str(candidate.composite_score),
                        "sentiment_score": str(candidate.sentiment_score),
                        "volume_ratio": str(candidate.volume_ratio),
                        "scan_timestamp": timestamp.isoformat(),
                    },
                )

                # Execute order
                result = self._paper_executor.execute_order(request)

                # Create audit record
                audit_record = TradeAuditRecord(
                    trade_id=result.order_id,
                    timestamp=create_timestamp(timestamp),
                    exchange=candidate.exchange,
                    symbol=candidate.symbol,
                    side=side,
                    quantity=create_quantity(str(result.filled_quantity)),
                    price=create_price(str(result.average_price)),
                    status=result.status,
                    strategy_id="paper-scanner-v1",
                    metadata=request.metadata,
                )

                executed_orders.append(audit_record)
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

            except Exception as exc:
                logger.error(
                    "Failed to execute paper order",
                    extra={"symbol": candidate.symbol, "error": str(exc)},
                    exc_info=True,
                )

        return executed_orders

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
            event = {
                "type": "scan_cycle_completed",
                "timestamp_utc": timestamp.isoformat(),
                "gainers": [
                    {
                        "symbol": c.symbol,
                        "pct_change": str(c.pct_change),
                        "composite_score": str(c.composite_score),
                        "rank": c.rank,
                    }
                    for c in scanner_result.gainers
                ],
                "losers": [
                    {
                        "symbol": c.symbol,
                        "pct_change": str(c.pct_change),
                        "composite_score": str(c.composite_score),
                        "rank": c.rank,
                    }
                    for c in scanner_result.losers
                ],
                "executed_orders": [
                    {
                        "trade_id": r.trade_id,
                        "symbol": r.symbol,
                        "side": r.side.value,
                        "quantity": str(r.quantity),
                        "price": str(r.price),
                    }
                    for r in executed_orders
                ],
                "total_scanned": scanner_result.total_scanned,
                "filtered_count": scanner_result.filtered_count,
            }

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
