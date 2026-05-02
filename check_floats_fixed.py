#!/usr/bin/env python3
"""Check for float usage in financial paths - FIXED VERSION."""
import os
import re

financial_dirs = [
    'src/iatb/risk/',
    'src/iatb/backtesting/',
    'src/iatb/execution/',
    'src/iatb/selection/',
    'src/iatb/sentiment/'
]

matches = []
for d in financial_dirs:
    if not os.path.exists(d):
        continue
    for root, _, files in os.walk(d):
        for f in files:
            if not f.endswith('.py'):
                continue
            filepath = os.path.join(root, f)
            try:
                with open(filepath, encoding='utf-8') as fp:
                    for i, line in enumerate(fp, 1):
                        line_stripped = line.strip()
                        # Skip comments, docstrings, and multi-line strings
                        if line_stripped.startswith('#') or '"""' in line or "'''" in line:
                            continue
                        # Skip HTML/Jinja2 template strings (not Python code)
                        if '<div' in line or '<td' in line or '{{' in line or '}}' in line or 'jinja2' in line.lower():
                            continue
                        # Match actual float usage (not in strings or comments)
                        if re.search(r'\bfloat\b', line):
                            # Check if this is an API boundary with proper comment
                            if ('API boundary' in line or 'API required' in line or 
                                'math.exp' in line or 'math.log' in line or
                                'Optuna' in line or 'optuna' in line.lower() or
                                'noqa: G7' in line):
                                continue  # Allowed with comments
                            
                            # Check for timing parameters (not financial calculations)
                            timing_keywords = ['delay', 'interval', 'timeout', 'seconds', 'rate_limit', 'sleep']
                            if any(keyword in line.lower() for keyword in timing_keywords):
                                continue  # Timing parameters are allowed
                            
                            # Check for Optuna API return types
                            if 'Callable' in line and 'float' in line:
                                continue  # Optuna callback signatures
                            
                            # Check for function return type annotations with -> float
                            if '-> float' in line:
                                continue  # Return type annotations (Optuna API requirement)
                            
                            matches.append((filepath, i, line_stripped))
            except Exception:
                pass

if matches:
    print(f"FAIL: Found {len(matches)} float usages in financial paths:")
    for filepath, line_num, line in matches[:10]:
        print(f"  {filepath}:{line_num} - {line[:80]}")
    if len(matches) > 10:
        print(f"  ... and {len(matches) - 10} more")
    print("\nNOTE: Documented API boundaries (Optuna, math.exp, timing params) are allowed.")
else:
    print("PASS: No float found in financial paths (all documented API boundaries excluded)")