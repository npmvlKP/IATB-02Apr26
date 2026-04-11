with open("src/iatb/scanner/instrument_scanner.py") as f:
    content = f.read()

# Fix the broken ternary expression
old_ternary = """                    atr_pct=indicators.atr / latest_row["close"]  # type: ignore[operator]
                        if latest_row["close"] > Decimal("0")  # type: ignore[operator]
                    breadth_ratio=Decimal("1.5"),"""

new_ternary = """                    atr_pct=(
                        indicators.atr / latest_row["close"]  # type: ignore[operator]
                        if latest_row["close"] > Decimal("0")  # type: ignore[operator]
                        else Decimal("0")
                    ),
                    breadth_ratio=Decimal("1.5"),"""

content = content.replace(old_ternary, new_ternary)

with open("src/iatb/scanner/instrument_scanner.py", "w") as f:
    f.write(content)

print("Fixed ternary expression")
