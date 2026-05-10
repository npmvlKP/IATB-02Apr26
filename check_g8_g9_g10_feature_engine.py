#!/usr/bin/env python3
"""G8-G10 checks for feature_engine.py"""
import ast
import sys

source = 'src/iatb/ml/feature_engine.py'
tree = ast.parse(open(source).read())

# G8: Check for naive datetime
naive_dt = False
dt_now_patterns = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id in ['datetime', 'now']:
                naive_dt = True
                dt_now_patterns.append(f'{source}:{node.lineno}: Found {node.func.id}()')

if naive_dt:
    print('FAIL G8: Naive datetime detected')
    print('\n'.join(dt_now_patterns))
    sys.exit(1)
else:
    print('PASS G8: No naive datetime usage')

# G9: Check for print statements
print_statements = []
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == 'print':
            print_statements.append(f'{source}:{node.lineno}: print() statement')

if print_statements:
    print('FAIL G9: print() statements found')
    print('\n'.join(print_statements))
    sys.exit(1)
else:
    print('PASS G9: No print() statements')

# G10: Check function size <= 50 LOC
func_sizes = {}
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        start = node.lineno
        end = node.end_lineno
        size = end - start + 1
        if size > 50:
            func_sizes[node.name] = size

if func_sizes:
    print('FAIL G10: Functions > 50 LOC found')
    for name, size in func_sizes.items():
        print(f'  {name}(): {size} LOC')
    sys.exit(1)
else:
    print('PASS G10: All functions <= 50 LOC')

print('\nAll G8-G10 checks passed!')