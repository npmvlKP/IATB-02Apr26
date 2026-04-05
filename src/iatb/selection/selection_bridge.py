"""
Bridge between selection output and strategy input.

Converts SelectionResult into ready-to-use StrategyContext objects,
closing the gap between instrument ranking and strategy execution.
"""

import logging
from collections.abc import Sequence
from decimal import Decimal

from iatb.core.enums import OrderSide
from iatb.core.exceptions import ConfigError
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.selection.ranking import RankedInstrument, SelectionResult
from iatb.strategies.base import StrategyContext

logger = logging.getLogger(__name__)


def build_strategy_contexts(
    selection: SelectionResult,
    strength_by_symbol: dict[str, StrengthInputs],
    side: OrderSide = OrderSide.BUY,
) -> list[StrategyContext]:
    """Convert ranked instruments into StrategyContext objects.

    Requires a mapping of symbol → StrengthInputs so each context
    carries the tradability data the strategy layer needs.
    """
    if not selection.selected:
        return []
    contexts: list[StrategyContext] = []
    for ranked in selection.selected:
        inputs = _resolve_strength(ranked, strength_by_symbol)
        contexts.append(
            StrategyContext(
                exchange=ranked.exchange,
                symbol=ranked.symbol,
                side=side,
                strength_inputs=inputs,
                composite_score=ranked.composite_score,
                selection_rank=ranked.rank,
            ),
        )
    logger.info(
        "Built %d strategy contexts from selection (side=%s)",
        len(contexts),
        side.value,
    )
    return contexts


def _resolve_strength(
    ranked: RankedInstrument,
    strength_map: dict[str, StrengthInputs],
) -> StrengthInputs:
    inputs = strength_map.get(ranked.symbol)
    if inputs is None:
        msg = f"no StrengthInputs for selected symbol: {ranked.symbol}"
        raise ConfigError(msg)
    return inputs


def extract_strength_map(
    signals_list: Sequence[object],
) -> dict[str, StrengthInputs]:
    """Build symbol → StrengthInputs from InstrumentSignals list.

    Accepts list[InstrumentSignals] typed as object to avoid circular import.
    Raises ConfigError if any signal lacks strength_inputs.
    """
    result: dict[str, StrengthInputs] = {}
    for sig in signals_list:
        symbol = getattr(sig, "symbol", None)
        inputs = getattr(sig, "strength_inputs", None)
        if symbol is None or not isinstance(symbol, str):
            msg = "signal missing symbol attribute"
            raise ConfigError(msg)
        if inputs is None or not isinstance(inputs, StrengthInputs):
            msg = f"no strength_inputs on InstrumentSignals for {symbol}"
            raise ConfigError(msg)
        result[symbol] = inputs
    return result


def scale_quantity_by_rank(
    base_quantity: Decimal,
    rank: int,
    total_selected: int,
) -> Decimal:
    """Scale position size inversely with rank.

    Rank 1 gets full base_quantity, lower ranks get proportionally less.
    """
    if total_selected <= 0:
        msg = "total_selected must be positive"
        raise ConfigError(msg)
    if rank < 1 or rank > total_selected:
        msg = f"rank {rank} out of range [1, {total_selected}]"
        raise ConfigError(msg)
    if base_quantity <= Decimal("0"):
        msg = "base_quantity must be positive"
        raise ConfigError(msg)
    weight = Decimal(total_selected - rank + 1) / Decimal(total_selected)
    return base_quantity * weight
