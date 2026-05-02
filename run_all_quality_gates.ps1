# Win11 PowerShell script to run all quality gates (G1-G10)
# Usage: .\run_all_quality_gates.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "IATB Quality Gates Validation (G1-G10)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"
$allPassed = $true

# G1: Lint
Write-Host "G1: Running ruff check..." -ForegroundColor Yellow
try {
    poetry run ruff check src/ tests/
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ G1 PASS: No linting violations" -ForegroundColor Green
    } else {
        Write-Host "✗ G1 FAIL: Linting violations found" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "✗ G1 FAIL: Error running ruff check: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# G2: Format
Write-Host "G2: Running ruff format check..." -ForegroundColor Yellow
try {
    poetry run ruff format --check src/ tests/
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ G2 PASS: No formatting issues" -ForegroundColor Green
    } else {
        Write-Host "✗ G2 FAIL: Formatting issues found" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "✗ G2 FAIL: Error running ruff format check: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# G3: Types
Write-Host "G3: Running mypy type check..." -ForegroundColor Yellow
try {
    poetry run mypy src/ --strict
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ G3 PASS: No type errors" -ForegroundColor Green
    } else {
        Write-Host "✗ G3 FAIL: Type errors found" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "✗ G3 FAIL: Error running mypy: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# G4: Security
Write-Host "G4: Running bandit security check..." -ForegroundColor Yellow
try {
    poetry run bandit -r src/ -q
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ G4 PASS: No high/medium security issues" -ForegroundColor Green
    } else {
        Write-Host "✗ G4 FAIL: Security issues found" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "✗ G4 FAIL: Error running bandit: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# G5: Secrets
Write-Host "G5: Running gitleaks secrets scan..." -ForegroundColor Yellow
try {
    gitleaks detect --source . --no-banner
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ G5 PASS: No secrets leaked" -ForegroundColor Green
    } else {
        Write-Host "✗ G5 FAIL: Secrets found" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "✗ G5 FAIL: Error running gitleaks: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# G6: Tests (90% coverage)
Write-Host "G6: Running pytest with 90% coverage requirement..." -ForegroundColor Yellow
try {
    poetry run pytest --cov=src/iatb --cov-fail-under=90 -x --tb=short
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ G6 PASS: Test coverage ≥90%" -ForegroundColor Green
    } else {
        Write-Host "✗ G6 FAIL: Test coverage below 90% or tests failed" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "✗ G6 FAIL: Error running pytest: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# G7: No float in financial paths
Write-Host "G7: Checking for float in financial paths..." -ForegroundColor Yellow
try {
    $output = python check_floats_fixed.py 2>&1
    if ($output -match "PASS") {
        Write-Host "✓ G7 PASS: No float in financial paths (API boundaries excluded)" -ForegroundColor Green
    } else {
        Write-Host "✗ G7 FAIL: Float found in financial paths" -ForegroundColor Red
        Write-Host $output
        $allPassed = $false
    }
} catch {
    Write-Host "✗ G7 FAIL: Error running float check: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# G8: No naive datetime
Write-Host "G8: Checking for naive datetime.now()..." -ForegroundColor Yellow
try {
    $output = python check_datetime_print_fixed.py 2>&1
    if ($output -match "PASS: No naive datetime.now()") {
        Write-Host "✓ G8 PASS: No naive datetime.now() found" -ForegroundColor Green
    } else {
        Write-Host "✗ G8 FAIL: Naive datetime.now() found" -ForegroundColor Red
        Write-Host $output
        $allPassed = $false
    }
} catch {
    Write-Host "✗ G8 FAIL: Error running datetime check: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# G9: No print statements
Write-Host "G9: Checking for print() statements in src/..." -ForegroundColor Yellow
try {
    $output = python check_datetime_print_fixed.py 2>&1
    if ($output -match "PASS: No print\(\) statements") {
        Write-Host "✓ G9 PASS: No print() statements in src/" -ForegroundColor Green
    } else {
        Write-Host "✗ G9 FAIL: print() statements found" -ForegroundColor Red
        Write-Host $output
        $allPassed = $false
    }
} catch {
    Write-Host "✗ G9 FAIL: Error running print check: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# G10: Function size ≤50 LOC
Write-Host "G10: Checking function size (≤50 LOC)..." -ForegroundColor Yellow
try {
    $output = python check_g10_function_size.py 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ G10 PASS: All functions ≤50 LOC" -ForegroundColor Green
    } else {
        Write-Host "✗ G10 FAIL: Functions exceed 50 LOC" -ForegroundColor Red
        Write-Host $output
        $allPassed = $false
    }
} catch {
    Write-Host "✗ G10 FAIL: Error running function size check: $_" -ForegroundColor Red
    $allPassed = $false
}
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "✓ ALL QUALITY GATES PASSED (G1-G10)" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "✗ SOME QUALITY GATES FAILED" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Cyan
    exit 1
}