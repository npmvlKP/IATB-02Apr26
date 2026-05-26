"""Comprehensive coverage tests for iatb.risk.trailing_stop."""

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
    TrailingStopStrategy,
)


def _make_position(
    side: OrderSide = OrderSide.BUY,
    entry_price: Decimal = Decimal("100"),
    current_price: Decimal = Decimal("105"),
    highest: Decimal = Decimal("110"),
    lowest: Decimal = Decimal("95"),
    atr: Decimal = Decimal("5"),
    regime: MarketRegime = MarketRegime.BULL,
    bars_held: int = 10,
) -> PositionState:
    return PositionState(
        entry_price=entry_price,
        current_price=current_price,
        highest_since_entry=highest,
        lowest_since_entry=lowest,
        side=side,
        current_atr=atr,
        current_regime=regime,
        bars_held=bars_held,
    )


class TestPositionState:
    def test_valid_creation(self) -> None:
        ps = _make_position()
        assert ps.entry_price == Decimal("100")
        assert ps.bars_held == 10

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

    def test_negative_entry_price_raises(self) -> None:
        with pytest.raises(ConfigError, match="entry_price must be positive"):
            _make_position(entry_price=Decimal("-1"))

    def test_zero_current_price_raises(self) -> None:
        with pytest.raises(ConfigError, match="current_price must be positive"):
            _make_position(current_price=Decimal("0"))

    def test_zero_atr_raises(self) -> None:
        with pytest.raises(ConfigError, match="current_atr must be positive"):
            _make_position(atr=Decimal("0"))

    def test_negative_bars_held_raises(self) -> None:
        with pytest.raises(ConfigError, match="bars_held cannot be negative"):
            _make_position(bars_held=-1)

    def test_zero_bars_held_ok(self) -> None:
        ps = _make_position(bars_held=0)
        assert ps.bars_held == 0

    def test_frozen(self) -> None:
        ps = _make_position()
        with pytest.raises(AttributeError):
            ps.entry_price = Decimal("200")  # type: ignore[misc]


class TestATRTrailingStop:
    def test_buy_first_call(self) -> None:
        strategy = ATRTrailingStop(Decimal("3"))
        state = _make_position(highest=Decimal("110"), atr=Decimal("5"))
        result = strategy.compute_stop(state)
        assert result == Decimal("95")

    def test_buy_ratchet_up(self) -> None:
        strategy = ATRTrailingStop(Decimal("3"))
        state1 = _make_position(highest=Decimal("110"), atr=Decimal("5"))
        stop1 = strategy.compute_stop(state1)
        state2 = _make_position(highest=Decimal("120"), atr=Decimal("5"))
        stop2 = strategy.compute_stop(state2)
        assert stop2 >= stop1

    def test_buy_no_ratchet_down(self) -> None:
        strategy = ATRTrailingStop(Decimal("3"))
        state1 = _make_position(highest=Decimal("120"), atr=Decimal("5"))
        stop1 = strategy.compute_stop(state1)
        state2 = _make_position(highest=Decimal("110"), atr=Decimal("5"))
        stop2 = strategy.compute_stop(state2)
        assert stop2 == stop1

    def test_sell_first_call(self) -> None:
        strategy = ATRTrailingStop(Decimal("3"))
        state = _make_position(
            side=OrderSide.SELL, lowest=Decimal("90"), atr=Decimal("5")
        )
        result = strategy.compute_stop(state)
        assert result == Decimal("105")

    def test_sell_ratchet_down(self) -> None:
        strategy = ATRTrailingStop(Decimal("3"))
        state1 = _make_position(
            side=OrderSide.SELL, lowest=Decimal("90"), atr=Decimal("5")
        )
        stop1 = strategy.compute_stop(state1)
        state2 = _make_position(
            side=OrderSide.SELL, lowest=Decimal("80"), atr=Decimal("5")
        )
        stop2 = strategy.compute_stop(state2)
        assert stop2 <= stop1

    def test_sell_no_ratchet_up(self) -> None:
        strategy = ATRTrailingStop(Decimal("3"))
        state1 = _make_position(
            side=OrderSide.SELL, lowest=Decimal("80"), atr=Decimal("5")
        )
        stop1 = strategy.compute_stop(state1)
        state2 = _make_position(
            side=OrderSide.SELL, lowest=Decimal("90"), atr=Decimal("5")
        )
        stop2 = strategy.compute_stop(state2)
        assert stop2 == stop1

    def test_zero_multiplier_raises(self) -> None:
        with pytest.raises(ConfigError, match="atr_multiplier must be positive"):
            ATRTrailingStop(Decimal("0"))

    def test_negative_multiplier_raises(self) -> None:
        with pytest.raises(ConfigError, match="atr_multiplier must be positive"):
            ATRTrailingStop(Decimal("-1"))

    def test_reset_clears_ratchet(self) -> None:
        strategy = ATRTrailingStop(Decimal("3"))
        state = _make_position(highest=Decimal("110"), atr=Decimal("5"))
        strategy.compute_stop(state)
        strategy.reset()
        state2 = _make_position(highest=Decimal("100"), atr=Decimal("5"))
        stop = strategy.compute_stop(state2)
        assert stop == Decimal("85")

    def test_buy_clamps_to_zero(self) -> None:
        strategy = ATRTrailingStop(Decimal("100"))
        state = _make_position(highest=Decimal("50"), atr=Decimal("1"))
        result = strategy.compute_stop(state)
        assert result >= Decimal("0")

    def test_default_multiplier(self) -> None:
        strategy = ATRTrailingStop()
        state = _make_position(highest=Decimal("110"), atr=Decimal("5"))
        result = strategy.compute_stop(state)
        assert result == Decimal("95")

    def test_implements_protocol(self) -> None:
        strategy = ATRTrailingStop()
        assert isinstance(strategy, TrailingStopStrategy)


class TestRegimeAdaptiveTrailingStop:
    def test_bull_regime(self) -> None:
        strategy = RegimeAdaptiveTrailingStop()
        state = _make_position(
            regime=MarketRegime.BULL, highest=Decimal("110"), atr=Decimal("5")
        )
        result = strategy.compute_stop(state)
        distance = Decimal("5") * Decimal("2.5")
        assert result == Decimal("110") - distance

    def test_bear_regime(self) -> None:
        strategy = RegimeAdaptiveTrailingStop()
        state = _make_position(
            regime=MarketRegime.BEAR, highest=Decimal("110"), atr=Decimal("5")
        )
        result = strategy.compute_stop(state)
        distance = Decimal("5") * Decimal("1.5")
        assert result == Decimal("110") - distance

    def test_sideways_regime(self) -> None:
        strategy = RegimeAdaptiveTrailingStop()
        state = _make_position(
            regime=MarketRegime.SIDEWAYS, highest=Decimal("110"), atr=Decimal("5")
        )
        result = strategy.compute_stop(state)
        distance = Decimal("5") * Decimal("3.0")
        assert result == Decimal("110") - distance

    def test_sell_side(self) -> None:
        strategy = RegimeAdaptiveTrailingStop()
        state = _make_position(
            side=OrderSide.SELL,
            regime=MarketRegime.BEAR,
            lowest=Decimal("90"),
            atr=Decimal("5"),
        )
        result = strategy.compute_stop(state)
        distance = Decimal("5") * Decimal("1.5")
        assert result == Decimal("90") + distance

    def test_zero_base_multiplier_raises(self) -> None:
        with pytest.raises(ConfigError, match="base_multiplier must be positive"):
            RegimeAdaptiveTrailingStop(Decimal("0"))

    def test_reset(self) -> None:
        strategy = RegimeAdaptiveTrailingStop()
        state = _make_position(
            regime=MarketRegime.BULL, highest=Decimal("110"), atr=Decimal("5")
        )
        strategy.compute_stop(state)
        strategy.reset()
        state2 = _make_position(
            regime=MarketRegime.BULL, highest=Decimal("100"), atr=Decimal("5")
        )
        stop = strategy.compute_stop(state2)
        distance = Decimal("5") * Decimal("2.5")
        assert stop == Decimal("100") - distance

    def test_ratchet_buy(self) -> None:
        strategy = RegimeAdaptiveTrailingStop()
        state1 = _make_position(
            regime=MarketRegime.BULL, highest=Decimal("110"), atr=Decimal("5")
        )
        stop1 = strategy.compute_stop(state1)
        state2 = _make_position(
            regime=MarketRegime.BULL, highest=Decimal("100"), atr=Decimal("5")
        )
        stop2 = strategy.compute_stop(state2)
        assert stop2 >= stop1

    def test_implements_protocol(self) -> None:
        strategy = RegimeAdaptiveTrailingStop()
        assert isinstance(strategy, TrailingStopStrategy)


class TestChandelierExit:
    def test_buy_side(self) -> None:
        chandelier = ChandelierExit(Decimal("3"))
        state = _make_position(highest=Decimal("110"), atr=Decimal("5"))
        result = chandelier.compute_stop(state)
        assert result == Decimal("95")

    def test_sell_side(self) -> None:
        chandelier = ChandelierExit(Decimal("3"))
        state = _make_position(
            side=OrderSide.SELL, lowest=Decimal("90"), atr=Decimal("5")
        )
        result = chandelier.compute_stop(state)
        assert result == Decimal("105")

    def test_buy_clamps_zero(self) -> None:
        chandelier = ChandelierExit(Decimal("100"))
        state = _make_position(highest=Decimal("10"), atr=Decimal("1"))
        result = chandelier.compute_stop(state)
        assert result == Decimal("0")

    def test_zero_multiplier_raises(self) -> None:
        with pytest.raises(ConfigError, match="atr_multiplier must be positive"):
            ChandelierExit(Decimal("0"))

    def test_no_ratchet_state(self) -> None:
        c1 = ChandelierExit(Decimal("3"))
        state = _make_position(highest=Decimal("110"), atr=Decimal("5"))
        r1 = c1.compute_stop(state)
        state2 = _make_position(highest=Decimal("100"), atr=Decimal("5"))
        r2 = c1.compute_stop(state2)
        assert r2 < r1

    def test_implements_protocol(self) -> None:
        chandelier = ChandelierExit()
        assert isinstance(chandelier, TrailingStopStrategy)


class TestTimeDecayTrailingStop:
    def test_initial_stop(self) -> None:
        strategy = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3"),
            decay_rate=Decimal("0.02"),
            min_multiplier=Decimal("1.0"),
        )
        state = _make_position(highest=Decimal("110"), atr=Decimal("5"), bars_held=0)
        result = strategy.compute_stop(state)
        assert result == Decimal("95")

    def test_decay_reduces_distance(self) -> None:
        strategy = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3"),
            decay_rate=Decimal("0.5"),
            min_multiplier=Decimal("0.5"),
        )
        state_0 = _make_position(highest=Decimal("110"), atr=Decimal("5"), bars_held=0)
        stop_0 = strategy.compute_stop(state_0)
        strategy.reset()
        state_10 = _make_position(
            highest=Decimal("110"), atr=Decimal("5"), bars_held=10
        )
        stop_10 = strategy.compute_stop(state_10)
        assert stop_10 >= stop_0

    def test_sell_side(self) -> None:
        strategy = TimeDecayTrailingStop(
            initial_multiplier=Decimal("3"),
            decay_rate=Decimal("0.02"),
            min_multiplier=Decimal("1.0"),
        )
        state = _make_position(
            side=OrderSide.SELL, lowest=Decimal("90"), atr=Decimal("5"), bars_held=0
        )
        result = strategy.compute_stop(state)
        assert result == Decimal("105")

    def test_zero_initial_raises(self) -> None:
        with pytest.raises(ConfigError, match="initial_multiplier must be positive"):
            TimeDecayTrailingStop(Decimal("0"), Decimal("0.02"), Decimal("1"))

    def test_zero_decay_raises(self) -> None:
        with pytest.raises(ConfigError, match="decay_rate must be positive"):
            TimeDecayTrailingStop(Decimal("3"), Decimal("0"), Decimal("1"))

    def test_min_greater_than_initial_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_multiplier must be in"):
            TimeDecayTrailingStop(Decimal("3"), Decimal("0.02"), Decimal("4"))

    def test_zero_min_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_multiplier must be in"):
            TimeDecayTrailingStop(Decimal("3"), Decimal("0.02"), Decimal("0"))

    def test_reset(self) -> None:
        strategy = TimeDecayTrailingStop(Decimal("3"), Decimal("0.02"), Decimal("1"))
        state = _make_position(highest=Decimal("110"), atr=Decimal("5"), bars_held=5)
        strategy.compute_stop(state)
        strategy.reset()
        state2 = _make_position(highest=Decimal("100"), atr=Decimal("5"), bars_held=0)
        stop = strategy.compute_stop(state2)
        assert stop == Decimal("85")

    def test_ratchet_buy(self) -> None:
        strategy = TimeDecayTrailingStop(Decimal("3"), Decimal("0.02"), Decimal("1"))
        state1 = _make_position(highest=Decimal("110"), atr=Decimal("5"), bars_held=5)
        stop1 = strategy.compute_stop(state1)
        state2 = _make_position(highest=Decimal("100"), atr=Decimal("5"), bars_held=5)
        stop2 = strategy.compute_stop(state2)
        assert stop2 >= stop1

    def test_implements_protocol(self) -> None:
        strategy = TimeDecayTrailingStop(Decimal("3"), Decimal("0.02"), Decimal("1"))
        assert isinstance(strategy, TrailingStopStrategy)


class TestFixedFractionTrailingStop:
    def test_buy_first_call(self) -> None:
        strategy = FixedFractionTrailingStop(Decimal("0.01"))
        state = _make_position(current_price=Decimal("100"))
        result = strategy.compute_stop(state)
        assert result == Decimal("99")

    def test_sell_first_call(self) -> None:
        strategy = FixedFractionTrailingStop(Decimal("0.01"))
        state = _make_position(side=OrderSide.SELL, current_price=Decimal("100"))
        result = strategy.compute_stop(state)
        assert result == Decimal("101")

    def test_buy_ratchet(self) -> None:
        strategy = FixedFractionTrailingStop(Decimal("0.01"))
        state1 = _make_position(current_price=Decimal("110"))
        stop1 = strategy.compute_stop(state1)
        state2 = _make_position(current_price=Decimal("100"))
        stop2 = strategy.compute_stop(state2)
        assert stop2 >= stop1

    def test_sell_ratchet(self) -> None:
        strategy = FixedFractionTrailingStop(Decimal("0.01"))
        state1 = _make_position(side=OrderSide.SELL, current_price=Decimal("90"))
        stop1 = strategy.compute_stop(state1)
        state2 = _make_position(side=OrderSide.SELL, current_price=Decimal("100"))
        stop2 = strategy.compute_stop(state2)
        assert stop2 <= stop1

    def test_zero_fraction_raises(self) -> None:
        with pytest.raises(ConfigError, match="trail_fraction must be between"):
            FixedFractionTrailingStop(Decimal("0"))

    def test_one_fraction_raises(self) -> None:
        with pytest.raises(ConfigError, match="trail_fraction must be between"):
            FixedFractionTrailingStop(Decimal("1"))

    def test_reset(self) -> None:
        strategy = FixedFractionTrailingStop(Decimal("0.01"))
        state = _make_position(current_price=Decimal("110"))
        strategy.compute_stop(state)
        strategy.reset()
        state2 = _make_position(current_price=Decimal("100"))
        stop = strategy.compute_stop(state2)
        assert stop == Decimal("99")

    def test_implements_protocol(self) -> None:
        strategy = FixedFractionTrailingStop()
        assert isinstance(strategy, TrailingStopStrategy)


class TestTrailingStopStrategyProtocol:
    def test_protocol_is_runtime_checkable(self) -> None:
        strategy = ATRTrailingStop(Decimal("3"))
        assert isinstance(strategy, TrailingStopStrategy)

    def test_protocol_instance_check(self) -> None:
        strategy = FixedFractionTrailingStop(Decimal("0.05"))
        assert isinstance(strategy, TrailingStopStrategy)

    def test_non_implementing_class_not_instance(self) -> None:
        assert not isinstance(object(), TrailingStopStrategy)
