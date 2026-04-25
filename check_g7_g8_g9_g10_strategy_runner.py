"""
Validate G7, G8, G9, G10 gates for strategy_runner.py
G7: No float in financial paths
G8: No naive datetime
G9: No print() statements
G10: Function size ≤50 LOC
"""

import ast
import sys
from pathlib import Path

def check_g7_no_float(filename: str) -> tuple[bool, list[str]]:
    """Check G7: No float in financial calculations."""
    issues = []
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines, 1):
        if 'float(' in line and ('allocation' in line.lower() or 
                                   'position' in line.lower() or 
                                   'capital' in line.lower() or
                                   'value' in line.lower()):
            issues.append(f"Line {i}: Potential float in financial calculation: {line.strip()}")
    
    return len(issues) == 0, issues

def check_g8_no_naive_datetime(filename: str) -> tuple[bool, list[str]]:
    """Check G8: No naive datetime.now()."""
    issues = []
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for datetime.now() without timezone
    if 'datetime.now()' in content:
        # Check if it's using UTC
        if 'datetime.now(UTC)' not in content:
            issues.append("Found datetime.now() without UTC timezone")
    
    # Parse AST to find datetime usage
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if (node.func.attr == 'now' and 
                        isinstance(node.func.value, ast.Name) and 
                        node.func.value.id == 'datetime' and
                        len(node.args) == 0):  # No args means naive
                        issues.append(f"Line {node.lineno}: datetime.now() without timezone")
    except:
        pass
    
    return len(issues) == 0, issues

def check_g9_no_print(filename: str) -> tuple[bool, list[str]]:
    """Check G9: No print() statements."""
    issues = []
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines, 1):
        if 'print(' in line and not line.strip().startswith('#'):
            issues.append(f"Line {i}: print() statement found: {line.strip()}")
    
    return len(issues) == 0, issues

def check_g10_function_size(filename: str, max_loc: int = 50) -> tuple[bool, list[str]]:
    """Check G10: Function size ≤50 LOC."""
    issues = []
    
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Count lines excluding docstring
                lines = content.split('\n')
                start_line = node.lineno
                end_line = node.end_lineno if node.end_lineno else start_line
                
                # Get function body
                body_lines = []
                for i in range(start_line, end_line + 1):
                    line = lines[i-1].strip()
                    if line and not line.startswith('#') and not line.startswith('"""') and not line.startswith("'''"):
                        body_lines.append(line)
                
                # Remove docstring lines
                if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                    docstring_lines = len(node.body[0].value.value.split('\n'))
                    body_lines = body_lines[docstring_lines:]
                
                loc = len(body_lines)
                if loc > max_loc:
                    issues.append(f"Function '{node.name}' at line {start_line}: {loc} LOC (max {max_loc})")
    except Exception as e:
        issues.append(f"Error parsing AST: {e}")
    
    return len(issues) == 0, issues

def main():
    """Run all checks."""
    filename = "src/iatb/core/strategy_runner.py"
    
    print(f"Validating gates for {filename}\n")
    
    # G7: No float in financial paths
    print("G7: No float in financial calculations")
    g7_pass, g7_issues = check_g7_no_float(filename)
    print(f"  Status: {'[PASS]' if g7_pass else '[FAIL]'}")
    if g7_issues:
        for issue in g7_issues:
            print(f"  - {issue}")
    print()
    
    # G8: No naive datetime
    print("G8: No naive datetime")
    g8_pass, g8_issues = check_g8_no_naive_datetime(filename)
    print(f"  Status: {'[PASS]' if g8_pass else '[FAIL]'}")
    if g8_issues:
        for issue in g8_issues:
            print(f"  - {issue}")
    print()
    
    # G9: No print statements
    print("G9: No print() statements")
    g9_pass, g9_issues = check_g9_no_print(filename)
    print(f"  Status: {'[PASS]' if g9_pass else '[FAIL]'}")
    if g9_issues:
        for issue in g9_issues:
            print(f"  - {issue}")
    print()
    
    # G10: Function size <=50 LOC
    print(f"G10: Function size <=50 LOC")
    g10_pass, g10_issues = check_g10_function_size(filename)
    print(f"  Status: {'[PASS]' if g10_pass else '[FAIL]'}")
    if g10_issues:
        for issue in g10_issues:
            print(f"  - {issue}")
    print()
    
    # Summary
    all_pass = g7_pass and g8_pass and g9_pass and g10_pass
    print("=" * 60)
    print(f"Overall: {'[ALL GATES PASS]' if all_pass else '[SOME GATES FAIL]'}")
    print("=" * 60)
    
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())