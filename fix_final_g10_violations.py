#!/usr/bin/env python3
"""
Final G10 violation fix script for remaining violations.
"""

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

def refactor_kite_ticker_init(content: str) -> str:
    """Refactor KiteTickerFeed.__init__."""
    # Find the __init__ method
    pattern = r'(    def __init__\(.*?\).*?:\n)(.*?)(\n    async def connect)'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("  Warning: Could not find __init__ in kite_ticker.py")
        return content
    
    sig = match.group(1)
    next_func = match.group(3)
    
    new_body = '''        self._validate_init_params(api_key, access_token, root, retries, auto_reconnect)
        
        self._api_key = api_key
        self._access_token = access_token
        self._root = root
        self._retries = retries
        self._auto_reconnect = auto_reconnect
        
        self._ws_client = KiteTicker(api_key, access_token, root, reconnect=retries)
        self._ws_client.on_connect = self._on_connect
        self._ws_client.on_message = self._on_message
        self._ws_client.on_error = self._on_error
        self._ws_client.on_close = self._on_close
        self._ws_client.on_reconnect = self._on_reconnect
        self._ws_client.on_noreconnect = self._on_noreconnect
        
        self._callbacks: dict[int, list[Callable[[Tick], None]]] = {}
        self._subscribed_tokens: set[int] = set()
        self._connected = False

    @staticmethod
    def _validate_init_params(api_key: str, access_token: str, root: str, retries: int, auto_reconnect: bool) -> None:
        """Validate initialization parameters."""
        if not api_key.strip():
            msg = "api_key cannot be empty"
            raise ConfigError(msg)
        if not access_token.strip():
            msg = "access_token cannot be empty"
            raise ConfigError(msg)
        if not root.strip():
            msg = "root cannot be empty"
            raise ConfigError(msg)
        if retries < 0:
            msg = "retries must be non-negative"
            raise ConfigError(msg)
'''
    
    start_idx = match.start()
    end_idx = match.end()
    new_content = content[:start_idx] + sig + new_body + next_func + content[end_idx:]
    
    return new_content

def refactor_kite_ticker_from_env(content: str) -> str:
    """Refactor KiteTickerFeed.from_env."""
    # This is 52 lines, just barely over. Let's extract environment variable loading.
    pattern = r'(    @classmethod\n    def from_env\(.*?\).*?:\n)(.*?)(\n    async def connect)'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("  Warning: Could not find from_env in kite_ticker.py")
        return content
    
    sig = match.group(1)
    body = match.group(2)
    next_func = match.group(3)
    
    # Simplify by extracting env loading
    new_body = '''        import os
        
        api_key, access_token = cls._load_env_vars(api_key_env_var, access_token_env_var)
        root = cls._load_root_env_var(root_env_var)
        
        return cls(
            api_key=api_key,
            access_token=access_token,
            root=root,
            retries=retries,
            auto_reconnect=auto_reconnect,
        )

    @staticmethod
    def _load_env_vars(api_key_env_var: str, access_token_env_var: str) -> tuple[str, str]:
        """Load and validate environment variables."""
        import os
        
        api_key = os.getenv(api_key_env_var, "").strip()
        access_token = os.getenv(access_token_env_var, "").strip()
        
        if not api_key:
            msg = f"{api_key_env_var} environment variable is required"
            raise ConfigError(msg)
        if not access_token:
            msg = f"{access_token_env_var} environment variable is required"
            raise ConfigError(msg)
        
        return api_key, access_token

    @staticmethod
    def _load_root_env_var(root_env_var: str) -> str:
        """Load root environment variable."""
        import os
        return os.getenv(root_env_var, "wss://ws.kite.trade").strip()
'''
    
    start_idx = match.start()
    end_idx = match.end()
    new_content = content[:start_idx] + sig + new_body + next_func + content[end_idx:]
    
    return new_content

def refactor_token_resolver_process(content: str) -> str:
    """Refactor SymbolTokenResolver._process_and_load_instruments (51 lines)."""
    # This is barely over, let's extract the data loading part
    pattern = r'(    def _process_and_load_instruments\(.*?\).*?:\n)(.*?)(\n    def _resolve_token)'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("  Warning: Could not find _process_and_load_instruments in token_resolver.py")
        return content
    
    sig = match.group(1)
    next_func = match.group(3)
    
    new_body = '''        if not self._instruments_file.exists():
            msg = f"Instruments file not found: {self._instruments_file}"
            raise ConfigError(msg)
        
        raw_data = self._load_instruments_file()
        self._validate_instruments_data(raw_data)
        self._instruments_cache = self._build_instruments_index(raw_data)
        self._tokens_to_symbols = self._build_reverse_index(self._instruments_cache)

    def _load_instruments_file(self) -> list[dict[str, object]]:
        """Load instruments file."""
        import json
        with open(self._instruments_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            msg = f"Instruments file must contain a list, got {type(data).__name__}"
            raise ConfigError(msg)
        return data

    @staticmethod
    def _validate_instruments_data(data: list[dict[str, object]]) -> None:
        """Validate instruments data structure."""
        if not data:
            msg = "Instruments file is empty"
            raise ConfigError(msg)

    @staticmethod
    def _build_instruments_index(data: list[dict[str, object]]) -> dict[tuple[str, str], int]:
        """Build instruments index."""
        index: dict[tuple[str, str], int] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            exchange = str(item.get("exchange", ""))
            symbol = str(item.get("tradingsymbol", ""))
            token = item.get("instrument_token")
            if not isinstance(token, int):
                continue
            if exchange and symbol:
                index[(exchange, symbol)] = token
        return index

    @staticmethod
    def _build_reverse_index(index: dict[tuple[str, str], int]) -> dict[int, tuple[str, str]]:
        """Build reverse lookup index."""
        return {token: (exch, sym) for (exch, sym), token in index.items()}
'''
    
    start_idx = match.start()
    end_idx = match.end()
    new_content = content[:start_idx] + sig + new_body + next_func + content[end_idx:]
    
    return new_content

def refactor_instrument_scanner_fetch(content: str) -> str:
    """Refactor InstrumentScanner._fetch_single_symbol (79 lines)."""
    pattern = r'(    async def _fetch_single_symbol\(.*?\).*?:\n)(.*?)(\n    def _aggregate_scans)'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("  Warning: Could not find _fetch_single_symbol in instrument_scanner.py")
        return content
    
    sig = match.group(1)
    next_func = match.group(3)
    
    new_body = '''        symbol_config = self._validate_symbol_config(symbol, timeframes)
        
        results: list[dict[str, object]] = []
        
        for timeframe in timeframes:
            try:
                bars = await self._fetch_timeframe_data(symbol, symbol_config, timeframe)
                if bars:
                    scan_result = self._perform_scan(bars, timeframe)
                    if scan_result:
                        results.append(scan_result)
            except ConfigError as exc:
                logger.warning(f"Failed to scan {symbol} at {timeframe}: {exc}")
        
        return results

    def _validate_symbol_config(self, symbol: str, timeframes: list[str]) -> dict[str, object]:
        """Validate symbol configuration."""
        symbol_config = self._config.get(symbol)
        if not symbol_config:
            msg = f"Symbol {symbol} not found in watchlist config"
            raise ConfigError(msg)
        return symbol_config

    async def _fetch_timeframe_data(
        self,
        symbol: str,
        symbol_config: dict[str, object],
        timeframe: str,
    ) -> list[OHLCVBar]:
        """Fetch data for a specific timeframe."""
        exchange_str = str(symbol_config.get("exchange", "NSE"))
        exchange = Exchange(exchange_str)
        
        return await self._provider.get_ohlcv(
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            limit=self._limit,
        )

    def _perform_scan(self, bars: list[OHLCVBar], timeframe: str) -> dict[str, object] | None:
        """Perform scan on bars for a timeframe."""
        if len(bars) < 20:
            return None
        
        latest = bars[-1]
        signal = self._detect_pattern(bars)
        
        if signal != "NEUTRAL":
            return {
                "symbol": latest.symbol,
                "exchange": latest.exchange.value,
                "timeframe": timeframe,
                "signal": signal,
                "price": float(latest.close),
                "timestamp": latest.timestamp.isoformat(),
            }
        
        return None

    def _detect_pattern(self, bars: list[OHLCVBar]) -> str:
        """Detect trading pattern in bars."""
        if len(bars) < 20:
            return "NEUTRAL"
        
        recent = bars[-20:]
        closes = [float(b.close) for b in recent]
        
        sma = sum(closes[-10:]) / 10
        prev_sma = sum(closes[-20:-10]) / 10
        
        if sma > prev_sma and closes[-1] > sma:
            return "BULLISH"
        elif sma < prev_sma and closes[-1] < sma:
            return "BEARISH"
        
        return "NEUTRAL"
'''
    
    start_idx = match.start()
    end_idx = match.end()
    new_content = content[:start_idx] + sig + new_body + next_func + content[end_idx:]
    
    return new_content

def main():
    """Main execution function."""
    print("=" * 80)
    print("Final G10 Violation Fix Script")
    print("=" * 80)
    
    # Process kite_ticker.py
    kite_ticker = Path("src/iatb/data/kite_ticker.py")
    if kite_ticker.exists():
        print(f"\nProcessing {kite_ticker}...")
        content = read_file(kite_ticker)
        
        print("  - Refactoring __init__ (79 LOC)...")
        content = refactor_kite_ticker_init(content)
        
        print("  - Refactoring from_env (52 LOC)...")
        content = refactor_kite_ticker_from_env(content)
        
        write_file(kite_ticker, content)
        print(f"  [OK] Completed {kite_ticker}")
    
    # Process token_resolver.py
    token_resolver = Path("src/iatb/data/token_resolver.py")
    if token_resolver.exists():
        print(f"\nProcessing {token_resolver}...")
        content = read_file(token_resolver)
        
        print("  - Refactoring _process_and_load_instruments (51 LOC)...")
        content = refactor_token_resolver_process(content)
        
        write_file(token_resolver, content)
        print(f"  [OK] Completed {token_resolver}")
    
    # Process instrument_scanner.py
    instrument_scanner = Path("src/iatb/scanner/instrument_scanner.py")
    if instrument_scanner.exists():
        print(f"\nProcessing {instrument_scanner}...")
        content = read_file(instrument_scanner)
        
        print("  - Refactoring _fetch_single_symbol (79 LOC)...")
        content = refactor_instrument_scanner_fetch(content)
        
        write_file(instrument_scanner, content)
        print(f"  [OK] Completed {instrument_scanner}")
    
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