"""
Pytest configuration with deterministic random seeds for reproducibility.
"""

from __future__ import annotations

import random
import sys as _sys
from collections.abc import Generator
from datetime import UTC
from decimal import Decimal
from types import ModuleType
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path

# Fixed seed value for reproducibility across all tests
DETERMINISTIC_SEED: int = 42


@pytest.fixture(autouse=True)
def set_deterministic_seeds() -> Generator[None, None, None]:
    """Fixture that sets deterministic seeds for all random number generators."""
    random.seed(DETERMINISTIC_SEED)
    try:
        import numpy as np

        np.random.seed(DETERMINISTIC_SEED)
    except ImportError:
        pass
    yield


# ---------------------------------------------------------------------------
# Shared Infrastructure Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_storage_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for DuckDB/SQLite/Parquet/file tests."""
    return tmp_path


@pytest.fixture
def mock_kite_client() -> MagicMock:
    """Pre-configured mock of KiteConnect with historical_data/quote stubs."""
    client = MagicMock()
    client.historical_data = MagicMock(return_value=[])
    client.quote = MagicMock(return_value={})
    return client


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Pre-configured mock EventBus with subscribe/publish stubs."""
    bus = MagicMock()
    bus.subscribe = MagicMock(return_value=None)
    bus.publish = AsyncMock(return_value=None)
    return bus


@pytest.fixture
def mock_redis_client() -> MagicMock:
    """Pre-configured mock of redis.asyncio.Redis."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=None)
    return redis


@pytest.fixture
def mock_streamlit(monkeypatch: pytest.MonkeyPatch) -> Generator[MagicMock, None, None]:
    """Pre-configured mock of streamlit module with all UI methods."""
    st = ModuleType("streamlit")
    for name in (
        "title",
        "header",
        "text",
        "write",
        "table",
        "dataframe",
        "chart",
        "plotly_chart",
        "button",
        "selectbox",
        "text_input",
        "number_input",
        "slider",
        "checkbox",
        "radio",
        "sidebar",
        "columns",
        "expander",
        "metric",
        "progress",
        "spinner",
        "warning",
        "error",
        "info",
    ):
        setattr(st, name, MagicMock())
    monkeypatch.setitem(_sys.modules, "streamlit", st)
    yield st


@pytest.fixture
def sample_ohlcv_bars() -> list[dict]:
    """Fixture providing valid OHLCVBar-like list for reuse."""
    from datetime import datetime

    return [
        {
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
            "open_": Decimal("100"),
            "high": Decimal("101"),
            "low": Decimal("99"),
            "close": Decimal("100.5"),
            "volume": Decimal("5000"),
        }
        for _ in range(5)
    ]


@pytest.fixture
def sample_ticker_snapshot() -> dict:
    """Fixture providing valid TickerSnapshot."""
    from datetime import datetime

    return {
        "ticker": "AAPL",
        "last_price": Decimal("150.00"),
        "bid": Decimal("149.95"),
        "ask": Decimal("150.05"),
        "volume": 1_000_000,
        "timestamp": datetime.now(UTC),
    }


@pytest.fixture
def sample_market_tick_event() -> dict:
    """Fixture providing valid MarketTickEvent."""
    from datetime import datetime

    return {
        "symbol": "NIFTY50",
        "price": Decimal("22500.50"),
        "timestamp": datetime.now(UTC),
    }


@pytest.fixture
def sample_order_update_event() -> dict:
    """Fixture providing valid OrderUpdateEvent."""
    from datetime import datetime

    return {
        "order_id": "ORD-12345",
        "status": "FILLED",
        "filled_qty": Decimal("10"),
        "avg_price": Decimal("150.00"),
        "timestamp": datetime.now(UTC),
    }
