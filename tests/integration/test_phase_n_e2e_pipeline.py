"""
Phase N.1 — Full E2E Integration Test Suite.

End-to-end pipeline test:
  DataProvider → Scanner → Selection → Risk → Execution → Audit

Covers:
- Full pipeline wiring through Engine.run_full_cycle()
- Selection cycle: signals → rank → StrategyContext
- OrderManager 7-step safety pipeline
- TradeAuditLogger SQLite persistence
- Kill switch, circuit breaker, daily loss guard integration
- Portfolio risk snapshot computation
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus, OrderType
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_quantity, create_timestamp
from iatb.data.base import DataProvider, OHLCVBar
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.order_manager import OrderManager
from iatb.execution.order_throttle import OrderThrottle
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.pre_trade_validator import PreTradeConfig
from iatb.execution.trade_audit import TradeAuditLogger
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer
from iatb.risk.circuit_breaker import evaluate_circuit_breaker
from iatb.risk.daily_loss_guard import DailyLossGuard
from iatb.risk.kill_switch import KillSwitch
from iatb.risk.portfolio_risk import build_risk_snapshot
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    InstrumentScanner,
    MarketData,
    ScannerConfig,
    ScannerResult,
    SortDirection,
    create_mock_rl_predictor,
    create_mock_sentiment_analyzer,
)
from iatb.scanner.scan_cycle import ScanCycleResult
from iatb.selection.ranking import RankingConfig, SelectionResult, rank_and_select
from iatb.selection.selection_bridge import build_strategy_contexts


class SyntheticDataProvider(DataProvider):
    """Deterministic mock DataProvider producing synthetic OHLCV data."""

    def __init__(self, base_prices: dict[str, Decimal] | None = None) -> None:
        self._base_prices = base_prices or {}
        self._call_log: list[dict[str, Any]] = []

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: object = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        self._call_log.append({"symbol": symbol, "exchange": exchange})
        base = self._base_prices.get(symbol, Decimal("1000"))
        bars: list[OHLCVBar] = []
        for i in range(min(limit, 30)):
            ts = datetime.now(UTC) - timedelta(days=30 - i)
            close = base + (Decimal("5") * Decimal(i))
            bars.append(
                OHLCVBar(
                    timestamp=create_timestamp(ts),
                    exchange=exchange,
                    symbol=symbol,
                    open=close * Decimal("0.99"),
                    high=close * Decimal("1.02"),
                    low=close * Decimal("0.98"),
                    close=close,
                    volume=create_quantity("2000000"),
                    source="synthetic",
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


class CountingExecutor(Executor):
    """Executor that counts calls and records requests."""

    def __init__(self) -> None:
        self._counter = 0
        self._requests: list[OrderRequest] = []
        self._cancelled = False

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        self._counter += 1
        self._requests.append(request)
        order_id = f"CNT-{self._counter:06d}"
        fill_price = request.price or Decimal("100")
        return ExecutionResult(
            order_id=order_id,
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            average_price=fill_price,
            message="counting fill",
        )

    def cancel_all(self) -> int:
        self._cancelled = True
        return len(self._requests)

    def close_order(self, order_id: str) -> bool:
        return True


def _build_market_data(
    symbol: str,
    exchange: Exchange = Exchange.NSE,
    pct_change: Decimal = Decimal("3"),
    volume_ratio: Decimal = Decimal("3.0"),
    adx: Decimal = Decimal("25"),
    atr_pct: Decimal = Decimal("0.02"),
    breadth_ratio: Decimal = Decimal("1.5"),
    close_price: Decimal = Decimal("1000"),
) -> MarketData:
    prev_close = close_price / (Decimal("1") + pct_change / Decimal("100"))
    return MarketData(
        symbol=symbol,
        exchange=exchange,
        category=InstrumentCategory.STOCK,
        close_price=close_price,
        prev_close_price=prev_close,
        volume=Decimal("3000000"),
        avg_volume=Decimal("1000000"),
        timestamp_utc=datetime.now(UTC),
        high_price=close_price * Decimal("1.01"),
        low_price=close_price * Decimal("0.99"),
        adx=adx,
        atr_pct=atr_pct,
        breadth_ratio=breadth_ratio,
    )


def _build_order_request(
    symbol: str = "RELIANCE",
    exchange: Exchange = Exchange.NSE,
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("10"),
    price: Decimal = Decimal("1000"),
) -> OrderRequest:
    return OrderRequest(
        exchange=exchange,
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        price=price,
    )


def _create_full_order_manager(
    executor: Executor | None = None,
    audit_db_path: Path | None = None,
) -> OrderManager:
    executor = executor or PaperExecutor()
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
    audit = TradeAuditLogger(audit_db_path or Path("data/audit/test_trades.sqlite"))
    throttle = OrderThrottle(max_ops=50)
    return OrderManager(
        executor=executor,
        heartbeat_timeout_seconds=30,
        kill_switch=kill_switch,
        pre_trade_config=pre_trade,
        daily_loss_guard=daily_guard,
        audit_logger=audit,
        order_throttle=throttle,
        algo_id="TEST-E2E-001",
    )


class TestE2EDataProviderToScanner:
    """E2E test: DataProvider → Scanner pipeline."""

    def test_synthetic_provider_feeds_scanner(self) -> None:
        provider = SyntheticDataProvider(
            base_prices={"RELIANCE": Decimal("1000"), "TCS": Decimal("3500")}
        )
        sentiment = create_mock_sentiment_analyzer(
            {"RELIANCE": (Decimal("0.8"), True), "TCS": (Decimal("0.85"), True)}
        )
        rl = create_mock_rl_predictor(probability=Decimal("0.7"))
        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5, min_volume_ratio=Decimal("1.0")),
            data_provider=provider,
            strength_scorer=StrengthScorer(cache_enabled=False),
            sentiment_analyzer=sentiment,
            rl_predictor=rl,
            symbols=["RELIANCE", "TCS"],
        )
        result = scanner.scan(direction=SortDirection.GAINERS)
        assert result is not None
        assert result.total_scanned >= 0
        assert isinstance(result, ScannerResult)

    def test_scanner_with_custom_market_data(self) -> None:
        custom_data = [
            _build_market_data("RELIANCE", pct_change=Decimal("4")),
            _build_market_data("TCS", pct_change=Decimal("2")),
            _build_market_data("INFY", pct_change=Decimal("-1")),
        ]
        sentiment = create_mock_sentiment_analyzer(
            {"RELIANCE": (Decimal("0.8"), True), "TCS": (Decimal("0.8"), True)}
        )
        rl = create_mock_rl_predictor(probability=Decimal("0.6"))
        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5, min_volume_ratio=Decimal("1.0")),
            data_provider=None,
            sentiment_analyzer=sentiment,
            rl_predictor=rl,
            symbols=["RELIANCE", "TCS", "INFY"],
        )
        result = scanner.scan(direction=SortDirection.GAINERS, custom_data=custom_data)
        assert result.total_scanned == 3
        assert result.scan_timestamp_utc.tzinfo == UTC


class TestE2EScannerToSelection:
    """E2E test: Scanner → Selection → StrategyContext pipeline."""

    def test_rank_and_select_filters_candidates(self) -> None:
        candidates = [
            ("RELIANCE", Exchange.NSE, Decimal("0.8"), {"regime": "BULL"}),
            ("TCS", Exchange.NSE, Decimal("0.6"), {"regime": "BULL"}),
            ("INFY", Exchange.NSE, Decimal("0.1"), {"regime": "SIDEWAYS"}),
        ]
        result = rank_and_select(candidates, RankingConfig(min_score=Decimal("0.3"), top_n=2))
        assert len(result.selected) == 2
        assert result.selected[0].symbol == "RELIANCE"
        assert result.selected[0].rank == 1
        assert result.filtered_count == 1

    def test_correlation_filter_removes_similar(self) -> None:
        candidates = [
            ("RELIANCE", Exchange.NSE, Decimal("0.9"), {}),
            ("HDFCBANK", Exchange.NSE, Decimal("0.85"), {}),
            ("TCS", Exchange.NSE, Decimal("0.8"), {}),
        ]
        correlations: dict[tuple[str, str], Decimal] = {
            ("RELIANCE", "HDFCBANK"): Decimal("0.95"),
            ("HDFCBANK", "RELIANCE"): Decimal("0.95"),
        }
        result = rank_and_select(
            candidates,
            RankingConfig(min_score=Decimal("0.5"), correlation_limit=Decimal("0.8")),
            correlations=correlations,
        )
        assert len(result.selected) <= 2

    def test_build_strategy_contexts_from_selection(self) -> None:
        selection = SelectionResult(
            selected=[
                MagicMock(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    composite_score=Decimal("0.8"),
                    rank=1,
                    metadata={},
                ),
            ],
            filtered_count=0,
            total_candidates=1,
        )
        strength_map = {
            "RELIANCE": StrengthInputs(
                breadth_ratio=Decimal("1.5"),
                regime=MarketRegime.BULL,
                adx=Decimal("25"),
                volume_ratio=Decimal("2.0"),
                volatility_atr_pct=Decimal("0.02"),
            )
        }
        contexts = build_strategy_contexts(selection, strength_map, side=OrderSide.BUY)
        assert len(contexts) == 1
        assert contexts[0].symbol == "RELIANCE"
        assert contexts[0].side == OrderSide.BUY


class TestE2ERiskToExecution:
    """E2E test: Risk gates → Execution pipeline."""

    def test_kill_switch_blocks_orders(self) -> None:
        executor = CountingExecutor()
        kill_switch = KillSwitch(executor)
        om = OrderManager(
            executor=executor,
            kill_switch=kill_switch,
            heartbeat_timeout_seconds=30,
        )
        kill_switch.engage("test halt", datetime.now(UTC))
        assert kill_switch.is_engaged
        request = _build_order_request()
        with pytest.raises(ConfigError, match="kill switch"):
            om.place_order(request)
        assert executor._counter == 0

    def test_daily_loss_guard_engages_kill_switch(self) -> None:
        executor = CountingExecutor()
        kill_switch = KillSwitch(executor)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=kill_switch,
        )
        om = OrderManager(
            executor=executor,
            kill_switch=kill_switch,
            daily_loss_guard=guard,
            heartbeat_timeout_seconds=30,
        )
        big_loss = Decimal("-3000")
        guard.record_trade(big_loss, datetime.now(UTC))
        assert kill_switch.is_engaged
        with pytest.raises(ConfigError, match="kill switch"):
            om.place_order(_build_order_request())

    def test_order_throttle_rejects_excess(self) -> None:
        executor = CountingExecutor()
        throttle = OrderThrottle(max_ops=3)
        om = OrderManager(
            executor=executor,
            order_throttle=throttle,
            heartbeat_timeout_seconds=30,
        )
        for _ in range(3):
            om.place_order(_build_order_request())
        with pytest.raises(ConfigError, match="throttle"):
            om.place_order(_build_order_request())

    def test_pre_trade_validation_blocks_fat_finger(self) -> None:
        executor = CountingExecutor()
        pre_trade = PreTradeConfig(
            max_order_quantity=Decimal("10"),
            max_order_value=Decimal("500000"),
            max_price_deviation_pct=Decimal("0.05"),
            max_position_per_symbol=Decimal("200"),
            max_portfolio_exposure=Decimal("1000000"),
        )
        om = OrderManager(
            executor=executor,
            pre_trade_config=pre_trade,
            heartbeat_timeout_seconds=30,
        )
        om.update_market_data(
            last_prices={"RELIANCE": Decimal("1000")},
            positions={},
            total_exposure=Decimal("0"),
        )
        huge_request = _build_order_request(quantity=Decimal("500"))
        with pytest.raises(ConfigError, match="fat-finger"):
            om.place_order(huge_request)
        assert executor._counter == 0


class TestE2EExecutionToAudit:
    """E2E test: Execution → Audit trail pipeline."""

    def test_order_flow_persists_to_audit_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "audit.sqlite"
        executor = CountingExecutor()
        om = _create_full_order_manager(executor=executor, audit_db_path=db_path)
        om.update_market_data(
            last_prices={"RELIANCE": Decimal("1000")},
            positions={},
            total_exposure=Decimal("0"),
        )
        request = _build_order_request(price=Decimal("1000"))
        result = om.place_order(request, strategy_id="e2e-test")
        assert result.status == OrderStatus.FILLED
        assert executor._counter == 1
        audit = TradeAuditLogger(db_path)
        today = datetime.now(UTC).date()
        trades = audit.query_daily_trades(today)
        assert len(trades) >= 1
        assert trades[0].symbol == "RELIANCE"
        assert trades[0].strategy_id == "e2e-test"

    def test_multiple_trades_audit_trail(self, tmp_path: Path) -> None:
        db_path = tmp_path / "audit_multi.sqlite"
        executor = CountingExecutor()
        om = _create_full_order_manager(executor=executor, audit_db_path=db_path)
        om.update_market_data(
            last_prices={"RELIANCE": Decimal("1000"), "TCS": Decimal("3500")},
            positions={},
            total_exposure=Decimal("0"),
        )
        symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN"]
        for sym in symbols:
            price = Decimal("1000") if sym == "RELIANCE" else Decimal("500")
            om.update_market_data(
                last_prices={sym: price}, positions={}, total_exposure=Decimal("0")
            )
            om.place_order(
                _build_order_request(symbol=sym, price=price),
                strategy_id="multi-e2e",
            )
        audit = TradeAuditLogger(db_path)
        today = datetime.now(UTC).date()
        trades = audit.query_daily_trades(today)
        assert len(trades) == 5


class TestE2EFullPipelineWithEngine:
    """E2E test: Full pipeline through Engine."""

    @pytest.mark.asyncio
    async def test_engine_lifecycle(self) -> None:
        from iatb.core.engine import Engine

        engine = Engine()
        assert not engine.is_running
        await engine.start()
        assert engine.is_running
        await engine.stop()
        assert not engine.is_running

    @pytest.mark.asyncio
    async def test_engine_run_full_cycle_with_mocks(self) -> None:
        from iatb.core.engine import Engine

        executor = CountingExecutor()
        om = _create_full_order_manager(executor=executor)
        provider = SyntheticDataProvider(base_prices={"RELIANCE": Decimal("1000")})
        scanner_config = ScannerConfig(top_n=5, min_volume_ratio=Decimal("1.0"))
        engine = Engine(
            data_provider=provider,
            order_manager=om,
            scanner_config=scanner_config,
        )
        with patch("iatb.scanner.scan_cycle._initialize_sentiment_analyzer") as mock_sa:
            mock_sa.return_value = create_mock_sentiment_analyzer(
                {"RELIANCE": (Decimal("0.8"), True)}
            )
            with patch("iatb.scanner.scan_cycle._initialize_rl_predictor") as mock_rl:
                mock_rl.return_value = create_mock_rl_predictor(probability=Decimal("0.7"))
                with patch("iatb.scanner.scan_cycle._initialize_strength_scorer") as mock_ss:
                    mock_ss.return_value = StrengthScorer(cache_enabled=False)
                    with patch("iatb.scanner.scan_cycle.check_ml_readiness"):
                        result = engine.run_full_cycle(symbols=["RELIANCE"], max_trades=1)
        assert isinstance(result, ScanCycleResult)
        assert result.timestamp_utc.tzinfo == UTC


class TestE2EPortfolioRisk:
    """E2E test: Portfolio risk computation."""

    def test_risk_snapshot_with_drawdown(self) -> None:
        returns = [
            Decimal("0.01"),
            Decimal("-0.02"),
            Decimal("0.03"),
            Decimal("-0.01"),
            Decimal("0.02"),
            Decimal("-0.04"),
            Decimal("0.01"),
            Decimal("0.005"),
        ]
        equity = [
            Decimal("100000"),
            Decimal("99000"),
            Decimal("101970"),
            Decimal("100960"),
            Decimal("102979"),
            Decimal("98859"),
            Decimal("99847"),
            Decimal("100347"),
        ]
        snapshot = build_risk_snapshot(returns, equity, max_allowed_drawdown=Decimal("0.05"))
        assert snapshot.var_95 >= Decimal("0")
        assert snapshot.cvar_95 >= Decimal("0")
        assert snapshot.max_drawdown >= Decimal("0")

    def test_circuit_breaker_levels(self) -> None:
        no_halt = evaluate_circuit_breaker(Decimal("5"))
        assert not no_halt.halt_required
        level1 = evaluate_circuit_breaker(Decimal("10"))
        assert level1.halt_required
        assert level1.level == 1
        level2 = evaluate_circuit_breaker(Decimal("15"))
        assert level2.halt_required
        assert level2.level == 2
        level3 = evaluate_circuit_breaker(Decimal("20"))
        assert level3.halt_required
        assert level3.level == 3


class TestE2EPnLTracking:
    """E2E test: PnL tracking through order lifecycle."""

    def test_buy_sell_pnl_realized(self, tmp_path: Path) -> None:
        executor = CountingExecutor()
        om = _create_full_order_manager(executor=executor, audit_db_path=tmp_path / "pnl.sqlite")
        om.update_market_data(
            last_prices={"RELIANCE": Decimal("1000")},
            positions={},
            total_exposure=Decimal("0"),
        )
        buy_result = om.place_order(
            _build_order_request(side=OrderSide.BUY, price=Decimal("1000")),
            strategy_id="pnl-test",
        )
        assert buy_result.status == OrderStatus.FILLED
        om.update_market_data(
            last_prices={"RELIANCE": Decimal("1050")},
            positions={"RELIANCE": Decimal("10")},
            total_exposure=Decimal("10000"),
        )
        sell_result = om.place_order(
            _build_order_request(side=OrderSide.SELL, price=Decimal("1050")),
            strategy_id="pnl-test",
        )
        assert sell_result.status == OrderStatus.FILLED
        guard = om._daily_loss_guard
        assert guard is not None
        assert guard.state.cumulative_pnl > Decimal("0")

    def test_dead_man_switch_cancels_orders(self) -> None:
        executor = CountingExecutor()
        om = OrderManager(
            executor=executor,
            heartbeat_timeout_seconds=5,
        )
        om.receive_heartbeat(datetime.now(UTC) - timedelta(seconds=10))
        cancelled = om.check_dead_man_switch(datetime.now(UTC))
        assert cancelled is True
        assert executor._cancelled
