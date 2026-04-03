"""
Session masks for Indian market backtesting windows.
"""

from datetime import datetime

from iatb.core.clock import TradingSessions
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError


def is_in_session(timestamp_utc: datetime, exchange: Exchange) -> bool:
    _validate_exchange(exchange)
    return TradingSessions.is_market_open(timestamp_utc, exchange)


def filter_timestamps_in_session(
    timestamps_utc: list[datetime],
    exchange: Exchange,
) -> list[datetime]:
    _validate_exchange(exchange)
    return [stamp for stamp in timestamps_utc if is_in_session(stamp, exchange)]


def _validate_exchange(exchange: Exchange) -> None:
    if exchange not in {Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS}:
        msg = f"unsupported session exchange: {exchange.value}"
        raise ConfigError(msg)
