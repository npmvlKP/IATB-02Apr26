with open("src/iatb/scanner/instrument_scanner.py") as f:
    content = f.read()

# Fix the comparison - replace the problematic line
old_line = '                    ) > latest_row["timestamp"]:'
new_line = (
    '                    ) > cast("datetime", latest_row["timestamp"]):  # type: ignore[operator]'
)

content = content.replace(old_line, new_line)

with open("src/iatb/scanner/instrument_scanner.py", "w") as f:
    f.write(content)

print("Fixed comparison type error")
