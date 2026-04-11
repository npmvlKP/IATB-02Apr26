with open("src/iatb/scanner/instrument_scanner.py") as f:
    lines = f.readlines()

# Find and fix the imports
new_lines = []
for i, line in enumerate(lines):
    if "from collections.abc import Callable, Mapping, Sequence" in line:
        new_lines.append("from collections.abc import Callable, Iterable, Mapping, Sequence\n")
    elif "from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer" in line:
        new_lines.append(line)
        # Add IndicatorSnapshot import after strength_scorer import
        if i + 1 < len(lines) and not lines[i + 1].strip().startswith("from"):
            new_lines.append("from iatb.market_strength.indicators import IndicatorSnapshot\n")
    else:
        new_lines.append(line)

with open("src/iatb/scanner/instrument_scanner.py", "w") as f:
    f.writelines(new_lines)

print("Fixed imports successfully")
