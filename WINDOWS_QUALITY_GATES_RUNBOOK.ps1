# =============================================================================
# IATB Windows Quality Gates Runbook (G1-G10)
# =============================================================================
# This PowerShell script runs all quality gates for the IATB project on Windows.
# Replaces Unix grep commands with Windows-compatible Python validation scripts.
#
# Usage:
#   .\WINDOWS_QUALITY_GATES_RUNBOOK.ps1
#
# Exit Codes:
#   0 - All gates passed
#   1 - One or more gates failed
# =============================================================================

$ErrorActionPreference = "Stop"
$scriptPath = $PSScriptRoot
$projectRoot = if ($scriptPath) { $scriptPath } else { Get-Location }

Write-Host "`n======================================================================" -ForegroundColor Cyan
Write-Host "IATB QUALITY GATES (G1-G10) - Windows PowerShell Runbook" -ForegroundColor Cyan
Write-Host "======================================================================`n" -ForegroundColor Cyan

$allPassed = $true
$failures = @()

# =============================================================================
# Step 1: Verify Python and Poetry are available
# =============================================================================
Write-Host "[Step 1/7] Verifying environment..." -ForegroundColor Yellow

try {
    $pythonVersion = python --version 2>&1
    Write-Host "  [OK] Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Python not found. Please install Python 3.8+ and add to PATH." -ForegroundColor Red
    exit 1
}

try {
    $poetryVersion = poetry --version 2>&1
    Write-Host "  [OK] Poetry: $poetryVersion" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Poetry not found. Please install Poetry." -ForegroundColor Red
    exit 1
}

# =============================================================================
# Step 2: Install dependencies if needed
# =============================================================================
Write-Host "`n[Step 2/7] Checking dependencies..." -ForegroundColor Yellow
try {
    Write-Host "  Running: poetry install..." -ForegroundColor Gray
    $installOutput = poetry install 2>&1
    Write-Host "  [OK] Dependencies installed/verified" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Failed to install dependencies" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}

# =============================================================================
# Step 3: Run G1-G5 (Standard Quality Gates)
# =============================================================================
Write-Host "`n[Step 3/7] Running Standard Quality Gates (G1-G5)..." -ForegroundColor Yellow

# G1: Lint check
Write-Host "`n  [G1] Running: poetry run ruff check src/ tests/" -ForegroundColor Gray
try {
    $g1Output = poetry run ruff check src/ tests/ 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [G1] [PASS] - No lint violations" -ForegroundColor Green
    } else {
        Write-Host "  [G1] [FAIL] - Lint violations found:" -ForegroundColor Red
        Write-Host $g1Output
        $allPassed = $false
        $failures += "G1: Lint violations found"
    }
} catch {
    Write-Host "  [G1] [ERROR] - Failed to run ruff check" -ForegroundColor Red
    $allPassed = $false
    $failures += "G1: Failed to run ruff check"
}

# G2: Format check
Write-Host "`n  [G2] Running: poetry run ruff format --check src/ tests/" -ForegroundColor Gray
try {
    $g2Output = poetry run ruff format --check src/ tests/ 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [G2] [PASS] - Code properly formatted" -ForegroundColor Green
    } else {
        Write-Host "  [G2] [FAIL] - Code formatting issues found" -ForegroundColor Red
        Write-Host $g2Output
        $allPassed = $false
        $failures += "G2: Code formatting issues found"
    }
} catch {
    Write-Host "  [G2] [ERROR] - Failed to run ruff format check" -ForegroundColor Red
    $allPassed = $false
    $failures += "G2: Failed to run ruff format check"
}

# G3: Type check
Write-Host "`n  [G3] Running: poetry run mypy src/ --strict" -ForegroundColor Gray
try {
    $g3Output = poetry run mypy src/ --strict 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [G3] [PASS] - No type errors" -ForegroundColor Green
    } else {
        Write-Host "  [G3] [FAIL] - Type errors found:" -ForegroundColor Red
        Write-Host $g3Output
        $allPassed = $false
        $failures += "G3: Type errors found"
    }
} catch {
    Write-Host "  [G3] [ERROR] - Failed to run mypy" -ForegroundColor Red
    $allPassed = $false
    $failures += "G3: Failed to run mypy"
}

# G4: Security check
Write-Host "`n  [G4] Running: poetry run bandit -r src/ -q" -ForegroundColor Gray
try {
    $g4Output = poetry run bandit -r src/ -q 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [G4] [PASS] - No high/medium security issues" -ForegroundColor Green
    } else {
        Write-Host "  [G4] [FAIL] - Security issues found:" -ForegroundColor Red
        Write-Host $g4Output
        $allPassed = $false
        $failures += "G4: Security issues found"
    }
} catch {
    Write-Host "  [G4] [ERROR] - Failed to run bandit" -ForegroundColor Red
    $allPassed = $false
    $failures += "G4: Failed to run bandit"
}

# G5: Secrets check
Write-Host "`n  [G5] Running: gitleaks detect --source . --no-banner" -ForegroundColor Gray
try {
    $g5Output = gitleaks detect --source . --no-banner 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [G5] [PASS] - No secrets leaked" -ForegroundColor Green
    } else {
        Write-Host "  [G5] [FAIL] - Secrets found:" -ForegroundColor Red
        Write-Host $g5Output
        $allPassed = $false
        $failures += "G5: Secrets found"
    }
} catch {
    Write-Host "  [G5] [ERROR] - Failed to run gitleaks" -ForegroundColor Red
    $allPassed = $false
    $failures += "G5: Failed to run gitleaks"
}

# =============================================================================
# Step 4: Run G6 (Test Coverage)
# =============================================================================
Write-Host "`n[Step 4/7] Running Test Coverage (G6)..." -ForegroundColor Yellow
Write-Host "  [G6] Running: poetry run pytest --cov=src/iatb --cov-fail-under=90 -x" -ForegroundColor Gray
try {
    $g6Output = poetry run pytest --cov=src/iatb --cov-fail-under=90 -x 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [G6] [PASS] - All tests passed with >=90% coverage" -ForegroundColor Green
    } else {
        Write-Host "  [G6] [FAIL] - Tests failed or coverage <90%" -ForegroundColor Red
        Write-Host $g6Output
        $allPassed = $false
        $failures += "G6: Tests failed or coverage <90%"
    }
} catch {
    Write-Host "  [G6] [ERROR] - Failed to run pytest" -ForegroundColor Red
    $allPassed = $false
    $failures += "G6: Failed to run pytest"
}

# =============================================================================
# Step 5: Run G7-G10 (Windows-compatible Python validation)
# =============================================================================
Write-Host "`n[Step 5/7] Running Windows-compatible G7-G10 validation..." -ForegroundColor Yellow
Write-Host "  Running: python validate_windows_g7_g8_g9_g10.py" -ForegroundColor Gray

if (Test-Path "validate_windows_g7_g8_g9_g10.py") {
    try {
        $g7g10Output = python validate_windows_g7_g8_g9_g10.py 2>&1
        Write-Host $g7g10Output
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "`n  [G7-G10] [PASS] - All custom gates passed" -ForegroundColor Green
        } else {
            Write-Host "`n  [G7-G10] [FAIL] - Some custom gates failed" -ForegroundColor Red
            $allPassed = $false
            $failures += "G7-G10: Custom quality gates failed"
        }
    } catch {
        Write-Host "  [ERROR] - Failed to run G7-G10 validation" -ForegroundColor Red
        $allPassed = $false
        $failures += "G7-G10: Failed to run validation script"
    }
} else {
    Write-Host "  [ERROR] - validate_windows_g7_g8_g9_g10.py not found" -ForegroundColor Red
    $allPassed = $false
    $failures += "G7-G10: Validation script not found"
}

# =============================================================================
# Step 6: Generate Summary Report
# =============================================================================
Write-Host "`n[Step 6/7] Generating summary report..." -ForegroundColor Yellow

$reportPath = "QUALITY_GATES_REPORT_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
$report = @"

==============================================================================
IATB QUALITY GATES SUMMARY REPORT
==============================================================================
Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Project Root: $projectRoot

QUALITY GATES STATUS:
==============================================================================

[G1] Lint Check: $(if ($allPassed) { "PASS" } else { "CHECK LOGS" })
      Command: poetry run ruff check src/ tests/

[G2] Format Check: $(if ($allPassed) { "PASS" } else { "CHECK LOGS" })
      Command: poetry run ruff format --check src/ tests/

[G3] Type Check: $(if ($allPassed) { "PASS" } else { "CHECK LOGS" })
      Command: poetry run mypy src/ --strict

[G4] Security Check: $(if ($allPassed) { "PASS" } else { "CHECK LOGS" })
      Command: poetry run bandit -r src/ -q

[G5] Secrets Check: $(if ($allPassed) { "PASS" } else { "CHECK LOGS" })
      Command: gitleaks detect --source . --no-banner

[G6] Test Coverage: $(if ($allPassed) { "PASS" } else { "CHECK LOGS" })
      Command: poetry run pytest --cov=src/iatb --cov-fail-under=90 -x

[G7] No Float in Financial Paths: $(if ($allPassed) { "PASS" } else { "SEE G7-G10 OUTPUT" })
      Checked: risk/, backtesting/, execution/, selection/, sentiment/

[G8] No Naive Datetime: $(if ($allPassed) { "PASS" } else { "SEE G7-G10 OUTPUT" })
      Checked: src/ for datetime.now()

[G9] No Print Statements: $(if ($allPassed) { "PASS" } else { "SEE G7-G10 OUTPUT" })
      Checked: src/ for print()

[G10] Function Size <= 50 LOC: $(if ($allPassed) { "PASS" } else { "SEE G7-G10 OUTPUT" })
      Checked: src/ for function size

==============================================================================
OVERALL STATUS: $(if ($allPassed) { "ALL GATES PASSED" } else "SOME GATES FAILED" })
==============================================================================
"@

if ($failures.Count -gt 0) {
    $report += "`nFAILURES:`n"
    foreach ($failure in $failures) {
        $report += "  - $failure`n"
    }
}

$report += @"
==============================================================================
END OF REPORT
==============================================================================
"@

$report | Out-File -FilePath $reportPath -Encoding UTF8
Write-Host "  Report saved to: $reportPath" -ForegroundColor Green

# =============================================================================
# Step 7: Final Result
# =============================================================================
Write-Host "`n[Step 7/7] Final Result..." -ForegroundColor Yellow

Write-Host "`n======================================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "SUCCESS: All quality gates (G1-G10) passed!" -ForegroundColor Green
} else {
    Write-Host "FAILURE: Some quality gates failed. See above for details." -ForegroundColor Red
}
Write-Host "======================================================================`n" -ForegroundColor Cyan

exit (if ($allPassed) { 0 } else { 1 })