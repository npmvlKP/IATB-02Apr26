"""
Volume profile calculations (POC/VAH/VAL).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class VolumeProfile:
    poc: Decimal
    vah: Decimal
    val: Decimal
    total_volume: Decimal


def build_volume_profile(
    prices: Sequence[Decimal],
    volumes: Sequence[Decimal],
    *,
    value_area: Decimal = Decimal("0.70"),
) -> VolumeProfile:
    """Build volume profile using price-level aggregation."""
    if not prices or not volumes:
        msg = "prices and volumes cannot be empty"
        raise ConfigError(msg)
    if len(prices) != len(volumes):
        msg = "prices and volumes must have equal length"
        raise ConfigError(msg)
    if value_area <= Decimal("0") or value_area >= Decimal("1"):
        msg = "value_area must be between 0 and 1"
        raise ConfigError(msg)

    volume_by_price = _aggregate_volume_by_price(prices, volumes)
    sorted_by_volume = sorted(volume_by_price.items(), key=lambda item: item[1], reverse=True)
    poc = sorted_by_volume[0][0]
    total_volume = sum(volume_by_price.values(), Decimal("0"))
    selected_prices = _build_value_area(sorted_by_volume, total_volume, value_area)
    return VolumeProfile(
        poc=poc,
        vah=max(selected_prices),
        val=min(selected_prices),
        total_volume=total_volume,
    )


def _aggregate_volume_by_price(
    prices: Sequence[Decimal],
    volumes: Sequence[Decimal],
) -> dict[Decimal, Decimal]:
    aggregated: dict[Decimal, Decimal] = {}
    for price, volume in zip(prices, volumes, strict=True):
        if volume < Decimal("0"):
            msg = "volumes cannot include negative values"
            raise ConfigError(msg)
        aggregated[price] = aggregated.get(price, Decimal("0")) + volume
    return aggregated


def _build_value_area(
    sorted_by_volume: Sequence[tuple[Decimal, Decimal]],
    total_volume: Decimal,
    value_area: Decimal,
) -> set[Decimal]:
    target_volume = total_volume * value_area
    selected_prices: set[Decimal] = set()
    cumulative = Decimal("0")
    for price, volume in sorted_by_volume:
        selected_prices.add(price)
        cumulative += volume
        if cumulative >= target_volume:
            break
    return selected_prices
