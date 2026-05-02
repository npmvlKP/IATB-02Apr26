#!/usr/bin/env python3
"""Check for naive datetime and print statements - FIXED VERSION."""
import os
import re

# Check G8: No naive datetime.now()
datetime_matches = []
for root, _, files in os.walk('src'):
    for f in files:
        if not f.endswith('.py'):
            continue
        filepath = os.path.join(root, f)
        try:
            with open(filepath, encoding='utf-8') as fp:
                for i, line in enumerate(fp, 1):
                    # Only match actual datetime.now() calls, not comments or strings
                    if re.search(r'\bdatetime\.now\(\)', line) and not line.strip().startswith('#'):
                        datetime_matches.append((filepath, i, line.strip()))
        except Exception:
            pass

# Check G9: No print() statements in src/ - FIXED to match actual print calls
print_matches = []
for root, _, files in os.walk('src'):
    for f in files:
        if not f.endswith('.py'):
            continue
        filepath = os.path.join(root, f)
        try:
            with open(filepath, encoding='utf-8') as fp:
                for i, line in enumerate(fp, 1):
                    # Match actual print() function calls, not function names containing 'print'
                    if re.search(r'\bprint\s*\(', line) and not line.strip().startswith('#'):
                        print_matches.append((filepath, i, line.strip()))
        except Exception:
            pass

print("G8: No naive datetime.now()")
if datetime_matches:
    print(f"FAIL: Found {len(datetime_matches)} naive datetime.now() usages:")
    for filepath, line_num, line in datetime_matches[:10]:
        print(f"  {filepath}:{line_num} - {line[:80]}")
else:
    print("PASS: No naive datetime.now() found")

print("\nG9: No print() statements in src/")
if print_matches:
    print(f"FAIL: Found {len(print_matches)} print() usages:")
    for filepath, line_num, line in print_matches[:10]:
        print(f"  {filepath}:{line_num} - {line[:80]}")
else:
    print("PASS: No print() statements found")