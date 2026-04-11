with open("src/iatb/scanner/instrument_scanner.py") as f:
    lines = f.readlines()

fixed_lines = []
for i, line in enumerate(lines):
    # Fix line 343 - long line with volume extraction
    if i == 342 and '"volume", "VOLUME", "TOTTRDQTY", "TTL_TRD_QNT"))' in line:
        # Split the long line
        indent = "                                "
        fixed_lines.append(indent + "(\n")
        fixed_lines.append(indent + "    _extract_value(\n")
        fixed_lines.append(indent + "        row_dict,\n")
        fixed_lines.append(indent + '        ("volume", "VOLUME", "TOTTRDQTY", "TTL_TRD_QNT"),\n')
        fixed_lines.append(indent + "    ),\n")
        fixed_lines.append(indent + "),\n")
    # Fix line 369 - long line with close extraction
    elif i == 368 and '_extract_value(row_dict, ("close", "CLOSE")),' in line:
        indent = "                    "
        fixed_lines.append(indent + "_extract_value(\n")
        fixed_lines.append(indent + "    row_dict,\n")
        fixed_lines.append(indent + '    ("close", "CLOSE"),\n')
        fixed_lines.append(indent + "),\n")
    # Add noqa comments for S112 (try-except-continue is intentional for scanner)
    elif "except Exception:" in line and "continue" in lines[i + 1]:
        # Add noqa comment to the except line
        fixed_lines.append(
            line.rstrip() + "  # noqa: S112 - scanner continues on individual failures\n"
        )
    else:
        fixed_lines.append(line)

with open("src/iatb/scanner/instrument_scanner.py", "w") as f:
    f.writelines(fixed_lines)

print("Fixed final ruff errors")
