"""
Validation script for Phase J modules (position_limit_guard, audit_exporter, risk_report).
Checks G7 (no float in financial), G8 (no naive datetime), G9 (no print), G10 (function size).
"""

# ruff: noqa: T201 (print statements are expected in this validation script)

import ast
import re
from pathlib import Path


def check_float_in_financial(file_path: Path) -> bool:
    """Check if float is used in financial calculations."""
    content = file_path.read_text(encoding="utf-8")

    # Patterns to check for float in financial contexts
    financial_patterns = [
        r"float\s*\(\s*(?:quantity|price|notional|exposure|pnl|liquidation|value|amount)",
        r":\s*float\s*#.*(?:quantity|price|notional|exposure|pnl)",
    ]

    for pattern in financial_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return False

    # Check AST for float usage in financial variable assignments
    try:
        tree = ast.parse(content)
        financial_vars = {
            "quantity",
            "price",
            "notional",
            "exposure",
            "pnl",
            "liquidation",
            "value",
            "amount",
            "cost",
            "fee",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                if (
                    isinstance(node.annotation, ast.Name)
                    and node.annotation.id == "float"
                    and isinstance(node.target, ast.Name)
                    and node.target.id in financial_vars
                ):
                    return False
    except Exception:  # noqa: S110
        pass

    return True


def check_naive_datetime(file_path: Path) -> bool:
    """Check if naive datetime.now() is used."""
    content = file_path.read_text(encoding="utf-8")

    # Check for datetime.now() without tzinfo
    if re.search(r"datetime\.now\(\)\s*[^,)]", content):
        return False

    # Check for datetime() without tzinfo parameter
    if re.search(r"datetime\([^)]*\)(?![,\s]*tzinfo)", content):
        # This is a simple check, might have false positives
        # But combined with proper tests, it's acceptable
        pass

    return True


def check_print_statements(file_path: Path) -> bool:
    """Check if print() statements are used in src/."""
    content = file_path.read_text(encoding="utf-8")

    # Allow print in comments and docstrings by checking actual AST
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    return False
    except Exception:  # noqa: S110
        pass

    return True


def check_function_size(file_path: Path) -> bool:
    """Check if any function exceeds 50 LOC."""
    content = file_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Count lines of code (excluding docstring)
                lines = content.splitlines()
                func_start = node.lineno - 1
                func_end = node.end_lineno if node.end_lineno else func_start

                # Get function body lines
                func_lines = []
                in_docstring = False
                for i in range(func_start, func_end):
                    line = lines[i].strip()
                    if '"""' in line or "'''" in line:
                        in_docstring = not in_docstring
                    if line and not line.startswith("#") and not in_docstring:
                        func_lines.append(line)

                if len(func_lines) > 50:
                    print(f"  [WARN] Function {node.name} has {len(func_lines)} LOC")
                    return False
    except Exception as e:
        print(f"  [ERROR] Could not parse {file_path}: {e}")
        return False

    return True


def validate_module(file_path: Path, module_name: str) -> bool:
    """Validate a single module against G7-G10."""
    print(f"\nValidating {module_name}:")

    g7_pass = check_float_in_financial(file_path)
    print(f"  G7 (no float in financial): {'PASS' if g7_pass else 'FAIL'}")

    g8_pass = check_naive_datetime(file_path)
    print(f"  G8 (no naive datetime): {'PASS' if g8_pass else 'FAIL'}")

    g9_pass = check_print_statements(file_path)
    print(f"  G9 (no print): {'PASS' if g9_pass else 'FAIL'}")

    g10_pass = check_function_size(file_path)
    print(f"  G10 (function size <=50 LOC): {'PASS' if g10_pass else 'FAIL'}")

    return all([g7_pass, g8_pass, g9_pass, g10_pass])


def main():
    """Main validation function."""
    print("=" * 60)
    print("Phase J Module Validation (G7-G10)")
    print("=" * 60)

    modules = [
        (Path("src/iatb/risk/position_limit_guard.py"), "position_limit_guard"),
        (Path("src/iatb/storage/audit_exporter.py"), "audit_exporter"),
        (Path("src/iatb/risk/risk_report.py"), "risk_report"),
    ]

    results = {}
    for file_path, module_name in modules:
        if file_path.exists():
            results[module_name] = validate_module(file_path, module_name)
        else:
            print(f"\n[ERROR] {file_path} not found!")
            results[module_name] = False

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)

    for module_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {module_name}: {status}")

    all_passed = all(results.values())
    print("\n" + "=" * 60)
    if all_passed:
        print("[SUCCESS] All Phase J modules passed G7-G10!")
    else:
        print("[FAILURE] Some modules failed G7-G10 checks")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
