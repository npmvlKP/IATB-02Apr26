#!/usr/bin/env python3
"""Check G7-G10 validation gates for broker module."""

import ast
import os
import re
from pathlib import Path

def check_g7_float():
    """G7: Check for float usage in financial paths."""
    print("G7: Checking for float in financial paths...")
    
    financial_paths = [
        "src/iatb/broker/",
        "src/iatb/risk/",
        "src/iatb/execution/",
        "src/iatb/selection/",
        "src/iatb/sentiment/",
    ]
    
    violations = []
    
    for path in financial_paths:
        if not os.path.exists(path):
            continue
            
        for root, dirs, files in os.walk(path):
            for file in files:
                if not file.endswith('.py'):
                    continue
                    
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    
                for i, line in enumerate(lines, 1):
                    # Check for float usage
                    if 'float' in line:
                        # Skip if it's just a comment or type hint
                        if line.strip().startswith('#'):
                            continue
                        # Check for API boundary comment on this line or previous line
                        has_api_boundary = (
                            '# API boundary' in line or
                            '# float required:' in line or
                            'math.exp' in line or
                            'math.sqrt' in line or
                            'math.pow' in line
                        )
                        if i > 1 and not has_api_boundary:
                            prev_line = lines[i-2]
                            has_api_boundary = (
                                '# API boundary' in prev_line or
                                '# float required:' in prev_line
                            )
                        
                        if not has_api_boundary:
                            violations.append(f"{filepath}:{i}: {line.strip()}")
    
    if violations:
        print(f"  [X] FAIL: Found {len(violations)} float usages:")
        for v in violations[:10]:  # Show first 10
            print(f"    {v}")
        return False
    else:
        print("  [OK] PASS: No float usage in financial paths (except API boundaries)")
        return True

def check_g8_naive_datetime():
    """G8: Check for naive datetime.now() usage."""
    print("G8: Checking for naive datetime.now() usage...")
    
    violations = []
    
    for root, dirs, files in os.walk("src/"):
        for file in files:
            if not file.endswith('.py'):
                continue
                
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Check for datetime.now() without timezone
            if re.search(r'datetime\.now\(\)', content):
                # Check if it's using UTC
                if 'datetime.now(UTC)' not in content and 'from datetime import UTC' not in content:
                    violations.append(filepath)
    
    if violations:
        print(f"  [X] FAIL: Found {len(violations)} files with naive datetime.now():")
        for v in violations[:10]:
            print(f"    {v}")
        return False
    else:
        print("  [OK] PASS: No naive datetime.now() usage found")
        return True

def check_g9_print_statements():
    """G9: Check for print() statements in src/."""
    print("G9: Checking for print() statements in src/...")
    
    violations = []
    
    for root, dirs, files in os.walk("src/"):
        for file in files:
            if not file.endswith('.py'):
                continue
                
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines, 1):
                # Check for print() calls (not in comments)
                if 'print(' in line and not line.strip().startswith('#'):
                    violations.append(f"{filepath}:{i}: {line.strip()}")
    
    if violations:
        print(f"  [X] FAIL: Found {len(violations)} print() statements:")
        for v in violations[:10]:
            print(f"    {v}")
        return False
    else:
        print("  [OK] PASS: No print() statements found in src/")
        return True

def check_g10_function_size():
    """G10: Check for functions > 50 LOC."""
    print("G10: Checking for functions > 50 LOC...")
    
    violations = []
    
    for root, dirs, files in os.walk("src/iatb/broker/"):
        for file in files:
            if not file.endswith('.py'):
                continue
                
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Count lines (excluding docstrings and empty lines)
                        start_line = node.lineno
                        end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line
                        loc = end_line - start_line + 1
                        
                        if loc > 50:
                            violations.append(f"{filepath}:{start_line}: {node.name} ({loc} LOC)")
            except Exception as e:
                print(f"  Warning: Could not parse {filepath}: {e}")
    
    if violations:
        print(f"  [X] FAIL: Found {len(violations)} functions > 50 LOC:")
        for v in violations[:10]:
            print(f"    {v}")
        return False
    else:
        print("  [OK] PASS: All functions <= 50 LOC")
        return True

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Running G7-G10 Validation Gates")
    print("="*60 + "\n")
    
    g7 = check_g7_float()
    g8 = check_g8_naive_datetime()
    g9 = check_g9_print_statements()
    g10 = check_g10_function_size()
    
    print("\n" + "="*60)
    print("Summary:")
    print(f"  G7 (Float check): {'[OK] PASS' if g7 else '[X] FAIL'}")
    print(f"  G8 (Naive datetime): {'[OK] PASS' if g8 else '[X] FAIL'}")
    print(f"  G9 (Print statements): {'[OK] PASS' if g9 else '[X] FAIL'}")
    print(f"  G10 (Function size): {'[OK] PASS' if g10 else '[X] FAIL'}")
    print("="*60 + "\n")
    
    if all([g7, g8, g9, g10]):
        print("All G7-G10 gates passed!")
        exit(0)
    else:
        print("Some G7-G10 gates failed!")
        exit(1)