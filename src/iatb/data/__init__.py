"""
Data layer foundations for market data ingestion.
"""

from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.normalizer import normalize_ohlcv_batch, normalize_ohlcv_record
from iatb.data.validator import (
    validate_ohlcv_bar,
    validate_ohlcv_series,
    validate_ticker_snapshot,
)

__all__ = [
    "DataProvider",
    "OHLCVBar",
    "TickerSnapshot",
    "normalize_ohlcv_record",
    "normalize_ohlcv_batch",
    "validate_ohlcv_bar",
    "validate_ohlcv_series",
    "validate_ticker_snapshot",
]
