"""Validation scripts for G8, G9, G10 quality gates."""
import ast
import sys


def check_g8_no_naive_datetime(filepath: str) -> None:
    """G8: Check for naive datetime usage."""
    with open(filepath) as f:
        content = f.read()
        tree = ast.parse(content)

    naive_dt_found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if hasattr(node.func, "id"):
                if node.func.id in ["datetime", "now"]:
                    naive_dt_found = True
                    print(f"G8 FAIL: Found naive datetime call at line {node.lineno}")
                    break
            elif hasattr(node.func, "attr"):
                if node.func.attr in ["now", "utcnow"]:
                    naive_dt_found = True
                    print(f"G8 FAIL: Found naive datetime.{node.func.attr} at line {node.lineno}")
                    break

    if not naive_dt_found:
        print("G8 PASS: No naive datetime found")
    sys.exit(1 if naive_dt_found else 0)


def check_g9_no_print(filepath: str) -> None:
    """G9: Check for print() statements."""
    with open(filepath) as f:
        content = f.read()
        tree = ast.parse(content)

    print_found = any(
        isinstance(node, ast.Call) and hasattr(node.func, "id") and node.func.id == "print"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    )

    print(
        "G9 PASS: No print() statements found"
        if not print_found
        else "G9 FAIL: print() statements found"
    )
    sys.exit(1 if print_found else 0)


def check_g10_function_size(filepath: str) -> None:
    """G10: Check function size <=50 LOC."""
    with open(filepath) as f:
        lines = f.readlines()
        content = "".join(lines)
        tree = ast.parse(content)

    func_size_fail = any(
        (node.end_lineno - node.lineno + 1) > 50
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    )

    print(
        "G10 PASS: All functions <=50 LOC"
        if not func_size_fail
        else "G10 FAIL: Functions >50 LOC found"
    )
    sys.exit(1 if func_size_fail else 0)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python validate_g8_g9_g10.py <gate> <filepath>")
        print("Gates: g8, g9, g10")
        sys.exit(1)

    gate = sys.argv[1].lower()
    filepath = sys.argv[2]

    if gate == "g8":
        check_g8_no_naive_datetime(filepath)
    elif gate == "g9":
        check_g9_no_print(filepath)
    elif gate == "g10":
        check_g10_function_size(filepath)
    else:
        print(f"Unknown gate: {gate}. Use g8, g9, or g10.")
        sys.exit(1)
