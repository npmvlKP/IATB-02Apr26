"""
Pytest configuration with deterministic random seeds for reproducibility.
"""

from __future__ import annotations

import os
import platform
import random
import sys as _sys
import tempfile
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from types import ModuleType
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if _sys.platform == "win32":
    try:
        import duckdb  # noqa: F401 — pre-import to share DLL across xdist forks
    except OSError:
        pass

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
    if _sys.modules.get("torch") is not None:
        try:
            import torch

            torch.manual_seed(DETERMINISTIC_SEED)
        except (OSError, RuntimeError):
            pass
    return


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
    ):
        setattr(st, name, MagicMock())
    monkeypatch.setitem(_sys.modules, "streamlit", st)
    return st


@pytest.fixture
def sample_ohlcv_bars() -> list:
    """Fixture providing valid OHLCVBar objects for reuse."""
    from iatb.core.enums import Exchange
    from iatb.core.types import create_price, create_quantity, create_timestamp
    from iatb.data.base import OHLCVBar

    return [
        OHLCVBar(
            timestamp=create_timestamp(datetime(2024, 1, 1, 9, 30 + i, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("5000"),
            source="unit-test",
        )
        for i in range(5)
    ]


@pytest.fixture
def sample_ticker_snapshot() -> object:
    """Fixture providing valid TickerSnapshot."""
    from iatb.core.enums import Exchange
    from iatb.core.types import create_price, create_quantity, create_timestamp
    from iatb.data.base import TickerSnapshot

    return TickerSnapshot(
        timestamp=create_timestamp(datetime.now(UTC)),
        exchange=Exchange.NSE,
        symbol="AAPL",
        bid=create_price("149.95"),
        ask=create_price("150.05"),
        last=create_price("150.00"),
        volume_24h=create_quantity("1000000"),
        source="unit-test",
    )


@pytest.fixture
def sample_market_tick_event() -> dict:
    """Fixture providing valid MarketTickEvent."""
    return {
        "symbol": "NIFTY50",
        "price": Decimal("22500.50"),
        "timestamp": datetime.now(UTC),
    }


@pytest.fixture
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


@pytest.fixture
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


@pytest.fixture
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


@pytest.fixture
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


@pytest.fixture
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


@pytest.fixture
def freeze_time() -> Generator[None, None, None]:
    """Freeze time for retention/cleanup tests."""
    from freezegun import freeze_time as _freeze_time

    with _freeze_time(datetime(2026, 5, 11, tzinfo=UTC)):
        yield


@pytest.fixture
def mock_pyarrow_compression(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock pyarrow.parquet with compression support."""
    import pyarrow as pa

    mock_parquet = MagicMock()
    mock_table = MagicMock()
    mock_parquet.read_table.return_value = mock_table
    mock_table.to_pydict.return_value = {
        "exchange": ["NSE"],
        "symbol": ["BANKNIFTY"],
        "timestamp_utc": ["2026-01-01T09:15:00+00:00"],
        "open_price": ["100.00"],
        "high_price": ["101.00"],
        "low_price": ["99.00"],
        "close_price": ["100.50"],
        "volume": ["1500"],
        "source": ["unit-test"],
    }
    monkeypatch.setattr(pa, "parquet", mock_parquet)
    return mock_parquet


def pytest_xdist_auto_num_workers(config: object) -> int:
    """Limit xdist workers on Windows to avoid DuckDB DLL exhaustion."""
    if platform.system() == "Windows":
        return 6
    return os.cpu_count() or 4


if platform.system() == "Windows":
    _SHORT_TMP = os.path.abspath(
        os.path.join(os.environ.get("SYSTEMDRIVE", "C:"), os.sep, "t")
    )

    if not os.path.isdir(_SHORT_TMP):
        try:
            os.makedirs(_SHORT_TMP, exist_ok=True)
        except OSError:
            _SHORT_TMP = tempfile.gettempdir()

    def pytest_configure(config: pytest.Config) -> None:
        """Override basetemp on Windows with a short path to prevent MAX_PATH issues."""
        from pathlib import Path

        short_basetemp = Path(_SHORT_TMP) / "pt"
        config.option.basetemp = str(short_basetemp)
