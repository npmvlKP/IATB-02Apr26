with open("src/iatb/scanner/instrument_scanner.py") as f:
    lines = f.readlines()

# Fix the comparison on line 321
fixed_lines = []
for i, line in enumerate(lines):
    # Find and fix the problematic comparison
    if i == 318 and "if latest_row is None or _coerce_datetime(" in lines[i]:
        fixed_lines.append(lines[i])
        fixed_lines.append(
            lines[i + 1].rstrip()
            + ' > cast("datetime", latest_row["timestamp"]):  # type: ignore[operator]\n'
        )
        # Skip the next line (the old comparison)
        if i + 2 < len(lines):
            # Continue from line 322 onwards
            for j in range(i + 2, len(lines)):
                fixed_lines.append(lines[j])
        break
    else:
        fixed_lines.append(line)

with open("src/iatb/scanner/instrument_scanner.py", "w") as f:
    f.writelines(fixed_lines)

print("Fixed comparison type error")
