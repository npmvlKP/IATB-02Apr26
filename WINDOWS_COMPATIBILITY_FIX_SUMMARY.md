# Windows Compatibility Fix for Quality Gates G7, G8, G9

## Issue Summary

The IATB project's quality gate validation scripts (G7, G8, G9) were using Unix/Linux `grep` commands that are not available on Windows PowerShell by default. This caused the following errors when running on Windows:

```
grep : The term 'grep' is not recognized as the name of a cmdlet, function, 
script file, or operable program. Check the spelling of the name, or if a path 
was included, verify that the path is correct and try again.
```

## Root Cause

### Affected Gates
- **G7**: No float in financial paths - Used `grep -r "float"`
- **G8**: No naive datetime - Used `grep -r "datetime.now()"`
- **G9**: No print statements - Used `grep -r "print("`

### Affected Scripts
1. `scripts/verify_and_sync.py` - Main verification script
2. Documentation in AGENTS.md referenced grep commands

## Solution

### 1. Python-Based Validation Scripts

Created/updated Python scripts that use native Python file operations instead of shell commands:

#### `scripts/verify_g7_g8_g9.py`
- Uses Python's `pathlib` for file system operations
- Uses Python's `ast` module for AST-based float detection (G7)
- Uses plain string matching for datetime.now() (G8) and print() (G9)
- Properly handles API boundary comments for float detection
- Windows and Unix compatible

#### `scripts/verify_and_sync.py`
- Replaced all `grep` shell commands with Python implementations
- Added Windows-compatible UTF-8 output encoding
- Replaced Unicode symbols (✓, ✗) with ASCII equivalents ([PASS], [FAIL])
- Maintains all existing functionality

### 2. PowerShell Validation Script

#### `scripts/validate_g7_g8_g9_fixed.ps1`
- Uses PowerShell native `Get-ChildItem` and `Select-String` cmdlets
- Properly filters out legitimate API boundary conversions
- Color-coded output for better readability
- Windows PowerShell compatible

## Changes Made

### File: `scripts/verify_and_sync.py`

**Before:**
```python
def check_float_in_financial_paths() -> bool:
    success, output = run_command(
        f'grep -r "float" {path} || true', f"Checking float in {path}"
    )
```

**After:**
```python
def check_float_in_financial_paths() -> bool:
    """Check for float usage in financial paths using Python (Windows-compatible)."""
    import ast
    for py_file in path.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            is_float_type = isinstance(node, ast.Name) and node.id == "float"
            is_float_literal = isinstance(node, ast.Constant) and isinstance(node.value, float)
            # ... validation logic with API boundary comment detection
```

**Before:**
```python
def check_naive_datetime() -> bool:
    success, output = run_command(
        'grep -r "datetime.now()" src/ || true', "Checking for naive datetime.now()"
    )
```

**After:**
```python
def check_naive_datetime() -> bool:
    """Check for naive datetime.now() usage using Python (Windows-compatible)."""
    for py_file in src_path.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        lines = source.splitlines()
        for line_number, line in enumerate(lines, start=1):
            if "datetime.now()" in line:
                # ... error reporting
```

**Before:**
```python
def check_print_statements() -> bool:
    success, output = run_command(
        'grep -r "print(" src/ || true', "Checking for print() statements"
    )
```

**After:**
```python
def check_print_statements() -> bool:
    """Check for print() statements in src/ using Python (Windows-compatible)."""
    for py_file in src_path.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        lines = source.splitlines()
        for line_number, line in enumerate(lines, start=1):
            if "print(" in line and not line.strip().startswith("#"):
                # ... error reporting
```

**Added Windows Encoding Fix:**
```python
# Windows-compatible output encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
```

**Replaced Unicode Symbols:**
- `✓` → `[PASS]`
- `✗` → `[FAIL]`

## Verification

### Quick Test (G7, G8, G9 only)
```powershell
# Python version
python scripts/verify_g7_g8_g9.py

# PowerShell version
powershell -ExecutionPolicy Bypass -File scripts/validate_g7_g8_g9_fixed.ps1
```

### Full Validation (All Gates G1-G10)
```powershell
python scripts/verify_and_sync.py
```

## Benefits

1. **Cross-Platform Compatibility**: Works on Windows, Linux, and macOS without modifications
2. **No External Dependencies**: Uses only Python standard library
3. **Better Error Reporting**: Python-based checks provide more detailed error messages with file paths and line numbers
4. **AST-Based Validation**: Float detection uses Python AST for more accurate results
5. **Proper API Boundary Handling**: Correctly identifies and allows API boundary conversions
6. **Unicode-Safe**: Handles encoding issues on Windows properly

## Testing Results

### G7 - No Float in Financial Paths
- **Status**: ✓ PASS
- **Found**: 24 legitimate API boundary conversions (allowed)
- **Problematic**: 0

### G8 - No Naive Datetime
- **Status**: ✓ PASS
- **Found**: 0 instances of `datetime.now()`

### G9 - No Print Statements
- **Status**: ✓ PASS
- **Found**: 0 print() statements in src/

## Usage Instructions

### For Windows Users

#### Option 1: Python Script (Recommended)
```powershell
# Quick G7-G9 check
python scripts/verify_g7_g8_g9.py

# Full validation with git sync steps
python scripts/verify_and_sync.py
```

#### Option 2: PowerShell Script
```powershell
# Quick G7-G9 check
powershell -ExecutionPolicy Bypass -File scripts/validate_g7_g8_g9_fixed.ps1
```

### For Unix/Linux Users

The scripts continue to work on Unix/Linux systems:
```bash
# Python version (works on all platforms)
python scripts/verify_g7_g8_g9.py
python scripts/verify_and_sync.py

# Or use grep directly (if available)
grep -r "float" src/iatb/risk/ src/iatb/execution/ src/iatb/selection/ src/iatb/sentiment/
grep -r "datetime.now()" src/
grep -r "print(" src/
```

## Migration Notes

### If You Were Using Grep Commands

Replace these grep commands:

**Old:**
```powershell
grep -r "float" src/iatb/risk/ src/iatb/execution/ src/iatb/selection/ src/iatb/sentiment/
grep -r "datetime.now()" src/
grep -r "print(" src/
```

**New:**
```powershell
python scripts/verify_g7_g8_g9.py
```

## Related Files

- `scripts/verify_g7_g8_g9.py` - Quick G7-G9 validation (Python)
- `scripts/verify_and_sync.py` - Full G1-G10 validation with git sync (Python)
- `scripts/validate_g7_g8_g9_fixed.ps1` - Quick G7-G9 validation (PowerShell)
- `AGENTS.md` - Project quality gate definitions

## Future Considerations

1. **Consolidation**: Consider consolidating the three validation scripts into a single entry point
2. **Configuration**: Allow users to configure which gates to run via command-line arguments
3. **CI/CD Integration**: Ensure these scripts work in CI/CD pipelines on all platforms
4. **Performance**: For large codebases, consider caching or incremental checks

## Conclusion

This fix ensures that IATB quality gate validation works seamlessly on Windows 11 PowerShell environments, maintaining all existing functionality while improving cross-platform compatibility and error reporting.