#!/usr/bin/env python3
"""G8: Check for naive datetime usage - order_manager.py"""

import ast
import re
from pathlib import Path

# Read the source file
source_file = Path("src/iatb/execution/order_manager.py")
content = source_file.read_text(encoding="utf-8")

# Parse the AST
tree = ast.parse(content, filename=str(source_file))

violations = []

class NaiveDatetimeChecker(ast.NodeVisitor):
    def __init__(self):
        self.violations = []
    
    def visit_Call(self, node):
        # Check for datetime.datetime() or datetime() calls without tzinfo
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in ['datetime', 'datetime.datetime']:
                # Check if tzinfo is provided
                has_tzinfo = False
                for keyword in node.keywords:
                    if keyword.arg == 'tzinfo':
                        has_tzinfo = True
                        break
                
                if not has_tzinfo and len(node.args) <= 3:
                    # datetime(year, month, day) or datetime(year, month, day, hour, minute, second) without tzinfo
                    line_num = node.lineno
                    self.violations.append((line_num, f"{func_name}() call without tzinfo"))
        
        self.generic_visit(node)

checker = NaiveDatetimeChecker()
checker.visit(tree)

if checker.violations:
    print("[FAIL] G8: Naive datetime found")
    for line_num, reason in checker.violations:
        print(f"  Line {line_num}: {reason}")
    exit(1)
else:
    print("[PASS] G8: No naive datetime")
    exit(0)