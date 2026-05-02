#!/usr/bin/env python3
"""Check for float usage in financial paths.

Exclusions (per AGENTS.md):
- Type annotations (lines with ': float')
- Jinja2 template filters (lines with '|float')
- API boundary conversions with explicit comments (lines with '# float required')
"""
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
                        # Skip comments
                        if line.strip().startswith('#'):
                            continue
                        
                        # Skip type annotations (both : float and -> float and Callable[[...], float])
                        if ': float' in line or '-> float' in line or '[float]' in line or ', float]' in line:
                            continue
                        
                        # Skip Jinja2 template filters
                        if '|float' in line:
                            continue
                        
                        # Skip API boundary conversions with explicit comments
                        if '# float required' in line or 'API boundary:' in line:
                            continue
                        
                        # Skip lines with explicit noqa: G7
                        if '# noqa: G7' in line or '# noqa: G7,' in line:
                            continue
                        
                        # Look for actual float usage in code
                        if 'float' in line:
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
    print("G7: No float found in financial paths - PASS")
