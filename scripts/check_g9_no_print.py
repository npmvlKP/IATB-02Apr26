"""G9 Gate Check: No print() statements in src/."""

import ast
import sys
from pathlib import Path

SRC_PATHS = ["src/iatb"]


class PrintCallChecker(ast.NodeVisitor):
    """AST visitor to detect print() function calls."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.issues: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            self.issues.append((node.lineno, f"print() call at line {node.lineno}"))
        self.generic_visit(node)


def check_file_for_print(file_path: Path) -> list[tuple[int, str]]:
    """Check a file for print() usage via AST."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        checker = PrintCallChecker(file_path)
        checker.visit(tree)
        return checker.issues
    except SyntaxError:
        return []
    except Exception:
        return []


def main() -> int:
    """Main entry point."""
    all_issues: list[tuple[str, int, str]] = []
    for path_str in SRC_PATHS:
        path = Path(path_str)
        if not path.exists():
            continue
        for py_file in path.rglob("*.py"):
            issues = check_file_for_print(py_file)
            if issues:
                for line_num, line in issues:
                    all_issues.append((str(py_file), line_num, line))

    if all_issues:
        print(f"G9 FAIL: Found {len(all_issues)} print() statements:")
        for file_path, line_num, line in all_issues:
            print(f" {file_path}:{line_num}: {line}")
        return 1
    else:
        print("G9 PASS: No print() statements in src/")
        return 0


if __name__ == "__main__":
    sys.exit(main())
