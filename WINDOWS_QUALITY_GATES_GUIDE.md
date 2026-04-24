# Windows Quality Gates Guide (G1-G10)

## Overview

This guide provides Windows PowerShell users with a complete solution for running all IATB quality gates (G1-G10) without needing Unix/Linux tools like `grep`.

## Problem Statement

Windows PowerShell does not natively support Unix commands like `grep`. The AGENTS.md quality gates require checking for:

- **G7**: No `float` in financial paths
- **G8**: No `datetime.now()` (naive datetime)
- **G9**: No `print()` statements in `src/`
- **G10**: Function size ≤ 50 LOC

## Solution

We provide two Windows-compatible solutions:

### 1. Python Validation Script

**File**: `validate_windows_g7_g8_g9_g10.py`

A standalone Python script that checks G7-G10 without requiring Unix tools.

**Features**:
- ✅ Windows-compatible (no `grep` required)
- ✅ Comprehensive validation for G7, G8, G9, G10
- ✅ Detailed violation reporting
- ✅ ASCII-compatible output (no Unicode errors)
- ✅ Exit codes for CI/CD integration

**Usage**:
```powershell
# Run the validation
python validate_windows_g7_g8_g9_g10.py

# Check exit code
echo $LASTEXITCODE
# 0 = All passed, 1 = Failures found
```

**What it checks**:

| Gate | Description | Scope |
|------|-------------|-------|
| **G7** | No `float` in financial paths | `src/iatb/risk/`, `src/iatb/backtesting/`, `src/iatb/execution/`, `src/iatb/selection/`, `src/iatb/sentiment/` |
| **G8** | No `datetime.now()` | All of `src/` |
| **G9** | No `print()` statements | All of `src/` |
| **G10** | Function size ≤ 50 LOC | All of `src/` |

**Allowed exceptions**:
- G7: API boundary conversions with comments are allowed
- G8/G9: Commented-out lines are ignored

### 2. Complete PowerShell Runbook

**File**: `WINDOWS_QUALITY_GATES_RUNBOOK.ps1`

A comprehensive PowerShell script that runs ALL quality gates (G1-G10) in sequence.

**Features**:
- ✅ Runs G1-G6 using Poetry tools
- ✅ Runs G7-G10 using Windows-compatible Python script
- ✅ Environment verification (Python, Poetry)
- ✅ Automatic dependency installation
- ✅ Colored console output
- ✅ Detailed report generation
- ✅ Exit codes for CI/CD integration

**Usage**:
```powershell
# Run complete quality gates (G1-G10)
.\WINDOWS_QUALITY_GATES_RUNBOOK.ps1

# Check exit code
echo $LASTEXITCODE
# 0 = All gates passed, 1 = Some gates failed
```

**Output**:
- Console output with colored status indicators
- Timestamped report file: `QUALITY_GATES_REPORT_YYYYMMDD_HHMMSS.txt`

## Quick Start

### Option 1: Run Only G7-G10 (Quick Check)

```powershell
# Navigate to project root
cd G:\IATB-02Apr26\IATB

# Run Windows-compatible validation
python validate_windows_g7_g8_g9_g10.py
```

### Option 2: Run Complete Quality Gates (G1-G10)

```powershell
# Navigate to project root
cd G:\IATB-02Apr26\IATB

# Run complete quality gates
.\WINDOWS_QUALITY_GATES_RUNBOOK.ps1
```

## Understanding the Output

### G7: Float Check

**PASS**: No float usage in financial paths
```
G7: PASS - No float in financial paths
```

**FAIL**: Float usage detected
```
G7: FAIL - Found 1 violations
  src/iatb/execution/live_executor.py:44 - DEFAULT_CONFIRMATION_POLL_INTERVAL_SECONDS: float = 0.5
```

### G8: Naive Datetime Check

**PASS**: No naive datetime usage
```
G8: PASS - No naive datetime.now() found
```

**FAIL**: Naive datetime detected
```
G8: FAIL - Found 2 naive datetime.now() usages
  src/iatb/core/timer.py:15 - current_time = datetime.now()
```

### G9: Print Statement Check

**PASS**: No print statements
```
G9: PASS - No print() statements found
```

**FAIL**: Print statements detected
```
G9: FAIL - Found 3 print() usages
  src/iatb/debug/logger.py:20 - print(f"Debug: {message}")
```

### G10: Function Size Check

**PASS**: All functions within size limit
```
G10: PASS - All functions <= 50 LOC
```

**FAIL**: Functions exceed size limit
```
G10: FAIL - Found 2 functions exceeding 50 LOC
  src/iatb/selection/fundamental_filter.py - Function 'evaluate' at line 92: 113 LOC
  src/iatb/selection/technical_filter.py - Function 'evaluate' at line 101: 109 LOC
```

## Troubleshooting

### Issue: "python is not recognized"

**Solution**: Ensure Python is installed and added to PATH:
```powershell
# Check Python installation
python --version

# If not found, install Python from https://python.org
# During installation, check "Add Python to PATH"
```

### Issue: "poetry is not recognized"

**Solution**: Install Poetry:
```powershell
# Install Poetry
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Restart PowerShell and verify
poetry --version
```

### Issue: UnicodeEncodeError with special characters

**Solution**: The script uses ASCII-compatible characters. If you still see errors:
```powershell
# Set PowerShell encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

### Issue: Script execution blocked

**Solution**: Allow script execution in PowerShell:
```powershell
# Check execution policy
Get-ExecutionPolicy

# If Restricted, change to RemoteSigned
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Quality Gates (Windows)

on: [push, pull_request]

jobs:
  quality-gates:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install Poetry
        run: pip install poetry
      
      - name: Install dependencies
        run: poetry install
      
      - name: Run G7-G10 validation
        run: python validate_windows_g7_g8_g9_g10.py
      
      - name: Run complete quality gates
        run: .\WINDOWS_QUALITY_GATES_RUNBOOK.ps1
```

### Azure DevOps Example

```yaml
- script: python validate_windows_g7_g8_g9_g10.py
  displayName: 'Run G7-G10 Quality Gates'
  failOnStderr: true

- powershell: |
    .\WINDOWS_QUALITY_GATES_RUNBOOK.ps1
    if ($LASTEXITCODE -ne 0) {
      Write-Error "Quality gates failed"
      exit 1
    }
  displayName: 'Run Complete Quality Gates (G1-G10)'
```

## Comparison: Unix vs Windows

| Task | Unix/Linux Command | Windows Solution |
|------|-------------------|------------------|
| Check float | `grep -r "float" src/iatb/risk/` | `python validate_windows_g7_g8_g9_g10.py` |
| Check datetime | `grep -r "datetime.now()" src/` | `python validate_windows_g7_g8_g9_g10.py` |
| Check print | `grep -r "print(" src/` | `python validate_windows_g7_g8_g9_g10.py` |
| Complete gates | Shell script | `WINDOWS_QUALITY_GATES_RUNBOOK.ps1` |

## Best Practices

1. **Run Before Commits**: Always run quality gates before committing code
2. **Fix Violations Early**: Address violations immediately to prevent accumulation
3. **Automate in CI**: Integrate into your CI/CD pipeline
4. **Review Reports**: Save and review generated reports for trend analysis
5. **Update Documentation**: Keep this guide updated with any changes

## References

- **AGENTS.md**: Full quality gate specifications
- **Quality Gates (G1-G6)**: Run via Poetry tools (ruff, mypy, bandit, gitleaks, pytest)
- **Quality Gates (G7-G10)**: Validated by Windows-compatible Python script

## Support

For issues or questions:
1. Check this guide first
2. Review the AGENTS.md quality gate specifications
3. Check existing validation scripts for patterns
4. Consult the project documentation

---

**Last Updated**: 2026-04-24
**Windows Compatibility**: Windows 10/11 + PowerShell 5.1/7+
**Python Version**: 3.8+