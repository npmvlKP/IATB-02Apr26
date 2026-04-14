"""
Tests for normalized data contracts.
"""

import random
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.types import create_price
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class DummyProvider:
    """Minimal provider implementation for protocol checks."""

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: datetime | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        _ = timeframe, since, limit
        return [OHLCVBar(symbol=symbol, exchange=exchange, source="dummy")]

    async def get_ticker(
        self,
        *,
        symbol: str,
        exchange: Exchange,
    ) -> TickerSnapshot:
        return TickerSnapshot(
            symbol=symbol,
            exchange=exchange,
            bid=create_price("99"),
            ask=create_price("101"),
            last=create_price("100"),
            source="dummy",
        )

    async def get_ohlcv_batch(
        self,
        *,
        symbols: list[str],
        exchange: Exchange,
        timeframe: str,
        since: datetime | None = None,
        limit: int = 500,
    ) -> dict[str, list[OHLCVBar]]:
        _ = timeframe, since, limit
        return {
            symbol: [OHLCVBar(symbol=symbol, exchange=exchange, source="dummy")]
            for symbol in symbols
        }


class TestDataContracts:
    """Test normalized data models and provider protocol."""

    def test_ohlcv_bar_defaults_use_utc_timestamp(self) -> None:
        bar = OHLCVBar()
        assert bar.timestamp.tzinfo == UTC
        assert isinstance(bar.timestamp, datetime)

    def test_ticker_snapshot_defaults_use_utc_timestamp(self) -> None:
        ticker = TickerSnapshot()
        assert ticker.timestamp.tzinfo == UTC
        assert isinstance(ticker.timestamp, datetime)

    def test_ohlcv_bar_is_frozen(self) -> None:
        bar = OHLCVBar()
        with pytest.raises(FrozenInstanceError):  # noqa: B017
            bar.symbol = "NIFTY"  # type: ignore[misc]

    def test_provider_runtime_protocol(self) -> None:
        provider = DummyProvider()
        assert isinstance(provider, DataProvider)
