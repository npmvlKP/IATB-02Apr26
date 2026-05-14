#!/usr/bin/env python3
"""G7: Check for float usage in financial paths - order_manager.py"""

import ast
import re
from pathlib import Path

# Read the source file
source_file = Path("src/iatb/execution/order_manager.py")
content = source_file.read_text(encoding="utf-8")

# Find all float literals (excluding those in comments)
float_pattern = r'(?<!\w)(\d+\.\d+|\.\d+)(?![\w.])'
matches = re.finditer(float_pattern, content)

violations = []
for match in matches:
    # Check if this float is in a financial context (price, quantity, PnL, etc.)
    line_num = content[:match.start()].count('\n') + 1
    line_content = content.split('\n')[line_num - 1]
    
    # Skip if in comment
    if '#' in line_content and line_content.index('#') < match.start() - content.rfind('\n', 0, match.start()):
        continue
    
    # Check for financial context
    financial_keywords = ['price', 'quantity', 'pnl', 'exposure', 'amount', 'cost', 'value', 'Decimal']
    is_financial = any(keyword in line_content.lower() for keyword in financial_keywords)
    
    if is_financial:
        violations.append((line_num, match.group(), line_content.strip()))

if violations:
    print("[FAIL] G7: Float found in financial paths")
    for line_num, float_val, line in violations:
        print(f"  Line {line_num}: {float_val} -> {line}")
    exit(1)
else:
    print("[PASS] G7: No float in financial paths")
    exit(0)
