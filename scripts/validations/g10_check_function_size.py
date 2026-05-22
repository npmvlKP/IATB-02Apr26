#!/usr/bin/env python3
"""
G10: Check function sizes - all functions must be ≤50 lines.
"""

import ast
import sys
from pathlib import Path
from typing import List, Tuple, Dict

class FunctionSizeAnalyzer(ast.NodeVisitor):
    """AST visitor to find all functions and their sizes."""
    def __init__(self):
        self.functions = []  # List of (name, start_line, end_line, file_path)
    
    def visit_FunctionDef(self, node):
        self._record_function(node)
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node):
        self._record_function(node)
        self.generic_visit(node)
    
    def _record_function(self, node):
        # Get the actual end line - we need to look at the node's body
        if node.body:
            start_line = node.lineno
            # The end line is the last statement's end line
            last_stmt = node.body[-1]
            end_line = last_stmt.end_lineno if hasattr(last_stmt, 'end_lineno') else last_stmt.lineno
        else:
            start_line = node.lineno
            end_line = node.lineno
        
        loc = end_line - start_line + 1
        self.functions.append({
            'name': node.name,
            'start': start_line,
            'end': end_line,
            'loc': loc,
            'is_method': node.col_offset > 0  # Check if it's indented (method)
        })

def count_function_loc(source_lines: List[str], start_line: int, end_line: int) -> int:
    """Count non-empty, non-comment lines in a function."""
    count = 0
    for i in range(start_line - 1, min(end_line, len(source_lines))):
        line = source_lines[i].strip()
        if line and not line.startswith('#'):
            count += 1
    return count

def check_file_function_sizes(filepath: Path, max_size: int = 50) -> List[Tuple[int, str, str, int]]:
    """Check function sizes in a file. Returns list of (line, func_name, file, loc)."""
    violations = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            source_lines = content.split('\n')
        
        tree = ast.parse(content)
        analyzer = FunctionSizeAnalyzer()
        analyzer.visit(tree)
        
        for func in analyzer.functions:
            # Calculate actual LOC (non-empty, non-comment)
            actual_loc = count_function_loc(source_lines, func['start'], func['end'])
            
            if actual_loc > max_size:
                violations.append((
                    func['start'],
                    func['name'],
                    filepath.name,
                    actual_loc
                ))
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error processing {filepath}: {e}", file=sys.stderr)
    
    return violations

def main():
    print("=== G10 Validation: Function Size Check ===\n")
    
    src_dir = Path("src/iatb")
    if not src_dir.exists():
        print(f"ERROR: Source directory not found: {src_dir}")
        return 1
    
    all_violations = []
    total_files_checked = 0
    total_functions_checked = 0
    
    # Find all Python files recursively
    python_files = list(src_dir.rglob("*.py"))
    
    for py_file in python_files:
        total_files_checked += 1
        violations = check_file_function_sizes(py_file)
        total_functions_checked += len(violations)
        
        if violations:
            all_violations.extend(violations)
            print(f"FAIL: {py_file.relative_to(src_dir.parent)} - Found {len(violations)} oversized function(s):")
            for line_num, func_name, _, loc in violations:
                print(f"  {func_name}() at line {line_num}: {loc} LOC")
    
    print(f"\n--- Summary ---")
    print(f"Files checked: {total_files_checked}")
    print(f"Functions exceeding 50 LOC: {len(all_violations)}")
    
    if len(all_violations) == 0:
        print("G10 Status: PASS")
        return 0
    else:
        print("G10 Status: FAIL")
        return 1

if __name__ == "__main__":
    sys.exit(main())
