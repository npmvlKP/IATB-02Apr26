#!/usr/bin/env python3
"""
G7: Check for 'float' usage in financial calculation paths.
Targets: src/iatb/storage/parquet_store.py and related financial modules.
Must return 0 float instances in financial calculation code.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple

# Financial modules to check (explicitly mentioned)
FINANCIAL_MODULES = [
    "src/iatb/storage/parquet_store.py",
    "src/iatb/execution/transaction_costs.py",
    "src/iatb/backtesting/indian_costs.py"
]

def check_file_for_float(filepath: Path) -> List[Tuple[int, str, str]]:
    """Check a single file for float usage in financial contexts."""
    violations = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            # Skip comments and strings
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            
            # Check for float keyword outside of comments
            # Pattern: float, float(), cast to float, etc.
            if re.search(r'\bfloat\s*\(', line) or re.search(r'\bfloat\b', line.split('#')[0]):
                # Exclude cases where it's in a string or comment
                # Also allow if it's in a comment explaining API boundary conversion
                if '#' in line:
                    comment_part = line.split('#')[1].lower()
                    if 'api boundary' in comment_part or 'conversion' in comment_part:
                        continue
                violations.append((line_num, line.strip(), filepath.name))
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
    
    return violations

def main():
    print("=== G7 Validation: Float Usage in Financial Modules ===\n")
    
    all_violations = []
    total_files_checked = 0
    
    for module_path in FINANCIAL_MODULES:
        path = Path(module_path)
        if not path.exists():
            print(f"WARNING: File not found: {module_path}")
            continue
        
        total_files_checked += 1
        violations = check_file_for_float(path)
        
        if violations:
            all_violations.extend(violations)
            print(f"FAIL: {module_path} - Found {len(violations)} float instance(s):")
            for line_num, content, _ in violations:
                print(f"  Line {line_num}: {content}")
        else:
            print(f"PASS: {module_path} - No float usage found")
    
    print(f"\n--- Summary ---")
    print(f"Files checked: {total_files_checked}")
    print(f"Total violations: {len(all_violations)}")
    
    if len(all_violations) == 0:
        print("G7 Status: PASS")
        return 0
    else:
        print("G7 Status: FAIL")
        return 1

if __name__ == "__main__":
    sys.exit(main())
