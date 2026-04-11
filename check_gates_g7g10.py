#!/usr/bin/env python
"""Check custom gates G7-G10."""

import os
from pathlib import Path

# G7: No float in financial paths
print("G7: Checking for floats in financial paths...")
paths = [
    "src/iatb/risk/",
    "src/iatb/backtesting/",
    "src/iatb/execution/",
    "src/iatb/selection/",
    "src/iatb/sentiment/",
]
found_floats = []
for path in paths:
    for root, dirs, files in os.walk(path):
        for f in files:
            if f.endswith(".py"):
                filepath = os.path.join(root, f)
                with open(filepath, encoding="utf-8") as fp:
                    for i, line in enumerate(fp, 1):
                        if (
                            "float" in line
                            and "# noqa" not in line
                            and "__float__" not in line
                        ):
                            found_floats.append((filepath, i, line.strip()))

if found_floats:
    print("  FAIL: Found floats in financial paths:")
    for f, l, line in found_floats[:5]:
        print(f"    {f}:{l} - {line}")
else:
    print("  PASS: No floats in financial paths")

# G8: No naive datetime
print("\nG8: Checking for naive datetime.now()...")
found_naive = []
for root, dirs, files in os.walk("src/"):
    for f in files:
        if f.endswith(".py"):
            filepath = os.path.join(root, f)
            with open(filepath, encoding="utf-8") as fp:
                for i, line in enumerate(fp, 1):
                    if "datetime.now()" in line and "# noqa" not in line:
                        found_naive.append((filepath, i, line.strip()))

if found_naive:
    print("  FAIL: Found naive datetime.now():")
    for f, l, line in found_naive[:5]:
        print(f"    {f}:{l} - {line}")
else:
    print("  PASS: No naive datetime.now()")

# G9: No print statements in src/
print("\nG9: Checking for print() in src/...")
found_print = []
for root, dirs, files in os.walk("src/"):
    for f in files:
        if f.endswith(".py"):
            filepath = os.path.join(root, f)
            with open(filepath, encoding="utf-8") as fp:
                for i, line in enumerate(fp, 1):
                    if "print(" in line and "# noqa" not in line:
                        found_print.append((filepath, i, line.strip()))

if found_print:
    print("  FAIL: Found print() statements:")
    for f, l, line in found_print[:5]:
        print(f"    {f}:{l} - {line}")
else:
    print("  PASS: No print() statements in src/")

# G10: Function size <=50 LOC
print("\nG10: Checking function size (<=50 LOC)...")
found_large_funcs = []
for root, dirs, files in os.walk("src/"):
    for f in files:
        if f.endswith(".py"):
            filepath = os.path.join(root, f)
            with open(filepath, encoding="utf-8") as fp:
                lines = fp.readlines()
                in_func = False
                func_start = 0
                func_name = ""
                indent_level = 0
                
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("def ") and ":" in stripped:
                        # Save previous function if any
                        if in_func and func_name:
                            func_size = i - func_start - 1
                            if func_size > 50:
                                found_large_funcs.append((filepath, func_name, func_size, func_start))
                        # Start new function
                        in_func = True
                        func_start = i
                        func_name = stripped.split("(")[0].replace("def ", "")
                
                # Check last function
                if in_func and func_name:
                    func_size = len(lines) - func_start
                    if func_size > 50:
                        found_large_funcs.append((filepath, func_name, func_size, func_start))

if found_large_funcs:
    print("  FAIL: Found functions >50 LOC:")
    for f, name, size, line in found_large_funcs[:5]:
        print(f"    {f}:{line} - {name}() - {size} LOC")
else:
    print("  PASS: All functions ≤50 LOC")

print("\n=== G7-G10 Summary ===")
if not found_floats and not found_naive and not found_print and not found_large_funcs:
    print("ALL PASS: G7, G8, G9, G10")
else:
    print("FAIL: Some gates failed")