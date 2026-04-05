"""
Order-per-second throttle per SEBI 10 OPS threshold.
"""

import logging
from datetime import UTC, datetime

from iatb.core.exceptions import ConfigError

logger = logging.getLogger(__name__)

_DEFAULT_MAX_OPS = 10


class OrderThrottle:
    """Reject orders exceeding the configured OPS limit."""

    def __init__(self, max_ops: int = _DEFAULT_MAX_OPS) -> None:
        if max_ops <= 0:
            msg = "max_ops must be positive"
            raise ConfigError(msg)
        self._max_ops = max_ops
        self._current_second: int = 0
        self._count: int = 0

    def check_and_record(self, now_utc: datetime) -> bool:
        """Return True if order is allowed. Rejects if OPS exceeded."""
        if now_utc.tzinfo != UTC:
            msg = "now_utc must be UTC"
            raise ConfigError(msg)
        second = int(now_utc.timestamp())
        if second != self._current_second:
            self._current_second = second
            self._count = 0
        self._count += 1
        if self._count > self._max_ops:
            logger.warning(
                "OPS throttle: %d orders in second %d (max %d)",
                self._count,
                second,
                self._max_ops,
            )
            return False
        return True

    @property
    def current_count(self) -> int:
        return self._count
