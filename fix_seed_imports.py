#!/usr/bin/env python
"""Fix missing imports for seed statements."""

import re

files_to_fix = [
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

for filepath in files_to_fix:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check which imports are needed
        needs_random = "random.seed(42)" in content and "import random" not in content
        needs_np = "np.random.seed(42)" in content and "import numpy" not in content and "import np" not in content
        needs_torch = "torch.manual_seed(42)" in content and "import torch" not in content
        
        if not (needs_random or needs_np or needs_torch):
            print(f"SKIP: {filepath} - all imports present")
            continue
        
        # Find where to insert imports (before seed block)
        import_block = []
        if needs_random:
            import_block.append("import random")
        if needs_np:
            import_block.append("import numpy as np")
        if needs_torch:
            import_block.append("import torch")
        
        # Insert before seed block
        seed_pattern = r"(# Set deterministic seeds for reproducibility)"
        match = re.search(seed_pattern, content)
        
        if match:
            insert_pos = match.start()
            new_content = content[:insert_pos] + "\n".join(import_block) + "\n\n" + content[insert_pos:]
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            print(f"[OK] Fixed imports in {filepath}")
        else:
            print(f"SKIP: {filepath} - no seed block found")
    except Exception as e:
        print(f"[ERR] Error with {filepath}: {e}")

print("\nDone!")