"""
G8 Gate Check: No naive datetime.

This script checks for naive datetime usage (datetime.now() without timezone).
"""

import ast
import sys
from pathlib import Path

# Paths to check
ALL_PATHS = ["src/iatb"]

def check_file_for_naive_datetime(file_path: Path) -> list[tuple[int, str]]:
    """Check a file for naive datetime usage."""
    issues = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            # Check for naive datetime patterns
            naive_patterns = [
                "datetime.now()",
                "datetime.utcnow()",
                "datetime.today()",
                "datetime.fromtimestamp(",
            ]
            for pattern in naive_patterns:
                if pattern in line:
                    # Skip if it's a comment or docstring
                    if line.strip().startswith("#") or line.strip().startswith('"""') or line.strip().startswith("'''"):
                        continue
                    # Skip if it's in a test file (tests are allowed to test rejection)
                    if "tests/" in str(file_path):
                        continue
                    issues.append((i, line.strip()))
    except Exception:
        pass
    return issues

def main() -> int:
    """Main entry point."""
    all_issues = []
    for path_str in ALL_PATHS:
        path = Path(path_str)
        if not path.exists():
            continue
        for py_file in path.rglob("*.py"):
            issues = check_file_for_naive_datetime(py_file)
            if issues:
                for line_num, line in issues:
                    all_issues.append((str(py_file), line_num, line))

    if all_issues:
        print(f"G8 FAIL: Found {len(all_issues)} naive datetime usages:")
        for file_path, line_num, line in all_issues:
            print(f"  {file_path}:{line_num}: {line}")
        return 1
    else:
        print("G8 PASS: No naive datetime")
        return 0

if __name__ == "__main__":
    sys.exit(main())
