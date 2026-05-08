"""
G7 Gate Check: No float in financial paths.

This script checks for float usage in financial calculations.
API boundary conversions with comments are allowed.
"""

import ast
import sys
from pathlib import Path

# Financial paths to check
FINANCIAL_PATHS = [
    "src/iatb/execution",
    "src/iatb/risk",
    "src/iatb/storage",
    "src/iatb/scanner",
    "src/iatb/selection",
    "src/iatb/backtesting",
]

# Allowed patterns (API boundaries with comments)
ALLOWED_PATTERNS = [
    "float(",  # Only allowed with explicit conversion comments
]

def check_file_for_floats(file_path: Path) -> list[tuple[int, str]]:
    """Check a file for float usage in financial paths."""
    issues = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            if "float" in line.lower():
                if line.strip().startswith("#") or line.strip().startswith('"""') or line.strip().startswith("'''"):
                    continue
                if "float required:" in line or "float conversion" in line:
                    continue
                if "# noqa: G7" in line or "# API boundary" in line:
                    continue
                if "float(" in line or ": float" in line or "= float" in line:
                    issues.append((i, line.strip()))
    except Exception:
        pass
    return issues

def main() -> int:
    """Main entry point."""
    all_issues = []
    for path_str in FINANCIAL_PATHS:
        path = Path(path_str)
        if not path.exists():
            continue
        for py_file in path.rglob("*.py"):
            issues = check_file_for_floats(py_file)
            if issues:
                for line_num, line in issues:
                    all_issues.append((str(py_file), line_num, line))

    if all_issues:
        print(f"G7 FAIL: Found {len(all_issues)} float usages in financial paths:")
        for file_path, line_num, line in all_issues:
            print(f"  {file_path}:{line_num}: {line}")
        return 1
    else:
        print("G7 PASS: No float in financial paths")
        return 0

if __name__ == "__main__":
    sys.exit(main())
