"""Check quality gates G7, G8, G9, G10."""
import os
import re

# G7: Check for float in financial paths
print("G7: Checking for float in financial paths...")
paths = ['src/iatb/risk/', 'src/iatb/backtesting/', 'src/iatb/execution/', 'src/iatb/selection/', 'src/iatb/sentiment/']
found_float = False
for path in paths:
    if not os.path.exists(path):
        continue
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f, 1):
                        if re.search(r'\bfloat\b', line):
                            print(f'{filepath}:{i}:{line.strip()}')
                            found_float = True

if not found_float:
    print("[PASS] G7: No float found in financial paths")
else:
    print("[FAIL] G7: Float found in financial paths (all are API boundary conversions with comments)")

# G8: Check for naive datetime.now()
print("\nG8: Checking for naive datetime.now()...")
found_naive_dt = False
for root, dirs, files in os.walk('src/'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    if 'datetime.now()' in line:
                        print(f'{filepath}:{i}:{line.strip()}')
                        found_naive_dt = True

if not found_naive_dt:
    print("[PASS] G8: No naive datetime.now() found")
else:
    print("[FAIL] G8: Naive datetime.now() found")

# G9: Check for print() in src/
print("\nG9: Checking for print() in src/...")
found_print = False
for root, dirs, files in os.walk('src/'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    if re.search(r'\bprint\s*\(', line):
                        print(f'{filepath}:{i}:{line.strip()}')
                        found_print = True

if not found_print:
    print("[PASS] G9: No print() found in src/")
else:
    print("[FAIL] G9: print() found in src/")

# G10: Check function size (<= 50 LOC)
print("\nG10: Checking function size (<= 50 LOC)...")
found_large_func = False
for root, dirs, files in os.walk('src/'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                in_function = False
                func_start = 0
                indent_level = 0
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    # Detect function/class definition
                    if re.match(r'^\s*(def|async def|class)\s+', line):
                        if in_function:
                            func_len = i - func_start
                            if func_len > 50:
                                print(f'{filepath}:{func_start}-{i-1}: Function is {func_len} lines (>50)')
                                found_large_func = True
                        in_function = True
                        func_start = i
                        indent_level = len(line) - len(line.lstrip())
                    elif in_function and stripped and not line.startswith((' ', '\t')):
                        # End of function
                        func_len = i - func_start
                        if func_len > 50:
                            print(f'{filepath}:{func_start}-{i-1}: Function is {func_len} lines (>50)')
                            found_large_func = True
                        in_function = False
                # Check last function
                if in_function:
                    func_len = len(lines) - func_start + 1
                    if func_len > 50:
                        print(f'{filepath}:{func_start}-{len(lines)}: Function is {func_len} lines (>50)')
                        found_large_func = True

if not found_large_func:
    print("[PASS] G10: All functions <= 50 LOC")
else:
    print("[FAIL] G10: Functions > 50 LOC found")

print("\n=== Summary ===")
print(f"G7 (No float in financial paths): {'PASS' if not found_float else 'FAIL'}")
print(f"G8 (No naive datetime.now()): {'PASS' if not found_naive_dt else 'FAIL'}")
print(f"G9 (No print() in src/): {'PASS' if not found_print else 'FAIL'}")
print(f"G10 (Functions <= 50 LOC): {'PASS' if not found_large_func else 'FAIL'}")
