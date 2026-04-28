"""Validation gates G7-G10 for P0 critical fixes."""

import ast
from pathlib import Path

src_path = Path("src/iatb")

# G7: No float in financial paths
float_usage = []
for py_file in src_path.rglob("*.py"):
    content = py_file.read_text(encoding="utf-8")
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)
        ):
            if isinstance(node.left, ast.Constant) and isinstance(
                node.left.value, float
            ):
                float_usage.append((py_file, node.lineno, "float constant"))

print(f"Float usage in financial paths: {len(float_usage)}")
if len(float_usage) == 0:
    print("G7: No float in financial paths - PASS")
else:
    print(f"G7: No float in financial paths - FAIL ({len(float_usage)} instances)")
    for py_file, line_no, usage_type in float_usage:
        print(f"  - {py_file}:{line_no} ({usage_type})")

# G8: No naive datetime
naive_dt_usage = []
for py_file in src_path.rglob("*.py"):
    content = py_file.read_text(encoding="utf-8")
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "datetime"
            and len(node.args) == 0
            and not any(
                isinstance(kw, ast.keyword) and kw.arg == "tzinfo"
                for kw in node.keywords
            )
        ):
            naive_dt_usage.append((py_file, node.lineno))

print(f"Naive datetime usage: {len(naive_dt_usage)}")
if len(naive_dt_usage) == 0:
    print("G8: No naive datetime - PASS")
else:
    print(f"G8: No naive datetime - FAIL ({len(naive_dt_usage)} instances)")

# G9: No print statements
print_usage = []
for py_file in src_path.rglob("*.py"):
    content = py_file.read_text(encoding="utf-8")
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            print_usage.append((py_file, node.lineno))

print(f"Print statement usage: {len(print_usage)}")
if len(print_usage) == 0:
    print("G9: No print statements - PASS")
else:
    print(f"G9: No print statements - FAIL ({len(print_usage)} instances)")

# G10: Function size ≤50 LOC
large_funcs = []
for py_file in src_path.rglob("*.py"):
    content = py_file.read_text(encoding="utf-8")
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            start_line = node.lineno
            end_line = (
                node.end_lineno if hasattr(node, "end_lineno") else start_line
            )
            func_size = end_line - start_line + 1
            if func_size > 50:
                large_funcs.append((py_file, node.name, func_size))

print(f"Functions > 50 LOC: {len(large_funcs)}")
if len(large_funcs) == 0:
    print("G10: Function size <= 50 LOC - PASS")
else:
    print(f"G10: Function size <= 50 LOC - FAIL ({len(large_funcs)} functions exceed limit)")
