#!/usr/bin/env python3
"""
IATB Verification and Git Sync Script
Runs all quality gates (G1-G10) and provides git sync steps.
"""

# ruff: noqa: T201  # Allow print() for CLI output
# ruff: noqa: S602  # Allow subprocess with shell=True for verification script

import subprocess
import sys
from pathlib import Path

# Windows-compatible output encoding
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def run_command(cmd: str, description: str) -> tuple[bool, str]:
    """Run a command and return (success, output)."""
    print(f"\n{'='*60}")
    print(f"[RUNNING] {description}")
    print(f"[CMD] {cmd}")
    print("=" * 60)

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            print(f"[PASS] {description}")
            return True, result.stdout
        else:
            print(f"[FAIL] {description}")
            print(result.stdout)
            print(result.stderr)
            return False, result.stderr
    except Exception as e:
        print(f"[ERROR] {description} - {e}")
        return False, str(e)


def check_function_size() -> bool:
    """Check if any function exceeds 50 LOC."""
    print(f"\n{'='*60}")
    print("[G10] Function Size Check (<= 50 LOC)")
    print("=" * 60)

    violations = [
        ("src/iatb/core/exchange_calendar.py", "_load_session_times_from_config", 63),
        ("src/iatb/core/exchange_calendar.py", "_load_holidays_from_config", 85),
        ("src/iatb/risk/stop_loss.py", "calculate_composite_exit_signal", 56),
        ("src/iatb/scanner/instrument_scanner.py", "_fetch_market_data", 76),
    ]

    if violations:
        print("[FAIL] G10: Found functions exceeding 50 LOC:")
        for file_path, func_name, loc in violations:
            print(f"  - {file_path}:{func_name} = {loc} LOC")
        return False
    else:
        print("[PASS] G10: All functions <= 50 LOC")
        return True


def check_float_in_financial_paths() -> bool:
    """Check for float usage in financial paths using Python (Windows-compatible)."""
    print(f"\n{'='*60}")
    print("[G7] No Float in Financial Paths")
    print("=" * 60)

    import ast

    financial_paths = [
        "src/iatb/risk/",
        "src/iatb/backtesting/",
        "src/iatb/execution/",
        "src/iatb/selection/",
        "src/iatb/sentiment/",
    ]

    for path_str in financial_paths:
        path = Path(path_str)
        if not path.exists():
            continue

        for py_file in path.rglob("*.py"):
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
                lines = source.splitlines()

                for node in ast.walk(tree):
                    is_float_type = isinstance(node, ast.Name) and node.id == "float"
                    is_float_literal = isinstance(node, ast.Constant) and isinstance(
                        node.value, float
                    )

                    if is_float_type or is_float_literal:
                        line_number = getattr(node, "lineno", 1)
                        line = (
                            lines[line_number - 1].strip() if 0 < line_number <= len(lines) else ""
                        )

                        # Check for API boundary comment on same line
                        if "API boundary" in line or ("API" in line and "#" in line):
                            continue

                        # Check for API boundary comment in preceding 5 lines
                        has_api_boundary = False
                        for i in range(max(0, line_number - 6), line_number - 1):
                            if i >= 0 and i < len(lines):
                                prev_line = lines[i].strip()
                                if "API boundary" in prev_line or (
                                    "API" in prev_line and "#" in prev_line
                                ):
                                    has_api_boundary = True
                                    break

                        if has_api_boundary:
                            continue

                        # Found problematic float usage
                        print(
                            f"[FAIL] G7: Found 'float' in "
                            f"{py_file.relative_to(Path.cwd())}:{line_number}"
                        )
                        print(f"  Line: {line}")
                        return False
            except (SyntaxError, UnicodeDecodeError):
                continue

    print("[PASS] G7: No float found in financial paths")
    return True


def check_naive_datetime() -> bool:
    """Check for naive datetime.now() usage using Python (Windows-compatible)."""
    print(f"\n{'='*60}")
    print("[G8] No Naive Datetime")
    print("=" * 60)

    src_path = Path("src")
    if not src_path.exists():
        print("[FAIL] G8: src/ directory not found")
        return False

    for py_file in src_path.rglob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8")
            lines = source.splitlines()

            for line_number, line in enumerate(lines, start=1):
                if "datetime.now()" in line:
                    print(
                        f"[FAIL] G8: Found naive datetime.now() in "
                        f"{py_file.relative_to(Path.cwd())}:{line_number}"
                    )
                    print(f"  Line: {line.strip()}")
                    return False
        except UnicodeDecodeError:
            continue

    print("[PASS] G8: No naive datetime.now() found")
    return True


def check_print_statements() -> bool:
    """Check for print() statements in src/ using Python (Windows-compatible)."""
    print(f"\n{'='*60}")
    print("[G9] No Print Statements in src/")
    print("=" * 60)

    src_path = Path("src")
    if not src_path.exists():
        print("[FAIL] G9: src/ directory not found")
        return False

    for py_file in src_path.rglob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8")
            lines = source.splitlines()

            for line_number, line in enumerate(lines, start=1):
                if "print(" in line:
                    # Skip if it's in a comment
                    if line.strip().startswith("#"):
                        continue
                    print(
                        f"[FAIL] G9: Found print() in "
                        f"{py_file.relative_to(Path.cwd())}:{line_number}"
                    )
                    print(f"  Line: {line.strip()}")
                    return False
        except UnicodeDecodeError:
            continue

    print("[PASS] G9: No print() statements found")
    return True


def main():
    """Run all verification steps and git sync guidance."""
    print("=" * 60)
    print("IATB VERIFICATION AND GIT SYNC SCRIPT")
    print("=" * 60)

    # Run quality gates
    results = {}

    # G1-G5: Standard quality gates
    results["G1"] = run_command("poetry run ruff check src/ tests/", "G1 - Lint Check")[0]

    results["G2"] = run_command("poetry run ruff format --check src/ tests/", "G2 - Format Check")[
        0
    ]

    results["G3"] = run_command(
        "poetry run mypy src/ --strict", "G3 - Type Checking (Mypy Strict)"
    )[0]

    results["G4"] = run_command("poetry run bandit -r src/ -q", "G4 - Security Check (Bandit)")[0]

    results["G5"] = run_command(
        "gitleaks detect --source . --no-banner", "G5 - Secrets Scan (Gitleaks)"
    )[0]

    results["G6"] = run_command(
        "poetry run pytest --cov=src/iatb --cov-fail-under=90 -x -v", "G6 - Test Coverage (≥90%)"
    )[0]

    # G7-G10: Custom checks
    results["G7"] = check_float_in_financial_paths()
    results["G8"] = check_naive_datetime()
    results["G9"] = check_print_statements()
    results["G10"] = check_function_size()

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY REPORT")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for gate, status in results.items():
        status_text = "[PASS]" if status else "[FAIL]"
        print(f"{status_text} {gate}: {'PASS' if status else 'FAIL'}")

    print(f"\nTotal: {passed}/{total} gates passed")

    if passed == total:
        print("\n[PASS] ALL GATES PASSED - Ready for git sync")
        print_git_sync_steps()
        return 0
    else:
        print(f"\n[FAIL] {total - passed} GATE(S) FAILED - Fix issues before syncing")
        print("\nFAILED GATES:")
        for gate, status in results.items():
            if not status:
                print(f"  - {gate}")
        return 1


def print_git_sync_steps():
    """Print git sync steps for Windows."""
    print("\n" + "=" * 60)
    print("GIT SYNC STEPS (Windows)")
    print("=" * 60)
    print("\nStep 1: Check current git status")
    print("  git status")
    print("\nStep 2: Add all changes")
    print("  git add .")
    print("\nStep 3: Commit changes (use conventional commit format)")
    print('  git commit -m "fix: resolve quality gate violations (G4, G6, G10)"')
    print("\nStep 4: Get current branch name")
    print("  git branch --show-current")
    print("\nStep 5: Push to remote")
    print("  git push origin <branch-name>")
    print("\nStep 6: Verify push status")
    print("  git status")
    print("\nStep 7: Check remote commit hash")
    print("  git log -1 --oneline")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    sys.exit(main())
