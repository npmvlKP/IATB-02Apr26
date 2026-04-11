import ast
import sys

files = ["src/iatb/risk/stop_loss.py", "src/iatb/rl/reward.py"]
violations = []

for f in files:
    with open(f) as fp:
        tree = ast.parse(fp.read(), filename=f)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            lines = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
            if lines > 50:
                violations.append((f, node.name, node.lineno, lines))

if violations:
    for v in violations:
        sys.stderr.write(f"{v[0]}: Function {v[1]} at line {v[2]} has {v[3]} LOC (>50)\n")
    sys.exit(1)
else:
    sys.stderr.write("All functions <=50 LOC\n")
