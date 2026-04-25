#!/usr/bin/env python
"""Validate G7-G10 for position_limit_guard.py."""

import ast
import sys
from pathlib import Path

# Read the source file
source_path = Path("src/iatb/risk/position_limit_guard.py")
source_code = source_path.read_text()

# Parse the AST
tree = ast.parse(source_code)

# G7: Check for float in financial calculations
# We allow float only in API boundary conversions with comments
print("G7: Checking for float in financial paths...")
float_violations = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "float":
            # Check if this is in a financial context
            # For now, we'll flag all float() calls
            line_num = node.lineno
            lines = source_code.split('\n')
            if line_num <= len(lines):
                line = lines[line_num - 1]
                if "# API boundary" not in line:
                    float_violations.append(f"Line {line_num}: {line.strip()}")

if float_violations:
    print(f"  [FAIL] Found {len(float_violations)} float() calls without API boundary comment:")
    for v in float_violations[:5]:  # Show first 5
        print(f"    {v}")
    sys.exit(1)
else:
    print("  [PASS] No float in financial calculations")

# G8: Check for naive datetime (datetime.now() without UTC)
print("\nG8: Checking for naive datetime...")
naive_dt_violations = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            # Check for datetime.now() calls
            if (node.func.attr == "now" and 
                isinstance(node.func.value, ast.Name) and
                node.func.value.id == "datetime"):
                # Check if it's being called with UTC
                has_utc = False
                for arg in node.args:
                    if isinstance(arg, ast.Name) and arg.id == "UTC":
                        has_utc = True
                        break
                if not has_utc and not node.keywords:
                    line_num = node.lineno
                    lines = source_code.split('\n')
                    if line_num <= len(lines):
                        naive_dt_violations.append(f"Line {line_num}: {lines[line_num - 1].strip()}")

if naive_dt_violations:
    print(f"  [FAIL] Found {len(naive_dt_violations)} naive datetime.now() calls:")
    for v in naive_dt_violations:
        print(f"    {v}")
    sys.exit(1)
else:
    print("  [PASS] No naive datetime calls")

# G9: Check for print() statements
print("\nG9: Checking for print() statements...")
print_violations = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            line_num = node.lineno
            lines = source_code.split('\n')
            if line_num <= len(lines):
                print_violations.append(f"Line {line_num}: {lines[line_num - 1].strip()}")

if print_violations:
    print(f"  [FAIL] Found {len(print_violations)} print() statements:")
    for v in print_violations:
        print(f"    {v}")
    sys.exit(1)
else:
    print("  [PASS] No print() statements")

# G10: Check function size (<=50 LOC)
print("\nG10: Checking function size...")
function_violations = []
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        # Calculate lines of code (excluding docstrings and comments)
        func_start = node.lineno
        func_end = node.end_lineno if node.end_lineno else func_start
        
        # Get the function body
        lines = source_code.split('\n')
        func_lines = lines[func_start:func_end]
        
        # Filter out empty lines and comments
        code_lines = [
            line for line in func_lines
            if line.strip() and not line.strip().startswith('#')
        ]
        
        # Subtract docstring if present
        docstring = ast.get_docstring(node)
        if docstring:
            doc_lines = len(docstring.split('\n')) + 2  # +2 for triple quotes
            code_lines = code_lines[doc_lines:]
        
        loc = len(code_lines)
        if loc > 50:
            function_violations.append(f"  Function '{node.name}' at line {func_start}: {loc} LOC")

if function_violations:
    print(f"  [FAIL] Found {len(function_violations)} functions exceeding 50 LOC:")
    for v in function_violations:
        print(v)
    sys.exit(1)
else:
    print("  [PASS] All functions <=50 LOC")

print("\n[SUCCESS] All G7-G10 checks passed!")