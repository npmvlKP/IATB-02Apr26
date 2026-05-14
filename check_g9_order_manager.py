#!/usr/bin/env python3
"""G9: Check for print statements - order_manager.py"""

import ast
from pathlib import Path

# Read the source file
source_file = Path("src/iatb/execution/order_manager.py")
content = source_file.read_text(encoding="utf-8")

# Parse the AST
tree = ast.parse(content, filename=str(source_file))

violations = []

class PrintChecker(ast.NodeVisitor):
    def __init__(self):
        self.violations = []
    
    def visit_Call(self, node):
        # Check for print() calls
        if isinstance(node.func, ast.Name) and node.func.id == 'print':
            line_num = node.lineno
            self.violations.append(line_num)
        
        self.generic_visit(node)

checker = PrintChecker()
checker.visit(tree)

if checker.violations:
    print("[FAIL] G9: print() statements found")
    for line_num in checker.violations:
        print(f"  Line {line_num}: print() statement")
    exit(1)
else:
    print("[PASS] G9: No print() statements")
    exit(0)