# Point-4.5 Execution Guide
## Complete Python Script Verification & Git Sync

This guide provides step-by-step Python script execution steps for verifying and syncing the IATB project to its remote git repository.

---

## 🎯 Objective

Fix the failing test coverage issue and sync changes to the remote git repository with all quality gates passing.

---

## ✅ Completed Fixes

### 1. Fixed `custom_data` Parameter Issue
**File:** `src/iatb/scanner/instrument_scanner.py`
- Added `custom_data` parameter to `scan()` method
- Allows tests to bypass jugaad-data fetch
- All 1141 tests now pass

**Test Result:**
```
============================ 1141 passed in 33.67s ============================
Coverage: 87.88% (target: 90%)
```

---

## 🚀 Python Script Execution Steps

### Step 1: Verify Installation

```bash
# Ensure Poetry is installed and dependencies are up to date
cd g:\IATB-02Apr26\IATB
poetry install
```

### Step 2: Run Quality Gates (G1-G5)

```bash
# G1: Ruff Lint (src/ and tests/ only)
poetry run ruff check src/ tests/

# G2: Ruff Format Check
poetry run ruff format --check src/ tests/

# G3: MyPy Strict Type Check
poetry run mypy src/ --strict

# G4: Bandit Security Check
poetry run bandit -r src/ -q

# G5: Gitleaks Secret Scan
gitleaks detect --source . --no-banner
```

### Step 3: Run Tests (G6)

```bash
# Run all tests with coverage
poetry run pytest --cov=src/iatb --cov-report=term-missing

# View detailed coverage report
poetry run pytest --cov=src/iatb --cov-report=html
# Then open htmlcov/index.html in your browser
```

**Expected Result:**
- All 1141 tests should pass
- Target coverage: ≥90%
- Current coverage: 87.88% (needs improvement)

### Step 4: Additional Checks (G7-G10)

```bash
# G7: Check for float in financial paths
grep -r "float" src/iatb/risk/ src/iatb/backtesting/ src/iatb/execution/ src/iatb/selection/ src/iatb/sentiment/
# Expected: 0 results (pass)

# G8: Check for naive datetime
grep -r "datetime.now()" src/
# Expected: 0 results (pass)

# G9: Check for print statements
grep -r "print(" src/
# Expected: 0 results (pass)

# G10: Function size check (≤50 LOC per function)
# Manual review or use automated tool
```

### Step 5: Run Complete Verification Script

```bash
# Run the comprehensive verification and sync script
python verify_and_sync.py
```

This script will:
1. Run all quality gates (G1-G10)
2. Display detailed results for each gate
3. Check git status
4. Stage all changes
5. Commit with message: `fix(scanner): add custom_data parameter for testing`
6. Push to remote repository

### Step 6: Manual Git Sync (Alternative)

If you prefer manual control:

```bash
# Check current git status
git status --short

# Stage all changes
git add .

# View staged changes
git status

# Get current branch
git branch --show-current

# Get latest commit hash
git rev-parse HEAD

# Commit changes
git commit -m "fix(scanner): add custom_data parameter for testing"

# Push to remote
git push origin optimize/dashboard-approval-matrix
```

---

## 📊 Current Status

### Quality Gates Status

| Gate | Status | Notes |
|------|--------|-------|
| G1: Ruff Check | ✅ PASS | src/ and tests/ only |
| G2: Ruff Format | ✅ PASS | src/ and tests/ only |
| G3: MyPy Strict | ❌ FAIL | 3 import errors (tomli, numpy, unreachable) |
| G4: Bandit Security | ✅ PASS | 0 high/medium |
| G5: Gitleaks | ✅ PASS | 0 leaks |
| G6: Test Coverage | ❌ FAIL | 87.88% (need 90%) |
| G7: Float Check | ✅ PASS | No float in financial paths |
| G8: Naive Datetime | ✅ PASS | No datetime.now() |
| G9: Print Statements | ✅ PASS | No print() in src/ |
| G10: Function Size | ✅ PASS | All functions ≤50 LOC |

### Issues to Fix

1. **Coverage Gap (87.88% → 90%):** Need ~2.12% more coverage
   - Focus on: `src/iatb/scanner/instrument_scanner.py` (54.19%)
   - Focus on: `src/iatb/selection/weight_optimizer.py` (30.47%)
   - Focus on: `src/iatb/selection/drl_signal.py` (60.40%)
   - Focus on: `src/iatb/risk/sebi_compliance.py` (60.98%)

2. **MyPy Import Errors:**
   - `src/iatb/core/exchange_calendar.py:89` - Cannot find module "tomli"
   - `src/iatb/rl/agent.py:107` - Cannot find module "numpy"
   - `src/iatb/scanner/instrument_scanner.py:319` - Right operand of "or" is never evaluated

---

## 🔧 How to Fix Remaining Issues

### Fixing Coverage Gap

Add tests for uncovered lines:

```python
# Example: Add test for instrument_scanner.py
# tests/unit/test_scanner/test_instrument_scanner_coverage.py

def test_scan_with_empty_custom_data():
    """Test scan with empty custom_data list."""
    scanner = InstrumentScanner()
    result = scanner.scan(custom_data=[])
    assert result.total_scanned == 0
    assert result.gainers == []
    assert result.losers == []
```

### Fixing MyPy Errors

1. **Add type stubs for missing modules:**
```bash
# Install type stubs
poetry add --group dev types-tomli types-numpy
```

2. **Fix unreachable code warning:**
```python
# In src/iatb/scanner/instrument_scanner.py line 319
# Remove the unreachable part of the "or" expression
```

---

## 📋 Verification Checklist

Before syncing to git, ensure:

- [ ] All 1141 tests pass
- [ ] Coverage ≥ 90%
- [ ] G1-G10 all pass
- [ ] No float in financial paths
- [ ] No naive datetime.now()
- [ ] No print() in src/
- [ ] All functions ≤50 LOC
- [ ] Git status is clean
- [ ] Commit message follows conventional commits
- [ ] Push to remote succeeds

---

## 🎯 Git Sync Workflow

### Automated (Recommended)

```bash
python verify_and_sync.py
```

### Manual Step-by-Step

```bash
# 1. Verify all gates pass
poetry run pytest --cov=src/iatb
poetry run ruff check src/ tests/
poetry run mypy src/ --strict

# 2. Check git status
git status --short

# 3. Stage changes
git add .

# 4. Commit
git commit -m "fix(scanner): add custom_data parameter for testing"

# 5. Push
git push origin optimize/dashboard-approval-matrix

# 6. Verify push
git log --oneline -1
git status
```

---

## 📝 Notes

- **Script Files:** Files in `scripts/` directory are excluded from G1/G2 linting
- **Test Files:** Test coverage is calculated only for `src/iatb/` directory
- **Remote Repository:** `git@github.com:npmvlKP/IATB-02Apr26.git`
- **Current Branch:** `optimize/dashboard-approval-matrix`
- **Latest Commit:** `57246d2e906f2b73ada1eaec27ec41ffb68a44b2`

---

## 🔗 Related Files

- `verify_and_sync.py` - Complete verification and git sync script
- `fix_custom_data_param.py` - Script that fixed the custom_data parameter
- `src/iatb/scanner/instrument_scanner.py` - Main file with the fix
- `tests/unit/test_scanner/test_instrument_scanner.py` - Test file

---

## 📞 Support

If you encounter issues:

1. Check the error message carefully
2. Run `poetry install` to ensure all dependencies are installed
3. Check Python version: `python --version` (should be 3.12+)
4. Check Poetry version: `poetry --version` (should be 1.8+)
5. Review the test output for specific failures

---

**Last Updated:** 2026-04-07
**Status:** In Progress - Coverage at 87.88% (target: 90%)