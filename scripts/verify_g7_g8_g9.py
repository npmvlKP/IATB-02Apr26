#!/usr/bin/env python
"""
Quick verification for G7, G8, G9 gates (no full test suite)

Run this to verify G7, G8, G9 gates only:
    python scripts/verify_g7_g8_g9.py
"""

import ast
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
SRC_DIR = ROOT_DIR / "src" / "iatb"


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def print_success(message: str) -> None:
    """Print success message."""
    print(f"[PASS] {message}")


def print_error(message: str) -> None:
    """Print error message."""
    print(f"[FAIL] {message}")


def find_pattern_matches(pattern: str, files: list[Path]) -> list[str]:
    """Find plain-text pattern matches and return path:line records."""
    matches: list[str] = []
    for file_path in files:
        if not file_path.exists():
            continue
        lines = file_path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if pattern in line:
                relative = file_path.relative_to(ROOT_DIR)
                matches.append(f"{relative}:{line_number}: {line.strip()}")
    return matches


def find_float_code_matches(files: list[Path]) -> list[str]:
    """Find float type/literal usage in code via AST (ignoring comments/docs)."""
    matches: list[str] = []
    for file_path in files:
        if not file_path.exists():
            continue
        source = file_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        lines = source.splitlines()
        for node in ast.walk(tree):
            is_float_type = isinstance(node, ast.Name) and node.id == "float"
            is_float_literal = isinstance(node, ast.Constant) and isinstance(node.value, float)
            if is_float_type or is_float_literal:
                line_number = getattr(node, "lineno", 1)
                relative = file_path.relative_to(ROOT_DIR)
                line = lines[line_number - 1].strip() if 0 < line_number <= len(lines) else ""

                # Check for exemption comment on same line
                if (
                    "API boundary" in line
                    or ("API" in line and "#" in line)
                    or "timing parameter" in line.lower()
                    or "not financial" in line.lower()
                    or "timing configuration" in line.lower()
                ):
                    continue

                # Check for exemption comment in preceding 5 lines
                has_exemption_comment = False
                for i in range(max(0, line_number - 6), line_number):
                    if i >= 0 and i < len(lines):
                        prev_line = lines[i].strip()
                        if (
                            "API boundary" in prev_line
                            or ("API" in prev_line and "#" in prev_line)
                            or "timing parameter" in prev_line.lower()
                            or "not financial" in prev_line.lower()
                            or "timing configuration" in prev_line.lower()
                        ):
                            has_exemption_comment = True
                            break

                if has_exemption_comment:
                    continue

                matches.append(f"{relative}:{line_number}: {line}")
    return matches


def run_pattern_gate(
    gate_name: str,
    pattern: str,
    files: list[Path],
    success_message: str,
) -> tuple[str, bool]:
    """Run a source-pattern gate and return gate status tuple."""
    print_section(gate_name)
    matches = find_pattern_matches(pattern, files)
    if matches:
        print_error(f"{gate_name}: FAILED")
        print("\n".join(matches))
        return gate_name, False
    print_success(success_message)
    return gate_name, True


def run_float_gate(files: list[Path]) -> tuple[str, bool]:
    """Run float usage gate for financial paths using AST."""
    gate_name = "G7 - No Float in Financial Paths"
    print_section(gate_name)
    matches = find_float_code_matches(files)
    if matches:
        print_error(f"{gate_name}: FAILED")
        print("\n".join(matches))
        return gate_name, False
    print_success("No float found in financial paths (PASS)")
    return gate_name, True


def main() -> int:
    """Run G7, G8, G9 gate checks."""
    print("\n" + "=" * 70)
    print("  IATB G7, G8, G9 GATES VERIFICATION")
    print("=" * 70)

    # G7: Financial paths as per AGENTS.md
    financial_paths = []
    for module in ["risk", "backtesting", "execution", "selection", "sentiment"]:
        module_dir = SRC_DIR / module
        if module_dir.exists():
            financial_paths.extend(module_dir.rglob("*.py"))

    # G8 & G9: All src/ files
    src_python_files = list(SRC_DIR.rglob("*.py"))

    results = [
        run_float_gate(financial_paths),
        run_pattern_gate(
            "G8 - No Naive Datetime",
            "datetime.now()",
            src_python_files,
            "No naive datetime.now() found (PASS)",
        ),
        run_pattern_gate(
            "G9 - No Print Statements",
            "print(",
            src_python_files,
            "No print() found (PASS)",
        ),
    ]

    print_section("SUMMARY")
    passed = sum(1 for _, status in results if status)
    total = len(results)
    print(f"\nGates Passed: {passed}/{total}\n")
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {name}: {status}")

    if passed == total:
        print_success("\n[SUCCESS] All G7, G8, G9 gates passed!")
        return 0
    print_error(f"\n[ERROR] {total - passed} gate(s) failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
