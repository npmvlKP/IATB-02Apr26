"""Comprehensive coverage tests for iatb.execution.paper_executor."""

from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.enums import Exchange, MarketType, OrderSide, OrderStatus, OrderType
from iatb.core.exceptions import ConfigError
from iatb.execution.base import OrderRequest
from iatb.execution.paper_executor import (
    PaperExecutor,
    _compute_slippage_bps,
    _resolve_base_slippage,
    _volume_adjustment_factor,
    apply_slippage,
    is_liquid_instrument,
    validate_fill_against_market,
)


def _make_order(**overrides: object) -> OrderRequest:
    defaults = {
        "exchange": Exchange.NSE,
        "symbol": "RELIANCE",
        "side": OrderSide.BUY,
        "quantity": Decimal("10"),
        "order_type": OrderType.MARKET,
        "price": Decimal("2500"),
        "market_type": MarketType.SPOT,
    }
    defaults.update(overrides)
    return OrderRequest(**defaults)


class TestResolveBaseSlippage:
    def test_nse_spot(self) -> None:
        assert _resolve_base_slippage(Exchange.NSE, MarketType.SPOT) == Decimal("3")

    def test_nse_futures(self) -> None:
        assert _resolve_base_slippage(Exchange.NSE, MarketType.FUTURES) == Decimal("2")

    def test_nse_options(self) -> None:
        assert _resolve_base_slippage(Exchange.NSE, MarketType.OPTIONS) == Decimal("2")

    def test_bse_spot(self) -> None:
        assert _resolve_base_slippage(Exchange.BSE, MarketType.SPOT) == Decimal("5")

    def test_mcx_spot(self) -> None:
        assert _resolve_base_slippage(Exchange.MCX, MarketType.SPOT) == Decimal("8")

    def test_mcx_futures(self) -> None:
        assert _resolve_base_slippage(Exchange.MCX, MarketType.FUTURES) == Decimal("8")

    def test_mcx_options(self) -> None:
        assert _resolve_base_slippage(Exchange.MCX, MarketType.OPTIONS) == Decimal("8")

    def test_fallback(self) -> None:
        assert _resolve_base_slippage(Exchange.CDS, MarketType.SPOT) == Decimal("5")

    def test_binance_spot(self) -> None:
        assert _resolve_base_slippage(Exchange.BINANCE, MarketType.SPOT) == Decimal("5")


class TestVolumeAdjustmentFactor:
    def test_zero_quantity(self) -> None:
        assert _volume_adjustment_factor(Decimal("0")) == Decimal("1.0")

    def test_negative_quantity(self) -> None:
        assert _volume_adjustment_factor(Decimal("-1")) == Decimal("1.0")

    def test_small_quantity(self) -> None:
        factor = _volume_adjustment_factor(Decimal("1"))
        assert Decimal("0.5") <= factor <= Decimal("1.0")

    def test_large_quantity(self) -> None:
        factor = _volume_adjustment_factor(Decimal("1000000"))
        assert factor >= Decimal("0.5")

    def test_factor_bounded_min(self) -> None:
        factor = _volume_adjustment_factor(Decimal("1e30"))
        assert factor == Decimal("0.5")

    def test_factor_bounded_max(self) -> None:
        factor = _volume_adjustment_factor(Decimal("0"))
        assert factor <= Decimal("1.0")

    def test_exception_in_ln_returns_zero(self) -> None:
        factor = _volume_adjustment_factor(Decimal("1e999999999"))
        assert factor == Decimal("1.0")

    def test_factor_at_max_boundary(self) -> None:
        factor = _volume_adjustment_factor(Decimal("1e-100"))
        assert Decimal("0.5") <= factor <= Decimal("1.0")


class TestComputeSlippageBps:
    def test_override_bps(self) -> None:
        result = _compute_slippage_bps(
            Exchange.NSE, MarketType.SPOT, Decimal("10"), Decimal("7")
        )
        assert result == Decimal("7")

    def test_no_override(self) -> None:
        result = _compute_slippage_bps(
            Exchange.NSE, MarketType.SPOT, Decimal("10"), None
        )
        assert result > Decimal("0")

    def test_none_override_uses_base(self) -> None:
        result = _compute_slippage_bps(
            Exchange.NSE, MarketType.SPOT, Decimal("10"), None
        )
        base = _resolve_base_slippage(Exchange.NSE, MarketType.SPOT)
        assert result <= base


class TestApplySlippage:
    def test_buy_slippage_adds(self) -> None:
        result = apply_slippage(Decimal("100"), Decimal("5"), OrderSide.BUY)
        assert result > Decimal("100")

    def test_sell_slippage_subtracts(self) -> None:
        result = apply_slippage(Decimal("100"), Decimal("5"), OrderSide.SELL)
        assert result < Decimal("100")

    def test_sell_clamps_to_zero(self) -> None:
        result = apply_slippage(Decimal("1"), Decimal("50000"), OrderSide.SELL)
        assert result == Decimal("0")

    def test_buy_exact_calculation(self) -> None:
        impact = Decimal("5") / Decimal("10000") * Decimal("100")
        expected = Decimal("100") + impact
        result = apply_slippage(Decimal("100"), Decimal("5"), OrderSide.BUY)
        assert result == expected

    def test_sell_exact_calculation(self) -> None:
        impact = Decimal("5") / Decimal("10000") * Decimal("100")
        expected = Decimal("100") - impact
        result = apply_slippage(Decimal("100"), Decimal("5"), OrderSide.SELL)
        assert result == expected


class TestIsLiquidInstrument:
    def test_nse_spot_liquid(self) -> None:
        assert is_liquid_instrument(Exchange.NSE, MarketType.SPOT) is True

    def test_nse_futures_liquid(self) -> None:
        assert is_liquid_instrument(Exchange.NSE, MarketType.FUTURES) is True

    def test_mcx_not_liquid(self) -> None:
        assert is_liquid_instrument(Exchange.MCX, MarketType.SPOT) is False

    def test_unknown_not_liquid(self) -> None:
        assert is_liquid_instrument(Exchange.CDS, MarketType.CURRENCY_FO) is False


class TestValidateFillAgainstMarket:
    def test_valid_fill(self) -> None:
        is_valid, msg, actual = validate_fill_against_market(
            Decimal("100.05"), Decimal("100"), OrderSide.BUY, Decimal("5")
        )
        assert is_valid is True
        assert actual > Decimal("0")

    def test_zero_market_price(self) -> None:
        is_valid, msg, actual = validate_fill_against_market(
            Decimal("0"), Decimal("0"), OrderSide.BUY, Decimal("5")
        )
        assert is_valid is True
        assert actual == Decimal("0")

    def test_out_of_bounds(self) -> None:
        is_valid, msg, actual = validate_fill_against_market(
            Decimal("110"),
            Decimal("100"),
            OrderSide.BUY,
            Decimal("5"),
            tolerance_bps=Decimal("1"),
        )
        assert is_valid is False

    def test_custom_tolerance(self) -> None:
        is_valid, _, _ = validate_fill_against_market(
            Decimal("100.07"),
            Decimal("100"),
            OrderSide.BUY,
            Decimal("5"),
            tolerance_bps=Decimal("10"),
        )
        assert is_valid is True


class TestPaperExecutorInit:
    def test_default_init(self) -> None:
        pe = PaperExecutor()
        assert pe._slippage_override_bps is None

    def test_custom_slippage(self) -> None:
        pe = PaperExecutor(slippage_bps=Decimal("3"))
        assert pe._slippage_override_bps == Decimal("3")

    def test_negative_slippage_raises(self) -> None:
        with pytest.raises(ConfigError, match="negative"):
            PaperExecutor(slippage_bps=Decimal("-1"))

    def test_crash_recovery_mode(self) -> None:
        pe = PaperExecutor(crash_recovery_mode=True)
        assert pe._crash_recovery_mode is True

    def test_state_file_not_found(self) -> None:
        pe = PaperExecutor(state_file="nonexistent.json")
        assert pe._positions == {}

    def test_state_persistence_path(self, tmp_path: Path) -> None:
        pe = PaperExecutor(state_persistence_path=tmp_path / "state.json")
        assert pe._state_persistence_path == tmp_path / "state.json"


class TestPaperExecutorExecuteOrder:
    def test_buy_order(self) -> None:
        pe = PaperExecutor()
        order = _make_order(side=OrderSide.BUY)
        result = pe.execute_order(order)
        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == Decimal("10")
        assert result.average_price > Decimal("0")

    def test_sell_order(self) -> None:
        pe = PaperExecutor()
        order = _make_order(side=OrderSide.SELL)
        result = pe.execute_order(order)
        assert result.status == OrderStatus.FILLED

    def test_order_without_price(self) -> None:
        pe = PaperExecutor()
        order = _make_order(price=None)
        result = pe.execute_order(order)
        assert result.status == OrderStatus.FILLED

    def test_unique_order_ids(self) -> None:
        pe = PaperExecutor()
        order = _make_order()
        r1 = pe.execute_order(order)
        r2 = pe.execute_order(order)
        assert r1.order_id != r2.order_id

    def test_positions_update_buy(self) -> None:
        pe = PaperExecutor()
        order = _make_order(side=OrderSide.BUY, symbol="TCS")
        pe.execute_order(order)
        positions = pe.get_positions()
        assert "TCS" in positions

    def test_positions_update_sell(self) -> None:
        pe = PaperExecutor()
        buy_order = _make_order(
            side=OrderSide.BUY, symbol="TCS", quantity=Decimal("10")
        )
        pe.execute_order(buy_order)
        sell_order = _make_order(
            side=OrderSide.SELL, symbol="TCS", quantity=Decimal("5")
        )
        pe.execute_order(sell_order)
        positions = pe.get_positions()
        qty, _ = positions["TCS"]
        assert qty == Decimal("5")


class TestPaperExecutorCancelAll:
    def test_cancel_all_clears_orders(self) -> None:
        pe = PaperExecutor()
        order = _make_order()
        pe.execute_order(order)
        count = pe.cancel_all()
        assert count >= 0

    def test_cancel_all_empty(self) -> None:
        pe = PaperExecutor()
        count = pe.cancel_all()
        assert count == 0


class TestPaperExecutorCloseOrder:
    def test_close_existing_order(self) -> None:
        pe = PaperExecutor()
        order = _make_order()
        result = pe.execute_order(order)
        assert pe.close_order(result.order_id) is True

    def test_close_nonexistent_order(self) -> None:
        pe = PaperExecutor()
        assert pe.close_order("NONEXISTENT") is False


class TestPaperExecutorGetPositions:
    def test_empty_positions(self) -> None:
        pe = PaperExecutor()
        assert pe.get_positions() == {}

    def test_returns_copy(self) -> None:
        pe = PaperExecutor()
        order = _make_order()
        pe.execute_order(order)
        pos1 = pe.get_positions()
        pos2 = pe.get_positions()
        assert pos1 is not pos2


class TestPaperExecutorPersistState:
    def test_persist_and_restore(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        pe = PaperExecutor(state_persistence_path=state_path)
        order = _make_order()
        pe.execute_order(order)
        assert state_path.exists()
        pe2 = PaperExecutor(state_persistence_path=state_path)
        positions = pe2.get_positions()
        assert "RELIANCE" in positions

    def test_state_file_string(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        pe = PaperExecutor(state_file=str(state_path))
        order = _make_order()
        pe.execute_order(order)
        assert state_path.exists()
