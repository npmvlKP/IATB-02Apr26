"""Conftest for integration tests - auto-mock market session checks.

Integration tests run outside market hours, so Gate 6 (market session
validation) must be bypassed to allow orders to flow through the pipeline.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _skip_market_session_check() -> Any:
    """Auto-skip Gate 6 market session validation for all integration tests.

    Integration tests run 24/7 (including outside IST market hours
    09:15-15:30). Without this fixture, any test calling
    OrderManager.place_order would fail with ConfigError:
    'outside market session'.
    """
    with patch(
        "iatb.execution.pre_trade_validator._check_market_session",
        lambda *a, **kw: None,
    ):
        yield
