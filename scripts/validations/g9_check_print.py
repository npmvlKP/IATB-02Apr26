#!/usr/bin/env python3
"""
G9: Check for print() statements in src/ directory.
Must return 0 print() instances.
"""

import ast
import sys
from pathlib import Path
from typing import List, Tuple

class PrintFinder(ast.NodeVisitor):
    """AST visitor to find print() calls."""
    def __init__(self):
        self.print_calls = []
    
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == 'print':
            self.print_calls.append(node.lineno)
        self.generic_visit(node)

def check_file_for_print(filepath: Path) -> List[Tuple[int, str, str]]:
    """Check a file for print() statements using AST."""
    violations = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        finder = PrintFinder()
        finder.visit(tree)
        
        for line_num in finder.print_calls:
            # Get the actual line
            line_content = content.split('\n')[line_num - 1].strip()
            violations.append((line_num, line_content, filepath.name))
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
    
    return violations

def main():
    print("=== G9 Validation: Print Statements ===\n")
    
    src_dir = Path("src/iatb")
    if not src_dir.exists():
        print(f"ERROR: Source directory not found: {src_dir}")
        return 1
    
    all_violations = []
    total_files_checked = 0
    
    # Find all Python files recursively
    python_files = list(src_dir.rglob("*.py"))
    
    for py_file in python_files:
        total_files_checked += 1
        violations = check_file_for_print(py_file)
        
        if violations:
            all_violations.extend(violations)
            print(f"FAIL: {py_file.relative_to(src_dir.parent)} - Found {len(violations)} print() call(s):")
            for line_num, content, _ in violations:
                print(f"  Line {line_num}: {content}")
    
    print(f"\n--- Summary ---")
    print(f"Files checked: {total_files_checked}")
    print(f"Total print() violations: {len(all_violations)}")
    
    if len(all_violations) == 0:
        print("G9 Status: PASS")
        return 0
    else:
        print("G9 Status: FAIL")
        return 1

if __name__ == "__main__":
    sys.exit(main())
