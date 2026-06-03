"""Fix mypy Decimal|Literal error by adding explicit type annotations."""
import re

filepath = "src/iatb/selection/auto_selector.py"
content = open(filepath).read()

# Replace the two problematic lines
old_line1 = '        clamped = total if total > Decimal("0") else Decimal("0")'
old_line2 = '        return clamped if clamped < Decimal("1") else Decimal("1")'

new_lines = (
    '        zero_bound: Decimal = Decimal("0")\n'
    '        one_bound: Decimal = Decimal("1")\n'
    '        clamped: Decimal = total if total > zero_bound else zero_bound\n'
    '        result: Decimal = clamped if clamped < one_bound else one_bound\n'
    '        return result'
)

if old_line1 in content and old_line2 in content:
    idx1 = content.index(old_line1)
    idx2 = content.index(old_line2)
    # Replace both lines
    content = content[:idx1] + new_lines + content[idx2 + len(old_line2):]
    open(filepath, "w").write(content)
    print("SUCCESS: Replaced Decimal clamp lines with typed annotations")
else:
    print("FAILED: Could not find target lines")
    print(f"Line1 found: {old_line1 in content}")
    print(f"Line2 found: {old_line2 in content}")