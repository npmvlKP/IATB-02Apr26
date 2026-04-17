#!/usr/bin/env python3
"""Script to fix G10 function size violations."""

import ast
import re
from pathlib import Path

def get_function_size(filepath: Path, func_name: str, class_name: str | None = None) -> tuple[int, int] | None:
    """Get start and end line numbers of a function."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name == func_name:
                # Check if this is in the right class
                if class_name:
                    parent = getattr(node, 'parent', None)
                    if not isinstance(parent, ast.ClassDef) or parent.name != class_name:
                        continue
                
                # Find the end line (excluding docstring and trailing whitespace)
                start_line = node.lineno
                end_line = node.end_lineno if node.end_lineno else start_line
                
                return (start_line, end_line)
    
    return None

def get_all_oversized_functions() -> list[tuple[Path, str, str | None, int, int]]:
    """Get all functions exceeding 50 LOC."""
    results = []
    
    # Based on the check output
    violations = [
        ("src/iatb/data/kite_provider.py", "KiteProvider", "__init__", 189, 242),
        ("src/iatb/data/kite_provider.py", "KiteProvider", "get_ohlcv", 261, 324),
        ("src/iatb/data/kite_provider.py", "KiteProvider", "get_ticker", 325, 387),
        ("src/iatb/data/kite_provider.py", "KiteProvider", "_retry_with_backoff", 388, 440),
        ("src/iatb/data/kite_ticker.py", "KiteTickerFeed", "__init__", 120, 198),
        ("src/iatb/data/kite_ticker.py", "KiteTickerFeed", "from_env", 585, 636),
        ("src/iatb/data/token_resolver.py", "SymbolTokenResolver", "_process_and_load_instruments", 299, 349),
        ("src/iatb/scanner/instrument_scanner.py", "InstrumentScanner", "_fetch_single_symbol", 303, 381),
    ]
    
    for filepath, cls, func, start, end in violations:
        results.append((Path(filepath), func, cls, start, end))
    
    return results

if __name__ == "__main__":
    violations = get_all_oversized_functions()
    
    print("G10 Function Size Violations:")
    print("=" * 80)
    for filepath, func_name, class_name, start, end in violations:
        size = end - start + 1
        class_str = f"{class_name}." if class_name else ""
        print(f"{filepath}:{class_str}{func_name} = {size} LOC (lines {start}-{end})")
    
    print("\nTotal violations:", len(violations))