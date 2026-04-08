#!/usr/bin/env python3
"""
Fix S112 linting errors by reading file line by line and making precise replacements.
"""

# Read the file
with open("src/iatb/scanner/instrument_scanner.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Track which lines to modify
modifications = {}

# Find and mark the 4 try-except-continue patterns
for i, line in enumerate(lines):
    # Pattern 1: Line 370 - "except Exception:" followed by continue
    if i >= 0 and "except Exception:  # nosec - B112: scanner continues on individual failures" in line:
        next_line = lines[i+1] if i+1 < len(lines) else ""
        if "continue" in next_line:
            modifications[i] = line.replace("except Exception:", "except Exception as exc:")

# Apply modifications
for line_num in modifications:
    lines[line_num] = modifications[line_num]

# Now add the logger.debug() statements before continue
new_lines = []
i = 0
while i < len(lines):
    new_lines.append(lines[i])
    
    # Check if this is an "as exc:" line that needs logging
    if "except Exception as exc:  # nosec - B112: scanner continues on individual failures" in lines[i]:
        # Check next line for continue
        if i + 1 < len(lines) and "continue" in lines[i+1]:
            # Determine which context we're in based on surrounding lines
            indent = len(lines[i]) - len(lines[i].lstrip())
            logger_line = " " * indent + 'logger.debug("Failed to process row: %s", exc)\n'
            new_lines.append(logger_line)
    i += 1

# Write the modified content
with open("src/iatb/scanner/instrument_scanner.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Fixed S112 linting errors")