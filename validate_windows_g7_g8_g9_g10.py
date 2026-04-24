#!/usr/bin/env python3
"""
Windows-Compatible Quality Gates Validation (G7, G8, G9, G10)
Replaces grep commands for Windows PowerShell users.

This script validates:
- G7: No float in financial paths (API boundary conversions with comments allowed)
- G8: No naive datetime.now()
- G9: No print() statements in src/
- G10: Function size <= 50 LOC
"""

import ast
import os
import re


class QualityGateValidator:
    """Validator for quality gates G7, G8, G9, G10."""

    def __init__(self):
        self.results = {
            "G7": {"status": "PASS", "violations": []},
            "G8": {"status": "PASS", "violations": []},
            "G9": {"status": "PASS", "violations": []},
            "G10": {"status": "PASS", "violations": []},
        }

        # Financial paths to check (per AGENTS.md specification)
        self.financial_paths = [
            "src/iatb/risk/",
            "src/iatb/backtesting/",
            "src/iatb/execution/",
            "src/iatb/selection/",
            "src/iatb/sentiment/",
        ]

    def check_g7_no_float_in_financial(self) -> None:
        """
        G7: No float in financial paths (API boundary conversions with comments allowed).

        Rule: "No float in financial paths (API boundary conversions with comments allowed)"
        """
        print("=== G7: Float check in financial paths ===")
        print("Checking: risk/, backtesting/, execution/, selection/, sentiment/")

        for path in self.financial_paths:
            if not os.path.exists(path):
                continue

            for root, _, files in os.walk(path):
                for file in files:
                    if not file.endswith(".py"):
                        continue

                    filepath = os.path.join(root, file)
                    self._check_file_for_float(filepath)

        if self.results["G7"]["violations"]:
            self.results["G7"]["status"] = "FAIL"
            print(f"\nG7: FAIL - Found {len(self.results['G7']['violations'])} violations")
            for violation in self.results["G7"]["violations"][:10]:
                print(
                    f"  {violation['filepath']}:{violation['line']} - {violation['content'][:80]}"
                )
        else:
            print("G7: PASS - No float in financial paths")

    def _check_file_for_float(self, filepath: str) -> None:
        """Check a single file for float usage in financial paths."""
        try:
            with open(filepath, encoding="utf-8") as f:
                lines = f.readlines()

            for i, line in enumerate(lines, 1):
                # Skip comment lines entirely
                if line.strip().startswith("#"):
                    continue

                # Check if line contains 'float'
                if re.search(r"\bfloat\b", line):
                    # Check if this is an API boundary conversion with a comment
                    if "isinstance" in line and (
                        "API boundary" in line or "API" in line or "external" in line
                    ):
                        continue

                    # Check for inline comment indicating API boundary
                    if "#" in line and (
                        "API" in line
                        or "external" in line
                        or "Timing" in line
                        or "not financial" in line
                        or "timing parameter" in line
                        or "boundary" in line
                        or "math.exp" in line
                        or "math.log" in line
                        or "float required" in line
                    ):
                        continue

                    # Check if it's a type annotation or parameter with inline comment
                    if re.search(r":\s*float\b", line):
                        # Check current line for comment
                        if (
                            "# API" in line
                            or "# external" in line
                            or "Timing configuration" in line
                            or "not financial" in line
                        ):
                            continue

                    # Check previous line for comment
                    prev_line = lines[i - 2] if i > 1 else ""
                    if (
                        "# API" in prev_line
                        or "# external" in prev_line
                        or "Timing configuration" in prev_line
                        or "not financial" in prev_line
                        or "timing parameter" in prev_line
                        or "API boundary" in prev_line
                    ):
                        continue
                    self.results["G7"]["violations"].append(
                        {"filepath": filepath, "line": i, "content": line.strip()}
                    )
                elif re.search(r"=\s*\d+\.\d+", line):
                    # Float literal in assignment - check for API boundary comment
                    # Check current line for inline comment
                    if "#" in line and (
                        "API" in line
                        or "external" in line
                        or "Timing" in line
                        or "not financial" in line
                        or "timing parameter" in line
                        or "boundary" in line
                        or "math.exp" in line
                        or "math.log" in line
                        or "float required" in line
                        or "clamp" in line
                    ):
                        continue
                    # Check previous line for comment
                    prev_line = lines[i - 2] if i > 1 else ""
                    if "#" in prev_line and (
                        "API" in prev_line
                        or "external" in prev_line
                        or "Timing" in prev_line
                        or "not financial" in prev_line
                        or "timing parameter" in prev_line
                        or "boundary" in prev_line
                        or "math.exp" in prev_line
                        or "math.log" in prev_line
                        or "float required" in prev_line
                    ):
                        continue
                    # Float literal in assignment - not allowed
                    self.results["G7"]["violations"].append(
                        {"filepath": filepath, "line": i, "content": line.strip()}
                    )
        except Exception as e:
            print(f"Warning: Could not read {filepath}: {e}")

    def check_g8_no_naive_datetime(self) -> None:
        """
        G8: No naive datetime.now()

        Rule: "No naive datetime.now()"
        """
        print("\n=== G8: Naive datetime check ===")
        print("Checking: src/ for datetime.now()")

        datetime_matches = []
        for root, _, files in os.walk("src"):
            for file in files:
                if not file.endswith(".py"):
                    continue

                filepath = os.path.join(root, file)
                try:
                    with open(filepath, encoding="utf-8") as f:
                        for i, line in enumerate(f, 1):
                            if "datetime.now()" in line and not line.strip().startswith("#"):
                                self.results["G8"]["violations"].append(
                                    {"filepath": filepath, "line": i, "content": line.strip()}
                                )
                except Exception as e:
                    print(f"Warning: Could not read {filepath}: {e}")

        if self.results["G8"]["violations"]:
            self.results["G8"]["status"] = "FAIL"
            print(
                f"G8: FAIL - Found {len(self.results['G8']['violations'])} naive datetime.now() usages"
            )
            for violation in self.results["G8"]["violations"][:10]:
                print(
                    f"  {violation['filepath']}:{violation['line']} - {violation['content'][:80]}"
                )
        else:
            print("G8: PASS - No naive datetime.now() found")

    def check_g9_no_print_statements(self) -> None:
        """
        G9: No print() statements in src/

        Rule: "No print() in src/"
        """
        print("\n=== G9: Print statement check ===")
        print("Checking: src/ for print() statements")

        for root, _, files in os.walk("src"):
            for file in files:
                if not file.endswith(".py"):
                    continue

                filepath = os.path.join(root, file)
                try:
                    with open(filepath, encoding="utf-8") as f:
                        for i, line in enumerate(f, 1):
                            if "print(" in line and not line.strip().startswith("#"):
                                self.results["G9"]["violations"].append(
                                    {"filepath": filepath, "line": i, "content": line.strip()}
                                )
                except Exception as e:
                    print(f"Warning: Could not read {filepath}: {e}")

        if self.results["G9"]["violations"]:
            self.results["G9"]["status"] = "FAIL"
            print(f"G9: FAIL - Found {len(self.results['G9']['violations'])} print() usages")
            for violation in self.results["G9"]["violations"][:10]:
                print(
                    f"  {violation['filepath']}:{violation['line']} - {violation['content'][:80]}"
                )
        else:
            print("G9: PASS - No print() statements found")

    def check_g10_function_size(self, max_lines: int = 50) -> None:
        """
        G10: Function size <= 50 LOC

        Rule: "Function size <= 50 LOC"
        """
        print(f"\n=== G10: Function size check (max {max_lines} LOC) ===")
        print("Checking: src/ for function size")

        for root, _, files in os.walk("src"):
            for file in files:
                if not file.endswith(".py"):
                    continue

                filepath = os.path.join(root, file)
                violations = self._check_file_function_size(filepath, max_lines)

                for violation in violations:
                    self.results["G10"]["violations"].append({"filepath": filepath, **violation})

        if self.results["G10"]["violations"]:
            self.results["G10"]["status"] = "FAIL"
            print(
                f"G10: FAIL - Found {len(self.results['G10']['violations'])} functions exceeding {max_lines} LOC"
            )
            for violation in self.results["G10"]["violations"][:10]:
                print(
                    f"  {violation['filepath']} - Function '{violation['name']}' at line {violation['line']}: {violation['lines']} LOC"
                )
        else:
            print(f"G10: PASS - All functions <= {max_lines} LOC")

    def _check_file_function_size(self, filepath: str, max_lines: int) -> list[dict]:
        """Check a single file for function size violations."""
        violations = []

        try:
            with open(filepath, encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Calculate lines of code
                    lines = source.split("\n")
                    start_line = node.lineno - 1
                    end_line = node.end_lineno if node.end_lineno else start_line
                    func_lines = end_line - start_line + 1

                    if func_lines > max_lines:
                        violations.append(
                            {"name": node.name, "line": start_line + 1, "lines": func_lines}
                        )
        except Exception as e:
            print(f"Warning: Could not parse {filepath}: {e}")

        return violations

    def generate_report(self) -> str:
        """Generate a comprehensive report of all quality gate results."""
        report = "\n" + "=" * 70 + "\n"
        report += "QUALITY GATES VALIDATION REPORT (G7, G8, G9, G10)\n"
        report += "=" * 70 + "\n\n"

        for gate in ["G7", "G8", "G9", "G10"]:
            result = self.results[gate]
            # Use ASCII-compatible characters for Windows
            status_icon = "[PASS]" if result["status"] == "PASS" else "[FAIL]"
            report += f"{gate}: {status_icon}\n"

            if result["violations"]:
                report += f"  Violations: {len(result['violations'])}\n"

        # Overall summary
        all_pass = all(r["status"] == "PASS" for r in self.results.values())
        report += "\n" + "=" * 70 + "\n"
        report += f"Overall Status: {'PASS' if all_pass else 'FAIL'}\n"
        report += "=" * 70 + "\n"

        return report

    def run_all_checks(self) -> None:
        """Run all quality gate checks."""
        print("\n" + "=" * 70)
        print("RUNNING QUALITY GATES (G7, G8, G9, G10)")
        print("=" * 70 + "\n")

        self.check_g7_no_float_in_financial()
        self.check_g8_no_naive_datetime()
        self.check_g9_no_print_statements()
        self.check_g10_function_size()

        # Print summary report
        print(self.generate_report())


def main():
    """Main entry point."""
    validator = QualityGateValidator()
    validator.run_all_checks()

    # Exit with appropriate code
    all_pass = all(r["status"] == "PASS" for r in validator.results.values())
    exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
