#!/usr/bin/env python3
"""G10: Check function size <= 50 LOC - order_manager.py"""

import ast
from pathlib import Path

# Read the source file
source_file = Path("src/iatb/execution/order_manager.py")
content = source_file.read_text(encoding="utf-8")

# Parse the AST
tree = ast.parse(content, filename=str(source_file))

violations = []

class FunctionSizeChecker(ast.NodeVisitor):
    def __init__(self, lines):
        self.violations = []
        self.lines = lines
    
    def visit_FunctionDef(self, node):
        # Calculate function size (excluding docstrings)
        start_line = node.lineno
        end_line = node.end_lineno if node.end_lineno else start_line
        
        # Get the function body lines
        function_lines = self.lines[start_line:end_line]
        
        # Remove docstrings and blank lines
        actual_lines = []
        in_docstring = False
        docstring_quotes = None
        
        for line in function_lines:
            stripped = line.strip()
            
            # Check for docstring
            if not in_docstring and (stripped.startswith('"""') or stripped.startswith("'''")):
                in_docstring = True
                docstring_quotes = stripped[:3]
                if stripped.count(docstring_quotes) >= 2:  # Single-line docstring
                    in_docstring = False
                continue
            
            if in_docstring:
                if stripped.endswith(docstring_quotes):
                    in_docstring = False
                continue
            
            # Skip blank lines and comments
            if not stripped or stripped.startswith('#'):
                continue
            
            actual_lines.append(line)
        
        # Check function size
        if len(actual_lines) > 50:
            self.violations.append((node.name, start_line, len(actual_lines)))
        
        self.generic_visit(node)

lines = content.split('\n')
checker = FunctionSizeChecker(lines)
checker.visit(tree)

if checker.violations:
    print("[FAIL] G10: Functions exceed 50 LOC")
    for func_name, line_num, size in checker.violations:
        print(f"  Line {line_num}: {func_name}() - {size} LOC (max: 50)")
    exit(1)
else:
    print("[PASS] G10: All functions <= 50 LOC")
    exit(0)