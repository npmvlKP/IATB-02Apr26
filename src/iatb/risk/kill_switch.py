"""
Kill switch for immediate trading halt.

Engages on command or automatic trigger, cancels all open orders,
blocks new orders, and fires an alert callback.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from iatb.core.exceptions import ConfigError
from iatb.core.observability.alerting import get_alerter
from iatb.execution.base import Executor

logger = logging.getLogger(__name__)

EngageCallback = Callable[[str, datetime], None]


@dataclass(frozen=True)
class KillSwitchState:
    engaged: bool
    reason: str
    triggered_utc: datetime | None


class KillSwitch:
    """Immediate trading halt with cancel-all and alert dispatch."""

    def __init__(
        self,
        executor: Executor,
        on_engage: EngageCallback | None = None,
    ) -> None:
        self._executor = executor
        self._on_engage = on_engage or self._default_engage_callback
        self._engaged = False
        self._reason = ""
        self._triggered_utc: datetime | None = None

    def _default_engage_callback(self, reason: str, engaged_utc: datetime) -> None:
        """Default callback to send kill switch alert via Telegram.

        Args:
            reason: Reason for kill switch engagement.
            engaged_utc: UTC timestamp when kill switch was engaged.
        """
        try:
            alerter = get_alerter()
            alerter.send_kill_switch_alert(reason, engaged_utc)
        except Exception as exc:
            logger.error("Failed to send kill switch alert: %s", exc)

    @property
    def is_engaged(self) -> bool:
        return self._engaged

    @property
    def state(self) -> KillSwitchState:
        return KillSwitchState(
            engaged=self._engaged,
            reason=self._reason,
            triggered_utc=self._triggered_utc,
        )

    def check_order_allowed(self) -> bool:
        """Return False when kill switch is engaged."""
        return not self._engaged

    def engage(self, reason: str, now_utc: datetime) -> KillSwitchState:
        """Engage kill switch: cancel all orders, block new ones."""
        _validate_utc(now_utc)
        if not reason.strip():
            msg = "kill switch reason cannot be empty"
            raise ConfigError(msg)
        if self._engaged:
            return self.state
        self._engaged = True
        self._reason = reason
        self._triggered_utc = now_utc
        cancelled = self._executor.cancel_all()
        logger.critical(
            "KILL SWITCH ENGAGED: %s (cancelled %d orders)",
            reason,
            cancelled,
        )
        if self._on_engage is not None:
            self._on_engage(reason, now_utc)
        return self.state

    def disengage(self, now_utc: datetime) -> KillSwitchState:
        """Manual reset. Requires explicit call — never auto-resets."""
        _validate_utc(now_utc)
        if not self._engaged:
            return self.state
        logger.warning("Kill switch disengaged at %s", now_utc.isoformat())
        self._engaged = False
        self._reason = ""
        self._triggered_utc = None
        return self.state


def _validate_utc(dt: datetime) -> None:
    if dt.tzinfo != UTC:
        msg = "datetime must be UTC"
        raise ConfigError(msg)
