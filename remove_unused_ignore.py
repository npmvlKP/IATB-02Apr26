with open("src/iatb/scanner/instrument_scanner.py") as f:
    content = f.read()

# Remove the unused type: ignore comment
content = content.replace(
    '                    ) > cast("datetime", latest_row["timestamp"]):  # type: ignore[operator]',
    '                    ) > cast("datetime", latest_row["timestamp"]):',
)

with open("src/iatb/scanner/instrument_scanner.py", "w") as f:
    f.write(content)

print("Removed unused type: ignore comment")
