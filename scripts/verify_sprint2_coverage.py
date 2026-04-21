#!/usr/bin/env python3
"""
Sprint 2 Coverage Verification Script

Analyzes test coverage for Sprint 2 implementation:
- Runs pytest with coverage
- Analyzes coverage by module
- Identifies untested code paths
- Generates coverage report

Usage:
    python scripts/verify_sprint2_coverage.py
"""

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_coverage_analysis():
    """Run coverage analysis for Sprint 2 tests."""
    print("\n" + "=" * 70)
    print("📈 SPRINT 2 COVERAGE VERIFICATION")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    start_time = datetime.now()

    # Run tests with coverage
    print("🧪 Running tests with coverage analysis...")
    cmd = "poetry run pytest tests/data/ --cov=src/iatb/data --cov-report=term-missing --cov-report=html -q"

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)

        elapsed = (datetime.now() - start_time).total_seconds()

        # Parse coverage results
        coverage_data = parse_coverage_output(result.stdout)

        # Display results
        print("\n" + "=" * 70)
        print("📊 COVERAGE ANALYSIS RESULTS")
        print("=" * 70)

        if coverage_data["total_coverage"]:
            print(f"Total Coverage: {coverage_data['total_coverage']:.1f}%")
        else:
            print("Total Coverage: N/A")

        print(f"Elapsed: {elapsed:.2f}s")
        print("-" * 70)

        # Module coverage
        if coverage_data["modules"]:
            print("\n📁 Module Coverage:")
            for module, cov in coverage_data["modules"]:
                status = "✅" if cov >= 80 else "⚠️" if cov >= 60 else "❌"
                print(f"  {status} {module}: {cov:.1f}%")

        # Missing lines
        if coverage_data["missing_lines"]:
            print("\n❌ Missing Coverage by Module:")
            for module, lines in coverage_data["missing_lines"]:
                print(f"  {module}:")
                for line_range in lines[:3]:  # Show first 3
                    print(f"    - Line {line_range}")
                if len(lines) > 3:
                    print(f"    ... and {len(lines) - 3} more")

        print("=" * 70)

        # Assessment
        total_cov = coverage_data.get("total_coverage", 0)

        if total_cov >= 85:
            print("\n✅ EXCELLENT! Coverage meets Sprint 2 target (≥85%).")
            print(f"   Total coverage: {total_cov:.1f}%")
            return 0
        elif total_cov >= 75:
            print("\n✅ GOOD! Coverage is above minimum threshold (≥75%).")
            print(f"   Total coverage: {total_cov:.1f}%")
            return 0
        elif total_cov >= 60:
            print("\n⚠️  ACCEPTABLE but below target.")
            print(f"   Total coverage: {total_cov:.1f}% (target: ≥85%)")
            print("   Consider adding more tests for missing lines.")
            return 1
        else:
            print("\n❌ INSUFFICIENT COVERAGE!")
            print(f"   Total coverage: {total_cov:.1f}% (target: ≥85%)")
            print("   Sprint 2 requires more test coverage before deployment.")
            return 1

    except subprocess.TimeoutExpired:
        print("\n❌ TIMEOUT: Coverage analysis took longer than 300s")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return 1


def parse_coverage_output(output: str) -> dict:
    """Parse pytest-cov output."""
    data = {"total_coverage": 0.0, "modules": [], "missing_lines": []}

    lines = output.split("\n")

    # Parse total coverage
    total_match = re.search(r"TOTAL\s+(\d+)", output)
    if total_match:
        # Look for percentage in the same or next line
        for line in lines:
            if "TOTAL" in line:
                percent_match = re.search(r"(\d+)%", line)
                if percent_match:
                    data["total_coverage"] = float(percent_match.group(1))
                    break

    # Parse module coverage
    for line in lines:
        # Match lines like: src/iatb/data/__init__.py      1      0   100%
        module_match = re.match(r"(src/iatb/data/\S+)\s+\d+\s+\d+\s+(\d+)%", line)
        if module_match:
            module = module_match.group(1)
            cov = float(module_match.group(2))
            data["modules"].append((module, cov))

            # Check for missing lines
            if "%" in line and "-" in line:
                # Extract missing line ranges
                parts = line.split()
                if len(parts) > 3:
                    missing = parts[-1]
                    if missing != "100%":
                        data["missing_lines"].append((module, [missing]))

    return data


def generate_html_report():
    """Generate HTML coverage report."""
    print("\n📄 Generating HTML coverage report...")
    cmd = "poetry run pytest tests/data/ --cov=src/iatb/data --cov-report=html -q"

    try:
        subprocess.run(cmd, shell=True, capture_output=True, timeout=300)

        html_dir = Path("htmlcov/index.html")
        if html_dir.exists():
            print(f"✅ HTML report generated: {html_dir.absolute()}")
            print("   Open htmlcov/index.html in a browser to view detailed coverage.")
            return True
        else:
            print("⚠️  HTML report not found.")
            return False
    except Exception as e:
        print(f"❌ Error generating HTML report: {str(e)}")
        return False


if __name__ == "__main__":
    # Run coverage analysis
    exit_code = run_coverage_analysis()

    # Optionally generate HTML report
    if exit_code == 0:
        generate_html_report()

    sys.exit(exit_code)
