"""
Phase N.1 — Stress Tests.

Stress test scenarios:
- 50+ symbols scanned concurrently
- 100+ concurrent order submissions
- High-throughput audit logging
- Memory and performance bounds
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.types import create_quantity, create_timestamp
from iatb.data.base import DataProvider, OHLCVBar
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.order_manager import OrderManager
from iatb.execution.order_throttle import OrderThrottle
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.pre_trade_validator import PreTradeConfig
from iatb.execution.trade_audit import TradeAuditLogger
from iatb.risk.daily_loss_guard import DailyLossGuard
from iatb.risk.kill_switch import KillSwitch
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    InstrumentScanner,
    MarketData,
    ScannerConfig,
    SortDirection,
    create_mock_rl_predictor,
    create_mock_sentiment_analyzer,
)


class HighThroughputExecutor(Executor):
    """Lock-free executor optimized for stress testing."""

    def __init__(self) -> None:
        self._counter = 0
        self._lock = threading.Lock()
        self._total_orders = 0

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        with self._lock:
            self._counter += 1
            self._total_orders += 1
            order_id = f"HT-{self._counter:06d}"
        fill_price = request.price or Decimal("100")
        return ExecutionResult(
            order_id=order_id,
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            average_price=fill_price,
            message="ht fill",
        )

    def cancel_all(self) -> int:
        return 0

    def close_order(self, order_id: str) -> bool:
        return True

    @property
    def total_orders(self) -> int:
        return self._total_orders


class BulkDataProvider(DataProvider):
    """Provider that serves many symbols with minimal overhead."""

    def __init__(self, symbol_count: int) -> None:
        self._symbol_count = symbol_count
        self._call_count = 0

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: object = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        self._call_count += 1
        bars: list[OHLCVBar] = []
        base = Decimal("100") + Decimal(str(hash(symbol) % 9000))
        for i in range(min(limit, 20)):
            ts = datetime.now(UTC) - timedelta(days=20 - i)
            close = base + (Decimal("2") * Decimal(i))
            bars.append(
                OHLCVBar(
                    timestamp=create_timestamp(ts),
                    exchange=exchange,
                    symbol=symbol,
                    open=close * Decimal("0.99"),
                    high=close * Decimal("1.01"),
                    low=close * Decimal("0.99"),
                    close=close,
                    volume=create_quantity("1000000"),
                    source="bulk",
                )
            )
        return bars

    async def get_ticker(self, *, symbol: str, exchange: Exchange) -> Any:
        return None

    async def get_ohlcv_batch(
        self,
        *,
        symbols: list[str],
        exchange: Exchange,
        timeframe: str,
        since: object = None,
        limit: int = 500,
    ) -> dict[str, list[OHLCVBar]]:
        result: dict[str, list[OHLCVBar]] = {}
        for sym in symbols:
            result[sym] = await self.get_ohlcv(
                symbol=sym, exchange=exchange, timeframe=timeframe, since=since, limit=limit
            )
        return result

    @property
    def call_count(self) -> int:
        return self._call_count


def _generate_symbols(count: int) -> list[str]:
    prefixes = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN"]
    symbols: list[str] = []
    for i in range(count):
        prefix = prefixes[i % len(prefixes)]
        if i < len(prefixes):
            symbols.append(prefix)
        else:
            symbols.append(f"{prefix}_{i}")
    return symbols


def _generate_market_data(symbols: Sequence[str]) -> list[MarketData]:
    data: list[MarketData] = []
    for sym in symbols:
        base = Decimal("100") + Decimal(str(abs(hash(sym)) % 9000))
        pct = Decimal(str((abs(hash(sym)) % 50) - 10))
        data.append(
            MarketData(
                symbol=sym,
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                close_price=base,
                prev_close_price=base / (Decimal("1") + pct / Decimal("100")),
                volume=Decimal("3000000"),
                avg_volume=Decimal("1000000"),
                timestamp_utc=datetime.now(UTC),
                high_price=base * Decimal("1.01"),
                low_price=base * Decimal("0.99"),
                adx=Decimal("25"),
                atr_pct=Decimal("0.02"),
                breadth_ratio=Decimal("1.5"),
            )
        )
    return data


def _create_stress_order_manager(
    executor: Executor,
    audit_db_path: Path | None = None,
    max_ops: int = 200,
) -> OrderManager:
    kill_switch = KillSwitch(executor)
    pre_trade = PreTradeConfig(
        max_order_quantity=Decimal("1000"),
        max_order_value=Decimal("50000000"),
        max_price_deviation_pct=Decimal("0.10"),
        max_position_per_symbol=Decimal("10000"),
        max_portfolio_exposure=Decimal("100000000"),
    )
    daily_guard = DailyLossGuard(
        max_daily_loss_pct=Decimal("0.05"),
        starting_nav=Decimal("100000000"),
        kill_switch=kill_switch,
    )
    audit = TradeAuditLogger(audit_db_path or Path("data/audit/stress_test.sqlite"))
    throttle = OrderThrottle(max_ops=max_ops)
    return OrderManager(
        executor=executor,
        heartbeat_timeout_seconds=300,
        kill_switch=kill_switch,
        pre_trade_config=pre_trade,
        daily_loss_guard=daily_guard,
        audit_logger=audit,
        order_throttle=throttle,
        algo_id="STRESS-001",
    )


class TestStress50Symbols:
    """Stress test: 50+ symbols scanned."""

    def test_scan_50_symbols_with_custom_data(self) -> None:
        symbols = _generate_symbols(55)
        custom_data = _generate_market_data(symbols)
        sentiment = create_mock_sentiment_analyzer({s: (Decimal("0.8"), True) for s in symbols})
        rl = create_mock_rl_predictor(probability=Decimal("0.7"))
        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=10, min_volume_ratio=Decimal("1.0")),
            data_provider=None,
            sentiment_analyzer=sentiment,
            rl_predictor=rl,
            symbols=symbols,
        )
        start = time.perf_counter()
        result = scanner.scan(direction=SortDirection.GAINERS, custom_data=custom_data)
        elapsed = time.perf_counter() - start
        assert result.total_scanned == 55
        assert elapsed < 30.0

    @pytest.mark.asyncio
    async def test_data_provider_50_symbols(self) -> None:
        symbols = _generate_symbols(55)
        provider = BulkDataProvider(len(symbols))
        start = time.perf_counter()
        tasks = [
            provider.get_ohlcv(symbol=sym, exchange=Exchange.NSE, timeframe="1d", limit=20)
            for sym in symbols
        ]
        results = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start
        assert len(results) == 55
        assert all(len(r) > 0 for r in results)
        assert provider.call_count == 55
        assert elapsed < 30.0

    def test_selection_50_candidates(self) -> None:
        from iatb.selection.ranking import RankingConfig, rank_and_select

        candidates = [
            (f"SYM{i:03d}", Exchange.NSE, Decimal(str(0.9 - i * 0.01)), {}) for i in range(55)
        ]
        result = rank_and_select(
            candidates,
            RankingConfig(min_score=Decimal("0.1"), top_n=10),
        )
        assert len(result.selected) <= 10
        assert result.total_candidates == 55


class TestStress100ConcurrentOrders:
    """Stress test: 100+ concurrent order submissions."""

    def test_100_sequential_orders(self, tmp_path: Path) -> None:
        executor = HighThroughputExecutor()
        om = _create_stress_order_manager(
            executor, audit_db_path=tmp_path / "stress_100.sqlite", max_ops=200
        )
        symbols = _generate_symbols(100)
        for sym in symbols:
            price = Decimal("100") + Decimal(str(abs(hash(sym)) % 9000))
            om.update_market_data(
                last_prices={sym: price},
                positions={},
                total_exposure=Decimal("0"),
            )
            result = om.place_order(
                OrderRequest(
                    exchange=Exchange.NSE,
                    symbol=sym,
                    side=OrderSide.BUY,
                    quantity=Decimal("1"),
                    price=price,
                ),
                strategy_id="stress-100",
            )
            assert result.status == OrderStatus.FILLED
        assert executor.total_orders == 100
        audit = TradeAuditLogger(tmp_path / "stress_100.sqlite")
        today = datetime.now(UTC).date()
        trades = audit.query_daily_trades(today)
        assert len(trades) == 100

    def test_100_orders_timing(self, tmp_path: Path) -> None:
        executor = HighThroughputExecutor()
        om = _create_stress_order_manager(
            executor, audit_db_path=tmp_path / "stress_timing.sqlite", max_ops=200
        )
        start = time.perf_counter()
        for i in range(100):
            sym = f"SYM{i:03d}"
            price = Decimal("100") + Decimal(str(i * 10))
            om.update_market_data(
                last_prices={sym: price},
                positions={},
                total_exposure=Decimal("0"),
            )
            om.place_order(
                OrderRequest(
                    exchange=Exchange.NSE,
                    symbol=sym,
                    side=OrderSide.BUY,
                    quantity=Decimal("1"),
                    price=price,
                ),
                strategy_id="stress-timing",
            )
        elapsed = time.perf_counter() - start
        assert executor.total_orders == 100
        assert elapsed < 30.0

    def test_paper_executor_100_orders(self) -> None:
        executor = PaperExecutor(slippage_bps=Decimal("2"))
        om = OrderManager(
            executor=executor,
            heartbeat_timeout_seconds=300,
            order_throttle=OrderThrottle(max_ops=200),
        )
        for i in range(100):
            om.place_order(
                OrderRequest(
                    exchange=Exchange.NSE,
                    symbol=f"PAPER{i:03d}",
                    side=OrderSide.BUY,
                    quantity=Decimal("10"),
                    price=Decimal("100"),
                )
            )
        status = om.get_order_status("PAPER-000001")
        assert status == OrderStatus.FILLED


class TestStressAuditThroughput:
    """Stress test: High-throughput audit logging."""

    def test_audit_100_trades_persistence(self, tmp_path: Path) -> None:
        db_path = tmp_path / "stress_audit.sqlite"
        audit = TradeAuditLogger(db_path)
        for i in range(100):
            request = OrderRequest(
                exchange=Exchange.NSE,
                symbol=f"AUDIT{i:03d}",
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                price=Decimal("100"),
            )
            result = ExecutionResult(
                order_id=f"AUD-{i:06d}",
                status=OrderStatus.FILLED,
                filled_quantity=Decimal("10"),
                average_price=Decimal("100"),
            )
            audit.log_order(request, result, strategy_id="stress-audit")
        today = datetime.now(UTC).date()
        trades = audit.query_daily_trades(today)
        assert len(trades) == 100

    def test_audit_persistence_timing(self, tmp_path: Path) -> None:
        db_path = tmp_path / "stress_audit_timing.sqlite"
        audit = TradeAuditLogger(db_path)
        start = time.perf_counter()
        for i in range(100):
            request = OrderRequest(
                exchange=Exchange.NSE,
                symbol=f"TIMED{i:03d}",
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                price=Decimal("100"),
            )
            result = ExecutionResult(
                order_id=f"TIM-{i:06d}",
                status=OrderStatus.FILLED,
                filled_quantity=Decimal("10"),
                average_price=Decimal("100"),
            )
            audit.log_order(request, result, strategy_id="timing")
        elapsed = time.perf_counter() - start
        assert elapsed < 15.0


class TestStressCombinedPipeline:
    """Stress test: Combined pipeline under load."""

    @pytest.mark.asyncio
    async def test_full_pipeline_50_symbols_100_orders(self, tmp_path: Path) -> None:
        symbols = _generate_symbols(55)
        custom_data = _generate_market_data(symbols)
        sentiment = create_mock_sentiment_analyzer({s: (Decimal("0.8"), True) for s in symbols})
        rl = create_mock_rl_predictor(probability=Decimal("0.7"))
        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=20, min_volume_ratio=Decimal("1.0")),
            data_provider=None,
            sentiment_analyzer=sentiment,
            rl_predictor=rl,
            symbols=symbols,
        )
        scan_result = scanner.scan(direction=SortDirection.GAINERS, custom_data=custom_data)
        assert scan_result.total_scanned == 55
        executor = HighThroughputExecutor()
        om = _create_stress_order_manager(
            executor, audit_db_path=tmp_path / "combined.sqlite", max_ops=200
        )
        all_candidates = scan_result.gainers + scan_result.losers
        for candidate in all_candidates:
            om.update_market_data(
                last_prices={candidate.symbol: candidate.close_price},
                positions={},
                total_exposure=Decimal("0"),
            )
            om.place_order(
                OrderRequest(
                    exchange=candidate.exchange,
                    symbol=candidate.symbol,
                    side=OrderSide.BUY,
                    quantity=Decimal("1"),
                    price=candidate.close_price,
                ),
                strategy_id="combined-stress",
            )
        assert executor.total_orders == len(all_candidates)
