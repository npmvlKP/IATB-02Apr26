#!/usr/bin/env python
"""Add deterministic seeds to remaining test files."""

import re

files_to_update = [
    "tests/core/test_types.py",
    "tests/data/test_instrument_master.py",
    "tests/execution/test_instrument_resolver.py",
    "tests/integration/test_backtesting/test_session_masks.py",
    "tests/risk/test_daily_loss_guard.py",
    "tests/safety/test_safety.py",
    "tests/selection/test_selection.py",
    "tests/selection/test_selector_validator.py",
    "tests/selection/test_sentiment_signal.py",
    "tests/selection/test_strength_signal.py",
    "tests/unit/test_core/test_clock.py",
]

seed_block = """# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)
"""

for filepath in files_to_update:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check if seeds already present
        if "random.seed(42)" in content or "np.random.seed(42)" in content:
            print(f"SKIP: {filepath} - seeds already present")
            continue
        
        # Find import section and add seeds after it
        # Look for the last import statement
        import_pattern = r"(^import .*$|^from .*$)"
        matches = list(re.finditer(import_pattern, content, re.MULTILINE))
        
        if not matches:
            print(f"SKIP: {filepath} - no imports found")
            continue
        
        last_import = matches[-1]
        insert_pos = last_import.end()
        
        # Insert seeds after the last import
        new_content = content[:insert_pos] + "\n\n" + seed_block + content[insert_pos:]
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        print(f"[OK] Added seeds to {filepath}")
    except Exception as e:
        print(f"[ERR] Error with {filepath}: {e}")

print("\nDone!")
