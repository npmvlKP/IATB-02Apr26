"""
Test fixtures library for data provider tests.

Provides reusable fixtures for:
- Mock Kite Connect API responses
- Mock CCXT exchange responses
- Sample OHLCV data
- Sample ticker data
- Test provider instances
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import Exchange
from iatb.core.types import create_timestamp
from iatb.data.base import OHLCVBar, TickerSnapshot
from iatb.data.ccxt_provider import CCXTProvider
from iatb.data.kite_provider import KiteProvider


@pytest.fixture
def sample_kite_ohlcv_response():
    """Sample Kite Connect OHLCV API response."""
    return [
        {
            "date": datetime(2024, 4, 20, 9, 15, 0, tzinfo=UTC),
            "open": 1000.50,
            "high": 1025.75,
            "low": 995.00,
            "close": 1020.25,
            "volume": 1500000,
        },
        {
            "date": datetime(2024, 4, 21, 9, 15, 0, tzinfo=UTC),
            "open": 1020.25,
            "high": 1035.50,
            "low": 1015.00,
            "close": 1030.75,
            "volume": 1800000,
        },
        {
            "date": datetime(2024, 4, 22, 9, 15, 0, tzinfo=UTC),
            "open": 1030.75,
            "high": 1045.00,
            "low": 1025.50,
            "close": 1040.00,
            "volume": 2000000,
        },
    ]


@pytest.fixture
def sample_binance_ticker_response():
    """Sample Binance ticker API response."""
    return {
        "symbol": "BTCUSDT",
        "lastPrice": "50000.50",
        "bidPrice": "50000.00",
        "askPrice": "50001.00",
        "volume": "1500.25",
        "baseVolume": "1500.25",
        "quoteVolume": "75012500.00",
        "high": "50500.00",
        "low": "49500.00",
    }


@pytest.fixture
def sample_kite_ticker_response():
    """Sample Kite Connect ticker API response."""
    return {
        "NSE:RELIANCE": {
            "last_price": 1030.50,
            "bid": 1030.00,
            "ask": 1031.00,
            "volume": 1500000,
            "buy": 1030.00,
            "sell": 1031.00,
            "best_bid": 1030.00,
            "best_offer": 1031.00,
            "total_buy_qty": 1500000,
        }
    }


@pytest.fixture
def sample_ccxt_ohlcv_rows():
    """Sample CCXT OHLCV rows format."""
    return [
        [1735722900000, 100.0, 105.0, 95.0, 101.0, 1000],
        [1735722960000, 101.0, 106.0, 96.0, 102.0, 1200],
        [1735723020000, 102.0, 107.0, 97.0, 103.0, 1500],
    ]


@pytest.fixture
def sample_ohlcv_bars():
    """Sample OHLCVBar objects."""
    return [
        OHLCVBar(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            timestamp=create_timestamp(datetime(2024, 4, 20, 9, 15, 0, tzinfo=UTC)),
            open=Decimal("1000.50"),
            high=Decimal("1025.75"),
            low=Decimal("995.00"),
            close=Decimal("1020.25"),
            volume=Decimal("1500000"),
            source="kiteconnect",
        ),
        OHLCVBar(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            timestamp=create_timestamp(datetime(2024, 4, 21, 9, 15, 0, tzinfo=UTC)),
            open=Decimal("1020.25"),
            high=Decimal("1035.50"),
            low=Decimal("1015.00"),
            close=Decimal("1030.75"),
            volume=Decimal("1800000"),
            source="kiteconnect",
        ),
    ]


@pytest.fixture
def sample_ticker_snapshot():
    """Sample TickerSnapshot object."""
    return TickerSnapshot(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        bid=Decimal("1030.00"),
        ask=Decimal("1031.00"),
        last=Decimal("1030.50"),
        volume_24h=Decimal("1500000"),
        source="kiteconnect",
    )


@pytest.fixture
def mock_kite_client():
    """Mock KiteConnect client for testing."""
    client = MagicMock()
    client.historical_data.return_value = [
        {
            "date": datetime(2024, 4, 20, 9, 15, 0, tzinfo=UTC),
            "open": 1000.50,
            "high": 1025.75,
            "low": 995.00,
            "close": 1020.25,
            "volume": 1500000,
        },
        {
            "date": datetime(2024, 4, 21, 9, 15, 0, tzinfo=UTC),
            "open": 1020.25,
            "high": 1035.50,
            "low": 1015.00,
            "close": 1030.75,
            "volume": 1800000,
        },
    ]
    client.quote.return_value = {
        "NSE:RELIANCE": {
            "last_price": 1030.50,
            "bid": 1030.00,
            "ask": 1031.00,
            "volume": 1500000,
        }
    }
    return client


@pytest.fixture
def mock_ccxt_client():
    """Mock CCXT exchange client for testing."""
    client = MagicMock()
    client.fetch_ohlcv.return_value = [
        [1735722900000, 100.0, 105.0, 95.0, 101.0, 1000],
        [1735722960000, 101.0, 106.0, 96.0, 102.0, 1200],
    ]
    client.fetch_ticker.return_value = {
        "bid": 50000.00,
        "ask": 50001.00,
        "last": 50000.50,
        "baseVolume": 1500.25,
        "quoteVolume": 75012500.00,
        "high": 50500.00,
        "low": 49500.00,
        "close": 50000.50,
    }
    return client


@pytest.fixture
def kite_provider(mock_kite_client):
    """KiteProvider instance with mocked client."""
    return KiteProvider(
        api_key="test_key",
        access_token="test_token",
        kite_connect_factory=lambda k, t: mock_kite_client,
    )


@pytest.fixture
def ccxt_provider(mock_ccxt_client):
    """CCXTProvider instance with mocked client."""
    return CCXTProvider(exchange_factory=lambda _: mock_ccxt_client)


@pytest.fixture
def multi_day_kite_data():
    """30 days of mock Kite OHLCV data for backtesting."""
    now = datetime.now(UTC)
    bars = []
    for i in range(30):
        date = now - timedelta(days=30 - i)
        base_price = Decimal("1000.0")
        variation = Decimal(str(i * 10.0 + (i % 5) * 2.0))
        open_price = base_price + variation
        high_price = open_price * Decimal("1.02")
        low_price = open_price * Decimal("0.98")
        close_price = open_price + (variation * Decimal("0.01"))
        volume = 1000000 + (i * 50000)

        bars.append(
            {
                "date": date,
                "open": float(open_price),
                "high": float(high_price),
                "low": float(low_price),
                "close": float(close_price),
                "volume": float(volume),
            }
        )
    return bars


@pytest.fixture
def split_adjusted_kite_data():
    """Mock data simulating a 2:1 stock split."""
    split_date = datetime(2024, 1, 15, tzinfo=UTC)

    # Pre-split prices (higher)
    pre_split_bars = []
    for i in range(10):
        date = split_date - timedelta(days=10 - i)
        pre_split_bars.append(
            {
                "date": date,
                "open": 2000.0 + (i * 10),
                "high": 2050.0 + (i * 10),
                "low": 1950.0 + (i * 10),
                "close": 2030.0 + (i * 10),
                "volume": 500000,
            }
        )

    # Post-split prices (approximately half, adjusted)
    post_split_bars = []
    for i in range(20):
        date = split_date + timedelta(days=i)
        post_split_bars.append(
            {
                "date": date,
                "open": 1000.0 + (i * 5),
                "high": 1050.0 + (i * 5),
                "low": 950.0 + (i * 5),
                "close": 1030.0 + (i * 5),
                "volume": 1000000,
            }
        )

    return pre_split_bars + post_split_bars
