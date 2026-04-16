"""
Data layer foundations for market data ingestion.
"""

from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.ccxt_provider import CCXTProvider
from iatb.data.instrument import (
    Instrument,
    InstrumentProvider,
    InstrumentType,
    map_kite_instrument_type,
)
from iatb.data.instrument_master import InstrumentMaster
from iatb.data.jugaad_provider import JugaadProvider
from iatb.data.kite_provider import KiteProvider
from iatb.data.normalizer import normalize_ohlcv_batch, normalize_ohlcv_record
from iatb.data.openalgo_provider import OpenAlgoProvider
from iatb.data.token_resolver import SymbolTokenResolver
from iatb.data.validator import (
    validate_ohlcv_bar,
    validate_ohlcv_series,
    validate_ticker_snapshot,
)
from iatb.data.yfinance_provider import YFinanceProvider

__all__ = [
    "DataProvider",
    "OHLCVBar",
    "TickerSnapshot",
    "YFinanceProvider",
    "JugaadProvider",
    "CCXTProvider",
    "OpenAlgoProvider",
    "KiteProvider",
    "normalize_ohlcv_record",
    "normalize_ohlcv_batch",
    "validate_ohlcv_bar",
    "validate_ohlcv_series",
    "validate_ticker_snapshot",
    "Instrument",
    "InstrumentType",
    "InstrumentProvider",
    "InstrumentMaster",
    "map_kite_instrument_type",
    "SymbolTokenResolver",
]
