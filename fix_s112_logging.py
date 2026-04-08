#!/usr/bin/env python3
"""
Fix S112 linting errors in instrument_scanner.py by adding logging to
try-except-continue patterns.
"""

import re

# Read the file
with open("src/iatb/scanner/instrument_scanner.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add logging import after existing imports
if "import logging" not in content:
    # Find the position after the last import block
    import_pattern = r'(from iatb\.market_strength\.strength_scorer import StrengthInputs, StrengthScorer\n)'
    replacement = r'\1\nimport logging\n\nlogger = logging.getLogger(__name__)'
    content = re.sub(import_pattern, replacement, content)

# Fix the 4 try-except-continue patterns at specific lines
# Pattern 1: Line 367 - around "all_data.append(market_data)"
pattern1 = r'''(\s+)all_data\.append\(market_data\)
\1except Exception:  # nosec - B112: scanner continues on individual failures
\1+continue'''

replacement1 = r'''\1all_data.append(market_data)
\1except Exception as exc:  # nosec - B112: scanner continues on individual failures
\1    logger.debug("Failed to fetch market data for symbol %s: %s", symbol, exc)
\1    continue'''

content = re.sub(pattern1, replacement1, content)

# Pattern 2: Line 384 - around indicator calculation
pattern2 = r'''(\s+)closes\.append\(_to_decimal\(_extract_value\(row_dict, \("close", "CLOSE"\)\), "close"\)\)
\1+highs\.append\(_to_decimal\(_extract_value\(row_dict, \("high", "HIGH"\)\), "high"\)\)
\1+lows\.append\(_to_decimal\(_extract_value\(row_dict, \("low", "LOW"\)\), "low"\)\)
\1except Exception:  # nosec - B112: scanner continues on individual failures
\1+continue'''

replacement2 = r'''\1closes.append(_to_decimal(_extract_value(row_dict, ("close", "CLOSE")), "close"))
\1    highs.append(_to_decimal(_extract_value(row_dict, ("high", "HIGH")), "high"))
\1    lows.append(_to_decimal(_extract_value(row_dict, ("low", "LOW")), "low"))
\1except Exception as exc:  # nosec - B112: scanner continues on individual failures
\1    logger.debug("Failed to parse indicator row: %s", exc)
\1    continue'''

content = re.sub(pattern2, replacement2, content)

# Pattern 3: Line 454 - around volume calculation
pattern3 = r'''(\s+)\)
\1+volumes\.append\(vol\)
\1except Exception:  # nosec - B112: scanner continues on individual failures
\1+continue'''

replacement3 = r'''\1                )
\1                volumes.append(vol)
\1except Exception as exc:  # nosec - B112: scanner continues on individual failures
\1    logger.debug("Failed to parse volume row: %s", exc)
\1    continue'''

content = re.sub(pattern3, replacement3, content)

# Pattern 4: Line 469 - around close price
pattern4 = r'''(\s+)close = _to_decimal\(_extract_value\(row_dict, \("close", "CLOSE"\)\), "close"\)
\1+closes\.append\(close\)
\1except Exception:  # nosec - B112: scanner continues on individual failures
\1+continue'''

replacement4 = r'''\1                close = _to_decimal(_extract_value(row_dict, ("close", "CLOSE")), "close")
\1                closes.append(close)
\1except Exception as exc:  # nosec - B112: scanner continues on individual failures
\1    logger.debug("Failed to parse close price row: %s", exc)
\1    continue'''

content = re.sub(pattern4, replacement4, content)

# Write the fixed content
with open("src/iatb/scanner/instrument_scanner.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed S112 linting errors in instrument_scanner.py")