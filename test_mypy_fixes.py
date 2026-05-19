#!/usr/bin/env python3
"""Test script to verify mypy strict mode fixes."""

import subprocess
import sys


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run command and return exit code, stdout, stderr."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout, result.stderr


def test_file(filepath: str) -> bool:
    """Test a single file with mypy strict."""
    print(f"\nTesting {filepath}...")
    returncode, stdout, stderr = run_command(
        ["poetry", "run", "mypy", filepath, "--strict"]
    )

    if returncode != 0:
        print("  FAILED")
        print(f"  stdout: {stdout}")
        print(f"  stderr: {stderr}")
        return False

    print("  PASSED")
    return True


def main() -> int:
    """Run all mypy tests."""
    files_to_test = [
        "src/iatb/storage/audit_exporter.py",
        "src/iatb/market_strength/strength_scorer.py",
        "src/iatb/data/rate_limiter.py",
        "src/iatb/data/kite_ws_provider.py",
        "src/iatb/data/kite_provider.py",
        "src/iatb/data/failover_provider.py",
        "src/iatb/broker/token_manager.py",
        "src/iatb/api.py",
    ]

    print("=" * 60)
    print("Testing mypy strict mode fixes")
    print("=" * 60)

    passed = 0
    failed = 0

    for filepath in files_to_test:
        if test_file(filepath):
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
