#!/usr/bin/env python3
"""
G8: Check for naive datetime usage (datetime.now() without timezone).
Must return 0 instances of naive datetime in src/iatb/.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple

def check_file_for_naive_datetime(filepath: Path) -> List[Tuple[int, str, str]]:
    """Check a file for naive datetime.now() calls."""
    violations = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            # Skip comments and docstrings
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            
            # Look for datetime.now() without timezone parameter
            # Pattern: datetime.now(  ), where the argument is not a timezone
            # We'll check for explicit datetime.now(tz=...) or datetime.now(timezone.utc)
            if 'datetime.now(' in line:
                # Extract content inside parentheses
                inside_paren = line[line.find('datetime.now(') + len('datetime.now('):]
                # Find closing parenthesis
                paren_depth = 1
                idx = 0
                while idx < len(inside_paren) and paren_depth > 0:
                    if inside_paren[idx] == '(':
                        paren_depth += 1
                    elif inside_paren[idx] == ')':
                        paren_depth -= 1
                    idx += 1
                
                args = inside_paren[:idx-1].strip() if idx > 0 else ""
                
                # If args is empty, it's naive datetime.now()
                # Also check if args doesn't contain timezone-related keywords
                if not args:
                    violations.append((line_num, line.strip(), filepath.name))
                else:
                    # Check if argument provides timezone
                    # Common patterns: timezone.utc, pytz.utc, tz=..., ZoneInfo(...)
                    args_lower = args.lower()
                    if ('tz=' not in args_lower and 
                        'timezone' not in args_lower and 
                        'utc' not in args_lower and
                        'zoneinfo' not in args_lower):
                        violations.append((line_num, line.strip(), filepath.name))
                        
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
    
    return violations

def main():
    print("=== G8 Validation: Naive Datetime Usage ===\n")
    
    src_dir = Path("src/iatb")
    if not src_dir.exists():
        print(f"ERROR: Source directory not found: {src_dir}")
        return 1
    
    all_violations = []
    total_files_checked = 0
    
    # Find all Python files recursively
    python_files = list(src_dir.rglob("*.py"))
    
    for py_file in python_files:
        total_files_checked += 1
        violations = check_file_for_naive_datetime(py_file)
        
        if violations:
            all_violations.extend(violations)
            print(f"FAIL: {py_file.relative_to(src_dir.parent.parent)} - Found {len(violations)} naive datetime instance(s):")
            for line_num, content, _ in violations:
                print(f"  Line {line_num}: {content}")
    
    print(f"\n--- Summary ---")
    print(f"Files checked: {total_files_checked}")
    print(f"Total violations: {len(all_violations)}")
    
    if len(all_violations) == 0:
        print("G8 Status: PASS")
        return 0
    else:
        print("G8 Status: FAIL")
        return 1

if __name__ == "__main__":
    sys.exit(main())
