# Verification Scripts Guide

This directory contains comprehensive Python verification scripts to validate the Core Event Architecture implementation.

## Overview

Three main verification scripts are provided:

1. **verify_core_architecture.py** - Comprehensive module verification
2. **run_quality_gates.py** - Quality gates compliance check
3. **usage_examples.py** - Practical usage examples

---

## 1. Comprehensive Architecture Verification

### Script: `verify_core_architecture.py`

Verifies all components of the Core Event Architecture are working correctly.

### How to Run

```bash
# Option 1: Using Python directly
python scripts/verify_core_architecture.py

# Option 2: Using Poetry (recommended)
poetry run python scripts/verify_core_architecture.py
```

### What It Checks

✅ **Type Definitions** - Verifies Price, Quantity, and Timestamp types  
✅ **Enum Definitions** - Checks all enum values (Exchange, MarketType, etc.)  
✅ **Event System** - Validates event creation, immutability, and UTC timestamps  
✅ **Event Bus** - Tests pub/sub functionality and topic routing  
✅ **Engine Orchestrator** - Verifies lifecycle management and task execution  
✅ **Clock & Sessions** - Validates UTC clock and market session helpers  
✅ **Configuration** - Checks config loading and defaults  
✅ **Exception Hierarchy** - Verifies all exception types and inheritance  

### Expected Output

```
============================================================
  CORE EVENT ARCHITECTURE VERIFICATION
============================================================

============================================================
  1. Verifying Type Definitions
============================================================
✅ Price type works: 100.50
✅ Quantity type works: 10
✅ Timestamp type works: 2024-04-03 01:30:00+00:00

[... more checks ...]

============================================================
  VERIFICATION SUMMARY
============================================================

Checks Passed: 8/8

✅ 🎉 All verification checks passed!
```

### Exit Codes

- `0` - All checks passed
- `1` - One or more checks failed

---

## 2. Quality Gates Verification

### Script: `run_quality_gates.py`

Runs all quality gate checks to ensure code meets project standards.

### How to Run

```bash
# Option 1: Using Python directly
python scripts/run_quality_gates.py

# Option 2: Using Poetry (recommended)
poetry run python scripts/run_quality_gates.py
```

### What It Checks

#### G1 - Lint Check
- Runs `ruff check` on source and test files
- Ensures no linting violations

#### G2 - Format Check
- Runs `ruff format --check`
- Ensures code follows formatting standards

#### G3 - Type Checking
- Runs `mypy --strict`
- Ensures full type safety with strict mode

#### G4 - Security Scan
- Runs `bandit` security scanner
- Checks for security vulnerabilities

#### G6 - Test Coverage
- Runs `pytest` with coverage reporting
- Requires minimum 90% coverage

#### G7 - No Float in Financial Paths
- Scans for `float` usage in financial modules
- Ensures only `Decimal` is used for monetary values

#### G8 - No Naive Datetime
- Scans for `datetime.now()` usage
- Ensures all datetime objects are UTC-aware

#### G9 - No Print Statements
- Scans for `print()` statements
- Ensures only structured logging is used

### Expected Output

```
======================================================================
  IATB QUALITY GATES VERIFICATION
======================================================================

🔍 Running: G1 - Lint Check
   Command: poetry run ruff check src/ tests/
----------------------------------------------------------------------
Success: no issues found in 10 source files
✅ G1 - Lint Check: PASSED

[... more gates ...]

======================================================================
  QUALITY GATES SUMMARY
======================================================================

Gates Passed: 8/8

  G1 - Lint Check: ✅ PASSED
  G2 - Format Check: ✅ PASSED
  G3 - Type Checking: ✅ PASSED
  G4 - Security Scan: ✅ PASSED
  G6 - Test Coverage: ✅ PASSED
  G7 - No Float: ✅ PASSED
  G8 - No Naive DT: ✅ PASSED
  G9 - No Print: ✅ PASSED

✅ 🎉 All quality gates passed!
```

### Exit Codes

- `0` - All quality gates passed
- `1` - One or more quality gates failed

---

## 3. Usage Examples

### Script: `usage_examples.py`

Demonstrates practical usage of all Core Event Architecture components.

### How to Run

```bash
# Option 1: Using Python directly
python scripts/usage_examples.py

# Option 2: Using Poetry (recommended)
poetry run python scripts/usage_examples.py
```

### What It Shows

#### Example 1: Types and Enums
- Type-safe price and quantity calculations
- Risk management calculations (target, stop-loss)
- Enum usage for orders

#### Example 2: Creating Events
- MarketTickEvent creation
- OrderUpdateEvent creation
- SignalEvent creation
- RegimeChangeEvent creation

#### Example 3: Event Bus (Pub/Sub)
- Setting up event handlers
- Subscribing to topics with wildcards
- Publishing events
- Topic-based routing

#### Example 4: Engine Orchestrator
- Starting/stopping the engine
- Running background tasks
- Event bus integration
- Lifecycle management

#### Example 5: Clock and Market Sessions
- UTC clock usage
- Market session retrieval
- Trading status checking
- Session times for different exchanges

#### Example 6: Configuration
- Loading configuration
- Environment variable usage
- Configuration defaults

#### Example 7: Error Handling
- ValidationError handling
- EngineError handling
- Proper error handling patterns

#### Example 8: Complete Workflow
- Full trading system initialization
- Signal generation and processing
- System shutdown

### Expected Output

```
======================================================================
  CORE EVENT ARCHITECTURE - USAGE EXAMPLES
======================================================================

======================================================================
  Example 1: Types and Enums
======================================================================

Trade Setup:
  Entry Price: ₹2450.50
  Quantity: 50 shares
  Position Value: ₹122525.00

[... more examples ...]

======================================================================
  Examples Complete
======================================================================

✅ All examples executed successfully!

For more information, see:
  - scripts/verify_core_architecture.py - Verification script
  - scripts/run_quality_gates.py - Quality gates check
  - docs/core_architecture.md - Architecture documentation
```

---

## Quick Start

### Run All Verifications

```bash
# Run all checks in sequence
poetry run python scripts/verify_core_architecture.py && \
poetry run python scripts/run_quality_gates.py && \
poetry run python scripts/usage_examples.py
```

### Individual Module Verification

You can also verify individual components by importing and testing them:

```python
from iatb.core.types import Price, Quantity
from iatb.core.enums import Exchange
from iatb.core.events import MarketTickEvent
from decimal import Decimal

# Test types
price: Price = Decimal("100.50")
print(f"Price: {price}")

# Test enums
exchange = Exchange.NSE
print(f"Exchange: {exchange}")

# Test events
tick = MarketTickEvent(
    exchange=Exchange.NSE,
    symbol="RELIANCE",
    price=Decimal("2500.75"),
    quantity=Decimal("100"),
)
print(f"Event ID: {tick.event_id}")
```

---

## Troubleshooting

### Import Errors

If you get import errors, ensure you're running the script from the project root:

```bash
# From project root (g:/IATB-02Apr26/IATB)
poetry run python scripts/verify_core_architecture.py
```

### Poetry Not Installed

If you don't have Poetry installed:

```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Or using pip
pip install poetry

# Install dependencies
poetry install
```

### Quality Gate Failures

If quality gates fail, check the specific error messages:

```bash
# Run linting with auto-fix
poetry run ruff check --fix src/ tests/
poetry run ruff format src/ tests/

# Run type checking for details
poetry run mypy src/ --strict

# Run tests with verbose output
poetry run pytest tests/core/ --cov=src/iatb/core -v
```

---

## CI/CD Integration

These scripts can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
name: Quality Gates

on: [push, pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install Poetry
        run: curl -sSL https://install.python-poetry.org | python3 -
      
      - name: Install dependencies
        run: poetry install
      
      - name: Run verification
        run: poetry run python scripts/verify_core_architecture.py
      
      - name: Run quality gates
        run: poetry run python scripts/run_quality_gates.py
```

---

## Additional Resources

- **Project README**: `../README.md`
- **Setup Guide**: `../SETUP_COMPLETE.md`
- **Project Rules**: `../AGENTS.md`
- **Core Module**: `../src/iatb/core/`

---

## Support

If you encounter any issues:

1. Check the error messages in the output
2. Ensure all dependencies are installed: `poetry install`
3. Verify Python version: `python --version` (should be 3.12+)
4. Check that you're in the project root directory

---

## Version Information

- **Python**: 3.12+
- **Poetry**: Latest stable
- **IATB Version**: 0.1.0

Last Updated: April 3, 2026