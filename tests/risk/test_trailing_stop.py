"""Tests for adaptive trailing stop strategies."""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from iatb.core.enums import OrderSide
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.risk.trailing_stop import (
    ATRTrailingStop,
    ChandelierExit,
    FixedFractionTrailingStop,
    PositionState,
    RegimeAdaptiveTrailingStop,
    TimeDecayTrailingStop,
)


def _state(
    side: OrderSide = OrderSide.BUY,
    price: str = "100",
    atr: str = "5",
    regime: MarketRegime = MarketRegime.BULL,
    bars: int = 10,
) -> PositionState:
    p = Decimal(price)
    return PositionState(
        entry_price=p,
        current_price=p,
        highest_since_entry=p + Decimal("10"),
        lowest_since_entry=p - Decimal("5"),
        side=side,
        current_atr=Decimal(atr),
        current_regime=regime,
        bars_held=bars,
    )


class TestATRTrailingStop:
    def test_buy_stop_below_highest(self) -> None:
        ts = ATRTrailingStop(atr_multiplier=Decimal("2.0"))
        state = _state(side=OrderSide.BUY)
        stop = ts.compute_stop(state)
        assert stop < state.highest_since_entry

    def test_sell_stop_above_lowest(self) -> None:
        ts = ATRTrailingStop(atr_multiplier=Decimal("2.0"))
        state = _state(side=OrderSide.SELL)
        stop = ts.compute_stop(state)
        assert stop > state.lowest_since_entry

    def test_ratchet_buy_never_decreases(self) -> None:
        ts = ATRTrailingStop(atr_multiplier=Decimal("2.0"))
        s1 = _state(side=OrderSide.BUY, price="100")
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.BUY, price="105")
        stop2 = ts.compute_stop(s2)
        assert stop2 >= stop1

    def test_invalid_multiplier(self) -> None:
        with pytest.raises(ConfigError):
            ATRTrailingStop(atr_multiplier=Decimal("0"))


class TestRegimeAdaptiveTrailingStop:
    @pytest.mark.parametrize("regime", list(MarketRegime))
    def test_all_regimes_produce_positive_stop(self, regime: MarketRegime) -> None:
        ts = RegimeAdaptiveTrailingStop()
        state = _state(regime=regime)
        stop = ts.compute_stop(state)
        assert stop > Decimal("0")

    def test_bear_tighter_than_sideways(self) -> None:
        bear_ts = RegimeAdaptiveTrailingStop()
        side_ts = RegimeAdaptiveTrailingStop()
        bear_stop = bear_ts.compute_stop(_state(regime=MarketRegime.BEAR))
        side_stop = side_ts.compute_stop(_state(regime=MarketRegime.SIDEWAYS))
        # Bear uses 1.5x (tighter), sideways uses 3.0x (wider)
        assert bear_stop > side_stop


class TestChandelierExit:
    def test_buy_chandelier(self) -> None:
        ce = ChandelierExit(atr_multiplier=Decimal("3.0"))
        state = _state(side=OrderSide.BUY)
        stop = ce.compute_stop(state)
        assert stop == state.highest_since_entry - Decimal("3.0") * state.current_atr

    def test_sell_chandelier(self) -> None:
        ce = ChandelierExit(atr_multiplier=Decimal("3.0"))
        state = _state(side=OrderSide.SELL)
        stop = ce.compute_stop(state)
        assert stop == state.lowest_since_entry + Decimal("3.0") * state.current_atr


class TestTimeDecayTrailingStop:
    def test_multiplier_decreases_with_bars(self) -> None:
        ts = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3.0"),
            decay_rate=Decimal("0.1"),
            min_multiplier=Decimal("1.0"),
        )
        s1 = _state(bars=0)
        s2 = _state(bars=50)
        ts2 = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3.0"),
            decay_rate=Decimal("0.1"),
            min_multiplier=Decimal("1.0"),
        )
        stop_early = ts.compute_stop(s1)
        stop_late = ts2.compute_stop(s2)
        # Later bars = tighter multiplier = higher stop for BUY
        assert stop_late >= stop_early

    def test_invalid_decay_rate(self) -> None:
        with pytest.raises(ConfigError):
            TimeDecayTrailingStop(decay_rate=Decimal("0"))


class TestFixedFractionTrailingStop:
    def test_buy_stop_below_price(self) -> None:
        ts = FixedFractionTrailingStop(trail_fraction=Decimal("0.02"))
        state = _state(side=OrderSide.BUY)
        stop = ts.compute_stop(state)
        assert stop < state.current_price

    def test_invalid_fraction(self) -> None:
        with pytest.raises(ConfigError):
            FixedFractionTrailingStop(trail_fraction=Decimal("1.0"))


class TestATRTrailingStopSellSide:
    def test_sell_ratchet_never_increases(self) -> None:
        ts = ATRTrailingStop(atr_multiplier=Decimal("2.0"))
        s1 = _state(side=OrderSide.SELL, price="100")
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.SELL, price="95")
        stop2 = ts.compute_stop(s2)
        assert stop2 <= stop1

    def test_reset_clears_ratchet(self) -> None:
        ts = ATRTrailingStop(atr_multiplier=Decimal("2.0"))
        ts.compute_stop(_state(side=OrderSide.BUY))
        ts.reset()
        s = _state(side=OrderSide.BUY, price="50", atr="2")
        stop = ts.compute_stop(s)
        assert stop > Decimal("0")


class TestRegimeAdaptiveTrailingStopSellSide:
    def test_sell_side_ratchet(self) -> None:
        ts = RegimeAdaptiveTrailingStop()
        s1 = _state(side=OrderSide.SELL, regime=MarketRegime.BEAR)
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.SELL, price="90", regime=MarketRegime.BEAR)
        stop2 = ts.compute_stop(s2)
        assert stop2 <= stop1

    def test_reset_clears_state(self) -> None:
        ts = RegimeAdaptiveTrailingStop()
        ts.compute_stop(_state())
        ts.reset()
        stop = ts.compute_stop(_state(price="50", atr="1"))
        assert stop > Decimal("0")


class TestTimeDecayTrailingStopSellSide:
    def test_sell_side_computes(self) -> None:
        ts = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3.0"),
            decay_rate=Decimal("0.1"),
            min_multiplier=Decimal("1.0"),
        )
        state = _state(side=OrderSide.SELL, bars=5)
        stop = ts.compute_stop(state)
        assert stop > state.lowest_since_entry

    def test_sell_ratchet_never_increases(self) -> None:
        ts = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3.0"),
            decay_rate=Decimal("0.1"),
            min_multiplier=Decimal("1.0"),
        )
        s1 = _state(side=OrderSide.SELL, bars=5)
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.SELL, price="90", bars=10)
        stop2 = ts.compute_stop(s2)
        assert stop2 <= stop1

    def test_reset(self) -> None:
        ts = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3.0"),
            decay_rate=Decimal("0.1"),
            min_multiplier=Decimal("1.0"),
        )
        ts.compute_stop(_state())
        ts.reset()
        stop = ts.compute_stop(_state(price="200", atr="10"))
        assert stop > Decimal("0")


class TestFixedFractionTrailingStopSellSide:
    def test_sell_stop_above_price(self) -> None:
        ts = FixedFractionTrailingStop(trail_fraction=Decimal("0.02"))
        state = _state(side=OrderSide.SELL)
        stop = ts.compute_stop(state)
        assert stop > state.current_price

    def test_sell_ratchet_never_increases(self) -> None:
        ts = FixedFractionTrailingStop(trail_fraction=Decimal("0.02"))
        s1 = _state(side=OrderSide.SELL, price="100")
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.SELL, price="95")
        stop2 = ts.compute_stop(s2)
        assert stop2 <= stop1

    def test_reset(self) -> None:
        ts = FixedFractionTrailingStop(trail_fraction=Decimal("0.02"))
        ts.compute_stop(_state())
        ts.reset()
        stop = ts.compute_stop(_state(price="200"))
        assert stop > Decimal("0")


class TestPositionStateValidation:
    def test_negative_entry_price(self) -> None:
        with pytest.raises(ConfigError, match="entry_price must be positive"):
            PositionState(
                entry_price=Decimal("-1"),
                current_price=Decimal("100"),
                highest_since_entry=Decimal("110"),
                lowest_since_entry=Decimal("90"),
                side=OrderSide.BUY,
                current_atr=Decimal("5"),
                current_regime=MarketRegime.BULL,
                bars_held=0,
            )

    def test_negative_bars_held(self) -> None:
        with pytest.raises(ConfigError, match="bars_held cannot be negative"):
            PositionState(
                entry_price=Decimal("100"),
                current_price=Decimal("100"),
                highest_since_entry=Decimal("110"),
                lowest_since_entry=Decimal("90"),
                side=OrderSide.BUY,
                current_atr=Decimal("5"),
                current_regime=MarketRegime.BULL,
                bars_held=-1,
            )


_positive_decimal = st.decimals(
    min_value="1",
    max_value="10000",
    places=2,
    allow_nan=False,
    allow_infinity=False,
)
_atr_decimal = st.decimals(
    min_value="0.01",
    max_value="100",
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@given(price=_positive_decimal, atr=_atr_decimal)
@settings(max_examples=50)
def test_atr_trailing_buy_stop_positive(price: Decimal, atr: Decimal) -> None:
    ts = ATRTrailingStop(atr_multiplier=Decimal("2.0"))
    ts.reset()
    state = PositionState(
        entry_price=price,
        current_price=price,
        highest_since_entry=price + atr,
        lowest_since_entry=max(Decimal("0.01"), price - atr),
        side=OrderSide.BUY,
        current_atr=atr,
        current_regime=MarketRegime.BULL,
        bars_held=5,
    )
    stop = ts.compute_stop(state)
    assert stop >= Decimal("0")
