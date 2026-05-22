"""Remove 'import torch' and 'torch.manual_seed(42)' from test files.

The conftest.py set_deterministic_seeds fixture already handles torch seeding,
so individual test files do not need to import torch for this purpose.
"""

import os
import re

root = "G:/IATB-02Apr26/IATB/tests"
modified = []

for dirpath, dirnames, filenames in os.walk(root):
    for fname in filenames:
        if not fname.endswith(".py"):
            continue
        if fname in ("conftest.py", "conftest_optimized.py"):
            continue
        fpath = os.path.join(dirpath, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        if "import torch" not in content and "torch.manual_seed" not in content:
            continue

        lines = content.split("\n")
        new_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Handle try/except block for torch import
            if stripped == "try:" and i + 1 < len(lines) and "import torch" in lines[i + 1]:
                j = i + 1
                end = i
                while j < len(lines):
                    s = lines[j].strip()
                    if s.startswith("except ") and (
                        "OSError" in s or "ImportError" in s
                    ):
                        # Skip the except line and its body
                        j += 1
                        base_indent = len(lines[i]) - len(lines[i].lstrip())
                        while j < len(lines):
                            if lines[j].strip() == "":
                                j += 1
                                continue
                            curr_indent = len(lines[j]) - len(lines[j].lstrip())
                            if curr_indent <= base_indent and lines[j].strip():
                                break
                            j += 1
                        end = j
                        break
                    j += 1
                else:
                    end = j
                i = end
                continue

            # Handle bare 'import torch' line
            if stripped == "import torch" or stripped.startswith("import torch ") or stripped.startswith("import torch,"):
                # Check if next non-blank line is torch.manual_seed
                next_i = i + 1
                while next_i < len(lines) and lines[next_i].strip() == "":
                    next_i += 1
                if next_i < len(lines) and lines[next_i].strip() in (
                    "torch.manual_seed(42)",
                    "torch.manual_seed(DETERMINISTIC_SEED)",
                ):
                    i = next_i + 1
                    continue
                i += 1
                continue

            # Handle standalone torch.manual_seed line
            if stripped in (
                "torch.manual_seed(42)",
                "torch.manual_seed(DETERMINISTIC_SEED)",
            ):
                i += 1
                continue

            new_lines.append(line)
            i += 1

        new_content = "\n".join(new_lines)
        new_content = re.sub(r"\n{3,}", "\n\n", new_content)
        if new_content != content:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(new_content)
            modified.append(fpath)

print(f"Modified {len(modified)} files")
for f in sorted(modified):
    print(f)
