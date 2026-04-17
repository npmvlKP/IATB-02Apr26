#!/usr/bin/env python3
"""Comprehensive script to fix all G10 function size violations."""

import re
from pathlib import Path

def read_file(filepath: Path) -> str:
    """Read file content."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

def write_file(filepath: Path, content: str) -> None:
    """Write file content."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

def refactor_kite_provider_get_ohlcv(content: str) -> str:
    """Refactor get_ohlcv to extract helper methods."""
    # Find the method
    pattern = r'(    async def get_ohlcv\(\n        self,\n        \*,\n        symbol: str,\n        exchange: Exchange,\n        timeframe: str,\n        since: Timestamp \| None = None,\n        limit: int = 500,\n    \) -> list\[OHLCVBar\]:\n        """Fetch OHLCV bars from Kite Connect historical data endpoint\.\n\n        Args:\n            symbol: Trading symbol \(e\.g\., "RELIANCE"\)\.\n            exchange: Exchange \(NSE, BSE, MCX, or CDS\)\.\n            timeframe: Timeframe \(1m, 5m, 15m, 30m, 1h, 1d\)\.\n            since: Optional timestamp to filter from\.\n            limit: Maximum number of bars to return\.\n\n        Returns:\n            List of normalized OHLCVBar objects\.\n\n        Raises:\n            ConfigError: If exchange/timeframe unsupported or API errors occur\.\n        """\n)(.*?)(\n    async def get_ticker)'
    
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return content
    
    # Replace the method body
    new_body = '''        self._validate_ohlcv_params(limit)

        kite_interval, trading_symbol = self._prepare_ohlcv_request(symbol, exchange, timeframe)
        start_date, end_date = self._calculate_date_range(since, limit)

        client = self._get_client()
        data = await self._fetch_with_retry(client, trading_symbol, kite_interval, start_date, end_date)

        return self._process_and_normalize(data, symbol, exchange, since, limit)

    def _validate_ohlcv_params(self, limit: int) -> None:
        """Validate OHLCV parameters."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ConfigError(msg)

    def _prepare_ohlcv_request(self, symbol: str, exchange: Exchange, timeframe: str) -> tuple[str, str]:
        """Prepare Kite API request parameters."""
        _ensure_supported_exchange(exchange)
        kite_interval = _map_timeframe(timeframe)
        trading_symbol = _format_trading_symbol(symbol, exchange)
        return kite_interval, trading_symbol

    def _calculate_date_range(self, since: Timestamp | None, limit: int) -> tuple[datetime, datetime]:
        """Calculate start and end dates for historical data query."""
        end_date = datetime.now(UTC)
        if since is not None:
            start_date = datetime(since.year, since.month, since.day, tzinfo=UTC)
        else:
            start_date = end_date - timedelta(days=limit)
        return start_date, end_date

    async def _fetch_with_retry(
        self,
        client: Any,
        trading_symbol: str,
        kite_interval: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, object]]:
        """Fetch historical data with retry logic."""
        return await self._retry_with_backoff(
            self._fetch_historical_data,
            client,
            trading_symbol,
            kite_interval,
            start_date,
            end_date,
        )

    def _process_and_normalize(
        self,
        data: list[dict[str, object]],
        symbol: str,
        exchange: Exchange,
        since: Timestamp | None,
        limit: int,
    ) -> list[OHLCVBar]:
        """Process and normalize OHLCV data."""
        records = self._build_ohlcv_records(data, since=since)
        clipped = records[-limit:] if len(records) > limit else records
        return normalize_ohlcv_batch(
            clipped,
            symbol=symbol,
            exchange=exchange,
            source="kiteconnect",
        )
'''
    
    # Build the new method signature
    sig = '''    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """Fetch OHLCV bars from Kite Connect historical data endpoint.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").
            exchange: Exchange (NSE, BSE, MCX, or CDS).
            timeframe: Timeframe (1m, 5m, 15m, 30m, 1h, 1d).
            since: Optional timestamp to filter from.
            limit: Maximum number of bars to return.

        Returns:
            List of normalized OHLCVBar objects.

        Raises:
            ConfigError: If exchange/timeframe unsupported or API errors occur.
        """
'''
    
    new_content = content[:match.start()] + sig + new_body + '\n' + match.group(3)
    return new_content

def main():
    """Main function."""
    print("Fixing G10 violations...")
    
    # Process kite_provider.py
    kite_provider_path = Path("src/iatb/data/kite_provider.py")
    if kite_provider_path.exists():
        print(f"Processing {kite_provider_path}...")
        content = read_file(kite_provider_path)
        content = refactor_kite_provider_get_ohlcv(content)
        write_file(kite_provider_path, content)
        print(f"✓ Fixed get_ohlcv in {kite_provider_path}")
    
    print("\nDone! Run 'python check_g7_g8_g9_g10.py' to verify.")

if __name__ == "__main__":
    main()