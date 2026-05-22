import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import ast
import sys
import logging

logging.basicConfig(level=logging.INFO)


def check_no_float_in_financial_paths() -> None:
    """Check for float usage in financial paths."""
    root = Path("src/iatb/storage/parquet_store.py")
    financial_keywords = {"price", "volume", "quantity", "open", "high", "low", "close"}
    float_pattern = re.compile(r"float\(")
    visited_nodes = set()

    def visit_node(node: ast.AST) -> None:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.For, ast.While, ast.If)):
            for n in ast.walk(node):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "float":
                    logging.error(f"Found float() call at line {n.lineno}: {ast.unparse(n)}")
                    sys.exit(1)
                if isinstance(n, ast.Name) and n.id in financial_keywords:
                    logging.info(f"Valid financial keyword '{n.id}' at line {n.lineno}")
        for child in ast.iter_child_nodes(node):
            if child not in visited_nodes:
                visited_nodes.add(child)
                visit_node(child)

    try:
        tree = ast.parse(root.read_text(), filename=str(root))
    except SyntaxError as e:
        logging.error(f"Syntax error: {e}")
        sys.exit(1)
    visit_node(tree)
    logging.info("✓ No float usage in financial paths")


def check_no_naive_datetime() -> None:
    """Check for naive datetime usage."""
    root = Path("src/iatb/storage/parquet_store.py")
    naive_pattern = re.compile(r"datetime\.(now|utcnow|fromtimestamp)\()
    naive_calls = []
    for match in naive_pattern.finditer(root.read_text()):
        if "tzinfo" not in root.read_text()[match.start() : match.end() + 50]:
            naive_calls.append(match.group())
    if naive_calls:
        logging.error(f"Found naive datetime calls: {naive_calls}")
        sys.exit(1)
    logging.info("✓ No naive datetime usage")


def check_no_print() -> None:
    """Check for print statements."""
    root = Path("src/iatb/storage/parquet_store.py")
    if "print(" in root.read_text() or "print (" in root.read_text():
        logging.error("Found print statement")
        sys.exit(1)
    logging.info("✓ No print statements")


def check_function_size() -> None:
    """Check function size ≤50 LOC."""
    root = Path("src/iatb/storage/parquet_store.py")
    tree = ast.parse(root.read_text(), filename=str(root))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start_line = node.lineno
            end_line = node.end_lineno
            if end_line and (end_line - start_line + 1) > 50:
                logging.error(f"Function '{node.name}' exceeds 50 lines: {end_line - start_line + 1}")
                sys.exit(1)
    logging.info("✓ All functions ≤50 LOC")


def run_gates() -> None:
    """Run all validation gates."""
    logging.info("Running validation gates...")
    check_no_float_in_financial_paths()
    check_no_naive_datetime()
    check_no_print()
    check_function_size()
    logging.info("All gates passed!")


if __name__ == "__main__":
    run_gates()