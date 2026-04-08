import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.rl.environment import EnvironmentConfig, TradingEnvironment

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_environment_step_is_deterministic_with_fixed_seed() -> None:
    observations, prices, stamps = _sample_data()
    env_one = TradingEnvironment(
        observations=observations, close_prices=prices, timestamps_utc=stamps
    )
    env_two = TradingEnvironment(
        observations=observations, close_prices=prices, timestamps_utc=stamps
    )
    initial_one, info_one = env_one.reset(seed=7)
    initial_two, info_two = env_two.reset(seed=7)
    assert initial_one == initial_two
    assert info_one == info_two
    assert env_one.step(1) == env_two.step(1)
    assert env_one.step(0) == env_two.step(0)


def test_environment_auto_square_off_applies_after_1510_ist() -> None:
    observations = [
        [Decimal("100"), Decimal("1000"), Decimal("0.8"), Decimal("1"), Decimal("0"), Decimal("0")],
        [Decimal("101"), Decimal("1001"), Decimal("0.7"), Decimal("1"), Decimal("0"), Decimal("0")],
        [Decimal("102"), Decimal("1002"), Decimal("0.6"), Decimal("1"), Decimal("0"), Decimal("0")],
    ]
    prices = [Decimal("100"), Decimal("101"), Decimal("102")]
    stamps = [
        datetime(2026, 1, 6, 9, 39, tzinfo=UTC),  # 15:09 IST
        datetime(2026, 1, 6, 9, 41, tzinfo=UTC),  # 15:11 IST
        datetime(2026, 1, 6, 9, 42, tzinfo=UTC),  # 15:12 IST
    ]
    env = TradingEnvironment(observations=observations, close_prices=prices, timestamps_utc=stamps)
    env.reset(seed=11)
    env.step(1)
    _next_obs, _reward, _done, _truncated, info = env.step(0)
    assert info["auto_square_off"] == "1"


def test_environment_does_not_open_new_position_outside_session() -> None:
    observations = [[Decimal("100"), Decimal("1000")], [Decimal("101"), Decimal("1001")]]
    prices = [Decimal("100"), Decimal("101")]
    stamps = [
        datetime(2026, 1, 5, 2, 0, tzinfo=UTC),  # 07:30 IST
        datetime(2026, 1, 5, 2, 1, tzinfo=UTC),
    ]
    config = EnvironmentConfig(exchange=Exchange.NSE, trade_notional=Decimal("10000"))
    env = TradingEnvironment(
        observations=observations, close_prices=prices, timestamps_utc=stamps, config=config
    )
    env.reset(seed=3)
    _next_obs, reward, _done, _truncated, info = env.step(1)
    assert info["in_session"] == "0"
    assert reward == Decimal("0")


def test_environment_validates_input_lengths_and_timestamps() -> None:
    observations = [[Decimal("1")], [Decimal("2")]]
    prices = [Decimal("1"), Decimal("2")]
    good_stamps = [datetime(2026, 1, 5, 3, 50, tzinfo=UTC), datetime(2026, 1, 5, 3, 51, tzinfo=UTC)]
    bad_stamps = [datetime(2026, 1, 5, 3, 50), datetime(2026, 1, 5, 3, 51)]  # noqa: DTZ001
    with pytest.raises(ConfigError, match="equal length"):
        TradingEnvironment(
            observations=observations, close_prices=prices[:1], timestamps_utc=good_stamps[:1]
        )
    with pytest.raises(ConfigError, match="timezone-aware UTC"):
        TradingEnvironment(
            observations=observations, close_prices=prices, timestamps_utc=bad_stamps
        )


def test_environment_rejects_invalid_actions_and_terminal_overstep() -> None:
    observations, prices, stamps = _sample_data()
    env = TradingEnvironment(observations=observations, close_prices=prices, timestamps_utc=stamps)
    env.reset(seed=17)
    with pytest.raises(ConfigError, match="action must be 0, 1, or 2"):
        env.step(9)
    env.step(0)
    env.step(0)
    with pytest.raises(ConfigError, match="cannot step beyond terminal observation"):
        env.step(0)


def test_environment_uses_mcx_lot_size_and_skips_square_off_when_intraday_disabled() -> None:
    observations = [[Decimal("300"), Decimal("1")], [Decimal("302"), Decimal("1")]]
    prices = [Decimal("300"), Decimal("302")]
    stamps = [
        datetime(2026, 1, 5, 10, 30, tzinfo=UTC),  # 16:00 IST
        datetime(2026, 1, 5, 10, 31, tzinfo=UTC),
    ]
    config = EnvironmentConfig(
        exchange=Exchange.MCX,
        market_segment="mcx",
        intraday=False,
        mcx_lot_size=Decimal("50"),
        trade_notional=Decimal("100"),
    )
    env = TradingEnvironment(
        observations=observations, close_prices=prices, timestamps_utc=stamps, config=config
    )
    env.reset(seed=19)
    _next_obs, reward, _done, _truncated, info = env.step(1)
    assert reward != Decimal("0")
    assert info["auto_square_off"] == "0"


def _sample_data() -> tuple[list[list[Decimal]], list[Decimal], list[datetime]]:
    start = datetime(2026, 1, 5, 3, 50, tzinfo=UTC)
    observations = [
        [Decimal("100"), Decimal("1000"), Decimal("0.8"), Decimal("1"), Decimal("0"), Decimal("0")],
        [Decimal("101"), Decimal("1005"), Decimal("0.7"), Decimal("0"), Decimal("1"), Decimal("0")],
        [Decimal("102"), Decimal("1002"), Decimal("0.6"), Decimal("0"), Decimal("0"), Decimal("1")],
    ]
    prices = [Decimal("100"), Decimal("101"), Decimal("102")]
    stamps = [start, start + timedelta(minutes=1), start + timedelta(minutes=2)]
    return observations, prices, stamps
