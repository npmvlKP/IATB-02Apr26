"""
Pytest configuration with deterministic random seeds for reproducibility.
"""

from __future__ import annotations

import random
import sys as _sys
from collections.abc import Generator
from datetime import UTC, datetime
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
    return


# ---------------------------------------------------------------------------
# Shared Infrastructure Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_storage_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for DuckDB/SQLite/Parquet/file tests."""
    return tmp_path


@pytest.fixture()
def mock_kite_client() -> MagicMock:
    """Pre-configured mock of KiteConnect with historical_data/quote stubs."""
    client = MagicMock()
    client.historical_data = MagicMock(return_value=[])
    client.quote = MagicMock(return_value={})
    return client


@pytest.fixture()
def mock_event_bus() -> MagicMock:
    """Pre-configured mock EventBus with subscribe/publish stubs."""
    bus = MagicMock()
    bus.subscribe = MagicMock(return_value=None)
    bus.publish = AsyncMock(return_value=None)
    return bus


@pytest.fixture()
def mock_redis_client() -> MagicMock:
    """Pre-configured mock of redis.asyncio.Redis."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=None)
    return redis


@pytest.fixture()
def mock_streamlit(monkeypatch: pytest.MonkeyPatch) -> Generator[MagicMock, None, None]:
    """Pre-configured mock of streamlit module with all UI methods."""
    st = ModuleType("streamlit")
    for name in (
        "title",
        "header",
        "subheader",
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
        "divider",
    ):
        setattr(st, name, MagicMock())
    monkeypatch.setitem(_sys.modules, "streamlit", st)
    return st


@pytest.fixture()
def sample_ohlcv_bars() -> list[dict[str, object]]:
    """Fixture providing valid OHLCVBar dicts for reuse."""
    return [
        {
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
            "open": Decimal("100.00"),
            "high": Decimal("101.00"),
            "low": Decimal("99.00"),
            "close": Decimal("100.50"),
            "volume": Decimal("5000"),
        }
        for _ in range(5)
    ]


@pytest.fixture()
def sample_kite_historical_data() -> list[dict[str, object]]:
    """Fixture providing raw Kite API historical_data response dicts."""
    return [
        {
            "date": datetime(2024, 1, i + 1, 9, 15, tzinfo=UTC),
            "open": 100.0 + i,
            "high": 105.0 + i,
            "low": 98.0 + i,
            "close": 103.0 + i,
            "volume": 1_000_000 + i * 50_000,
        }
        for i in range(5)
    ]


@pytest.fixture()
def sample_kite_quote_data() -> dict[str, dict[str, object]]:
    """Fixture providing raw Kite API quote response dict."""
    return {
        "NSE:RELIANCE": {
            "last_price": Decimal("2450.50"),
            "bid": Decimal("2450.00"),
            "ask": Decimal("2451.00"),
            "volume": 1_500_000,
        }
    }


@pytest.fixture()
def sample_ticker_snapshot() -> dict:
    """Fixture providing valid TickerSnapshot."""
    return {
        "ticker": "AAPL",
        "last_price": Decimal("150.00"),
        "bid": Decimal("149.95"),
        "ask": Decimal("150.05"),
        "volume": 1_000_000,
        "timestamp": datetime.now(UTC),
    }


@pytest.fixture()
def sample_market_tick_event() -> dict:
    """Fixture providing valid MarketTickEvent."""
    return {
        "symbol": "NIFTY50",
        "price": Decimal("22500.50"),
        "timestamp": datetime.now(UTC),
    }


@pytest.fixture()
def sample_order_update_event() -> dict:
    """Fixture providing valid OrderUpdateEvent."""
    return {
        "order_id": "ORD-12345",
        "status": "FILLED",
        "filled_qty": Decimal("10"),
        "avg_price": Decimal("150.00"),
        "timestamp": datetime.now(UTC),
    }


def _event_stub(event_type_name: str, **attrs: object) -> object:
    """Create a lightweight dynamic object for branch testing."""
    event_type = type(event_type_name, (), {})
    instance = event_type()
    for key, value in attrs.items():
        setattr(instance, key, value)
    return instance


@pytest.fixture()
def sample_signal_event() -> object:
    """Fixture providing valid SignalEvent."""
    from iatb.core.enums import Exchange, OrderSide

    return _event_stub(
        "SignalEvent",
        timestamp=datetime.now(UTC),
        strategy_id="STRATEGY-001",
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        price=Decimal("100.50"),
        confidence=Decimal("0.75"),
    )


@pytest.fixture()
def sample_scan_update_event() -> object:
    """Fixture providing valid ScanUpdateEvent."""
    return _event_stub(
        "ScanUpdateEvent",
        timestamp=datetime.now(UTC),
        total_candidates=100,
        approved_candidates=80,
        trades_executed=50,
        duration_ms=1000,
        errors=[],
    )


@pytest.fixture()
def sample_pnl_update_event() -> object:
    """Fixture providing valid PnLUpdateEvent."""
    return _event_stub(
        "PnLUpdateEvent",
        timestamp=datetime.now(UTC),
        order_id="ORD-12345",
        symbol="RELIANCE",
        side="BUY",
        quantity=Decimal("100"),
        price=Decimal("100.50"),
        trade_pnl=Decimal("-50.00"),
        cumulative_pnl=Decimal("1000.00"),
    )


@pytest.fixture()
def sample_regime_change_event() -> object:
    """Fixture providing valid RegimeChangeEvent."""
    return _event_stub(
        "RegimeChangeEvent",
        timestamp=datetime.now(UTC),
        regime_type="VOLATILITY_SPIKE",
        description="Volatility increasing",
        confidence=Decimal("0.85"),
        metadata={"key1": "value1", "key2": "value2"},
    )


@pytest.fixture()
def sample_strength_inputs() -> dict[str, object]:
    """Fixture providing valid StrengthInputs kwargs for reuse."""
    from iatb.market_strength.regime_detector import MarketRegime

    return {
        "breadth_ratio": Decimal("1.0"),
        "regime": MarketRegime.SIDEWAYS,
        "adx": Decimal("20"),
        "volume_ratio": Decimal("1.0"),
        "volatility_atr_pct": Decimal("0.03"),
    }


@pytest.fixture()
def utc_now() -> datetime:
    """Fixture providing deterministic UTC datetime for tests."""
    return datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
