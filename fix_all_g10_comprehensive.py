#!/usr/bin/env python3
"""
Comprehensive G10 violation fix script.
Fixes all 8 function size violations by extracting helper methods.
"""

import ast
import re
from pathlib import Path
from typing import Any

def read_file(filepath: Path) -> str:
    """Read file content."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

def write_file(filepath: Path, content: str) -> None:
    """Write file content."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

def find_function_body(content: str, func_name: str, class_name: str | None = None) -> tuple[int, int] | None:
    """Find function body start and end positions using AST."""
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                return (node.lineno, node.end_lineno if node.end_lineno else node.lineno)
        return None
    except SyntaxError:
        return None

def fix_kite_provider_init(content: str) -> str:
    """Fix KiteProvider.__init__ (54 LOC -> <50)."""
    # Find the __init__ method and extract validation
    pattern = r'(    def __init__\(\n        self,\n        \*,\n        api_key: str,\n        access_token: str,\n        kite_connect_factory: Callable\[\[str, str\], Any\] \| None = None,\n        max_retries: int = _MAX_RETRIES,\n        initial_retry_delay: float = _INITIAL_RETRY_DELAY,\n        requests_per_second: int = _RATE_LIMIT_REQUESTS,\n    \) -> None:\n        """Initialize Kite Connect provider\.\n\n        Args:\n            api_key: Kite Connect API key\.\n            access_token: Kite Connect access token\.\n            kite_connect_factory: Optional factory for creating KiteConnect instance\.\n                Useful for testing/mocking\.\n            max_retries: Maximum number of retry attempts for failed requests\.\n            initial_retry_delay: Initial delay in seconds before first retry\.\n            requests_per_second: Rate limit in requests per second\.\n\n        Raises:\n            ConfigError: If api_key or access_token is empty, or if parameters invalid\.\n        """\n)'
    
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return content
    
    sig = match.group(1)
    
    # Find the validation block (first 5 if statements)
    after_sig = content[match.end():]
    validation_end = after_sig.find('\n\n        self._api_key = api_key')
    if validation_end == -1:
        return content
    
    validation_block = after_sig[:validation_end]
    rest = after_sig[validation_end:]
    
    # Replace validation with method call
    new_body = f'''        self._validate_init_params(api_key, access_token, max_retries, initial_retry_delay, requests_per_second)
        
{rest}'''
    
    content = content[:match.end()] + new_body
    
    # Add the helper method before @staticmethod
    staticmethod_pos = content.find('\n    @staticmethod\n    def _default_kite_factory')
    if staticmethod_pos == -1:
        return content
    
    helper = '''    @staticmethod
    def _validate_init_params(
        api_key: str,
        access_token: str,
        max_retries: int,
        initial_retry_delay: float,
        requests_per_second: int,
    ) -> None:
        """Validate initialization parameters."""
        if not api_key.strip():
            msg = "api_key cannot be empty"
            raise ConfigError(msg)
        if not access_token.strip():
            msg = "access_token cannot be empty"
            raise ConfigError(msg)
        if max_retries <= 0:
            msg = "max_retries must be positive"
            raise ConfigError(msg)
        if initial_retry_delay < 0:
            msg = "initial_retry_delay must be non-negative"
            raise ConfigError(msg)
        if requests_per_second <= 0:
            msg = "requests_per_second must be positive"
            raise ConfigError(msg)

'''
    
    content = content[:staticmethod_pos] + helper + content[staticmethod_pos:]
    return content

def fix_kite_provider_get_ohlcv(content: str) -> str:
    """Fix KiteProvider.get_ohlcv (64 LOC -> <50)."""
    # Find the method signature
    sig_pattern = r'(    async def get_ohlcv\(\n        self,\n        \*,\n        symbol: str,\n        exchange: Exchange,\n        timeframe: str,\n        since: Timestamp \| None = None,\n        limit: int = 500,\n    \) -> list\[OHLCVBar\]:\n)'
    
    sig_match = re.search(sig_pattern, content)
    if not sig_match:
        return content
    
    sig_end = sig_match.end()
    
    # Find the next method
    next_method = content.find('\n    async def get_ticker', sig_end)
    if next_method == -1:
        return content
    
    # Extract current body
    current_body = content[sig_end:next_method]
    
    # Replace with refactored version
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
    
    content = content[:sig_end] + new_body + '\n    async def get_ticker'
    return content

def fix_kite_provider_get_ticker(content: str) -> str:
    """Fix KiteProvider.get_ticker (63 LOC -> <50)."""
    sig_pattern = r'(    async def get_ticker\(\n        self,\n        \*,\n        symbol: str,\n        exchange: Exchange,\n    \) -> TickerSnapshot:\n)'
    
    sig_match = re.search(sig_pattern, content)
    if not sig_match:
        return content
    
    sig_end = sig_match.end()
    next_method = content.find('\n    async def _retry_with_backoff', sig_end)
    if next_method == -1:
        return content
    
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
    
    content = content[:sig_end] + new_body + '\n    async def _retry_with_backoff'
    return content

def fix_kite_provider_retry_with_backoff(content: str) -> str:
    """Fix KiteProvider._retry_with_backoff (53 LOC -> <50)."""
    sig_pattern = r'(    async def _retry_with_backoff\(\n        self,\n        func: Callable\[\.\.\., Any\],\n        \*args: object,\n    \) -> Any:\n)'
    
    sig_match = re.search(sig_pattern, content)
    if not sig_match:
        return content
    
    sig_end = sig_match.end()
    next_method = content.find('\n    async def _fetch_historical_data', sig_end)
    if next_method == -1:
        return content
    
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
    
    content = content[:sig_end] + new_body + '\n    async def _fetch_historical_data'
    return content

def main():
    """Main execution function."""
    print("=" * 80)
    print("Comprehensive G10 Violation Fix Script")
    print("=" * 80)
    
    # Fix kite_provider.py (4 violations)
    kite_provider = Path("src/iatb/data/kite_provider.py")
    if kite_provider.exists():
        print(f"\nProcessing {kite_provider}...")
        content = read_file(kite_provider)
        
        print("  - Fixing __init__ (54 LOC)...")
        content = fix_kite_provider_init(content)
        
        print("  - Fixing get_ohlcv (64 LOC)...")
        content = fix_kite_provider_get_ohlcv(content)
        
        print("  - Fixing get_ticker (63 LOC)...")
        content = fix_kite_provider_get_ticker(content)
        
        print("  - Fixing _retry_with_backoff (53 LOC)...")
        content = fix_kite_provider_retry_with_backoff(content)
        
        write_file(kite_provider, content)
        print(f"  [OK] Completed {kite_provider}")
    
    print("\n" + "=" * 80)
    print("Phase 1 complete: kite_provider.py (4/8 violations fixed)")
    print("=" * 80)
    print("\nNext: Run 'python check_g7_g8_g9_g10.py' to verify")
    print("Then manually fix remaining 4 violations")

if __name__ == "__main__":
    main()