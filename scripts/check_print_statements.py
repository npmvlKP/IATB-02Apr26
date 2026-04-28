"""Check for print() statements in src/iatb."""

import re
import sys
from pathlib import Path


def find_print_statements():
    src_path = Path('src/iatb')
    violations = []

    for py_file in src_path.rglob('*.py'):
        try:
            content = py_file.read_text()
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                if 'print(' in line and 'repr(' not in line:
                    if not re.search(r'["\'][^"\']*print', line):
                        violations.append((py_file, i, line.strip()))
        except Exception:
            continue

    return violations


if __name__ == "__main__":
    violations = find_print_statements()
    if violations:
        print(f"Found {len(violations)} print() statements:")
        for v in violations[:10]:
            print(f"  {v[0]}:{v[1]}: {v[2]}")
        sys.exit(1)
    else:
        print("No print() statements found in src/")
        sys.exit(0)
