"""Check G10 function size violations for observability files."""
import ast

files = [
    "src/iatb/core/observability/metrics.py",
    "src/iatb/core/observability/alerting.py",
]

violations = []

for filepath in files:
    with open(filepath, encoding="utf-8") as f:
        source = f.read()
    
    tree = ast.parse(source)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Get function source lines
            func_source = ast.get_source_segment(source, node)
            if func_source:
                loc = len([l for l in func_source.split("\n") if l.strip()])
                if loc > 50:
                    violations.append(f"{filepath}:{node.lineno}: {node.name} ({loc} LOC)")

if violations:
    print("G10 Violations (>50 LOC):")
    for v in violations:
        print(f"  - {v}")
else:
    print("G10: No violations (all functions <= 50 LOC)")
