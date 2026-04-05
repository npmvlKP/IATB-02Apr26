"""
Pre-trade order validation with five risk gates.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.execution.base import OrderRequest


@dataclass(frozen=True)
class PreTradeConfig:
    max_order_quantity: Decimal
    max_order_value: Decimal
    max_price_deviation_pct: Decimal
    max_position_per_symbol: Decimal
    max_portfolio_exposure: Decimal

    def __post_init__(self) -> None:
        for name, value in [
            ("max_order_quantity", self.max_order_quantity),
            ("max_order_value", self.max_order_value),
            ("max_position_per_symbol", self.max_position_per_symbol),
            ("max_portfolio_exposure", self.max_portfolio_exposure),
        ]:
            if value <= Decimal("0"):
                msg = f"{name} must be positive"
                raise ConfigError(msg)
        if self.max_price_deviation_pct <= Decimal("0"):
            msg = "max_price_deviation_pct must be positive"
            raise ConfigError(msg)


def validate_order(
    request: OrderRequest,
    config: PreTradeConfig,
    last_prices: dict[str, Decimal],
    current_positions: dict[str, Decimal],
    total_exposure: Decimal,
) -> OrderRequest:
    """Validate order against all pre-trade gates. Raises on failure."""
    price = _resolve_price(request, last_prices)
    _check_quantity(request, config)
    _check_notional(request, price, config)
    _check_price_deviation(request, price, last_prices, config)
    _check_position_limit(request, current_positions, config)
    _check_exposure(request, price, total_exposure, config)
    return request


def _resolve_price(request: OrderRequest, last_prices: dict[str, Decimal]) -> Decimal:
    if request.price is not None:
        return request.price
    last = last_prices.get(request.symbol)
    if last is None or last <= Decimal("0"):
        msg = f"no valid last price for {request.symbol}"
        raise ConfigError(msg)
    return last


def _check_quantity(request: OrderRequest, config: PreTradeConfig) -> None:
    if request.quantity > config.max_order_quantity:
        msg = f"fat-finger: quantity {request.quantity} exceeds max {config.max_order_quantity}"
        raise ConfigError(msg)


def _check_notional(request: OrderRequest, price: Decimal, config: PreTradeConfig) -> None:
    notional = request.quantity * price
    if notional > config.max_order_value:
        msg = f"notional {notional} exceeds max {config.max_order_value}"
        raise ConfigError(msg)


def _check_price_deviation(
    request: OrderRequest,
    price: Decimal,
    last_prices: dict[str, Decimal],
    config: PreTradeConfig,
) -> None:
    last = last_prices.get(request.symbol)
    if last is None or last <= Decimal("0"):
        return
    deviation = abs(price - last) / last
    if deviation > config.max_price_deviation_pct:
        msg = f"price deviation {deviation:.4f} exceeds max {config.max_price_deviation_pct}"
        raise ConfigError(msg)


def _check_position_limit(
    request: OrderRequest,
    current_positions: dict[str, Decimal],
    config: PreTradeConfig,
) -> None:
    current = abs(current_positions.get(request.symbol, Decimal("0")))
    projected = current + request.quantity
    if projected > config.max_position_per_symbol:
        msg = f"position {projected} exceeds max {config.max_position_per_symbol}"
        raise ConfigError(msg)


def _check_exposure(
    request: OrderRequest,
    price: Decimal,
    total_exposure: Decimal,
    config: PreTradeConfig,
) -> None:
    order_notional = request.quantity * price
    projected = total_exposure + order_notional
    if projected > config.max_portfolio_exposure:
        msg = f"exposure {projected} exceeds max {config.max_portfolio_exposure}"
        raise ConfigError(msg)
