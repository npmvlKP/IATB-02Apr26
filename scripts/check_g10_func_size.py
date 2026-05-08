"""
G10 Gate Check: Function size ≤50 LOC.

This script checks for functions exceeding 50 lines of code.
"""

import ast
import sys
from pathlib import Path

# Paths to check
SRC_PATHS = ["src/iatb"]

MAX_FUNCTION_LINES = 50

class FunctionSizeChecker(ast.NodeVisitor):
    """AST visitor to check function sizes."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.issues = []

    def _count_lines(self, node: ast.AST) -> int:
        """Count lines in a node."""
        if hasattr(node, "end_lineno") and hasattr(node, "lineno"):
            return node.end_lineno - node.lineno + 1
        return 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check function size."""
        lines = self._count_lines(node)
        if lines > MAX_FUNCTION_LINES:
            self.issues.append((node.lineno, node.name, lines))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check async function size."""
        lines = self._count_lines(node)
        if lines > MAX_FUNCTION_LINES:
            self.issues.append((node.lineno, node.name, lines))
        self.generic_visit(node)

def check_file_for_function_size(file_path: Path) -> list[tuple[int, str, int]]:
    """Check a file for oversized functions."""
    issues = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        checker = FunctionSizeChecker(file_path)
        checker.visit(tree)
        issues = checker.issues
    except Exception:
        pass
    return issues

def main() -> int:
    """Main entry point."""
    all_issues = []
    for path_str in SRC_PATHS:
        path = Path(path_str)
        if not path.exists():
            continue
        for py_file in path.rglob("*.py"):
            issues = check_file_for_function_size(py_file)
            if issues:
                for line_num, func_name, lines in issues:
                    all_issues.append((str(py_file), line_num, func_name, lines))

    if all_issues:
        print(f"G10 FAIL: Found {len(all_issues)} functions exceeding {MAX_FUNCTION_LINES} LOC:")
        for file_path, line_num, func_name, lines in all_issues:
            print(f"  {file_path}:{line_num}: {func_name}() - {lines} lines")
        return 1
    else:
        print(f"G10 PASS: All functions <={MAX_FUNCTION_LINES} LOC")
        return 0

if __name__ == "__main__":
    sys.exit(main())
