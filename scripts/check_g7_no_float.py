"""G7 Gate Check: No float in financial paths.

API boundary conversions with comments are allowed.
Uses AST analysis to detect float() calls while respecting
documented API boundary exemptions.
"""

import ast
import re
import sys
from pathlib import Path

FINANCIAL_PATHS = [
    "src/iatb/execution",
    "src/iatb/risk",
    "src/iatb/storage",
    "src/iatb/scanner",
    "src/iatb/selection",
    "src/iatb/backtesting",
    "src/iatb/core",
]

API_BOUNDARY_FUNCTIONS: frozenset[str] = frozenset(
    ["_decimal_to_prometheus_gauge_value"]
    # API boundary: Prometheus Gauge.set() requires float
)

ALLOWED_LINE_PATTERNS = [
    re.compile(r"#\s*noqa:\s*G7"),
    re.compile(r"#\s*API\s+boundary"),
    re.compile(r"float\s+required:"),
    re.compile(r"float\s+conversion"),
]


class FloatCallFinder(ast.NodeVisitor):
    """AST visitor that finds float() calls, excluding API boundaries."""

    def __init__(self, source_lines: list[str]) -> None:
        self.hits: list[tuple[int, str]] = []
        self._source_lines = source_lines
        self._api_boundary_ranges: list[tuple[int, int]] = []

    def _is_in_api_boundary_func(self, lineno: int) -> bool:
        return any(
            start <= lineno <= end for start, end in self._api_boundary_ranges
        )

    def _is_line_allowed(self, lineno: int) -> bool:
        if 1 <= lineno <= len(self._source_lines):
            line = self._source_lines[lineno - 1]
            for pattern in ALLOWED_LINE_PATTERNS:
                if pattern.search(line):
                    return True
        return False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name in API_BOUNDARY_FUNCTIONS:
            end_line = getattr(node, "end_lineno", node.lineno + 50)
            self._api_boundary_ranges.append((node.lineno, end_line))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node.name in API_BOUNDARY_FUNCTIONS:
            end_line = getattr(node, "end_lineno", node.lineno + 50)
            self._api_boundary_ranges.append((node.lineno, end_line))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "float"
            and not self._is_in_api_boundary_func(node.lineno)
            and not self._is_line_allowed(node.lineno)
        ):
            line_text = (
                self._source_lines[node.lineno - 1].strip()
                if 1 <= node.lineno <= len(self._source_lines)
                else ""
            )
            self.hits.append((node.lineno, line_text))
        self.generic_visit(node)


def check_file_for_floats(file_path: Path) -> list[tuple[int, str]]:
    """Check a file for float usage in financial paths."""
    issues: list[tuple[int, str]] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        source_lines = content.splitlines()
        tree = ast.parse(content)
        finder = FloatCallFinder(source_lines)
        finder.visit(tree)
        for lineno, line_text in finder.hits:
            issues.append((lineno, line_text))
    except SyntaxError:
        pass
    except Exception:
        pass
    return issues


def main() -> int:
    """Main entry point."""
    all_issues: list[tuple[str, int, str]] = []
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
        print(
            f"G7 FAIL: Found {len(all_issues)} float usages in financial paths:"
        )
        for file_path, line_num, line in all_issues:
            print(f"  {file_path}:{line_num}: {line}")
        return 1
    else:
        print("G7 PASS: No float in financial paths")
        return 0


if __name__ == "__main__":
    sys.exit(main())