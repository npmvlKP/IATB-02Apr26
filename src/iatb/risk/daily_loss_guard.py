"""
Daily loss guard with automatic kill-switch engagement.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.risk.kill_switch import KillSwitch

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DailyLossState:
    cumulative_pnl: Decimal
    limit: Decimal
    breached: bool
    trade_count: int


class DailyLossGuard:
    """Track intraday PnL and engage kill switch on breach."""

    def __init__(
        self,
        max_daily_loss_pct: Decimal,
        starting_nav: Decimal,
        kill_switch: KillSwitch,
    ) -> None:
        if max_daily_loss_pct <= Decimal("0") or max_daily_loss_pct > Decimal("1"):
            msg = "max_daily_loss_pct must be in (0, 1]"
            raise ConfigError(msg)
        if starting_nav <= Decimal("0"):
            msg = "starting_nav must be positive"
            raise ConfigError(msg)
        self._max_pct = max_daily_loss_pct
        self._limit = starting_nav * max_daily_loss_pct
        self._cumulative_pnl = Decimal("0")
        self._trade_count = 0
        self._kill_switch = kill_switch

    @property
    def state(self) -> DailyLossState:
        return DailyLossState(
            cumulative_pnl=self._cumulative_pnl,
            limit=self._limit,
            breached=self._cumulative_pnl <= -self._limit,
            trade_count=self._trade_count,
        )

    def record_trade(self, pnl: Decimal, now_utc: datetime) -> DailyLossState:
        """Add trade PnL. Auto-engage kill switch if limit breached."""
        _validate_utc(now_utc)
        self._cumulative_pnl += pnl
        self._trade_count += 1
        if self._cumulative_pnl <= -self._limit:
            logger.warning(
                "Daily loss limit breached: PnL=%s, limit=-%s",
                self._cumulative_pnl,
                self._limit,
            )
            self._kill_switch.engage(
                f"daily loss limit breached: {self._cumulative_pnl}",
                now_utc,
            )
        return self.state

    def reset(self, starting_nav: Decimal, now_utc: datetime) -> None:
        """Reset for new trading day."""
        _validate_utc(now_utc)
        if starting_nav <= Decimal("0"):
            msg = "starting_nav must be positive"
            raise ConfigError(msg)
        self._limit = starting_nav * self._max_pct
        self._cumulative_pnl = Decimal("0")
        self._trade_count = 0
        logger.info("Daily loss guard reset: NAV=%s, limit=%s", starting_nav, self._limit)


def _validate_utc(dt: datetime) -> None:
    if dt.tzinfo != UTC:
        msg = "datetime must be UTC"
        raise ConfigError(msg)
