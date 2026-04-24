#!/usr/bin/env python
"""Check G7-G10 for alerting module."""

import ast
import re
from pathlib import Path

def check_float_in_financial_paths(file_path: Path) -> bool:
    """G7: Check no float in financial paths."""
    content = file_path.read_text()
    tree = ast.parse(content)
    
    financial_contexts = [
        'pnl', 'price', 'quantity', 'amount', 'cost', 'profit', 'loss',
        'margin', 'capital', 'position', 'portfolio', 'balance', 'equity'
    ]
    
    class FloatVisitor(ast.NodeVisitor):
        def __init__(self):
            self.violations = []
            
        def visit_Call(self, node):
            # Check if float() is used in financial context
            if isinstance(node.func, ast.Name) and node.func.id == 'float':
                # Look for variable names that suggest financial context
                if isinstance(node.args[0], ast.Name):
                    var_name = node.args[0].id.lower()
                    if any(ctx in var_name for ctx in financial_contexts):
                        line_num = node.lineno
                        self.violations.append(f"Line {line_num}: float() on {var_name}")
            self.generic_visit(node)
    
    visitor = FloatVisitor()
    visitor.visit(tree)
    
    if visitor.violations:
        print(f"G7 FAIL: {file_path}")
        for v in visitor.violations:
            print(f"  {v}")
        return False
    return True

def check_no_naive_datetime(file_path: Path) -> bool:
    """G8: Check no naive datetime.now()."""
    content = file_path.read_text()
    
    # Check for datetime.now() without UTC
    pattern = r'datetime\.now\(\)'
    matches = list(re.finditer(pattern, content))
    
    # Filter out datetime.now(UTC)
    naive_matches = []
    for match in matches:
        start = match.start()
        # Check if followed by (UTC)
        after = content[start+13:start+13+6]  # Look ahead
        if not after.startswith('(UTC)'):
            line_num = content[:start].count('\n') + 1
            naive_matches.append(f"Line {line_num}: {match.group()}")
    
    if naive_matches:
        print(f"G8 FAIL: {file_path}")
        for m in naive_matches:
            print(f"  {m}")
        return False
    return True

def check_no_print_statements(file_path: Path) -> bool:
    """G9: Check no print() statements in src/."""
    content = file_path.read_text()
    tree = ast.parse(content)
    
    class PrintVisitor(ast.NodeVisitor):
        def __init__(self):
            self.violations = []
            
        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == 'print':
                line_num = node.lineno
                self.violations.append(f"Line {line_num}: print() call")
            self.generic_visit(node)
    
    visitor = PrintVisitor()
    visitor.visit(tree)
    
    if visitor.violations:
        print(f"G9 FAIL: {file_path}")
        for v in visitor.violations:
            print(f"  {v}")
        return False
    return True

def check_function_size(file_path: Path, max_lines: int = 50) -> bool:
    """G10: Check function size ≤50 LOC."""
    content = file_path.read_text()
    lines = content.split('\n')
    tree = ast.parse(content)
    
    class FunctionVisitor(ast.NodeVisitor):
        def __init__(self):
            self.violations = []
            
        def visit_FunctionDef(self, node):
            # Count lines in function body
            start_line = node.lineno
            end_line = node.end_lineno if node.end_lineno else start_line
            func_lines = end_line - start_line + 1
            
            if func_lines > max_lines:
                self.violations.append(
                    f"Line {start_line}: {node.name}() is {func_lines} lines (max {max_lines})"
                )
            self.generic_visit(node)
    
    visitor = FunctionVisitor()
    visitor.visit(tree)
    
    if visitor.violations:
        print(f"G10 FAIL: {file_path}")
        for v in visitor.violations:
            print(f"  {v}")
        return False
    return True

if __name__ == "__main__":
    alerting_file = Path("src/iatb/core/observability/alerting.py")
    test_file = Path("tests/core/test_multi_channel_alerting.py")
    
    print("Checking G7-G10 for alerting module...\n")
    
    # G7: Float in financial paths
    g7_pass = check_float_in_financial_paths(alerting_file)
    print(f"G7 (No float in financial paths): {'PASS' if g7_pass else 'FAIL'}\n")
    
    # G8: No naive datetime
    g8_pass = check_no_naive_datetime(alerting_file)
    print(f"G8 (No naive datetime.now()): {'PASS' if g8_pass else 'FAIL'}\n")
    
    # G9: No print statements
    g9_pass = check_no_print_statements(alerting_file)
    print(f"G9 (No print() in src/): {'PASS' if g9_pass else 'FAIL'}\n")
    
    # G10: Function size
    g10_pass = check_function_size(alerting_file)
    print(f"G10 (Function size <=50 LOC): {'PASS' if g10_pass else 'FAIL'}\n")
    
    all_pass = g7_pass and g8_pass and g9_pass and g10_pass
    print(f"\nOverall G7-G10: {'ALL PASS' if all_pass else 'SOME FAILED'}")