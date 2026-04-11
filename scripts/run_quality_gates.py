#!/usr/bin/env python
"""
Quality Gates Verification Script

Run this to verify all quality gates pass:
    python scripts/run_quality_gates.py
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
SRC_DIR = ROOT_DIR / "src" / "iatb"
MAIN_GATES = [
    ("G1 - Lint Check", "poetry run ruff check src/ tests/"),
    ("G2 - Format Check", "poetry run ruff format --check src/ tests/"),
    ("G3 - Type Checking", "poetry run mypy src/ --strict"),
    ("G4 - Security Scan", "poetry run python -m bandit -r src/ -q"),
    ("G5 - Secrets Scan", "gitleaks detect --source . --no-banner"),
    (
        "G6 - Test Coverage",
        "poetry run pytest --cov=src/iatb --cov-fail-under=90 -x",
    ),
]


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


def build_command_env() -> dict[str, str]:
    """Build env with src path so imports work without editable install."""
    env = os.environ.copy()
    src_path = str(ROOT_DIR / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        src_path if not existing_pythonpath else (f"{src_path}{os.pathsep}{existing_pythonpath}")
    )
    return env


def run_command(name: str, command: str) -> bool:
    """Run a command and return True if successful."""
    print(f"\n[RUN] {name}")
    print(f"   Command: {command}")
    print("-" * 70)
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            env=build_command_env(),
        )
        if result.stdout:
            print(result.stdout)
        if result.returncode == 0:
            print_success(f"{name}: PASSED")
            return True
        print_error(f"{name}: FAILED")
        if result.stderr:
            print(result.stderr)
        return False
    except Exception as e:
        print_error(f"{name}: ERROR - {e}")
        return False


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
    """Find float type/literal usage in code via AST (ignores comments/docs)."""
    matches: list[str] = []
    for file_path in files:
        if not file_path.exists():
            continue
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()
        for node in ast.walk(tree):
            is_float_type = isinstance(node, ast.Name) and node.id == "float"
            is_float_literal = isinstance(node, ast.Constant) and isinstance(node.value, float)
            if is_float_type or is_float_literal:
                line_number = getattr(node, "lineno", 1)
                relative = file_path.relative_to(ROOT_DIR)
                line = lines[line_number - 1].strip() if 0 < line_number <= len(lines) else ""
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


def run_main_gates() -> list[tuple[str, bool]]:
    """Execute command-based quality gates."""
    return [(name, run_command(name, command)) for name, command in MAIN_GATES]


def run_custom_gates() -> list[tuple[str, bool]]:
    """Execute source-pattern quality gates."""
    # G7: Financial paths as per AGENTS.md
    financial_paths = []
    for module in ["risk", "backtesting", "execution", "selection", "sentiment"]:
        module_dir = SRC_DIR / module
        if module_dir.exists():
            financial_paths.extend(module_dir.rglob("*.py"))

    # G8 & G9: All src/ files
    src_python_files = list(SRC_DIR.rglob("*.py"))

    return [
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


def print_summary(results: list[tuple[str, bool]]) -> int:
    """Print gate summary and return process exit code."""
    print_section("QUALITY GATES SUMMARY")
    passed = sum(1 for _, status in results if status)
    total = len(results)
    print(f"\nGates Passed: {passed}/{total}\n")
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {name}: {status}")
    if passed == total:
        print_success("\n[SUCCESS] All quality gates passed!")
        return 0
    print_error(f"\n[ERROR] {total - passed} gate(s) failed")
    return 1


def main() -> int:
    """Run all quality gate checks."""
    print("\n" + "=" * 70)
    print("  IATB QUALITY GATES VERIFICATION")
    print("=" * 70)
    results = run_main_gates()
    results.extend(run_custom_gates())
    return print_summary(results)


if __name__ == "__main__":
    sys.exit(main())
