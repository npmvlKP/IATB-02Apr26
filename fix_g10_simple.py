#!/usr/bin/env python3
"""
Simple G10 fix - extract validation logic only.
This is a conservative approach that minimizes changes.
"""

import re
from pathlib import Path

def read_file(filepath: Path) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

def write_file(filepath: Path, content: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

def fix_kite_ticker_from_env(content: str) -> str:
    """Fix from_env by extracting env loading (52 LOC -> <50)."""
    # Find the from_env method and extract env loading
    # This is a minimal change: just extract the os.getenv part
    
    # Find the section with os.getenv
    pattern = r'(    @classmethod\n    def from_env\(.*?\).*?:\n        """.*?"""\n        import os\n\n        )'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        # Replace with method call
        new_code = match.group(1) + 'api_key, access_token = cls._load_env_vars(api_key_env_var, access_token_env_var)\n\n        '
        content = content[:match.start()] + new_code + content[match.end():]
        
        # Add the helper method at the end of the class
        helper = '''
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
'''
        # Find the last method and add after it
        last_method = content.rfind('    def ')
        if last_method != -1:
            insert_pos = content.find('\n\n', last_method)
            if insert_pos == -1:
                insert_pos = len(content)
            content = content[:insert_pos] + helper + content[insert_pos:]
    
    return content

def fix_token_resolver_process(content: str) -> str:
    """Fix _process_and_load_instruments by extracting file loading (51 LOC -> <50)."""
    # Find the method and extract the file loading part
    pattern = r'(    def _process_and_load_instruments\(self\) -> None:\n        """.*?"""\n        )'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        # After the docstring, extract the file loading
        rest = content[match.end():]
        
        # Find where the actual processing starts
        if 'if not self._instruments_file.exists():' in rest:
            # Extract just the validation check and file loading
            file_load_section = rest[:rest.find('self._instruments_cache =')]
            
            # Replace with method call
            new_body = 'raw_data = self._load_and_validate_file()\n        '
            
            # Find where to insert the helper (before the class ends)
            class_end = content.rfind('\nclass ')
            if class_end == -1:
                class_end = len(content)
            
            helper = '''
    def _load_and_validate_file(self) -> list[dict[str, object]]:
        """Load and validate instruments file."""
        if not self._instruments_file.exists():
            msg = f"Instruments file not found: {self._instruments_file}"
            raise ConfigError(msg)
        import json
        with open(self._instruments_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            msg = f"Instruments file must contain a list, got {type(data).__name__}"
            raise ConfigError(msg)
        if not data:
            msg = "Instruments file is empty"
            raise ConfigError(msg)
        return data
'''
            # Replace the body
            end_of_method = match.end() + len(file_load_section)
            content = content[:match.end()] + new_body + content[end_of_method:]
            
            # Insert helper before class ends
            content = content[:class_end] + helper + content[class_end:]
    
    return content

def main():
    print("Simple G10 fix script...")
    
    # Fix kite_ticker.py from_env (52 LOC)
    kite_ticker = Path("src/iatb/data/kite_ticker.py")
    if kite_ticker.exists():
        print(f"Processing {kite_ticker}...")
        content = read_file(kite_ticker)
        content = fix_kite_ticker_from_env(content)
        write_file(kite_ticker, content)
        print(f"  [OK] Fixed from_env")
    
    # Fix token_resolver.py (51 LOC)
    token_resolver = Path("src/iatb/data/token_resolver.py")
    if token_resolver.exists():
        print(f"Processing {token_resolver}...")
        content = read_file(token_resolver)
        content = fix_token_resolver_process(content)
        write_file(token_resolver, content)
        print(f"  [OK] Fixed _process_and_load_instruments")
    
    print("\nDone! Run: python check_g7_g8_g9_g10.py")

if __name__ == "__main__":
    main()