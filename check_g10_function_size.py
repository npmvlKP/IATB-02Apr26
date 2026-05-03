import ast
import os

def check_function_size(filepath, max_lines=50):
    """Check if all functions in a file are <= max_lines, respecting # noqa: G10."""
    with open(filepath, encoding='utf-8') as f:
        source = f.read()
    
    tree = ast.parse(source)
    violations = []
    lines = source.split('\n')
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check if function has # noqa: G10 exception
            func_def_line = lines[node.lineno - 1]
            if '# noqa: G10' in func_def_line:
                continue  # Skip this function, it has an exception
            
            # Calculate lines of code
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

for root, dirs, files in os.walk('src/iatb'):
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