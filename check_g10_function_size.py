import ast
import os

def check_function_size(filepath, max_lines=50):
    """Check if all functions in a file are <= max_lines."""
    with open(filepath) as f:
        source = f.read()
    
    tree = ast.parse(source)
    violations = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Calculate lines of code
            lines = source.split('\n')
            start_line = node.lineno - 1
            end_line = node.end_lineno if node.end_lineno else start_line
            func_lines = end_line - start_line + 1
            
            if func_lines > max_lines:
                violations.append({
                    'name': node.name,
                    'line': start_line + 1,
                    'lines': func_lines
                })
    
    return violations

print("=== G10: Function size check (max 50 LOC) ===")
all_files_pass = True

for root, dirs, files in os.walk('src/iatb/data'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            violations = check_function_size(filepath)
            
            if violations:
                all_files_pass = False
                print(f'\n{filepath}:')
                for v in violations:
                    print(f"  Function '{v['name']}' at line {v['line']}: {v['lines']} LOC (max: 50)")

if all_files_pass:
    print('G10 (function size): PASS - All functions <= 50 LOC')
else:
    print('\nG10 (function size): FAIL - Some functions exceed 50 LOC')