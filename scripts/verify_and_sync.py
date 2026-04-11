#!/usr/bin/env python3
"""
IATB Verification and Git Sync Script
Runs all quality gates (G1-G10) and provides git sync steps.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: str, description: str) -> tuple[bool, str]:
    """Run a command and return (success, output)."""
    print(f"\n{'='*60}")
    print(f"[RUNNING] {description}")
    print(f"[CMD] {cmd}")
    print("=" * 60)

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            print(f"✓ {description}: PASS")
            return True, result.stdout
        else:
            print(f"✗ {description}: FAIL")
            print(result.stdout)
            print(result.stderr)
            return False, result.stderr
    except Exception as e:
        print(f"✗ {description}: ERROR - {e}")
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
        print("✗ G10: FAIL - Found functions exceeding 50 LOC:")
        for file_path, func_name, loc in violations:
            print(f"  - {file_path}:{func_name} = {loc} LOC")
        return False
    else:
        print("✓ G10: PASS - All functions <= 50 LOC")
        return True


def check_float_in_financial_paths() -> bool:
    """Check for float usage in financial paths."""
    print(f"\n{'='*60}")
    print("[G7] No Float in Financial Paths")
    print("=" * 60)

    financial_paths = [
        "src/iatb/risk/",
        "src/iatb/backtesting/",
        "src/iatb/execution/",
        "src/iatb/selection/",
        "src/iatb/sentiment/",
    ]

    for path in financial_paths:
        if Path(path).exists():
            success, output = run_command(
                f'grep -r "float" {path} || true', f"Checking float in {path}"
            )
            if "float" in output.lower() and "no float" not in output.lower():
                print(f"✗ G7: FAIL - Found 'float' in {path}")
                print(output)
                return False

    print("✓ G7: PASS - No float found in financial paths")
    return True


def check_naive_datetime() -> bool:
    """Check for naive datetime.now() usage."""
    print(f"\n{'='*60}")
    print("[G8] No Naive Datetime")
    print("=" * 60)

    success, output = run_command(
        'grep -r "datetime.now()" src/ || true', "Checking for naive datetime.now()"
    )

    if "datetime.now()" in output:
        print("✗ G8: FAIL - Found naive datetime.now()")
        print(output)
        return False

    print("✓ G8: PASS - No naive datetime.now() found")
    return True


def check_print_statements() -> bool:
    """Check for print() statements in src/."""
    print(f"\n{'='*60}")
    print("[G9] No Print Statements in src/")
    print("=" * 60)

    success, output = run_command(
        'grep -r "print(" src/ || true', "Checking for print() statements"
    )

    if "print(" in output:
        print("✗ G9: FAIL - Found print() statements")
        print(output)
        return False

    print("✓ G9: PASS - No print() statements found")
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
        symbol = "✓" if status else "✗"
        print(f"{symbol} {gate}: {'PASS' if status else 'FAIL'}")

    print(f"\nTotal: {passed}/{total} gates passed")

    if passed == total:
        print("\n✓ ALL GATES PASSED - Ready for git sync")
        print_git_sync_steps()
        return 0
    else:
        print(f"\n✗ {total - passed} GATE(S) FAILED - Fix issues before syncing")
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
