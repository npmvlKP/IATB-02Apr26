with open("src/iatb/scanner/instrument_scanner.py") as f:
    content = f.read()

# Replace the long line
old = '                    breadth_ratio=Decimal("1.5"),  # Placeholder; can be calculated from breadth data\n'
new = '                    breadth_ratio=Decimal("1.5"),\n'

content = content.replace(old, new)

with open("src/iatb/scanner/instrument_scanner.py", "w") as f:
    f.write(content)

print("Fixed line 374")
