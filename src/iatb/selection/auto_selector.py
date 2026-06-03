"""
auto_selector.py – Integrated Auto-Selection Pipeline
======================================================

Combines sentiment, volume-profile, RAG market strength, and DRL signals
to automatically select:
  - Option strike price (CE/PE) via StrikeSelector
  - Lot size via confidence-weighted position sizing
  - Adaptive trailing stop offset via TrailingStopStrategy

This module closes the gap between the four signal sources
(InstrumentScorer) and the execution layer (StrikeSelector,
position sizing, trailing stop) to produce a single
AutoSelectionResult ready for order placement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from iatb.core.enums import Exchange, OrderSide
from iatb.core.exceptions import ConfigError
from iatb.execution.strike_selector import (
    ATMSelector,
    LiquidityFilteredSelector,
    MoneynessPctSelector,
    OTMByStrikesSelector,
    StrikeSelector,
)
from iatb.market_strength.regime_detector import MarketRegime
from iatb.risk.trailing_stop import (
    RegimeAdaptiveTrailingStop,
    TrailingStopStrategy,
)
from iatb.selection.composite_score import RegimeWeights
from iatb.selection.instrument_scorer import (
    FilterConfig,
    InstrumentScorer,
    InstrumentSignals,
)
from iatb.selection.ranking import RankingConfig, SelectionResult

if TYPE_CHECKING:
    from iatb.data.instrument import Instrument

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Default configuration constants
# ------------------------------------------------------------------ #
_DEFAULT_MIN_LOTS = 1
_DEFAULT_MAX_LOTS = 10
_DEFAULT_BASE_TRAIL_FRACTION = Decimal("0.02")
_DEFAULT_MIN_TRAIL_FRACTION = Decimal("0.005")
_DEFAULT_MAX_TRAIL_FRACTION = Decimal("0.05")
_DEFAULT_STRIKE_SELECTOR_MODE = "regime_adaptive"
_DEFAULT_MIN_CONFIDENCE = Decimal("0.30")
_ZERO: Decimal = Decimal("0")
_ONE: Decimal = Decimal("1")


# ------------------------------------------------------------------ #
# Data classes
# ------------------------------------------------------------------ #
@dataclass(frozen=True)
class AutoSelectionResult:
    """Complete auto-selection output for a single instrument."""

    symbol: str
    exchange: Exchange
    option_type: str  # "CE" | "PE"
    strike_price: Decimal
    lots: int
    trail_offset_points: Decimal
    trail_strategy_name: str
    composite_score: Decimal
    confidence: Decimal
    regime: MarketRegime
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AutoSelectorConfig:
    """Configuration for the AutoSelector pipeline."""

    base_lots: int = _DEFAULT_MIN_LOTS
    max_lots: int = _DEFAULT_MAX_LOTS
    min_confidence: Decimal = _DEFAULT_MIN_CONFIDENCE
    base_trail_fraction: Decimal = _DEFAULT_BASE_TRAIL_FRACTION
    min_trail_fraction: Decimal = _DEFAULT_MIN_TRAIL_FRACTION
    max_trail_fraction: Decimal = _DEFAULT_MAX_TRAIL_FRACTION
    strike_selector_mode: str = _DEFAULT_STRIKE_SELECTOR_MODE
    ranking_config: RankingConfig | None = None
    custom_weights: dict[MarketRegime, RegimeWeights] | None = None
    filter_config: FilterConfig | None = None

    def __post_init__(self) -> None:
        if self.base_lots < 1:
            msg = "base_lots must be at least 1"
            raise ConfigError(msg)
        if self.max_lots < self.base_lots:
            msg = "max_lots must be >= base_lots"
            raise ConfigError(msg)
        if not (Decimal("0") <= self.min_confidence <= Decimal("1")):
            msg = "min_confidence must be in [0, 1]"
            raise ConfigError(msg)
        if self.base_trail_fraction <= Decimal("0"):
            msg = "base_trail_fraction must be positive"
            raise ConfigError(msg)
        if self.min_trail_fraction <= Decimal("0"):
            msg = "min_trail_fraction must be positive"
            raise ConfigError(msg)
        if self.max_trail_fraction < self.min_trail_fraction:
            msg = "max_trail_fraction must be >= min_trail_fraction"
            raise ConfigError(msg)
        valid_modes = {
            "atm",
            "otm_1",
            "otm_2",
            "otm_3",
            "moneyness_2pct",
            "moneyness_5pct",
            "regime_adaptive",
        }
        if self.strike_selector_mode not in valid_modes:
            msg = (
                f"strike_selector_mode must be one of {valid_modes}, "
                f"got '{self.strike_selector_mode}'"
            )
            raise ConfigError(msg)


# ------------------------------------------------------------------ #
# Main auto-selector class
# ------------------------------------------------------------------ #
class AutoSelector:
    """Integrated auto-selection pipeline.

    Combines the four signal sources (sentiment, volume-profile,
    RAG market strength, DRL) through InstrumentScorer, then
    feeds the scored instruments into strike selection, lot sizing,
    and adaptive trailing stop computation.
    """

    def __init__(
        self,
        config: AutoSelectorConfig | None = None,
        trailing_stop_strategy: TrailingStopStrategy | None = None,
    ) -> None:
        self._config = config or AutoSelectorConfig()
        self._scorer = InstrumentScorer(
            ranking_config=self._config.ranking_config,
            custom_weights=self._config.custom_weights,
            filter_config=self._config.filter_config,
            load_from_config=True,
        )
        self._trailing_stop = trailing_stop_strategy or RegimeAdaptiveTrailingStop()
        self._strike_selector = self._build_strike_selector(
            self._config.strike_selector_mode
        )

    @property
    def config(self) -> AutoSelectorConfig:
        """Return the active configuration."""
        return self._config

    def score_and_select(
        self,
        instrument_signals: list[InstrumentSignals],
        regime: MarketRegime,
        correlations: dict[tuple[str, str], Decimal] | None = None,
    ) -> SelectionResult:
        """Score instruments and select top-N via InstrumentScorer."""
        return self._scorer.score_and_select(instrument_signals, regime, correlations)

    def auto_select(
        self,
        instrument_signals: list[InstrumentSignals],
        regime: MarketRegime,
        option_chain: list[Instrument],
        underlying_price: Decimal,
        side: OrderSide = OrderSide.BUY,
        current_atr: Decimal | None = None,
        correlations: dict[tuple[str, str], Decimal] | None = None,
    ) -> list[AutoSelectionResult]:
        """Full pipeline: score → select → strike → lots → trail.

        Args:
            instrument_signals: Pre-computed signals per instrument.
            regime: Current market regime.
            option_chain: Available option instruments.
            underlying_price: Current underlying price.
            side: BUY or SELL.
            current_atr: Current ATR for trailing stop.
                Falls back to 2% of underlying price if None.
            correlations: Pairwise instrument correlations.

        Returns:
            List of AutoSelectionResult for each selected instrument.

        Raises:
            ConfigError: If inputs are invalid.
        """
        _validate_auto_select_inputs(instrument_signals, option_chain, underlying_price)
        atr = current_atr or underlying_price * Decimal("0.02")

        selection = self.score_and_select(instrument_signals, regime, correlations)

        results: list[AutoSelectionResult] = []
        for ranked in selection.selected:
            result = self._build_auto_result(
                ranked=ranked,
                regime=regime,
                option_chain=option_chain,
                underlying_price=underlying_price,
                side=side,
                atr=atr,
                total_selected=len(selection.selected),
            )
            if result is not None:
                results.append(result)

        logger.info(
            "Auto-selected %d instruments from %d candidates",
            len(results),
            selection.total_candidates,
        )
        return results

    def _build_auto_result(
        self,
        ranked: object,
        regime: MarketRegime,
        option_chain: list[Instrument],
        underlying_price: Decimal,
        side: OrderSide,
        atr: Decimal,
        total_selected: int,
    ) -> AutoSelectionResult | None:
        """Build an AutoSelectionResult from a ranked instrument."""
        symbol = getattr(ranked, "symbol", "")
        exchange = getattr(ranked, "exchange", Exchange.NSE)
        composite_score = getattr(ranked, "composite_score", Decimal("0"))
        rank = getattr(ranked, "rank", 1)
        metadata = getattr(ranked, "metadata", {})

        confidence = _extract_confidence(metadata)
        if confidence < self._config.min_confidence:
            logger.info(
                "Skipping %s: confidence %s below minimum %s",
                symbol,
                confidence,
                self._config.min_confidence,
            )
            return None

        option_type = _determine_option_type(regime, side)
        filtered_chain = _filter_chain_by_type(option_chain, option_type)
        if not filtered_chain:
            logger.warning("No %s options in chain for %s", option_type, symbol)
            return None

        selected_instrument = self._strike_selector.select(
            filtered_chain, underlying_price, side
        )

        lots = _compute_lots(
            base_lots=self._config.base_lots,
            max_lots=self._config.max_lots,
            confidence=confidence,
            rank=rank,
            total_selected=total_selected,
        )

        trail_offset = _compute_adaptive_trail_offset(
            base_trail_fraction=self._config.base_trail_fraction,
            min_trail_fraction=self._config.min_trail_fraction,
            max_trail_fraction=self._config.max_trail_fraction,
            confidence=confidence,
            regime=regime,
            underlying_price=underlying_price,
            atr=atr,
        )

        trail_strategy_name = type(self._trailing_stop).__name__

        strike_price = selected_instrument.strike or underlying_price

        reasons = _build_reasons(
            regime=regime,
            option_type=option_type,
            confidence=confidence,
            composite_score=composite_score,
            trail_offset=trail_offset,
            lots=lots,
            metadata=metadata,
        )

        return AutoSelectionResult(
            symbol=symbol,
            exchange=exchange,
            option_type=option_type,
            strike_price=strike_price,
            lots=lots,
            trail_offset_points=trail_offset,
            trail_strategy_name=trail_strategy_name,
            composite_score=composite_score,
            confidence=confidence,
            regime=regime,
            reasons=reasons,
        )

    def _build_strike_selector(self, mode: str) -> StrikeSelector:
        """Build the appropriate StrikeSelector based on mode."""
        if mode == "atm":
            return ATMSelector()
        if mode == "otm_1":
            return LiquidityFilteredSelector(OTMByStrikesSelector(1))
        if mode == "otm_2":
            return LiquidityFilteredSelector(OTMByStrikesSelector(2))
        if mode == "otm_3":
            return LiquidityFilteredSelector(OTMByStrikesSelector(3))
        if mode == "moneyness_2pct":
            return LiquidityFilteredSelector(MoneynessPctSelector(Decimal("0.02")))
        if mode == "moneyness_5pct":
            return LiquidityFilteredSelector(MoneynessPctSelector(Decimal("0.05")))
        # regime_adaptive: ATM in sideways, OTM-1 in bull, OTM-2 in bear
        return LiquidityFilteredSelector(ATMSelector())


def select_strike_by_regime(
    regime: MarketRegime,
    option_chain: list[Instrument],
    underlying_price: Decimal,
    side: OrderSide,
) -> Instrument:
    """Select strike price adapting to market regime.

    - BULL: ATM (tightest stop, highest confidence)
    - BEAR: OTM-2 (more room, defensive)
    - SIDEWAYS: OTM-1 (moderate room)

    Args:
        regime: Current market regime.
        option_chain: Available option instruments.
        underlying_price: Current underlying price.
        side: BUY or SELL.

    Returns:
        Selected Instrument from the option chain.
    """
    if not option_chain:
        msg = "option_chain cannot be empty"
        raise ConfigError(msg)
    if underlying_price <= Decimal("0"):
        msg = "underlying_price must be positive"
        raise ConfigError(msg)

    if regime == MarketRegime.BULL:
        selector: StrikeSelector = LiquidityFilteredSelector(ATMSelector())
    elif regime == MarketRegime.BEAR:
        selector = LiquidityFilteredSelector(OTMByStrikesSelector(2))
    else:
        selector = LiquidityFilteredSelector(OTMByStrikesSelector(1))
    return selector.select(option_chain, underlying_price, side)


# ------------------------------------------------------------------ #
# Helper functions (module-private)
# ------------------------------------------------------------------ #
def _validate_auto_select_inputs(
    instrument_signals: list[InstrumentSignals],
    option_chain: list[Instrument],
    underlying_price: Decimal,
) -> None:
    """Validate inputs for auto_select."""
    if not instrument_signals:
        msg = "instrument_signals cannot be empty"
        raise ConfigError(msg)
    if not option_chain:
        msg = "option_chain cannot be empty"
        raise ConfigError(msg)
    if underlying_price <= Decimal("0"):
        msg = "underlying_price must be positive"
        raise ConfigError(msg)


def _determine_option_type(regime: MarketRegime, side: OrderSide) -> str:
    """Determine CE or PE based on regime and order side."""
    if side == OrderSide.BUY:
        return "CE" if regime in (MarketRegime.BULL, MarketRegime.SIDEWAYS) else "PE"
    # SELL side: PE in bull/sideways (bearish), CE in bear (bullish reversal)
    return "PE" if regime in (MarketRegime.BULL, MarketRegime.SIDEWAYS) else "CE"


def _filter_chain_by_type(
    option_chain: list[Instrument], option_type: str
) -> list[Instrument]:
    """Filter option chain to only CE or PE instruments."""
    from iatb.data.instrument import InstrumentType

    target = (
        InstrumentType.OPTION_CE if option_type == "CE" else InstrumentType.OPTION_PE
    )
    return [inst for inst in option_chain if inst.instrument_type == target]


def _extract_confidence(metadata: dict[str, str]) -> Decimal:
    """Extract aggregate confidence from selection metadata."""
    for key in ("contrib_sentiment", "contrib_strength", "contrib_vp", "contrib_drl"):
        if key not in metadata:
            conf_default: Decimal = Decimal("0.50")
            return conf_default  # default moderate confidence
    try:
        total: Decimal = sum(
            (
                Decimal(metadata.get(k, "0"))
                for k in (
                    "contrib_sentiment",
                    "contrib_strength",
                    "contrib_vp",
                    "contrib_drl",
                )
            ),
            start=_ZERO,
        )
        if total > Decimal("0"):  # noqa: SIM108
            clamped_val: Decimal = total
        else:
            zero_val: Decimal = _ZERO
            clamped_val = zero_val
        if clamped_val < Decimal("1"):  # noqa: SIM108
            retval: Decimal = clamped_val
            return retval
        one_val: Decimal = _ONE
        return one_val
    except Exception:
        err_default: Decimal = Decimal("0.50")
        return err_default


def _compute_lots(
    base_lots: int,
    max_lots: int,
    confidence: Decimal,
    rank: int,
    total_selected: int,
) -> int:
    """Compute lot size based on confidence and rank.

    Higher confidence and better rank → more lots.
    """
    if total_selected <= 0:
        return base_lots
    rank_weight = Decimal(total_selected - rank + 1) / Decimal(total_selected)
    scaled = Decimal(base_lots) * confidence * rank_weight
    lots = max(base_lots, min(max_lots, int(scaled)))
    return lots


def _compute_adaptive_trail_offset(
    base_trail_fraction: Decimal,
    min_trail_fraction: Decimal,
    max_trail_fraction: Decimal,
    confidence: Decimal,
    regime: MarketRegime,
    underlying_price: Decimal,
    atr: Decimal,
) -> Decimal:
    """Compute adaptive trailing stop offset in points.

    Higher confidence → tighter trail (lower fraction).
    Bear regime → wider trail (higher fraction).
    """
    if confidence >= Decimal("0.80"):
        fraction = min_trail_fraction
    elif confidence >= Decimal("0.60"):
        fraction = base_trail_fraction
    else:
        fraction = max_trail_fraction

    # Widen in bear regime
    if regime == MarketRegime.BEAR:
        fraction = min(max_trail_fraction, fraction * Decimal("1.5"))

    # Narrow in bull regime
    if regime == MarketRegime.BULL:
        fraction = max(min_trail_fraction, fraction * Decimal("0.75"))

    # Use ATR-based offset if available
    atr_offset = atr * Decimal("2.0")
    price_offset = underlying_price * fraction
    # Take the larger of the two for safety
    return max(atr_offset, price_offset)


def _build_reasons(
    regime: MarketRegime,
    option_type: str,
    confidence: Decimal,
    composite_score: Decimal,
    trail_offset: Decimal,
    lots: int,
    metadata: dict[str, str],
) -> list[str]:
    """Build human-readable reasons for the selection."""
    reasons: list[str] = [
        f"regime={regime.value}",
        f"option_type={option_type}",
        f"confidence={confidence:.4f}",
        f"composite_score={composite_score:.4f}",
        f"trail_offset={trail_offset:.2f}",
        f"lots={lots}",
    ]
    for key in ("contrib_sentiment", "contrib_strength", "contrib_vp", "contrib_drl"):
        val = metadata.get(key, "N/A")
        reasons.append(f"{key}={val}")
    return reasons
