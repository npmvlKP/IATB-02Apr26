#!/usr/bin/env python3
"""
Detailed Sprint 2 Test Analysis Script

Provides comprehensive analysis of Sprint 2 test results:
- Categorizes tests by type (unit, integration, property-based, invariant)
- Analyzes test execution time
- Identifies slow tests
- Provides recommendations

Usage:
    python scripts/verify_sprint2_detailed.py
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def categorize_tests():
    """Categorize tests by type and file."""
    categories = {
        "unit": [],
        "integration": [],
        "property_based": [],
        "financial_invariant": [],
        "error_handling": [],
        "other": [],
    }

    # Scan test files
    test_dir = Path("tests/data")

    if not test_dir.exists():
        print(f"⚠️  Test directory not found: {test_dir}")
        return categories

    for test_file in test_dir.rglob("test_*.py"):
        content = test_file.read_text(encoding="utf-8", errors="ignore")

        # Count test functions
        test_count = len(re.findall(r"def test_\w+", content))

        file_info = {"file": str(test_file.relative_to(test_dir)), "tests": test_count}

        # Categorize based on filename and content
        if "integration" in str(test_file):
            categories["integration"].append(file_info)
        elif "properties" in str(test_file) or "property" in str(test_file):
            categories["property_based"].append(file_info)
        elif "invariant" in str(test_file) or "financial" in str(test_file):
            categories["financial_invariant"].append(file_info)
        elif "error" in str(test_file) or "edge" in str(test_file) or "fail" in str(test_file):
            categories["error_handling"].append(file_info)
        else:
            categories["unit"].append(file_info)

    return categories


def analyze_test_results():
    """Analyze test execution results."""
    print("\n" + "=" * 70)
    print("🔬 DETAILED TEST ANALYSIS")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Categorize tests
    print("📂 Categorizing tests...")
    categories = categorize_tests()

    # Display categorization
    print("\n" + "=" * 70)
    print("📊 TEST CATEGORIZATION")
    print("=" * 70)

    total_tests = 0
    for cat_name, files in categories.items():
        cat_total = sum(f["tests"] for f in files)
        total_tests += cat_total

        display_name = cat_name.replace("_", " ").title()
        print(f"\n{display_name}: {cat_total} tests")
        for file_info in files:
            print(f"  - {file_info['file']}: {file_info['tests']} tests")

    print(f"\n{'=' * 70}")
    print(f"TOTAL TESTS ACROSS ALL CATEGORIES: {total_tests}")
    print("=" * 70)

    # Run tests with timing
    print("\n🧪 Running tests with timing analysis...")
    cmd = "poetry run pytest tests/data/ -v --tb=short --durations=20"

    try:
        start_time = datetime.now()
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        elapsed = (datetime.now() - start_time).total_seconds()

        # Parse results
        passed, failed, skipped = parse_test_results(result.stdout)

        # Parse slow tests
        slow_tests = parse_slow_tests(result.stdout)

        # Display results
        print("\n" + "=" * 70)
        print("📊 TEST EXECUTION RESULTS")
        print("=" * 70)
        print(f"Total Tests:  {total_tests}")
        print(f"✅ Passed:    {passed}")
        print(f"❌ Failed:    {failed}")
        print(f"⚠️  Skipped:   {skipped}")
        print(f"Pass Rate:   {(passed/total_tests*100):.1f}%")
        print(f"Elapsed:     {elapsed:.2f}s")
        print("=" * 70)

        # Show slow tests
        if slow_tests:
            print("\n⏱️  Slowest Tests (Top 10):")
            for i, (test_name, duration) in enumerate(slow_tests[:10], 1):
                print(f"  {i:2d}. {test_name} ({duration:.2f}s)")

        # Recommendations
        print("\n" + "=" * 70)
        print("💡 RECOMMENDATIONS")
        print("=" * 70)

        if failed > 0:
            print(f"\n⚠️  {failed} test(s) failed. Review and fix before deployment.")

        if slow_tests and slow_tests[0][1] > 5.0:
            print("\n⚠️  Some tests are slow (>5s). Consider optimizing:")
            for test_name, duration in slow_tests[:3]:
                if duration > 5.0:
                    print(f"   - {test_name} ({duration:.2f}s)")

        # Check category balance
        cat_counts = {name: sum(f["tests"] for f in files) for name, files in categories.items()}
        unit_pct = (cat_counts.get("unit", 0) / total_tests * 100) if total_tests > 0 else 0
        int_pct = (cat_counts.get("integration", 0) / total_tests * 100) if total_tests > 0 else 0

        print("\n📈 Test Balance:")
        print(f"   Unit Tests:          {unit_pct:.1f}% (target: ≥70%)")
        print(f"   Integration Tests:   {int_pct:.1f}% (target: ≥20%)")
        print(f"   Property-Based:      {cat_counts.get('property_based', 0)} tests")
        print(f"   Financial Invariants: {cat_counts.get('financial_invariant', 0)} tests")

        # Final assessment
        print("\n" + "=" * 70)
        print("✅ SPRINT 2 DETAILED ANALYSIS COMPLETE")
        print("=" * 70)

        if failed == 0 and unit_pct >= 70:
            return 0
        elif failed == 0:
            print(
                f"\n✅ All tests pass, but unit test coverage ({unit_pct:.1f}%) is below target (70%)."
            )
            return 0
        else:
            print(f"\n⚠️  {failed} test(s) failed. Review failures above.")
            return 1

    except subprocess.TimeoutExpired:
        print("\n❌ TIMEOUT: Tests took longer than 300s")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return 1


def parse_test_results(output: str) -> tuple:
    """Parse pytest results."""
    passed = failed = skipped = 0

    match = re.search(r"(\d+) passed, (\d+) failed, (\d+) skipped", output)
    if match:
        passed = int(match.group(1))
        failed = int(match.group(2))
        skipped = int(match.group(3))

    return passed, failed, skipped


def parse_slow_tests(output: str) -> list:
    """Parse slow test information from pytest."""
    slow_tests = []

    # Look for the slowest tests section
    lines = output.split("\n")
    in_durations = False

    for line in lines:
        if "slowest durations" in line.lower():
            in_durations = True
            continue

        if in_durations:
            if "=" * 20 in line:  # End of durations section
                break

            # Parse lines like: 10.00s tests/data/test_kite_provider.py::TestClass::test_name
            match = re.match(r"(\d+\.?\d*)s\s+(.+)", line.strip())
            if match:
                duration = float(match.group(1))
                test_name = match.group(2)
                slow_tests.append((test_name, duration))

    return sorted(slow_tests, key=lambda x: x[1], reverse=True)


def generate_detailed_report():
    """Generate detailed JSON report."""
    categories = categorize_tests()

    report = {
        "timestamp": datetime.now().isoformat(),
        "categories": {name: [f["file"] for f in files] for name, files in categories.items()},
        "test_counts": {name: sum(f["tests"] for f in files) for name, files in categories.items()},
    }

    report_file = Path("SPRINT2_DETAILED_ANALYSIS.json")
    report_file.write_text(json.dumps(report, indent=2))
    print(f"\n📄 Detailed report saved to: {report_file.absolute()}")


if __name__ == "__main__":
    exit_code = analyze_test_results()
    generate_detailed_report()
    sys.exit(exit_code)
