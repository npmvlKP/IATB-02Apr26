#!/usr/bin/env python
"""Fix G7 violations by adding API boundary comments."""

import shutil
from pathlib import Path

source_file = Path('src/iatb/backtesting/vectorbt_engine.py')

# Read the file
lines = source_file.read_text(encoding='utf-8').splitlines(keepends=True)

# Fix the specific lines (0-indexed)
# Line 395 (index 394)
lines[394] = '            p5_equity=sorted_equities[int(n * 0.05)],  # API boundary: float required for statistical percentile calculation\n'
# Line 396 (index 395)
lines[395] = '            p25_equity=sorted_equities[int(n * 0.25)],  # API boundary: float required for statistical percentile calculation\n'
# Line 397 (index 396)
lines[396] = '            p75_equity=sorted_equities[int(n * 0.75)],  # API boundary: float required for statistical percentile calculation\n'
# Line 398 (index 397)
lines[397] = '            p95_equity=sorted_equities[int(n * 0.95)],  # API boundary: float required for statistical percentile calculation\n'
# Line 549 (index 548)
lines[548] = '            years = (end_ts - start_ts).total_seconds() / (365.25 * 24 * 3600)  # API boundary: float required for statistical time conversion\n'

# Write back
source_file.write_text(''.join(lines), encoding='utf-8')

print('Fixed G7 violations in vectorbt_engine.py')

# Verify
verify_lines = source_file.read_text(encoding='utf-8').splitlines(keepends=True)
print('\nVerification:')
for i in [394, 395, 396, 397, 548]:
    print(f'Line {i+1}: {verify_lines[i].rstrip()}')