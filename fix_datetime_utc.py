#!/usr/bin/env python3
"""Fix datetime.UTC to datetime.timezone.utc for Python 3.10 compatibility."""

import os
import re
from pathlib import Path

def fix_datetime_utc_in_file(file_path: Path) -> bool:
    """Replace datetime.UTC with datetime.timezone.utc in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        # Replace import statements
        content = re.sub(
            r'from datetime import([^,]*)UTC([^,]*)',
            r'from datetime import\1timezone\2',
            content
        )
        
        # Replace usage of UTC
        content = re.sub(r'\bUTC\b', 'timezone.utc', content)
        
        if content != original:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Fixed: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def main():
    """Process all Python files in src/iatb."""
    base_path = Path('src/iatb')
    
    # Files to fix
    files_to_fix = [
        'src/iatb/data/base.py',
        'src/iatb/data/instrument_master.py',
        'src/iatb/data/failover_provider.py',
        'src/iatb/data/jugaad_provider.py',
        'src/iatb/data/kite_provider.py',
        'src/iatb/data/kite_ws_provider.py',
        'src/iatb/data/market_data_cache.py',
        'src/iatb/data/migration_provider.py',
        'src/iatb/data/normalizer.py',
        'src/iatb/data/price_reconciler.py',
        'src/iatb/data/rate_limiter.py',
        'src/iatb/data/token_resolver.py',
        'src/iatb/data/validator.py',
        'src/iatb/data/yfinance_provider.py',
    ]
    
    fixed_count = 0
    for file_path in files_to_fix:
        path = Path(file_path)
        if path.exists():
            if fix_datetime_utc_in_file(path):
                fixed_count += 1
        else:
            print(f"File not found: {file_path}")
    
    print(f"\nTotal files fixed: {fixed_count}")

if __name__ == '__main__':
    main()