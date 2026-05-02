#!/usr/bin/env python
"""Targeted G7 validation for metrics.py and alerting.py."""

import ast
from pathlib import Path

# Financial context keywords (strictly financial, not technical metrics)
FINANCIAL_KEYWORDS = [
    "pnl",
    "price",
    "quantity",
    "amount",
    "cost",
    "profit",
    "loss",
    "margin",
    "capital",
    "position",
    "portfolio",
    "balance",
    "equity",
    "trade_pnl",
    "portfolio_value",
    "daily_pnl",
]

# Non-financial technical metrics that should use float
TECHNICAL_METRICS = ["latency", "duration", "seconds", "time", "interval", "freshness"]


def is_financial_context(line: str, line_number: int, lines: list[str]) -> bool:
    """Check if a line is in a financial context."""
    line_lower = line.lower()

    # Exclude technical metrics
    if any(metric in line_lower for metric in TECHNICAL_METRICS):
        return False

    # Check current line for financial keywords
    if any(keyword in line_lower for keyword in FINANCIAL_KEYWORDS):
        return True

    # Check function definition (look back up to 10 lines)
    for i in range(max(0, line_number - 11), line_number):
        if i >= 0 and i < len(lines):
            prev_line = lines[i].strip().lower()
            if "def " in prev_line:
                # Check if function name contains financial keyword
                if any(keyword in prev_line for keyword in FINANCIAL_KEYWORDS):
                    return True

    return False


def is_string_formatting(line: str) -> bool:
    """Check if float() is used for string formatting."""
    return "{float(" in line or ":.2f" in line


def check_float_in_file(file_path: Path) -> tuple[bool, list[str]]:
    """Check for float usage in financial contexts in a file."""
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    tree = ast.parse(content)

    violations = []

    for node in ast.walk(tree):
        is_float_type = isinstance(node, ast.Name) and node.id == "float"
        is_float_literal = isinstance(node, ast.Constant) and isinstance(node.value, float)

        if is_float_type or is_float_literal:
            line_number = getattr(node, "lineno", 1)
            line = lines[line_number - 1].strip() if 0 < line_number <= len(lines) else ""

            # Check if this is in a financial context
            if not is_financial_context(line, line_number, lines):
                continue

            # Allow float() for string formatting
            if is_string_formatting(line):
                continue

            # Check for API boundary comment on same line
            if "API boundary" in line or ("API" in line and "#" in line):
                continue

            # Check for API boundary comment in preceding 5 lines
            has_api_boundary_comment = False
            for i in range(max(0, line_number - 6), line_number - 1):
                if i >= 0 and i < len(lines):
                    prev_line = lines[i].strip()
                    if "API boundary" in prev_line or ("API" in prev_line and "#" in prev_line):
                        has_api_boundary_comment = True
                        break

            if has_api_boundary_comment:
                continue

            violations.append(f"Line {line_number}: {line}")

    return len(violations) == 0, violations


def main():
    """Run G7 validation for metrics.py and alerting.py."""
    print("=" * 70)
    print("  G7 Validation for metrics.py and alerting.py")
    print("  (Checking only financial contexts)")
    print("=" * 70)

    metrics_file = Path("src/iatb/core/observability/metrics.py")
    alerting_file = Path("src/iatb/core/observability/alerting.py")

    all_pass = True

    # Check metrics.py
    print(f"\nChecking {metrics_file}...")
    metrics_pass, metrics_violations = check_float_in_file(metrics_file)
    if metrics_pass:
        print("[PASS] No float violations found in financial contexts")
    else:
        print("[FAIL] Float violations found in financial contexts:")
        for v in metrics_violations:
            print(f"  {v}")
        all_pass = False

    # Check alerting.py
    print(f"\nChecking {alerting_file}...")
    alerting_pass, alerting_violations = check_float_in_file(alerting_file)
    if alerting_pass:
        print("[PASS] No float violations found in financial contexts")
    else:
        print("[FAIL] Float violations found in financial contexts:")
        for v in alerting_violations:
            print(f"  {v}")
        all_pass = False

    print("\n" + "=" * 70)
    if all_pass:
        print("[SUCCESS] Both files pass G7 validation!")
        return 0
    else:
        print("[ERROR] G7 validation failed")
        return 1


if __name__ == "__main__":
    exit(main())
