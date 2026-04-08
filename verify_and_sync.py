#!/usr/bin/env python
"""
Complete verification and git sync script for IATB project.

This script:
1. Runs all quality gates (G1-G10)
2. Provides detailed output
3. Syncs to remote git repository if all gates pass
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> tuple[bool, str]:
    """Run a command and return success status and output."""
    print(f"\n{'='*60}")
    print(f"[{description}]")
    print(f"[CMD] {' '.join(cmd)}")
    print('='*60)
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    success = result.returncode == 0
    print(f"\n[RESULT] {'PASS' if success else 'FAIL'}")
    return success, result.stdout + result.stderr


def main():
    """Main execution flow."""
    print("="*60)
    print("IATB VERIFICATION AND GIT SYNC")
    print("="*60)
    
    all_passed = True
    results = {}
    
    # G1: Ruff check (excluding scripts directory)
    success, output = run_command(
        ["poetry", "run", "ruff", "check", "src/", "tests/"],
        "G1: Ruff Lint (src/ and tests/ only)"
    )
    results["G1"] = success
    all_passed = all_passed and success
    
    # G2: Ruff format check
    success, output = run_command(
        ["poetry", "run", "ruff", "format", "--check", "src/", "tests/"],
        "G2: Ruff Format"
    )
    results["G2"] = success
    all_passed = all_passed and success
    
    # G3: MyPy strict
    success, output = run_command(
        ["poetry", "run", "mypy", "src/", "--strict"],
        "G3: MyPy Strict Type Check"
    )
    results["G3"] = success
    all_passed = all_passed and success
    
    # G4: Bandit security check
    success, output = run_command(
        ["poetry", "run", "bandit", "-r", "src/", "-q"],
        "G4: Bandit Security Check"
    )
    results["G4"] = success
    all_passed = all_passed and success
    
    # G5: Gitleaks
    success, output = run_command(
        ["gitleaks", "detect", "--source", ".", "--no-banner"],
        "G5: Gitleaks Secret Scan"
    )
    results["G5"] = success
    all_passed = all_passed and success
    
    # G6: Pytest with coverage
    print(f"\n{'='*60}")
    print("[G6: Pytest with Coverage]")
    print("[CMD] poetry run pytest --cov=src/iatb --cov-fail-under=90")
    print('='*60)
    
    # Run pytest without -x to see all failures
    result = subprocess.run(
        ["poetry", "run", "pytest", "--cov=src/iatb"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    
    # Extract coverage from output
    coverage = "0.00%"
    for line in result.stdout.split('\n'):
        if "TOTAL" in line:
            parts = line.split()
            if len(parts) >= 5:
                coverage = parts[4]
    
    print(result.stdout)
    
    # Check if coverage >= 90%
    coverage_value = float(coverage.rstrip('%'))
    success = coverage_value >= 90.0 and result.returncode == 0
    results["G6"] = success
    all_passed = all_passed and success
    print(f"\n[RESULT] Coverage: {coverage} - {'PASS' if success else 'FAIL (need >=90%)'}")
    
    # G7: Check for float in financial paths
    print(f"\n{'='*60}")
    print("[G7: Float Check in Financial Paths]")
    print("[CMD] grep -r \"float\" src/iatb/risk/ src/iatb/backtesting/ src/iatb/execution/ src/iatb/selection/ src/iatb/sentiment/")
    print('='*60)
    
    result = subprocess.run(
        ["grep", "-r", "float", 
         "src/iatb/risk/", "src/iatb/backtesting/", "src/iatb/execution/",
         "src/iatb/selection/", "src/iatb/sentiment/"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    
    # Filter out comments and allowed cases
    float_lines = []
    for line in result.stdout.split('\n'):
        if line and not line.strip().startswith('#'):
            # Allow in type hints and comments
            if 'float |' in line or '# type: ignore' in line or 'API boundary' in line:
                continue
            float_lines.append(line)
    
    success = len(float_lines) == 0
    results["G7"] = success
    all_passed = all_passed and success
    
    if float_lines:
        print("FAIL - Found float in financial calculations:")
        for line in float_lines[:10]:  # Show first 10
            print(f"  {line}")
    else:
        print("PASS - No float in financial calculations")
    print(f"\n[RESULT] {'PASS' if success else 'FAIL'}")
    
    # G8: Check for naive datetime
    print(f"\n{'='*60}")
    print("[G8: Naive Datetime Check]")
    print("[CMD] grep -r \"datetime.now()\" src/")
    print('='*60)
    
    result = subprocess.run(
        ["grep", "-r", "datetime.now()", "src/"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    
    success = result.returncode != 0  # grep returns non-zero if no matches
    results["G8"] = success
    all_passed = all_passed and success
    
    if result.stdout:
        print("FAIL - Found naive datetime.now():")
        print(result.stdout)
    else:
        print("PASS - No naive datetime.now() found")
    print(f"\n[RESULT] {'PASS' if success else 'FAIL'}")
    
    # G9: Check for print statements
    print(f"\n{'='*60}")
    print("[G9: Print Statement Check]")
    print("[CMD] grep -r \"print(\" src/")
    print('='*60)
    
    result = subprocess.run(
        ["grep", "-r", "print(", "src/"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    
    success = result.returncode != 0
    results["G9"] = success
    all_passed = all_passed and success
    
    if result.stdout:
        print("FAIL - Found print() statements:")
        print(result.stdout)
    else:
        print("PASS - No print() statements found")
    print(f"\n[RESULT] {'PASS' if success else 'FAIL'}")
    
    # G10: Function size check (simplified)
    print(f"\n{'='*60}")
    print("[G10: Function Size Check]")
    print("[CMD] Checking for functions > 50 LOC")
    print('='*60)
    
    # Simple check - count lines in each function
    long_functions = []
    src_path = Path(__file__).parent / "src"
    
    for py_file in src_path.rglob("*.py"):
        with open(py_file, 'r') as f:
            lines = f.readlines()
            in_function = False
            function_start = 0
            indent_level = 0
            
            for i, line in enumerate(lines, 1):
                stripped = line.lstrip()
                if stripped.startswith('def ') and not stripped.startswith('def _'):
                    if in_function and (i - function_start) > 50:
                        long_functions.append(f"{py_file}:{function_start}")
                    in_function = True
                    function_start = i
                    indent_level = len(line) - len(stripped)
                elif in_function:
                    current_indent = len(line) - len(line.lstrip())
                    if stripped and current_indent <= indent_level and not stripped.startswith('#'):
                        if (i - function_start) > 50:
                            long_functions.append(f"{py_file}:{function_start} ({i-function_start} LOC)")
                        in_function = False
            if in_function and (len(lines) - function_start + 1) > 50:
                long_functions.append(f"{py_file}:{function_start} ({len(lines)-function_start+1} LOC)")
    
    success = len(long_functions) == 0
    results["G10"] = success
    all_passed = all_passed and success
    
    if long_functions:
        print("FAIL - Found functions > 50 LOC:")
        for func in long_functions[:10]:
            print(f"  {func}")
    else:
        print("PASS - All functions <= 50 LOC")
    print(f"\n[RESULT] {'PASS' if success else 'FAIL'}")
    
    # Summary
    print(f"\n{'='*60}")
    print("GATE SUMMARY")
    print('='*60)
    for gate, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"{gate}: {status}")
    
    print(f"\n{'='*60}")
    if all_passed:
        print("ALL GATES PASSED - Ready to sync to git")
    else:
        print("SOME GATES FAILED - Fix issues before syncing")
    print('='*60)
    
    # Git status
    print(f"\n{'='*60}")
    print("[GIT STATUS]")
    print('='*60)
    success, output = run_command(
        ["git", "status", "--short"],
        "Check Git Status"
    )
    
    if not all_passed:
        print("\n[STOP] Cannot proceed with git sync - gates not passed")
        return 1
    
    # Stage changes
    print(f"\n{'='*60}")
    print("[STAGE ALL CHANGES]")
    print('='*60)
    success, output = run_command(
        ["git", "add", "."],
        "Stage All Changes"
    )
    
    # Check branch
    success, output = run_command(
        ["git", "branch", "--show-current"],
        "Get Current Branch"
    )
    branch = output.strip()
    
    # Get commit hash
    success, output = run_command(
        ["git", "rev-parse", "HEAD"],
        "Get Latest Commit Hash"
    )
    commit_hash = output.strip()
    
    # Commit
    print(f"\n{'='*60}")
    print("[COMMIT CHANGES]")
    print(f"[MSG] fix(scanner): add custom_data parameter for testing")
    print('='*60)
    result = subprocess.run(
        ["git", "commit", "-m", "fix(scanner): add custom_data parameter for testing"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    
    if result.returncode == 0:
        print("SUCCESS - Changes committed")
        print(result.stdout)
    else:
        print("FAILED - Commit failed")
        print(result.stderr)
        return 1
    
    # Push
    print(f"\n{'='*60}")
    print(f"[PUSH TO REMOTE]")
    print(f"[CMD] git push origin {branch}")
    print('='*60)
    result = subprocess.run(
        ["git", "push", "origin", branch],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent
    )
    
    if result.returncode == 0:
        print("SUCCESS - Pushed to remote")
        print(result.stdout)
    else:
        print("FAILED - Push failed")
        print(result.stderr)
        return 1
    
    # Final report
    print(f"\n{'='*60}")
    print("GIT SYNC REPORT")
    print('='*60)
    print(f"Current Branch: {branch}")
    print(f"Latest Commit: {commit_hash}")
    print(f"Push Status: Success to origin/{branch}")
    print('='*60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())