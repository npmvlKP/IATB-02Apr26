"""Coverage tests for trailing_stop.py targeting >=90% coverage."""

from decimal import Decimal

import pytest
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


class TestPositionStateValidationCoverage:
    def test_zero_entry_price_raises(self) -> None:
        with pytest.raises(ConfigError, match="entry_price must be positive"):
            PositionState(
                entry_price=Decimal("0"),
                current_price=Decimal("100"),
                highest_since_entry=Decimal("110"),
                lowest_since_entry=Decimal("90"),
                side=OrderSide.BUY,
                current_atr=Decimal("5"),
                current_regime=MarketRegime.BULL,
                bars_held=0,
            )

    def test_zero_current_price_raises(self) -> None:
        with pytest.raises(ConfigError, match="current_price must be positive"):
            PositionState(
                entry_price=Decimal("100"),
                current_price=Decimal("0"),
                highest_since_entry=Decimal("110"),
                lowest_since_entry=Decimal("90"),
                side=OrderSide.BUY,
                current_atr=Decimal("5"),
                current_regime=MarketRegime.BULL,
                bars_held=0,
            )

    def test_zero_current_atr_raises(self) -> None:
        with pytest.raises(ConfigError, match="current_atr must be positive"):
            PositionState(
                entry_price=Decimal("100"),
                current_price=Decimal("100"),
                highest_since_entry=Decimal("110"),
                lowest_since_entry=Decimal("90"),
                side=OrderSide.BUY,
                current_atr=Decimal("0"),
                current_regime=MarketRegime.BULL,
                bars_held=0,
            )


class TestATRTrailingStopCoverage:
    def test_negative_multiplier_raises(self) -> None:
        with pytest.raises(ConfigError, match="atr_multiplier must be positive"):
            ATRTrailingStop(atr_multiplier=Decimal("-1"))

    def test_buy_stop_clamped_to_zero(self) -> None:
        ts = ATRTrailingStop(atr_multiplier=Decimal("100"))
        state = PositionState(
            entry_price=Decimal("10"),
            current_price=Decimal("10"),
            highest_since_entry=Decimal("15"),
            lowest_since_entry=Decimal("5"),
            side=OrderSide.BUY,
            current_atr=Decimal("1"),
            current_regime=MarketRegime.BULL,
            bars_held=0,
        )
        stop = ts.compute_stop(state)
        assert stop >= Decimal("0")

    def test_sell_no_previous_then_with_previous(self) -> None:
        ts = ATRTrailingStop(atr_multiplier=Decimal("2.0"))
        state1 = _state(side=OrderSide.SELL, price="100")
        stop1 = ts.compute_stop(state1)
        state2 = _state(side=OrderSide.SELL, price="95")
        stop2 = ts.compute_stop(state2)
        assert stop2 <= stop1

    def test_buy_with_previous_stop_ratchets(self) -> None:
        ts = ATRTrailingStop(atr_multiplier=Decimal("2.0"))
        s1 = _state(side=OrderSide.BUY, price="100")
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.BUY, price="90")
        stop2 = ts.compute_stop(s2)
        assert stop2 >= stop1

    def test_reset_clears_ratchet_state(self) -> None:
        ts = ATRTrailingStop(atr_multiplier=Decimal("2.0"))
        ts.compute_stop(_state(side=OrderSide.BUY))
        ts.reset()
        assert ts._previous_stop is None


class TestRegimeAdaptiveTrailingStopCoverage:
    def test_negative_base_multiplier_raises(self) -> None:
        with pytest.raises(ConfigError, match="base_multiplier must be positive"):
            RegimeAdaptiveTrailingStop(base_multiplier=Decimal("-1"))

    def test_buy_with_no_previous(self) -> None:
        ts = RegimeAdaptiveTrailingStop()
        state = _state(side=OrderSide.BUY, regime=MarketRegime.BULL)
        stop = ts.compute_stop(state)
        assert stop > Decimal("0")
        assert stop < state.highest_since_entry

    def test_sell_with_no_previous(self) -> None:
        ts = RegimeAdaptiveTrailingStop()
        state = _state(side=OrderSide.SELL, regime=MarketRegime.BEAR)
        stop = ts.compute_stop(state)
        assert stop > state.lowest_since_entry

    def test_buy_with_previous_ratchets(self) -> None:
        ts = RegimeAdaptiveTrailingStop()
        s1 = _state(side=OrderSide.BUY, price="100")
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.BUY, price="90")
        stop2 = ts.compute_stop(s2)
        assert stop2 >= stop1

    def test_sell_with_previous_ratchets(self) -> None:
        ts = RegimeAdaptiveTrailingStop()
        s1 = _state(side=OrderSide.SELL, price="100")
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.SELL, price="110")
        stop2 = ts.compute_stop(s2)
        assert stop2 <= stop1

    def test_reset_clears_state(self) -> None:
        ts = RegimeAdaptiveTrailingStop()
        ts.compute_stop(_state())
        ts.reset()
        assert ts._previous_stop is None

    def test_unknown_regime_uses_base(self) -> None:
        ts = RegimeAdaptiveTrailingStop(base_multiplier=Decimal("2.0"))
        state = PositionState(
            entry_price=Decimal("100"),
            current_price=Decimal("100"),
            highest_since_entry=Decimal("110"),
            lowest_since_entry=Decimal("95"),
            side=OrderSide.BUY,
            current_atr=Decimal("5"),
            current_regime=MarketRegime.SIDEWAYS,
            bars_held=5,
        )
        stop = ts.compute_stop(state)
        assert stop > Decimal("0")


class TestChandelierExitCoverage:
    def test_negative_multiplier_raises(self) -> None:
        with pytest.raises(ConfigError, match="atr_multiplier must be positive"):
            ChandelierExit(atr_multiplier=Decimal("-1"))

    def test_buy_clamped_to_zero(self) -> None:
        ce = ChandelierExit(atr_multiplier=Decimal("1000"))
        state = PositionState(
            entry_price=Decimal("10"),
            current_price=Decimal("10"),
            highest_since_entry=Decimal("15"),
            lowest_since_entry=Decimal("5"),
            side=OrderSide.BUY,
            current_atr=Decimal("1"),
            current_regime=MarketRegime.BULL,
            bars_held=0,
        )
        stop = ce.compute_stop(state)
        assert stop >= Decimal("0")

    def test_sell_returns_lowest_plus_distance(self) -> None:
        ce = ChandelierExit(atr_multiplier=Decimal("3.0"))
        state = _state(side=OrderSide.SELL)
        stop = ce.compute_stop(state)
        assert stop == state.lowest_since_entry + Decimal("3.0") * state.current_atr

    def test_buy_returns_highest_minus_distance(self) -> None:
        ce = ChandelierExit(atr_multiplier=Decimal("2.5"))
        state = _state(side=OrderSide.BUY)
        stop = ce.compute_stop(state)
        assert stop == state.highest_since_entry - Decimal("2.5") * state.current_atr


class TestTimeDecayTrailingStopCoverage:
    def test_zero_initial_multiplier_raises(self) -> None:
        with pytest.raises(ConfigError, match="initial_multiplier must be positive"):
            TimeDecayTrailingStop(initial_multiplier=Decimal("0"))

    def test_zero_decay_rate_raises(self) -> None:
        with pytest.raises(ConfigError, match="decay_rate must be positive"):
            TimeDecayTrailingStop(decay_rate=Decimal("0"))

    def test_min_multiplier_greater_than_initial_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_multiplier must be in"):
            TimeDecayTrailingStop(
                initial_multiplier=Decimal("2.0"),
                min_multiplier=Decimal("3.0"),
            )

    def test_zero_min_multiplier_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_multiplier must be in"):
            TimeDecayTrailingStop(min_multiplier=Decimal("0"))

    def test_buy_no_previous(self) -> None:
        ts = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3.0"),
            decay_rate=Decimal("0.1"),
            min_multiplier=Decimal("1.0"),
        )
        state = _state(side=OrderSide.BUY, bars=0)
        stop = ts.compute_stop(state)
        assert stop > Decimal("0")
        assert stop < state.highest_since_entry

    def test_sell_no_previous(self) -> None:
        ts = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3.0"),
            decay_rate=Decimal("0.1"),
            min_multiplier=Decimal("1.0"),
        )
        state = _state(side=OrderSide.SELL, bars=0)
        stop = ts.compute_stop(state)
        assert stop > state.lowest_since_entry

    def test_buy_with_previous_ratchets(self) -> None:
        ts = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3.0"),
            decay_rate=Decimal("0.1"),
            min_multiplier=Decimal("1.0"),
        )
        s1 = _state(side=OrderSide.BUY, bars=0)
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.BUY, bars=5)
        stop2 = ts.compute_stop(s2)
        assert stop2 >= stop1

    def test_sell_with_previous_ratchets(self) -> None:
        ts = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3.0"),
            decay_rate=Decimal("0.1"),
            min_multiplier=Decimal("1.0"),
        )
        s1 = _state(side=OrderSide.SELL, bars=0)
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.SELL, price="90", bars=5)
        stop2 = ts.compute_stop(s2)
        assert stop2 <= stop1

    def test_reset_clears_state(self) -> None:
        ts = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3.0"),
            decay_rate=Decimal("0.1"),
            min_multiplier=Decimal("1.0"),
        )
        ts.compute_stop(_state())
        ts.reset()
        assert ts._previous_stop is None


class TestFixedFractionTrailingStopCoverage:
    def test_zero_fraction_raises(self) -> None:
        with pytest.raises(ConfigError, match="trail_fraction must be between 0 and 1"):
            FixedFractionTrailingStop(trail_fraction=Decimal("0"))

    def test_one_fraction_raises(self) -> None:
        with pytest.raises(ConfigError, match="trail_fraction must be between 0 and 1"):
            FixedFractionTrailingStop(trail_fraction=Decimal("1.0"))

    def test_buy_no_previous(self) -> None:
        ts = FixedFractionTrailingStop(trail_fraction=Decimal("0.02"))
        state = _state(side=OrderSide.BUY)
        stop = ts.compute_stop(state)
        assert stop == state.current_price - state.current_price * Decimal("0.02")

    def test_sell_no_previous(self) -> None:
        ts = FixedFractionTrailingStop(trail_fraction=Decimal("0.02"))
        state = _state(side=OrderSide.SELL)
        stop = ts.compute_stop(state)
        assert stop == state.current_price + state.current_price * Decimal("0.02")

    def test_buy_with_previous_ratchets(self) -> None:
        ts = FixedFractionTrailingStop(trail_fraction=Decimal("0.02"))
        s1 = _state(side=OrderSide.BUY, price="100")
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.BUY, price="90")
        stop2 = ts.compute_stop(s2)
        assert stop2 >= stop1

    def test_sell_with_previous_ratchets(self) -> None:
        ts = FixedFractionTrailingStop(trail_fraction=Decimal("0.02"))
        s1 = _state(side=OrderSide.SELL, price="100")
        stop1 = ts.compute_stop(s1)
        s2 = _state(side=OrderSide.SELL, price="110")
        stop2 = ts.compute_stop(s2)
        assert stop2 <= stop1

    def test_reset_clears_state(self) -> None:
        ts = FixedFractionTrailingStop(trail_fraction=Decimal("0.02"))
        ts.compute_stop(_state())
        ts.reset()
        assert ts._previous_stop is None
