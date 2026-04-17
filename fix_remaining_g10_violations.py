#!/usr/bin/env python3
"""
Complete G10 violation fix script.

This script refactors all functions exceeding 50 LOC into smaller,
more maintainable functions by extracting helper methods.
"""

import re
from pathlib import Path
from typing import Callable

def read_file(filepath: Path) -> str:
    """Read file content."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

def write_file(filepath: Path, content: str) -> None:
    """Write file content."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

def extract_function(content: str, func_name: str, class_name: str | None = None) -> tuple[str, int, int] | None:
    """Extract function signature and body by searching for it."""
    # Find the function definition
    pattern = rf'(    (async )?def {func_name}\(.*?\) -> .*?:\n)(.*?)(\n    (def|async|@|class)|\Z)'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        start = match.start()
        end = match.end()
        return (match.group(0), start, end)
    
    return None

def refactor_get_ohlcv(content: str) -> str:
    """Refactor KiteProvider.get_ohlcv."""
    # Find the function signature
    sig_pattern = r'(    async def get_ohlcv\(\n        self,\n        \*,\n        symbol: str,\n        exchange: Exchange,\n        timeframe: str,\n        since: Timestamp \| None = None,\n        limit: int = 500,\n    \) -> list\[OHLCVBar\]:\n)(.*?)(\n    async def get_ticker)'
    
    match = re.search(sig_pattern, content, re.DOTALL)
    if not match:
        print("  Warning: Could not find get_ohlcv function")
        return content
    
    sig = match.group(1)
    body = match.group(2)
    next_func = match.group(3)
    
    # New refactored body
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
    
    # Replace
    start_idx = match.start()
    end_idx = match.end()
    new_content = content[:start_idx] + sig + new_body + next_func + content[end_idx:]
    
    return new_content

def refactor_get_ticker(content: str) -> str:
    """Refactor KiteProvider.get_ticker."""
    # Find the function
    pattern = r'(    async def get_ticker\(\n        self,\n        \*,\n        symbol: str,\n        exchange: Exchange,\n    \) -> TickerSnapshot:\n)(.*?)(\n    async def _retry_with_backoff)'
    
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print("  Warning: Could not find get_ticker function")
        return content
    
    sig = match.group(1)
    next_func = match.group(3)
    
    new_body = '''        _ensure_supported_exchange(exchange)
        trading_symbol = _format_trading_symbol(symbol, exchange)

        client = self._get_client()
        quote_data = await self._fetch_quote_with_retry(client, trading_symbol)

        snapshot = self._extract_ticker_snapshot(quote_data, trading_symbol, symbol, exchange)
        validate_ticker_snapshot(snapshot)
        return snapshot

    async def _fetch_quote_with_retry(self, client: Any, trading_symbol: str) -> dict[str, Any]:
        """Fetch quote data with retry logic."""
        return await self._retry_with_backoff(
            self._fetch_quote,
            client,
            trading_symbol,
        )

    def _extract_ticker_snapshot(
        self,
        quote_data: dict[str, Any],
        trading_symbol: str,
        symbol: str,
        exchange: Exchange,
    ) -> TickerSnapshot:
        """Extract ticker snapshot from quote data."""
        quote = quote_data.get(trading_symbol, {})

        bid = _coerce_numeric_input(
            _extract_numeric(quote, ("bid", "buy", "best_bid")),
            field_name="bid",
        )
        ask = _coerce_numeric_input(
            _extract_numeric(quote, ("ask", "sell", "best_offer")),
            field_name="ask",
        )
        last = _coerce_numeric_input(
            _extract_numeric(quote, ("last_price", "last")),
            field_name="last_price",
        )
        volume = _coerce_numeric_input(
            _extract_numeric(quote, ("volume", "total_buy_qty")),
            field_name="volume",
        )

        return TickerSnapshot(
            exchange=exchange,
            symbol=symbol,
            bid=create_price(bid),
            ask=create_price(ask),
            last=create_price(last),
            volume_24h=create_quantity(volume),
            source="kiteconnect",
        )
'''
    
    start_idx = match.start()
    end_idx = match.end()
    new_content = content[:start_idx] + sig + new_body + next_func + content[end_idx:]
    
    return new_content

def refactor_retry_with_backoff(content: str) -> str:
    """Refactor KiteProvider._retry_with_backoff."""
    pattern = r'(    async def _retry_with_backoff\(\n        self,\n        func: Callable\[\.\.\., Any\],\n        \*args: object,\n    \) -> Any:\n)(.*?)(\n    async def _fetch_historical_data)'
    
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        print("  Warning: Could not find _retry_with_backoff function")
        return content
    
    sig = match.group(1)
    next_func = match.group(3)
    
    new_body = '''        attempt = 0
        delay = self._initial_retry_delay

        for attempt in range(self._max_retries + 1):
            try:
                await self._rate_limiter.acquire()
                result = await func(*args)
                return result
            except Exception as exc:
                if not self._is_retryable_error(exc):
                    raise ConfigError(f"Kite API error: {exc}") from exc

                if attempt >= self._max_retries:
                    msg = f"Kite API failed after {self._max_retries} retries: {exc}"
                    raise ConfigError(msg) from exc

                await asyncio.sleep(delay)
                delay *= _RETRY_BACKOFF_MULTIPLIER

        raise ConfigError("Kite API error")

    def _is_retryable_error(self, exc: Exception) -> bool:
        """Check if error is retryable (rate limit or server error)."""
        error_str = str(exc).lower()
        is_rate_limit = "429" in error_str or "rate limit" in error_str
        is_server_error = any(code in error_str for code in ("500", "502", "503", "504"))
        return is_rate_limit or is_server_error
'''
    
    start_idx = match.start()
    end_idx = match.end()
    new_content = content[:start_idx] + sig + new_body + next_func + content[end_idx:]
    
    return new_content

def main():
    """Main execution function."""
    print("=" * 80)
    print("G10 Violation Fix Script")
    print("=" * 80)
    
    # Process kite_provider.py
    kite_provider = Path("src/iatb/data/kite_provider.py")
    if kite_provider.exists():
        print(f"\nProcessing {kite_provider}...")
        content = read_file(kite_provider)
        
        print("  - Refactoring get_ohlcv...")
        content = refactor_get_ohlcv(content)
        
        print("  - Refactoring get_ticker...")
        content = refactor_get_ticker(content)
        
        print("  - Refactoring _retry_with_backoff...")
        content = refactor_retry_with_backoff(content)
        
        write_file(kite_provider, content)
        print(f"✓ Completed {kite_provider}")
    
    print("\n" + "=" * 80)
    print("Refactoring complete!")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Run: python check_g7_g8_g9_g10.py")
    print("2. If G10 passes, run: poetry run ruff format src/")
    print("3. Then run: poetry run ruff check src/")
    print("4. Finally run: poetry run pytest tests/")

if __name__ == "__main__":
    main()