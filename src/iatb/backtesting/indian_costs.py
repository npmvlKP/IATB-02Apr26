"""
Indian market transaction cost model for backtests.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from iatb.core.exceptions import ConfigError

MarketSegment = Literal["equity_delivery", "equity_intraday", "fo", "mcx"]

_SEBI_RATE = Decimal("0.000001")
_NSE_TXN_RATE = Decimal("0.0000297")
_MCX_TXN_RATE = Decimal("0.0000267")
_STAMP_DUTY_RATE = Decimal("0.00003")
_GST_RATE = Decimal("0.18")
_STT_BY_SEGMENT: dict[MarketSegment, Decimal] = {
    "equity_delivery": Decimal("0.001"),
    "equity_intraday": Decimal("0.00025"),
    "fo": Decimal("0.0001"),
    "mcx": Decimal("0.0001"),
}


@dataclass(frozen=True)
class CostBreakdown:
    stt: Decimal
    sebi: Decimal
    exchange_txn: Decimal
    stamp_duty: Decimal
    gst: Decimal
    total: Decimal


def calculate_indian_costs(notional: Decimal, segment: MarketSegment) -> CostBreakdown:
    if notional <= Decimal("0"):
        msg = "notional must be positive"
        raise ConfigError(msg)
    if segment not in _STT_BY_SEGMENT:
        msg = f"unsupported segment: {segment}"
        raise ConfigError(msg)
    stt = notional * _STT_BY_SEGMENT[segment]
    sebi = notional * _SEBI_RATE
    exchange_txn = notional * _exchange_rate(segment)
    stamp_duty = notional * _STAMP_DUTY_RATE
    gst = (exchange_txn + sebi) * _GST_RATE
    total = stt + sebi + exchange_txn + stamp_duty + gst
    return CostBreakdown(
        stt=stt,
        sebi=sebi,
        exchange_txn=exchange_txn,
        stamp_duty=stamp_duty,
        gst=gst,
        total=total,
    )


def _exchange_rate(segment: MarketSegment) -> Decimal:
    if segment == "mcx":
        return _MCX_TXN_RATE
    return _NSE_TXN_RATE
