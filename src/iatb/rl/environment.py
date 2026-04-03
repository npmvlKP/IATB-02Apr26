"""
Custom RL trading environment with deterministic transitions.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal

from iatb.backtesting import session_masks
from iatb.backtesting.indian_costs import MarketSegment, calculate_indian_costs
from iatb.core.clock import Clock
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class EnvironmentConfig:
    max_steps: int = 500
    trade_notional: Decimal = Decimal("10000")
    market_segment: MarketSegment = "fo"
    exchange: Exchange = Exchange.NSE
    intraday: bool = True
    auto_square_off_ist: time = time(15, 10)
    lot_size: Decimal = Decimal("1")
    mcx_lot_size: Decimal = Decimal("50")


class TradingEnvironment:
    """Discrete(3) action environment: Hold(0), Buy(1), Sell(2)."""

    def __init__(
        self,
        observations: list[list[Decimal]],
        close_prices: list[Decimal],
        timestamps_utc: list[datetime],
        config: EnvironmentConfig | None = None,
    ) -> None:
        _validate_inputs(observations, close_prices, timestamps_utc)
        self._observations = observations
        self._close_prices = close_prices
        self._timestamps_utc = timestamps_utc
        self._config = config or EnvironmentConfig()
        self.action_space_n = 3
        self.observation_size = len(observations[0])
        self._index = 0
        self._steps = 0
        self._position = 0

    def reset(self, seed: int = 42) -> tuple[list[Decimal], dict[str, str]]:
        self._index = 0
        self._steps = 0
        self._position = 0
        return list(self._observations[0]), {"seed": str(seed)}

    def step(self, action: int) -> tuple[list[Decimal], Decimal, bool, bool, dict[str, str]]:
        _validate_action(action)
        if self._index >= len(self._close_prices) - 1:
            msg = "cannot step beyond terminal observation"
            raise ConfigError(msg)
        timestamp_now = self._timestamps_utc[self._index]
        tradable = session_masks.is_in_session(timestamp_now, self._config.exchange)
        prior_position = self._position
        self._position = _next_position(action, prior_position, tradable)
        auto_square_off = _must_auto_square_off(timestamp_now, self._config)
        if auto_square_off and self._position != 0:
            self._position = 0
        reward = _step_reward(self._close_prices, self._index, self._position, self._config)
        if self._position != prior_position:
            reward -= _transaction_cost(self._config)
        self._index += 1
        self._steps += 1
        done = self._index >= len(self._close_prices) - 1 or self._steps >= self._config.max_steps
        info = _step_info(self._index, tradable, auto_square_off)
        return list(self._observations[self._index]), reward, done, False, info


def _validate_inputs(
    observations: list[list[Decimal]],
    close_prices: list[Decimal],
    timestamps_utc: list[datetime],
) -> None:
    if len(observations) != len(close_prices) or len(observations) != len(timestamps_utc):
        msg = "observations, close_prices, and timestamps_utc must have equal length"
        raise ConfigError(msg)
    if len(observations) < 2:
        msg = "environment requires at least two timesteps"
        raise ConfigError(msg)
    if any(not row for row in observations):
        msg = "each observation row must contain at least one feature"
        raise ConfigError(msg)
    if any(stamp.tzinfo != UTC for stamp in timestamps_utc):
        msg = "timestamps_utc must be timezone-aware UTC datetimes"
        raise ConfigError(msg)


def _validate_action(action: int) -> None:
    if action not in (0, 1, 2):
        msg = f"action must be 0, 1, or 2; got {action}"
        raise ConfigError(msg)


def _next_position(action: int, current: int, tradable: bool) -> int:
    if not tradable:
        return current
    if action == 0:
        return current
    if action == 1:
        return 1
    return -1


def _must_auto_square_off(timestamp_utc: datetime, config: EnvironmentConfig) -> bool:
    if not config.intraday:
        return False
    return Clock.to_ist(timestamp_utc).time() >= config.auto_square_off_ist


def _step_reward(
    close_prices: list[Decimal],
    index: int,
    position: int,
    config: EnvironmentConfig,
) -> Decimal:
    price_now = close_prices[index]
    price_next = close_prices[index + 1]
    lot_size = _effective_lot_size(config)
    return (price_next - price_now) * Decimal(position) * lot_size


def _transaction_cost(config: EnvironmentConfig) -> Decimal:
    lot_size = _effective_lot_size(config)
    costs = calculate_indian_costs(config.trade_notional * lot_size, config.market_segment)
    return costs.total


def _effective_lot_size(config: EnvironmentConfig) -> Decimal:
    if config.exchange == Exchange.MCX:
        return config.mcx_lot_size
    return config.lot_size


def _step_info(index: int, tradable: bool, auto_square_off: bool) -> dict[str, str]:
    return {
        "index": str(index),
        "in_session": "1" if tradable else "0",
        "auto_square_off": "1" if auto_square_off else "0",
    }
