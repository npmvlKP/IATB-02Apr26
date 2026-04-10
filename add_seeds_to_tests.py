"""Add deterministic seeds to all test files at module level."""
import ast
import os

# Find all test files (exclude __pycache__ and .bak files)
test_files = []
for root, dirs, files in os.walk("tests"):
    # Skip __pycache__ directories
    if "__pycache__" in root:
        continue
    for file in files:
        # Only process .py files
        if not file.endswith(".py"):
            continue
        # Skip backup files
        if file.endswith(".bak") or file.endswith(".bak2") or file.endswith(".bak3"):
            continue
        if file.startswith("test_") or file.endswith("_test.py"):
            test_files.append(os.path.join(root, file))

print(f"Found {len(test_files)} test files")

# Seed code to add
SEED_IMPORTS = """import random
import numpy as np
import torch

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)
"""

for filepath in test_files:
    print(f"Processing {filepath}...")

    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # Check if seeds are already present
    if "random.seed(42)" in content:
        print("  - Seeds already present, skipping")
        continue

    # Parse the file with AST
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        print(f"  - Syntax error, skipping: {e}")
        continue

    # Find the last import statement and the first non-import statement
    lines = content.split("\n")
    last_import_end = -1
    first_non_import = len(lines)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            # This is an import, find its end line
            if hasattr(node, "end_lineno") and node.end_lineno:
                last_import_end = max(last_import_end, node.end_lineno)

    # Find the first class or function definition
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if hasattr(node, "lineno") and node.lineno:
                first_non_import = min(first_non_import, node.lineno)

    # Insert seeds between last import and first class/function
    if last_import_end < first_non_import:
        insert_idx = last_import_end
        # Insert seed code with proper spacing
        lines.insert(insert_idx, "")
        lines.insert(insert_idx + 1, SEED_IMPORTS.strip())

        # Write back
        new_content = "\n".join(lines)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        print(f"  - Added seeds at line {insert_idx + 1}")
    else:
        print("  - Could not find suitable insertion point, skipping")

print("\nDone!")
