#!/usr/bin/env python3
"""Automated refactoring script for G10 function size violations."""

import re
from pathlib import Path


def refactor_kite_provider_init(content: str) -> str:
    """Refactor KiteProvider.__init__ to extract validation logic."""
    # Find the __init__ method
    pattern = r"(    def __init__\(.*?\).*?:\n)(.*?)(\n    @staticmethod)"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        return content

    indent = "        "
    body = match.group(2)

    # Extract validation logic
    validation_code = f"""{indent}self._validate_init_params(
{indent}    api_key,
{indent}    access_token,
{indent}    max_retries,
{indent}    initial_retry_delay,
{indent}    requests_per_second,
{indent})

"""

    # Replace validation blocks with the new helper call
    body = re.sub(
        rf"{indent}if not api_key\.strip\(\):.*?raise ConfigError\(msg\)\n",
        "",
        body,
        flags=re.DOTALL,
    )
    body = re.sub(
        rf"{indent}if not access_token\.strip\(\):.*?raise ConfigError\(msg\)\n",
        "",
        body,
        flags=re.DOTALL,
    )
    body = re.sub(
        rf"{indent}if max_retries <= 0:.*?raise ConfigError\(msg\)\n", "", body, flags=re.DOTALL
    )
    body = re.sub(
        rf"{indent}if initial_retry_delay < 0:.*?raise ConfigError\(msg\)\n",
        "",
        body,
        flags=re.DOTALL,
    )
    body = re.sub(
        rf"{indent}if requests_per_second <= 0:.*?raise ConfigError\(msg\)\n",
        "",
        body,
        flags=re.DOTALL,
    )

    # Remove empty lines
    body = re.sub(r"\n{3,}", "\n\n", body)

    # Add validation at the start
    new_body = validation_code + body.strip() + "\n"

    # Add the helper method
    helper_method = '''    @staticmethod
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

    # Replace the __init__ method
    new_init = (
        f'    def __init__({match.group(0).split("def __init__(")[1].split("):")[0]}):\n{new_body}'
    )

    # Insert the helper method before @staticmethod
    new_content = (
        content[: match.start()]
        + new_init
        + "\n"
        + helper_method
        + content[match.end() - len(match.group(3)) :]
    )

    return new_content


def refactor_kite_provider_get_ohlcv(content: str) -> str:
    """Refactor get_ohlcv to extract helper methods."""
    # Find the method
    pattern = r"(    async def get_ohlcv\(.*?\).*?:\n)(.*?)(\n    async def get_ticker)"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        return content

    indent = "        "
    _ = match.group(2)  # Not used, body is rebuilt

    # Extract helper methods from the body
    new_body = f'''{indent}self._validate_ohlcv_params(limit)

{indent}kite_interval, trading_symbol = (
    {indent}self._prepare_ohlcv_request(symbol, exchange, timeframe)
)
{indent}start_date, end_date = self._calculate_date_range(since, limit)

{indent}client = self._get_client()
{indent}data = await self._fetch_with_retry(
    {indent}client, trading_symbol, kite_interval, start_date, end_date
)

{indent}return self._process_and_normalize(
    {indent}data, symbol, exchange, since, limit
)

    def _validate_ohlcv_params(self, limit: int) -> None:
        """Validate OHLCV parameters."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ConfigError(msg)

    def _prepare_ohlcv_request(
        self, symbol: str, exchange: Exchange, timeframe: str
    ) -> tuple[str, str]:
        """Prepare Kite API request parameters."""
        _ensure_supported_exchange(exchange)
        kite_interval = _map_timeframe(timeframe)
        trading_symbol = _format_trading_symbol(symbol, exchange)
        return kite_interval, trading_symbol

    def _calculate_date_range(
        self, since: Timestamp | None, limit: int
    ) -> tuple[datetime, datetime]:
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

    # Replace the method
    method_signature = (
        f'    async def get_ohlcv('
        f'{match.group(0).split("async def get_ohlcv(")[1].split("):")[0]})'
        f':\n{new_body}\n'
    )
    new_content = (
        content[: match.start()] + method_signature + content[match.end() - len(match.group(3)) :]
    )

    return new_content


def main() -> None:  # noqa: T201
    """Main function to run all refactorings."""
    print("Starting G10 refactoring...")  # noqa: T201

    # Process kite_provider.py
    kite_provider_path = Path("src/iatb/data/kite_provider.py")
    if kite_provider_path.exists():
        print(f"Processing {kite_provider_path}...")  # noqa: T201
        with open(kite_provider_path, encoding="utf-8") as f:
            content = f.read()

        # Apply refactorings
        content = refactor_kite_provider_init(content)
        content = refactor_kite_provider_get_ohlcv(content)

        with open(kite_provider_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"✓ Refactored {kite_provider_path}")  # noqa: T201

    print("\nRefactoring complete!")  # noqa: T201
    print(  # noqa: T201
        "Please run 'python check_g7_g8_g9_g10.py' to verify G10 passes."
    )


if __name__ == "__main__":
    main()
