#!/usr/bin/env python3
"""
Quick Sprint 2 Verification Script

Runs only the essential checks for fast verification:
- Test execution (data tests only)
- Pass rate calculation
- Quick summary

Usage:
    python scripts/verify_sprint2_quick.py
"""

import re
import subprocess
import sys
from datetime import datetime


def run_quick_verification():
    """Run quick verification of Sprint 2 tests."""
    print("\n" + "=" * 70)
    print("⚡ SPRINT 2 QUICK VERIFICATION")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    start_time = datetime.now()

    # Run tests
    print("🧪 Running test suite...")
    cmd = "poetry run pytest tests/data/ -v --tb=short -q"

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180)

        elapsed = (datetime.now() - start_time).total_seconds()

        # Parse results
        passed = 0
        failed = 0
        skipped = 0
        total = 0

        if result.stdout:
            # Look for the summary line
            match = re.search(r"(\d+) passed, (\d+) failed, (\d+) skipped", result.stdout)
            if match:
                passed = int(match.group(1))
                failed = int(match.group(2))
                skipped = int(match.group(3))
                total = passed + failed + skipped

        # Calculate pass rate
        pass_rate = (passed / total * 100) if total > 0 else 0

        # Display results
        print("\n" + "=" * 70)
        print("📊 QUICK VERIFICATION RESULTS")
        print("=" * 70)
        print(f"Total Tests:  {total}")
        print(f"✅ Passed:    {passed}")
        print(f"❌ Failed:    {failed}")
        print(f"⚠️  Skipped:   {skipped}")
        print(f"Pass Rate:   {pass_rate:.1f}%")
        print(f"Elapsed:     {elapsed:.2f}s")
        print("=" * 70)

        # Assessment
        if pass_rate >= 98:
            print("\n✅ EXCELLENT! Sprint 2 implementation is production-ready.")
            print(f"   {passed}/{total} tests passed with {pass_rate:.1f}% pass rate.")
            return 0
        elif pass_rate >= 95:
            print("\n✅ GOOD! Sprint 2 implementation meets quality standards.")
            print(f"   {passed}/{total} tests passed with {pass_rate:.1f}% pass rate.")
            return 0
        elif pass_rate >= 90:
            print("\n⚠️  ACCEPTABLE but needs attention.")
            print(f"   {failed} tests failed. Review failures before deployment.")
            return 1
        else:
            print("\n❌ FAILURES DETECTED!")
            print(f"   {failed} tests failed. Sprint 2 not ready for deployment.")

            # Show failed test names
            if result.stdout:
                print("\n❌ Failed Tests:")
                for line in result.stdout.split("\n"):
                    if "FAILED" in line and "::" in line:
                        print(f"   - {line.strip()}")

            return 1

    except subprocess.TimeoutExpired:
        print("\n❌ TIMEOUT: Tests took longer than 180s")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(run_quick_verification())
