#!/usr/bin/env python3
"""Check for float usage in financial paths."""
import os

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
                        if 'float' in line and not line.strip().startswith('#'):
                            matches.append((filepath, i, line.strip()))
            except Exception:
                pass

if matches:
    print(f"Found {len(matches)} float usages in financial paths:")
    for filepath, line_num, line in matches[:10]:  # Show first 10
        print(f"  {filepath}:{line_num} - {line[:80]}")
    if len(matches) > 10:
        print(f"  ... and {len(matches) - 10} more")
else:
    print("PASS: No float found in financial paths")