"""
Portfolio view helpers for dashboard rendering.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    quantity: Decimal
    average_price: Decimal
    current_price: Decimal

    @property
    def unrealized_pnl(self) -> Decimal:
        return (self.current_price - self.average_price) * self.quantity


def build_portfolio_snapshot(
    positions: list[PositionSnapshot],
    equity_curve: list[Decimal],
) -> dict[str, object]:
    if not equity_curve:
        msg = "equity_curve cannot be empty"
        raise ConfigError(msg)
    total_pnl = sum([position.unrealized_pnl for position in positions], Decimal("0"))
    drawdown_series = _drawdown_series(equity_curve)
    return {
        "position_count": len(positions),
        "total_unrealized_pnl": total_pnl,
        "max_drawdown": max(drawdown_series, default=Decimal("0")),
        "drawdown_series": drawdown_series,
    }


def _drawdown_series(equity_curve: list[Decimal]) -> list[Decimal]:
    peak = equity_curve[0]
    series: list[Decimal] = []
    for value in equity_curve:
        peak = max(peak, value)
        series.append((peak - value) / max(peak, Decimal("1")))
    return series
