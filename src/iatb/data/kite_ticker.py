"""
DEPRECATED: KiteTicker WebSocket feed for real-time market data.

This module is deprecated as of 2026-05-02. All functionality has been
consolidated into KiteWebSocketProvider which implements the DataProvider
protocol with enhanced features.

Migration guide:
- Replace: from iatb.data.kite_ticker import KiteTickerFeed
- With:     from iatb.data.kite_ws_provider import KiteWebSocketProvider
- Replace: KiteTickerFeed(api_key="...", access_token="...")
- With:     KiteWebSocketProvider(api_key="...", access_token="...")

The consolidated provider includes all KiteTickerFeed features:
- Auto-reconnect with exponential backoff
- Heartbeat monitoring for connection health
- Thread-safe tick buffer for scanner consumption
- Connection statistics and memory monitoring
- Symbol-to-exchange resolution via SymbolTokenResolver
- Full DataProvider protocol implementation for OHLCV data
"""

from __future__ import annotations

import warnings

from iatb.data.kite_ws_provider import (
    ConnectionStats,
    KiteWebSocketProvider,
    TickBuffer,
)

warnings.warn(
    "KiteTickerFeed is deprecated. Use KiteWebSocketProvider instead. "
    "This module will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Export for backward compatibility
KiteTickerFeed = KiteWebSocketProvider  # type: ignore[misc]

__all__ = [
    "KiteTickerFeed",
    "KiteWebSocketProvider",
    "ConnectionStats",
    "TickBuffer",
]
