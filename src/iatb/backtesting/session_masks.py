"""
Session masks for Indian market backtesting windows.

Enforces MIS (intraday-only) product type for Stocks/Options/Futures
on NSE/CDS/MCX exchanges. Hard-blocks DELIVERY (CNC) trades.
"""

import logging
from datetime import date, datetime, time

from iatb.core.clock import (
    MIS_CLOSE_TIMES,
    MIS_SUPPORTED_EXCHANGES,
    ProductType,
    TradingSessions,
)
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.exchange_calendar import ExchangeCalendar

logger = logging.getLogger(__name__)

# Asset types that require MIS enforcement
MIS_REQUIRED_ASSETS: frozenset[str] = frozenset({"STOCKS", "OPTIONS", "FUTURES", "CURRENCY_FO"})


def is_in_session(timestamp_utc: datetime, exchange: Exchange) -> bool:
    """Check if timestamp falls within trading session."""
    _validate_exchange(exchange)
    return TradingSessions.is_market_open(timestamp_utc, exchange)


def filter_timestamps_in_session(
    timestamps_utc: list[datetime],
    exchange: Exchange,
) -> list[datetime]:
    """Filter timestamps to only include those within trading session."""
    _validate_exchange(exchange)
    return [ts for ts in timestamps_utc if is_in_session(ts, exchange)]


def is_mis_trading_allowed(
    timestamp_utc: datetime,
    exchange: Exchange,
    asset_type: str,
) -> bool:
    """Check if MIS trading is allowed for given exchange/asset at timestamp."""
    _validate_exchange(exchange)
    TradingSessions._require_utc(timestamp_utc)

    if exchange not in MIS_SUPPORTED_EXCHANGES:
        logger.debug("Exchange does not support MIS", extra={"exchange": exchange.value})
        return False

    if asset_type.upper() not in MIS_REQUIRED_ASSETS:
        logger.debug("Asset type not in MIS-required set", extra={"asset_type": asset_type})
        return False

    return TradingSessions.is_mis_session_active(timestamp_utc, exchange)


def validate_trade_product(
    timestamp_utc: datetime,
    exchange: Exchange,
    asset_type: str,
    product_type: str,
) -> ProductType:
    """Validate product type for trade, blocking DELIVERY for MIS-required assets."""
    TradingSessions._require_utc(timestamp_utc)
    _validate_exchange(exchange)

    asset_upper = asset_type.upper()
    if asset_upper not in MIS_REQUIRED_ASSETS:
        logger.debug(
            "Asset not MIS-required, allowing any product",
            extra={"asset_type": asset_type, "product_type": product_type},
        )
        pt_upper = product_type.upper()
        if pt_upper in ProductType.__members__:
            return ProductType(pt_upper)
        return ProductType.MIS

    if exchange in MIS_SUPPORTED_EXCHANGES:
        if product_type.upper() == "CNC":
            msg = f"DELIVERY (CNC) blocked for {asset_type} on {exchange.value}"
            logger.warning(
                "DELIVERY trade blocked",
                extra={"exchange": exchange.value, "asset_type": asset_type},
            )
            raise ConfigError(msg)

        if product_type.upper() == "DELIVERY":
            msg = f"DELIVERY blocked for {asset_type} on {exchange.value}"
            logger.warning(
                "DELIVERY trade blocked",
                extra={"exchange": exchange.value, "asset_type": asset_type},
            )
            raise ConfigError(msg)

        if not is_mis_trading_allowed(timestamp_utc, exchange, asset_type):
            msg = f"MIS session not active for {asset_type} on {exchange.value}"
            raise ConfigError(msg)

    return TradingSessions.validate_product_type(product_type, exchange, timestamp_utc)


def get_mis_session_window(
    exchange: Exchange,
    trading_date: date,
    calendar: ExchangeCalendar | None = None,
) -> tuple[time, time] | None:
    """Get MIS session open and square-off times for given exchange/date."""
    _validate_exchange(exchange)

    if exchange not in MIS_SUPPORTED_EXCHANGES:
        return None

    cal = calendar or TradingSessions.calendar
    session = cal.session_for(exchange, trading_date)
    if session is None:
        return None

    mis_close = MIS_CLOSE_TIMES.get(exchange, session.close_time)
    return (session.open_time, mis_close)


def create_mis_session_mask(
    exchange: Exchange,
    start_date: date,
    end_date: date,
    calendar: ExchangeCalendar | None = None,
) -> list[date]:
    """Create list of dates with valid MIS sessions within date range."""
    _validate_exchange(exchange)

    if exchange not in MIS_SUPPORTED_EXCHANGES:
        return []

    cal = calendar or TradingSessions.calendar
    valid_dates: list[date] = []
    current = start_date

    while current <= end_date:
        window = get_mis_session_window(exchange, current, cal)
        if window is not None:
            valid_dates.append(current)
        if current.day < 28:
            current = date(current.year, current.month, current.day + 1)
        else:
            current = _next_date(current)

    return valid_dates


def _next_date(current: date) -> date:
    """Get next date handling month/year boundaries."""
    from datetime import timedelta

    return current + timedelta(days=1)


def _validate_exchange(exchange: Exchange) -> None:
    """Validate exchange supports session masking."""
    if exchange not in {Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS}:
        msg = f"Unsupported session exchange: {exchange.value}"
        raise ConfigError(msg)
