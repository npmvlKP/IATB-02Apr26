# IATB Quality Gate Script
# This script runs all quality checks to ensure code meets standards

Write-Host "=== IATB Quality Gate ===" -ForegroundColor Cyan
Write-Host ""

# Track overall status
$allPassed = $true

# Function to run a check and report results
function Run-Check {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    
    Write-Host "Running: $Name" -ForegroundColor Yellow
    try {
        & $Command
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ PASSED: $Name" -ForegroundColor Green
            Write-Host ""
            return $true
        } else {
            Write-Host "✗ FAILED: $Name" -ForegroundColor Red
            Write-Host ""
            return $false
        }
    } catch {
        Write-Host "✗ ERROR: $Name" -ForegroundColor Red
        Write-Host "Error: $_" -ForegroundColor Red
        Write-Host ""
        return $false
    }
}

# Check 1: Ruff Lint
$allPassed = $allPassed -and (Run-Check "Ruff Lint Check" { poetry run ruff check src/ tests/ })

# Check 2: Ruff Format
$allPassed = $allPassed -and (Run-Check "Ruff Format Check" { poetry run ruff format --check src/ tests/ })

# Check 3: MyPy Strict Type Checking
$allPassed = $allPassed -and (Run-Check "MyPy Strict Type Check" { poetry run mypy src/ --strict })

# Check 4: Bandit Security Check
$allPassed = $allPassed -and (Run-Check "Bandit Security Check" { poetry run bandit -r src/ -q })

# Check 5: Pytest with Coverage
$allPassed = $allPassed -and (Run-Check "Pytest with 90% Coverage" { poetry run pytest --cov-fail-under=90 })

# Check 6: Gitleaks (if available)
Write-Host "Running: Gitleaks Secret Detection" -ForegroundColor Yellow
if (Get-Command gitleaks -ErrorAction SilentlyContinue) {
    $gitleaksResult = & gitleaks detect --source . --no-git --verbose 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ PASSED: Gitleaks Secret Detection" -ForegroundColor Green
    } else {
        Write-Host "✗ FAILED: Gitleaks Secret Detection" -ForegroundColor Red
        Write-Host $gitleaksResult
        $allPassed = $false
    }
} else {
    Write-Host "⊘ SKIPPED: Gitleaks not installed" -ForegroundColor Yellow
}
Write-Host ""

# Summary
Write-Host "=== Quality Gate Summary ===" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "✓ ALL CHECKS PASSED" -ForegroundColor Green
    Write-Host "Your code meets all quality standards." -ForegroundColor Green
    exit 0
} else {
    Write-Host "✗ SOME CHECKS FAILED" -ForegroundColor Red
    Write-Host "Please fix the issues above before committing." -ForegroundColor Red
    exit 1
}