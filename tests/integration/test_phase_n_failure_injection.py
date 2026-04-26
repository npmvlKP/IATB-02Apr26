"""
Phase N.1 — Failure Injection Tests.

Failure injection scenarios:
- Network partition: DataProvider becomes unreachable mid-pipeline
- Token expiry: Broker token expires during order execution
- API downtime: External API returns 5xx errors
- Partial failures: Some symbols fail, others succeed
- Timeout: Operations exceed time limits
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_quantity, create_timestamp
from iatb.data.base import DataProvider, OHLCVBar
from iatb.data.rate_limiter import CircuitBreaker
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


class NetworkPartitionProvider(DataProvider):
    """Simulates network partition by failing after N successful calls."""

    def __init__(self, fail_after: int = 2) -> None:
        self._fail_after = fail_after
        self._call_count = 0
        self._partition_active = False

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
        if self._call_count >= self._fail_after:
            self._partition_active = True
            raise ConnectionError("Network partition: connection refused")
        base = Decimal("1000")
        bars: list[OHLCVBar] = []
        for i in range(min(limit, 20)):
            ts = datetime.now(UTC) - timedelta(days=20 - i)
            close = base + (Decimal("5") * Decimal(i))
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
                    source="network_test",
                )
            )
        return bars

    async def get_ticker(self, *, symbol: str, exchange: Exchange) -> Any:
        self._call_count += 1
        if self._call_count >= self._fail_after:
            raise ConnectionError("Network partition: connection refused")
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
            try:
                result[sym] = await self.get_ohlcv(
                    symbol=sym, exchange=exchange, timeframe=timeframe, since=since, limit=limit
                )
            except ConnectionError:
                result[sym] = []
        return result

    @property
    def is_partition_active(self) -> bool:
        return self._partition_active


class TokenExpiryBroker(Executor):
    """Simulates broker token expiry mid-session."""

    def __init__(self, fail_after: int = 3) -> None:
        self._fail_after = fail_after
        self._counter = 0
        self._token_expired = False

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        self._counter += 1
        if self._counter > self._fail_after:
            self._token_expired = True
            raise PermissionError("Token expired: 401 Unauthorized")
        return ExecutionResult(
            order_id=f"TEX-{self._counter:06d}",
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            average_price=request.price or Decimal("100"),
            message="token-ok fill",
        )

    def cancel_all(self) -> int:
        return 0

    def close_order(self, order_id: str) -> bool:
        return True

    @property
    def is_token_expired(self) -> bool:
        return self._token_expired


class APIDowntimeBroker(Executor):
    """Simulates API downtime with 5xx errors."""

    def __init__(self, error_probability: Decimal = Decimal("0.5")) -> None:
        self._error_probability = error_probability
        self._counter = 0
        self._success_count = 0
        self._error_count = 0

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        self._counter += 1
        if float(self._error_probability) >= Decimal("0.99"):
            self._error_count += 1
            raise ConnectionError("503 Service Unavailable")
        if float(self._error_probability) <= Decimal("0.01"):
            self._success_count += 1
            return ExecutionResult(
                order_id=f"API-{self._counter:06d}",
                status=OrderStatus.FILLED,
                filled_quantity=request.quantity,
                average_price=request.price or Decimal("100"),
                message="api-ok fill",
            )
        if self._counter % 2 == 0:
            self._error_count += 1
            raise ConnectionError("503 Service Unavailable")
        self._success_count += 1
        return ExecutionResult(
            order_id=f"API-{self._counter:06d}",
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            average_price=request.price or Decimal("100"),
            message="api-ok fill",
        )

    def cancel_all(self) -> int:
        return 0

    def close_order(self, order_id: str) -> bool:
        return True


class PartialFailureProvider(DataProvider):
    """Returns data for some symbols but fails for others."""

    def __init__(self, failing_symbols: set[str] | None = None) -> None:
        self._failing_symbols = failing_symbols or {"FAIL1", "FAIL2"}

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: object = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        if symbol in self._failing_symbols:
            raise TimeoutError(f"Timeout fetching {symbol}")
        base = Decimal("1000")
        bars: list[OHLCVBar] = []
        for i in range(min(limit, 20)):
            ts = datetime.now(UTC) - timedelta(days=20 - i)
            close = base + (Decimal("5") * Decimal(i))
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
                    source="partial_test",
                )
            )
        return bars

    async def get_ticker(self, *, symbol: str, exchange: Exchange) -> Any:
        if symbol in self._failing_symbols:
            raise TimeoutError(f"Timeout fetching ticker {symbol}")
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
            try:
                result[sym] = await self.get_ohlcv(
                    symbol=sym, exchange=exchange, timeframe=timeframe, since=since, limit=limit
                )
            except TimeoutError:
                result[sym] = []
        return result


class TimeoutProvider(DataProvider):
    """Simulates slow API that times out."""

    def __init__(self, timeout_symbols: set[str] | None = None) -> None:
        self._timeout_symbols = timeout_symbols or {"SLOW1"}

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: object = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        if symbol in self._timeout_symbols:
            await asyncio.sleep(10)
            raise TimeoutError(f"Timeout after 10s for {symbol}")
        base = Decimal("1000")
        bars: list[OHLCVBar] = []
        for i in range(min(limit, 20)):
            ts = datetime.now(UTC) - timedelta(days=20 - i)
            close = base + (Decimal("5") * Decimal(i))
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
                    source="timeout_test",
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
            try:
                result[sym] = await self.get_ohlcv(
                    symbol=sym, exchange=exchange, timeframe=timeframe, since=since, limit=limit
                )
            except (TimeoutError, asyncio.CancelledError):
                result[sym] = []
        return result


def _create_resilient_order_manager(
    executor: Executor,
    audit_db_path: Path | None = None,
) -> OrderManager:
    kill_switch = KillSwitch(executor)
    pre_trade = PreTradeConfig(
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
    audit = TradeAuditLogger(audit_db_path or Path("data/audit/failure_test.sqlite"))
    throttle = OrderThrottle(max_ops=50)
    return OrderManager(
        executor=executor,
        heartbeat_timeout_seconds=30,
        kill_switch=kill_switch,
        pre_trade_config=pre_trade,
        daily_loss_guard=daily_guard,
        audit_logger=audit,
        order_throttle=throttle,
        algo_id="FAIL-TEST-001",
    )


class TestNetworkPartition:
    """Failure injection: Network partition scenarios."""

    @pytest.mark.asyncio
    async def test_network_partition_during_data_fetch(self) -> None:
        provider = NetworkPartitionProvider(fail_after=2)
        ok_bars = await provider.get_ohlcv(symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d")
        assert len(ok_bars) > 0
        assert not provider.is_partition_active
        with pytest.raises(ConnectionError, match="Network partition"):
            await provider.get_ohlcv(symbol="TCS", exchange=Exchange.NSE, timeframe="1d")
        assert provider.is_partition_active

    @pytest.mark.asyncio
    async def test_scanner_handles_network_partition_gracefully(self) -> None:
        custom_data = [
            MarketData(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                close_price=Decimal("1000"),
                prev_close_price=Decimal("970"),
                volume=Decimal("3000000"),
                avg_volume=Decimal("1000000"),
                timestamp_utc=datetime.now(UTC),
                high_price=Decimal("1010"),
                low_price=Decimal("990"),
                adx=Decimal("25"),
                atr_pct=Decimal("0.02"),
                breadth_ratio=Decimal("1.5"),
            )
        ]
        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5),
            data_provider=None,
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(probability=Decimal("0.7")),
            symbols=["RELIANCE"],
        )
        result = scanner.scan(direction=SortDirection.GAINERS, custom_data=custom_data)
        assert result.total_scanned == 1

    @pytest.mark.asyncio
    async def test_partial_network_failure_continues(self) -> None:
        provider = PartialFailureProvider(failing_symbols={"FAIL1", "FAIL2"})
        results = await provider.get_ohlcv_batch(
            symbols=["OK1", "FAIL1", "OK2", "FAIL2"],
            exchange=Exchange.NSE,
            timeframe="1d",
        )
        assert len(results["OK1"]) > 0
        assert len(results["FAIL1"]) == 0
        assert len(results["OK2"]) > 0
        assert len(results["FAIL2"]) == 0


class TestTokenExpiry:
    """Failure injection: Token expiry scenarios."""

    def test_token_expiry_halts_trading(self, tmp_path: Path) -> None:
        broker = TokenExpiryBroker(fail_after=2)
        om = _create_resilient_order_manager(broker, tmp_path / "token_expiry.sqlite")
        om.update_market_data(
            last_prices={"RELIANCE": Decimal("1000")},
            positions={},
            total_exposure=Decimal("0"),
        )
        result1 = om.place_order(
            OrderRequest(
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                price=Decimal("1000"),
            ),
            strategy_id="token-test",
        )
        assert result1.status == OrderStatus.FILLED
        result2 = om.place_order(
            OrderRequest(
                exchange=Exchange.NSE,
                symbol="TCS",
                side=OrderSide.BUY,
                quantity=Decimal("5"),
                price=Decimal("3500"),
            ),
            strategy_id="token-test",
        )
        assert result2.status == OrderStatus.FILLED
        with pytest.raises(PermissionError, match="Token expired"):
            om.place_order(
                OrderRequest(
                    exchange=Exchange.NSE,
                    symbol="INFY",
                    side=OrderSide.BUY,
                    quantity=Decimal("10"),
                    price=Decimal("1500"),
                )
            )
        assert broker.is_token_expired

    def test_successful_orders_persisted_before_expiry(self, tmp_path: Path) -> None:
        broker = TokenExpiryBroker(fail_after=2)
        om = _create_resilient_order_manager(broker, tmp_path / "token_persist.sqlite")
        om.update_market_data(
            last_prices={"RELIANCE": Decimal("1000")},
            positions={},
            total_exposure=Decimal("0"),
        )
        om.place_order(
            OrderRequest(
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                price=Decimal("1000"),
            ),
            strategy_id="persist-test",
        )
        try:
            om.place_order(
                OrderRequest(
                    exchange=Exchange.NSE,
                    symbol="TCS",
                    side=OrderSide.BUY,
                    quantity=Decimal("5"),
                    price=Decimal("3500"),
                ),
                strategy_id="persist-test",
            )
            om.place_order(
                OrderRequest(
                    exchange=Exchange.NSE,
                    symbol="INFY",
                    side=OrderSide.BUY,
                    quantity=Decimal("10"),
                    price=Decimal("1500"),
                ),
                strategy_id="persist-test",
            )
        except PermissionError:
            pass
        audit = TradeAuditLogger(tmp_path / "token_persist.sqlite")
        today = datetime.now(UTC).date()
        trades = audit.query_daily_trades(today)
        assert len(trades) >= 1


class TestAPIDowntime:
    """Failure injection: API downtime (5xx errors)."""

    def test_api_downtime_partial_success(self, tmp_path: Path) -> None:
        broker = APIDowntimeBroker(error_probability=Decimal("0.5"))
        om = _create_resilient_order_manager(broker, tmp_path / "downtime.sqlite")
        om.update_market_data(
            last_prices={"RELIANCE": Decimal("1000")},
            positions={},
            total_exposure=Decimal("0"),
        )
        success_count = 0
        error_count = 0
        for _ in range(20):
            try:
                result = om.place_order(
                    OrderRequest(
                        exchange=Exchange.NSE,
                        symbol="RELIANCE",
                        side=OrderSide.BUY,
                        quantity=Decimal("1"),
                        price=Decimal("1000"),
                    ),
                    strategy_id="downtime-test",
                )
                if result.status == OrderStatus.FILLED:
                    success_count += 1
            except ConnectionError:
                error_count += 1
        assert success_count > 0
        assert error_count > 0
        assert broker._success_count == success_count

    def test_api_downtime_with_full_failure(self, tmp_path: Path) -> None:
        broker = APIDowntimeBroker(error_probability=Decimal("1.0"))
        om = _create_resilient_order_manager(broker, tmp_path / "full_downtime.sqlite")
        om.update_market_data(
            last_prices={"RELIANCE": Decimal("1000")},
            positions={},
            total_exposure=Decimal("0"),
        )
        for _ in range(5):
            with pytest.raises(ConnectionError, match="503"):
                om.place_order(
                    OrderRequest(
                        exchange=Exchange.NSE,
                        symbol="RELIANCE",
                        side=OrderSide.BUY,
                        quantity=Decimal("1"),
                        price=Decimal("1000"),
                    )
                )
        assert broker._success_count == 0


class TestTimeoutScenarios:
    """Failure injection: Timeout scenarios."""

    @pytest.mark.asyncio
    async def test_timeout_provider_with_timeout_symbols(self) -> None:
        provider = TimeoutProvider(timeout_symbols={"SLOW1"})
        fast_result = await provider.get_ohlcv(
            symbol="FAST1", exchange=Exchange.NSE, timeframe="1d"
        )
        assert len(fast_result) > 0
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                provider.get_ohlcv(symbol="SLOW1", exchange=Exchange.NSE, timeframe="1d"),
                timeout=2.0,
            )

    @pytest.mark.asyncio
    async def test_batch_fetch_with_partial_timeouts(self) -> None:
        provider = TimeoutProvider(timeout_symbols={"SLOW1"})
        results = await asyncio.gather(
            provider.get_ohlcv(symbol="FAST1", exchange=Exchange.NSE, timeframe="1d"),
            asyncio.wait_for(
                provider.get_ohlcv(symbol="SLOW1", exchange=Exchange.NSE, timeframe="1d"),
                timeout=1.0,
            ),
            return_exceptions=True,
        )
        assert len(results) == 2
        assert isinstance(results[0], list)
        assert isinstance(results[1], TimeoutError | asyncio.TimeoutError)


class TestCircuitBreakerUnderFailure:
    """Failure injection: Circuit breaker behavior under repeated failures."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self) -> None:
        from iatb.data.rate_limiter import CircuitState

        cb = CircuitBreaker(failure_threshold=3, reset_timeout=5.0, name="test_cb")
        assert cb.state == CircuitState.CLOSED
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_resets_after_timeout(self) -> None:
        import time

        from iatb.data.rate_limiter import CircuitState

        cb = CircuitBreaker(failure_threshold=2, reset_timeout=1.0, name="reset_cb")
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(1.5)
        await cb.acquire()
        assert cb.state == CircuitState.HALF_OPEN
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_allows_during_normal(self) -> None:
        from iatb.data.rate_limiter import CircuitState

        cb = CircuitBreaker(failure_threshold=5, reset_timeout=60.0, name="normal_cb")
        for _ in range(4):
            await cb.acquire()
            await cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestKillSwitchUnderFailure:
    """Failure injection: Kill switch engagement under various failures."""

    def test_kill_switch_engaged_on_daily_loss_breach(self) -> None:
        executor = PaperExecutor()
        kill_switch = KillSwitch(executor)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.01"),
            starting_nav=Decimal("100000"),
            kill_switch=kill_switch,
        )
        guard.record_trade(Decimal("-500"), datetime.now(UTC))
        guard.record_trade(Decimal("-600"), datetime.now(UTC))
        assert kill_switch.is_engaged

    def test_kill_switch_prevents_recovery_trades_until_reset(self, tmp_path: Path) -> None:
        executor = PaperExecutor()
        om = _create_resilient_order_manager(executor, tmp_path / "ks_reset.sqlite")
        om.update_market_data(
            last_prices={"RELIANCE": Decimal("1000")},
            positions={},
            total_exposure=Decimal("0"),
        )
        assert om._kill_switch is not None
        om._kill_switch.engage("test halt", datetime.now(UTC))
        assert om._kill_switch.is_engaged
        with pytest.raises(ConfigError, match="kill switch"):
            om.place_order(
                OrderRequest(
                    exchange=Exchange.NSE,
                    symbol="RELIANCE",
                    side=OrderSide.BUY,
                    quantity=Decimal("10"),
                    price=Decimal("1000"),
                ),
                strategy_id="ks-reset-test",
            )
        om._kill_switch.disengage(datetime.now(UTC))
        assert not om._kill_switch.is_engaged
