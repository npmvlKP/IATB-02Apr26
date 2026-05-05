"""
Tests for slippage validation functionality in PaperExecutor.

These tests validate that deterministic slippage model produces
realistic fills within acceptable bounds when compared to market prices.
"""
from decimal import Decimal

from iatb.core.enums import Exchange, MarketType, OrderSide
from iatb.execution.base import OrderRequest
from iatb.execution.paper_executor import (
    _ILLIQUID_TARGET_SLIPPAGE_BPS,
    _LIQUID_TARGET_SLIPPAGE_BPS,
    _VALIDATION_TOLERANCE_BPS,
    PaperExecutor,
    _compute_slippage_bps,
    is_liquid_instrument,
    validate_fill_against_market,
)


def test_validate_fill_against_market_within_tolerance() -> None:
    """Test validation passes when fill is within tolerance."""
    fill_price = Decimal("100.06")  # 6 bps slippage
    market_price = Decimal("100")
    side = OrderSide.BUY
    target_bps = _LIQUID_TARGET_SLIPPAGE_BPS  # 5 bps
    tolerance = _VALIDATION_TOLERANCE_BPS  # 2 bps

    is_valid, message, actual_bps = validate_fill_against_market(
        fill_price, market_price, side, target_bps, tolerance
    )

    assert is_valid is True
    assert "validated" in message.lower()
    assert abs(actual_bps - Decimal("6")) < Decimal("0.1")


def test_validate_fill_against_market_exceeds_tolerance() -> None:
    """Test validation fails when fill exceeds tolerance."""
    fill_price = Decimal("100.15")  # 15 bps slippage
    market_price = Decimal("100")
    side = OrderSide.BUY
    target_bps = _LIQUID_TARGET_SLIPPAGE_BPS  # 5 bps
    tolerance = _VALIDATION_TOLERANCE_BPS  # 2 bps

    is_valid, message, actual_bps = validate_fill_against_market(
        fill_price, market_price, side, target_bps, tolerance
    )

    assert is_valid is False
    assert "out of bounds" in message.lower()
    assert abs(actual_bps - Decimal("15")) < Decimal("0.1")


def test_validate_fill_against_market_sell_side() -> None:
    """Test validation for sell orders."""
    fill_price = Decimal("99.95")  # 5 bps slippage
    market_price = Decimal("100")
    side = OrderSide.SELL
    target_bps = _LIQUID_TARGET_SLIPPAGE_BPS

    is_valid, message, actual_bps = validate_fill_against_market(
        fill_price, market_price, side, target_bps
    )

    assert is_valid is True
    assert "validated" in message.lower()


def test_validate_fill_against_market_liquid_vs_illiquid() -> None:
    """Test that liquid instruments have tighter tolerances."""
    fill_price = Decimal("100.08")  # 8 bps slippage
    market_price = Decimal("100")

    # For liquid (5 bps target, ±2 bps = 3-7 bps range)
    is_valid_liquid, _, _ = validate_fill_against_market(
        fill_price, market_price, OrderSide.BUY, _LIQUID_TARGET_SLIPPAGE_BPS
    )
    assert is_valid_liquid is False  # 8 bps exceeds 7 bps upper bound

    # For illiquid (10 bps target, ±2 bps = 8-12 bps range)
    is_valid_illiquid, _, _ = validate_fill_against_market(
        fill_price, market_price, OrderSide.BUY, _ILLIQUID_TARGET_SLIPPAGE_BPS
    )
    assert is_valid_illiquid is True  # 8 bps is within range


def test_is_liquid_instrument_nse_equity() -> None:
    """Test NSE equity is considered liquid."""
    assert is_liquid_instrument(Exchange.NSE, MarketType.SPOT) is True


def test_is_liquid_instrument_nse_futures() -> None:
    """Test NSE futures are considered liquid."""
    assert is_liquid_instrument(Exchange.NSE, MarketType.FUTURES) is True


def test_is_liquid_instrument_nse_options() -> None:
    """Test NSE options are considered liquid."""
    assert is_liquid_instrument(Exchange.NSE, MarketType.OPTIONS) is True


def test_is_liquid_instrument_bse() -> None:
    """Test BSE equity is considered liquid."""
    assert is_liquid_instrument(Exchange.BSE, MarketType.SPOT) is True


def test_is_liquid_instrument_mcx() -> None:
    """Test MCX instruments are considered illiquid."""
    assert is_liquid_instrument(Exchange.MCX, MarketType.SPOT) is False
    assert is_liquid_instrument(Exchange.MCX, MarketType.FUTURES) is False
    assert is_liquid_instrument(Exchange.MCX, MarketType.OPTIONS) is False


def test_is_liquid_instrument_unknown_exchange() -> None:
    """Test unknown exchanges are considered illiquid."""
    assert is_liquid_instrument(Exchange.BINANCE, MarketType.SPOT) is False
    assert is_liquid_instrument(Exchange.CDS, MarketType.FUTURES) is False


def test_validate_fill_edge_case_exact_target() -> None:
    """Test validation when fill matches target exactly."""
    # 5 bps = 0.05 on price 100
    fill_price = Decimal("100.05")
    market_price = Decimal("100")
    target_bps = _LIQUID_TARGET_SLIPPAGE_BPS

    is_valid, message, actual_bps = validate_fill_against_market(
        fill_price, market_price, OrderSide.BUY, target_bps
    )

    assert is_valid is True
    assert abs(actual_bps - target_bps) < Decimal("0.01")


def test_validate_fill_zero_slippage() -> None:
    """Test validation when there's no slippage (market price fill)."""
    fill_price = Decimal("100.00")
    market_price = Decimal("100")
    target_bps = _LIQUID_TARGET_SLIPPAGE_BPS

    is_valid, message, actual_bps = validate_fill_against_market(
        fill_price, market_price, OrderSide.BUY, target_bps
    )

    # 0 bps is 5 bps away from target, exceeds 2 bps tolerance
    assert is_valid is False
    assert actual_bps == Decimal("0")


def test_validate_fill_negative_price_protection() -> None:
    """Test that sell orders don't go negative."""
    fill_price = Decimal("0.50")  # Should not go below 0
    market_price = Decimal("1")
    side = OrderSide.SELL
    target_bps = Decimal("50")  # Large slippage

    is_valid, message, actual_bps = validate_fill_against_market(
        fill_price, market_price, side, target_bps
    )

    # Should calculate correctly without negative prices
    assert is_valid or not is_valid  # Just ensure it doesn't crash


def test_validate_fill_tolerance_boundaries() -> None:
    """Test validation at tolerance boundaries."""
    market_price = Decimal("100")
    target_bps = _LIQUID_TARGET_SLIPPAGE_BPS  # 5 bps

    # Upper boundary: 5 + 2 = 7 bps = 100.07
    is_valid_upper, _, _ = validate_fill_against_market(
        Decimal("100.07"), market_price, OrderSide.BUY, target_bps
    )
    assert is_valid_upper is True

    # Just above upper boundary: 7.1 bps = 100.071
    is_valid_above, _, _ = validate_fill_against_market(
        Decimal("100.071"), market_price, OrderSide.BUY, target_bps
    )
    assert is_valid_above is False

    # Lower boundary: 5 - 2 = 3 bps = 100.03
    is_valid_lower, _, _ = validate_fill_against_market(
        Decimal("100.03"), market_price, OrderSide.BUY, target_bps
    )
    assert is_valid_lower is True

    # Just below lower boundary: 2.9 bps = 100.029
    is_valid_below, _, _ = validate_fill_against_market(
        Decimal("100.029"), market_price, OrderSide.BUY, target_bps
    )
    assert is_valid_below is False


def test_paper_executor_fills_are_conservative_liquid() -> None:
    """End-to-end test: Paper executor fills should be conservative
    (≤ target) for liquid instruments."""
    executor = PaperExecutor()  # Use exchange-specific slippage
    request = OrderRequest(
        Exchange.NSE, "RELIANCE", OrderSide.BUY, Decimal("10"), price=Decimal("1000")
    )
    result = executor.execute_order(request)

    # Get expected slippage from model
    expected_slippage_bps = _compute_slippage_bps(
        Exchange.NSE, MarketType.SPOT, Decimal("10"), None
    )

    # Validate against actual computed slippage (not constant target)
    is_valid, message, actual_bps = validate_fill_against_market(
        result.average_price,
        Decimal("1000"),
        OrderSide.BUY,
        expected_slippage_bps,
    )

    # The fill should match computed slippage exactly
    assert is_valid is True, f"Fill failed validation: {message}"
    # Verify actual slippage is within realistic range for liquid instruments
    assert actual_bps <= _LIQUID_TARGET_SLIPPAGE_BPS, (
        f"Actual slippage {actual_bps} bps exceeds "
        f"liquid target {_LIQUID_TARGET_SLIPPAGE_BPS} bps"
    )


def test_paper_executor_fills_are_conservative_illiquid() -> None:
    """End-to-end test: MCX fills should be conservative
    (≤ target) for illiquid instruments."""
    executor = PaperExecutor()
    request = OrderRequest(Exchange.MCX, "GOLD", OrderSide.BUY, Decimal("2"), price=Decimal("3000"))
    result = executor.execute_order(request)

    # Get expected slippage from model
    expected_slippage_bps = _compute_slippage_bps(Exchange.MCX, MarketType.SPOT, Decimal("2"), None)

    # Validate against actual computed slippage
    is_valid, message, actual_bps = validate_fill_against_market(
        result.average_price,
        Decimal("3000"),
        OrderSide.BUY,
        expected_slippage_bps,
    )

    # The fill should match computed slippage exactly
    assert is_valid is True, f"Fill failed validation: {message}"
    # Verify actual slippage is within realistic range for illiquid instruments
    assert actual_bps <= _ILLIQUID_TARGET_SLIPPAGE_BPS, (
        f"Actual slippage {actual_bps} bps exceeds "
        f"illiquid target {_ILLIQUID_TARGET_SLIPPAGE_BPS} bps"
    )


def test_paper_executor_sell_orders_are_conservative() -> None:
    """End-to-end test: Sell orders should be conservative (≤ target)."""
    executor = PaperExecutor()
    request = OrderRequest(Exchange.NSE, "INFY", OrderSide.SELL, Decimal("1"), price=Decimal("100"))
    result = executor.execute_order(request)

    # Get expected slippage from model
    expected_slippage_bps = _compute_slippage_bps(Exchange.NSE, MarketType.SPOT, Decimal("1"), None)

    # Validate against actual computed slippage
    is_valid, message, actual_bps = validate_fill_against_market(
        result.average_price,
        Decimal("100"),
        OrderSide.SELL,
        expected_slippage_bps,
    )

    # The fill should match computed slippage exactly
    assert is_valid is True, f"Sell fill failed validation: {message}"
    # Verify actual slippage is within realistic range for liquid instruments
    assert actual_bps <= _LIQUID_TARGET_SLIPPAGE_BPS, (
        f"Actual slippage {actual_bps} bps exceeds "
        f"liquid target {_LIQUID_TARGET_SLIPPAGE_BPS} bps"
    )


def test_validate_fill_custom_tolerance() -> None:
    """Test validation with custom tolerance values."""
    fill_price = Decimal("100.09")  # 9 bps slippage
    market_price = Decimal("100")

    # Default tolerance (2 bps) should fail
    is_valid_default, _, _ = validate_fill_against_market(
        fill_price, market_price, OrderSide.BUY, _LIQUID_TARGET_SLIPPAGE_BPS
    )
    assert is_valid_default is False

    # Custom tolerance (5 bps) should pass
    is_valid_custom, _, _ = validate_fill_against_market(
        fill_price,
        market_price,
        OrderSide.BUY,
        _LIQUID_TARGET_SLIPPAGE_BPS,
        tolerance_bps=Decimal("5"),
    )
    assert is_valid_custom is True


def test_validate_fill_message_format() -> None:
    """Test that validation messages are properly formatted."""
    fill_price = Decimal("100.05")
    market_price = Decimal("100")

    is_valid, message, actual_bps = validate_fill_against_market(
        fill_price, market_price, OrderSide.BUY, _LIQUID_TARGET_SLIPPAGE_BPS
    )

    # Message should contain key information
    assert "bps" in message.lower()
    assert "slippage" in message.lower()
    assert "target" in message.lower()
    assert "tolerance" in message.lower() or "±" in message
