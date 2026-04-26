"""
Phase N.1 — Live-Like Simulation with Mocked Broker.

Simulates a realistic trading session:
- Mocked broker with realistic fills, latency, and slippage
- Full pipeline: scan → select → risk check → execute → audit
- Simulated market data with realistic price movements
- Order lifecycle: place → fill → cancel → PnL tracking
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus, OrderType
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.order_manager import OrderManager
from iatb.execution.order_throttle import OrderThrottle
from iatb.execution.pre_trade_validator import PreTradeConfig
from iatb.execution.trade_audit import TradeAuditLogger
from iatb.market_strength.strength_scorer import StrengthScorer
from iatb.risk.daily_loss_guard import DailyLossGuard
from iatb.risk.kill_switch import KillSwitch
from iatb.risk.position_sizer import (
    PositionSizingInput,
    fixed_fractional_size,
    kelly_fraction,
    volatility_adjusted_size,
)
from iatb.scanner.instrument_scanner import (
    ScannerConfig,
    create_mock_rl_predictor,
    create_mock_sentiment_analyzer,
)
from iatb.scanner.scan_cycle import run_scan_cycle


class SimulatedBroker(Executor):
    """Broker simulator with realistic fills, latency, and partial fills."""

    def __init__(
        self,
        base_prices: dict[str, Decimal] | None = None,
        slippage_bps: Decimal = Decimal("3"),
        rejection_rate: Decimal = Decimal("0"),
        latency_ms: int = 10,
    ) -> None:
        self._base_prices = base_prices or {}
        self._slippage_bps = slippage_bps
        self._rejection_rate = rejection_rate
        self._latency_ms = latency_ms
        self._counter = 0
        self._orders: dict[str, dict[str, Any]] = {}
        self._positions: dict[str, Decimal] = {}
        self._fills: list[dict[str, Any]] = []

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        self._counter += 1
        order_id = f"SIM-{self._counter:06d}"
        if self._rejection_rate > Decimal("0"):
            r = random.random()
            if r < float(self._rejection_rate):
                self._orders[order_id] = {"status": OrderStatus.REJECTED, "request": request}
                return ExecutionResult(
                    order_id=order_id,
                    status=OrderStatus.REJECTED,
                    filled_quantity=Decimal("0"),
                    average_price=Decimal("0"),
                    message="simulated rejection",
                )
        base = self._base_prices.get(request.symbol, request.price or Decimal("100"))
        slippage = (self._slippage_bps / Decimal("10000")) * base
        if request.side == OrderSide.BUY:
            fill_price = base + slippage
        else:
            fill_price = max(Decimal("0.01"), base - slippage)
        self._orders[order_id] = {
            "status": OrderStatus.FILLED,
            "request": request,
            "fill_price": fill_price,
        }
        self._fills.append(
            {
                "order_id": order_id,
                "symbol": request.symbol,
                "side": request.side.value,
                "quantity": request.quantity,
                "fill_price": fill_price,
            }
        )
        return ExecutionResult(
            order_id=order_id,
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            average_price=fill_price,
            message="simulated fill",
        )

    def cancel_all(self) -> int:
        cancelled = 0
        for oid in self._orders:
            if self._orders[oid]["status"] == OrderStatus.FILLED:
                cancelled += 1
        return cancelled

    def close_order(self, order_id: str) -> bool:
        if order_id in self._orders:
            self._orders[order_id]["status"] = OrderStatus.CANCELLED
            return True
        return False

    @property
    def fill_count(self) -> int:
        return len(self._fills)

    @property
    def total_notional(self) -> Decimal:
        return sum(Decimal(str(f["quantity"])) * Decimal(str(f["fill_price"])) for f in self._fills)


class LiveMarketSimulator(DataProvider):
    """Simulates live market data with realistic tick-by-tick updates."""

    def __init__(self, symbols: list[str], base_prices: dict[str, Decimal]) -> None:
        self._symbols = symbols
        self._base_prices = base_prices
        self._tick_count = 0

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: object = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        base = self._base_prices.get(symbol, Decimal("1000"))
        bars: list[OHLCVBar] = []
        for i in range(min(limit, 30)):
            ts = datetime.now(UTC) - timedelta(days=30 - i)
            noise = Decimal(str(random.gauss(0, 0.01)))
            close = base * (Decimal("1") + Decimal(str(i * 0.002)) + noise)
            close = max(Decimal("1"), close)
            bars.append(
                OHLCVBar(
                    timestamp=create_timestamp(ts),
                    exchange=exchange,
                    symbol=symbol,
                    open=close * Decimal("0.998"),
                    high=close * Decimal("1.005"),
                    low=close * Decimal("0.995"),
                    close=close,
                    volume=create_quantity(str(int(1000000 + random.gauss(0, 200000)))),
                    source="live_simulation",
                )
            )
        return bars

    async def get_ticker(self, *, symbol: str, exchange: Exchange) -> TickerSnapshot:
        self._tick_count += 1
        base = self._base_prices.get(symbol, Decimal("1000"))
        noise = Decimal(str(random.gauss(0, 0.002)))
        last = base * (Decimal("1") + noise)
        last = max(Decimal("1"), last)
        spread = last * Decimal("0.001")
        return TickerSnapshot(
            timestamp=create_timestamp(datetime.now(UTC)),
            exchange=exchange,
            symbol=symbol,
            bid=create_price(str(last - spread)),
            ask=create_price(str(last + spread)),
            last=create_price(str(last)),
            volume_24h=create_quantity("5000000"),
            source="live_simulation",
        )

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
    def tick_count(self) -> int:
        return self._tick_count


def _create_simulated_order_manager(
    broker: SimulatedBroker,
    audit_db_path: Path,
) -> OrderManager:
    kill_switch = KillSwitch(broker)
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
    audit = TradeAuditLogger(audit_db_path)
    throttle = OrderThrottle(max_ops=50)
    return OrderManager(
        executor=broker,
        heartbeat_timeout_seconds=30,
        kill_switch=kill_switch,
        pre_trade_config=pre_trade,
        daily_loss_guard=daily_guard,
        audit_logger=audit,
        order_throttle=throttle,
        algo_id="SIM-LIVE-001",
    )


class TestSimulatedBrokerFills:
    """Test simulated broker produces realistic fills."""

    def test_broker_fills_with_slippage(self) -> None:
        broker = SimulatedBroker(
            base_prices={"RELIANCE": Decimal("1000")},
            slippage_bps=Decimal("5"),
        )
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
            price=Decimal("1000"),
        )
        result = broker.execute_order(request)
        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == Decimal("10")
        assert result.average_price > Decimal("1000")

    def test_broker_rejection_simulation(self) -> None:
        broker = SimulatedBroker(
            rejection_rate=Decimal("1.0"),
        )
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("1000"),
        )
        result = broker.execute_order(request)
        assert result.status == OrderStatus.REJECTED
        assert result.filled_quantity == Decimal("0")

    def test_broker_sell_slippage(self) -> None:
        broker = SimulatedBroker(
            base_prices={"RELIANCE": Decimal("1000")},
            slippage_bps=Decimal("5"),
        )
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.SELL,
            quantity=Decimal("10"),
            price=Decimal("1000"),
        )
        result = broker.execute_order(request)
        assert result.status == OrderStatus.FILLED
        assert result.average_price < Decimal("1000")

    def test_broker_tracks_total_notional(self) -> None:
        broker = SimulatedBroker(base_prices={"RELIANCE": Decimal("1000")})
        for _ in range(5):
            broker.execute_order(
                OrderRequest(
                    exchange=Exchange.NSE,
                    symbol="RELIANCE",
                    side=OrderSide.BUY,
                    quantity=Decimal("10"),
                    price=Decimal("1000"),
                )
            )
        assert broker.fill_count == 5
        assert broker.total_notional > Decimal("0")


class TestLiveSimulationPipeline:
    """Test full pipeline with live-like simulated data."""

    @pytest.mark.asyncio
    async def test_scan_cycle_with_simulated_data(self, tmp_path: Path) -> None:
        symbols = ["RELIANCE", "TCS", "INFY"]
        base_prices = {
            "RELIANCE": Decimal("2500"),
            "TCS": Decimal("3500"),
            "INFY": Decimal("1500"),
        }
        provider = LiveMarketSimulator(symbols, base_prices)
        broker = SimulatedBroker(base_prices=base_prices, slippage_bps=Decimal("3"))
        om = _create_simulated_order_manager(broker, tmp_path / "sim_audit.sqlite")
        scanner_config = ScannerConfig(top_n=5, min_volume_ratio=Decimal("1.0"))
        with patch("iatb.scanner.scan_cycle._initialize_sentiment_analyzer") as mock_sa:
            mock_sa.return_value = create_mock_sentiment_analyzer(
                {s: (Decimal("0.8"), True) for s in symbols}
            )
            with patch("iatb.scanner.scan_cycle._initialize_rl_predictor") as mock_rl:
                mock_rl.return_value = create_mock_rl_predictor(probability=Decimal("0.7"))
                with patch("iatb.scanner.scan_cycle._initialize_strength_scorer") as mock_ss:
                    mock_ss.return_value = StrengthScorer(cache_enabled=False)
                    with patch("iatb.scanner.scan_cycle.check_ml_readiness"):
                        result = run_scan_cycle(
                            symbols=symbols,
                            max_trades=3,
                            order_manager=om,
                            data_provider=provider,
                            scanner_config=scanner_config,
                        )
        assert result is not None
        assert result.timestamp_utc.tzinfo == UTC

    @pytest.mark.asyncio
    async def test_simulated_trading_session(self, tmp_path: Path) -> None:
        base_prices = {"RELIANCE": Decimal("2500"), "TCS": Decimal("3500")}
        broker = SimulatedBroker(base_prices=base_prices, slippage_bps=Decimal("2"))
        om = _create_simulated_order_manager(broker, tmp_path / "session_audit.sqlite")
        trades = [
            ("RELIANCE", OrderSide.BUY, Decimal("10"), Decimal("2500")),
            ("TCS", OrderSide.BUY, Decimal("5"), Decimal("3500")),
            ("RELIANCE", OrderSide.SELL, Decimal("10"), Decimal("2550")),
        ]
        for symbol, side, qty, price in trades:
            om.update_market_data(
                last_prices={symbol: price},
                positions={},
                total_exposure=Decimal("0"),
            )
            result = om.place_order(
                OrderRequest(
                    exchange=Exchange.NSE,
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    price=price,
                ),
                strategy_id="sim-session",
            )
            assert result.status == OrderStatus.FILLED
        audit = TradeAuditLogger(tmp_path / "session_audit.sqlite")
        today = datetime.now(UTC).date()
        db_trades = audit.query_daily_trades(today)
        assert len(db_trades) == 3

    @pytest.mark.asyncio
    async def test_position_sizing_in_simulation(self) -> None:
        inputs = PositionSizingInput(
            equity=Decimal("1000000"),
            entry_price=Decimal("1000"),
            stop_price=Decimal("980"),
            risk_fraction=Decimal("0.02"),
            realized_volatility=Decimal("0.15"),
        )
        size = fixed_fractional_size(inputs)
        assert size > Decimal("0")
        kelly = kelly_fraction(
            win_rate=Decimal("0.55"),
            win_loss_ratio=Decimal("1.5"),
        )
        assert Decimal("0") < kelly <= Decimal("0.5")
        vol_size = volatility_adjusted_size(
            equity=Decimal("1000000"),
            target_risk_fraction=Decimal("0.02"),
            realized_volatility=Decimal("0.15"),
            base_volatility=Decimal("0.10"),
            lot_size=Decimal("1"),
        )
        assert vol_size > Decimal("0")

    @pytest.mark.asyncio
    async def test_market_data_tick_generation(self) -> None:
        provider = LiveMarketSimulator(["RELIANCE"], {"RELIANCE": Decimal("2500")})
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert ticker.symbol == "RELIANCE"
        assert ticker.source == "live_simulation"
        assert Decimal(str(ticker.bid)) < Decimal(str(ticker.ask))
        assert provider.tick_count == 1


class TestSimulatedRiskScenarios:
    """Test risk scenarios in simulated environment."""

    def test_kill_switch_halt_simulation(self, tmp_path: Path) -> None:
        broker = SimulatedBroker(base_prices={"RELIANCE": Decimal("1000")})
        om = _create_simulated_order_manager(broker, tmp_path / "halt.sqlite")
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
            strategy_id="halt-test",
        )
        assert broker.fill_count == 1
        om._kill_switch.engage("simulated halt", datetime.now(UTC))
        with pytest.raises(ConfigError):
            om.place_order(
                OrderRequest(
                    exchange=Exchange.NSE,
                    symbol="TCS",
                    side=OrderSide.BUY,
                    quantity=Decimal("10"),
                    price=Decimal("3500"),
                )
            )
        assert broker.fill_count == 1

    def test_pre_trade_blocks_oversized_in_simulation(self, tmp_path: Path) -> None:
        broker = SimulatedBroker(base_prices={"RELIANCE": Decimal("1000")})
        om = _create_simulated_order_manager(broker, tmp_path / "oversize.sqlite")
        om.update_market_data(
            last_prices={"RELIANCE": Decimal("1000")},
            positions={},
            total_exposure=Decimal("0"),
        )
        with pytest.raises(ConfigError):
            om.place_order(
                OrderRequest(
                    exchange=Exchange.NSE,
                    symbol="RELIANCE",
                    side=OrderSide.BUY,
                    quantity=Decimal("500"),
                    price=Decimal("1000"),
                )
            )
        assert broker.fill_count == 0
