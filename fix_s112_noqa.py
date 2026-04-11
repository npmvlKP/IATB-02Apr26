#!/usr/bin/env python3
"""
Add # noqa: S112 to suppress try-except-continue warnings where appropriate.
"""

# Read the file
with open("src/iatb/scanner/instrument_scanner.py", encoding="utf-8") as f:
    lines = f.readlines()

# Find lines with except Exception that have nosec comment
# and add noqa: S112 to suppress the S112 warning
new_lines = []
for line in lines:
    if "except Exception:  # nosec - B112: scanner continues on individual failures" in line:
        # Add noqa: S112 to suppress the S112 rule
        line = line.replace(
            "# nosec - B112: scanner continues on individual failures",
            "# nosec - B112: scanner continues on individual failures  # noqa: S112",
        )
    new_lines.append(line)

# Write the modified content
with open("src/iatb/scanner/instrument_scanner.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Added noqa: S112 to suppress try-except-continue warnings")
