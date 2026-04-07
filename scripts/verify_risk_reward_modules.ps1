# IATB Risk & Reward Modules Verification Script
# Comprehensive verification for stop_loss.py and reward.py
# Win11 PowerShell compatible

param(
    [switch]$Full = $false,
    [switch]$Quick = $false
)

$ErrorActionPreference = "Stop"
$startTime = Get-Date

Write-Host "`n=== IATB Risk & Reward Modules Verification ===" -ForegroundColor Cyan
Write-Host "Target Files:" -ForegroundColor Yellow
Write-Host "  - src/iatb/risk/stop_loss.py" -ForegroundColor White
Write-Host "  - src/iatb/rl/reward.py" -ForegroundColor White
Write-Host ""

# Function to write section headers
function Write-Section {
    param([string]$Title)
    Write-Host "`n--- $Title ---" -ForegroundColor Cyan
}

# Function to write test result
function Write-TestResult {
    param([string]$Name, [bool]$Passed, [string]$Details = "")
    $color = if ($Passed) { "Green" } else { "Red" }
    $status = if ($Passed) { "✓ PASS" } else { "✗ FAIL" }
    Write-Host "  [$status] $Name" -ForegroundColor $color
    if ($Details) { Write-Host "        $Details" -ForegroundColor Gray }
}

# Track overall status
$allPassed = $true

# Step 1: Verify file existence
Write-Section "Step 1: File Existence Check"
$filesExist = $true
if (Test-Path "src/iatb/risk/stop_loss.py") {
    Write-TestResult "stop_loss.py exists" $true
} else {
    Write-TestResult "stop_loss.py exists" $false
    $filesExist = $false
    $allPassed = $false
}

if (Test-Path "src/iatb/rl/reward.py") {
    Write-TestResult "reward.py exists" $true
} else {
    Write-TestResult "reward.py exists" $false
    $filesExist = $false
    $allPassed = $false
}

if (-not $filesExist) {
    Write-Host "`n✗ Cannot proceed - required files missing" -ForegroundColor Red
    exit 1
}

# Step 2: Syntax validation
Write-Section "Step 2: Python Syntax Validation"
$syntaxPassed = $true

try {
    $out = poetry run python -m py_compile src/iatb/risk/stop_loss.py 2>&1
    Write-TestResult "stop_loss.py syntax" ($LASTEXITCODE -eq 0)
    if ($LASTEXITCODE -ne 0) { $syntaxPassed = $false; $allPassed = $false }
} catch {
    Write-TestResult "stop_loss.py syntax" $false $_.Exception.Message
    $syntaxPassed = $false
    $allPassed = $false
}

try {
    $out = poetry run python -m py_compile src/iatb/rl/reward.py 2>&1
    Write-TestResult "reward.py syntax" ($LASTEXITCODE -eq 0)
    if ($LASTEXITCODE -ne 0) { $syntaxPassed = $false; $allPassed = $false }
} catch {
    Write-TestResult "reward.py syntax" $false $_.Exception.Message
    $syntaxPassed = $false
    $allPassed = $false
}

# Step 3: Type checking (MyPy strict)
Write-Section "Step 3: Type Checking (MyPy Strict)"
try {
    $out = poetry run mypy src/iatb/risk/stop_loss.py src/iatb/rl/reward.py --strict 2>&1
    Write-TestResult "MyPy strict type check" ($LASTEXITCODE -eq 0)
    if ($LASTEXITCODE -ne 0) {
        Write-Host "        Output: $out" -ForegroundColor Yellow
        $allPassed = $false
    }
} catch {
    Write-TestResult "MyPy strict type check" $false $_.Exception.Message
    $allPassed = $false
}

# Step 4: Linting (Ruff)
Write-Section "Step 4: Code Linting (Ruff)"
try {
    $out = poetry run ruff check src/iatb/risk/stop_loss.py src/iatb/rl/reward.py 2>&1
    Write-TestResult "Ruff lint check" ($LASTEXITCODE -eq 0)
    if ($LASTEXITCODE -ne 0) {
        Write-Host "        Output: $out" -ForegroundColor Yellow
        $allPassed = $false
    }
} catch {
    Write-TestResult "Ruff lint check" $false $_.Exception.Message
    $allPassed = $false
}

# Step 5: Formatting check (Ruff format)
Write-Section "Step 5: Code Formatting (Ruff Format)"
try {
    $out = poetry run ruff format --check src/iatb/risk/stop_loss.py src/iatb/rl/reward.py 2>&1
    Write-TestResult "Ruff format check" ($LASTEXITCODE -eq 0)
    if ($LASTEXITCODE -ne 0) {
        Write-Host "        Output: $out" -ForegroundColor Yellow
        $allPassed = $false
    }
} catch {
    Write-TestResult "Ruff format check" $false $_.Exception.Message
    $allPassed = $false
}

# Step 6: Security check (Bandit)
Write-Section "Step 6: Security Check (Bandit)"
try {
    $out = poetry run bandit -r src/iatb/risk/stop_loss.py src/iatb/rl/reward.py -q 2>&1
    Write-TestResult "Bandit security check" ($LASTEXITCODE -eq 0)
    if ($LASTEXITCODE -ne 0) {
        Write-Host "        Output: $out" -ForegroundColor Yellow
        $allPassed = $false
    }
} catch {
    Write-TestResult "Bandit security check" $false $_.Exception.Message
    $allPassed = $false
}

# Step 7: Import validation
Write-Section "Step 7: Import Validation"
$importsPassed = $true

try {
    $out = poetry run python -c "from iatb.risk.stop_loss import *; print('stop_loss imports OK')" 2>&1
    Write-TestResult "stop_loss.py imports" ($LASTEXITCODE -eq 0)
    if ($LASTEXITCODE -ne 0) { $importsPassed = $false; $allPassed = $false }
} catch {
    Write-TestResult "stop_loss.py imports" $false $_.Exception.Message
    $importsPassed = $false
    $allPassed = $false
}

try {
    $out = poetry run python -c "from iatb.rl.reward import *; print('reward imports OK')" 2>&1
    Write-TestResult "reward.py imports" ($LASTEXITCODE -eq 0)
    if ($LASTEXITCODE -ne 0) { $importsPassed = $false; $allPassed = $false }
} catch {
    Write-TestResult "reward.py imports" $false $_.Exception.Message
    $importsPassed = $false
    $allPassed = $false
}

# Step 8: Test execution (if Quick is not set)
if (-not $Quick) {
    Write-Section "Step 8: Unit Test Execution"
    
    try {
        $out = poetry run pytest tests/risk/test_stop_loss.py -v --tb=short 2>&1
        Write-TestResult "stop_loss.py tests" ($LASTEXITCODE -eq 0)
        if ($LASTEXITCODE -ne 0) {
            Write-Host "        See test output above for details" -ForegroundColor Yellow
            $allPassed = $false
        }
    } catch {
        Write-TestResult "stop_loss.py tests" $false $_.Exception.Message
        $allPassed = $false
    }
    
    try {
        $out = poetry run pytest tests/rl/test_reward.py -v --tb=short 2>&1
        Write-TestResult "reward.py tests" ($LASTEXITCODE -eq 0)
        if ($LASTEXITCODE -ne 0) {
            Write-Host "        See test output above for details" -ForegroundColor Yellow
            $allPassed = $false
        }
    } catch {
        Write-TestResult "reward.py tests" $false $_.Exception.Message
        $allPassed = $false
    }
} else {
    Write-Host "  [SKIP] Unit tests (Quick mode)" -ForegroundColor Yellow
}

# Step 9: Decimal-only compliance (no float)
Write-Section "Step 9: Decimal-Only Compliance"
$floatCheckPassed = $true

$stopLossFloats = (Select-String -Path "src/iatb/risk/stop_loss.py" -Pattern "\bfloat\b" | Measure-Object).Count
Write-TestResult "No float in stop_loss.py" ($stopLossFloats -eq 0) "$stopLossFloats occurrences found"
if ($stopLossFloats -gt 0) { $floatCheckPassed = $false; $allPassed = $false }

$rewardFloats = (Select-String -Path "src/iatb/rl/reward.py" -Pattern "\bfloat\b" | Measure-Object).Count
Write-TestResult "No float in reward.py" ($rewardFloats -eq 0) "$rewardFloats occurrences found"
if ($rewardFloats -gt 0) { $floatCheckPassed = $false; $allPassed = $false }

# Step 10: UTC-aware datetime compliance
Write-Section "Step 10: UTC-Aware Datetime Compliance"
$dtCheckPassed = $true

$stopLossNaive = (Select-String -Path "src/iatb/risk/stop_loss.py" -Pattern "datetime\.now\(\)" | Measure-Object).Count
Write-TestResult "No naive datetime in stop_loss.py" ($stopLossNaive -eq 0) "$stopLossNaive occurrences found"
if ($stopLossNaive -gt 0) { $dtCheckPassed = $false; $allPassed = $false }

$rewardNaive = (Select-String -Path "src/iatb/rl/reward.py" -Pattern "datetime\.now\(\)" | Measure-Object).Count
Write-TestResult "No naive datetime in reward.py" ($rewardNaive -eq 0) "$rewardNaive occurrences found"
if ($rewardNaive -gt 0) { $dtCheckPassed = $false; $allPassed = $false }

# Step 11: No print() statements
Write-Section "Step 11: No print() Statements"
$printCheckPassed = $true

$stopLossPrints = (Select-String -Path "src/iatb/risk/stop_loss.py" -Pattern "\bprint\(" | Measure-Object).Count
Write-TestResult "No print() in stop_loss.py" ($stopLossPrints -eq 0) "$stopLossPrints occurrences found"
if ($stopLossPrints -gt 0) { $printCheckPassed = $false; $allPassed = $false }

$rewardPrints = (Select-String -Path "src/iatb/rl/reward.py" -Pattern "\bprint\(" | Measure-Object).Count
Write-TestResult "No print() in reward.py" ($rewardPrints -eq 0) "$rewardPrints occurrences found"
if ($rewardPrints -gt 0) { $printCheckPassed = $false; $allPassed = $false }

# Step 12: Test coverage (if Full is set)
if ($Full) {
    Write-Section "Step 12: Test Coverage Analysis"
    
    try {
        $out = poetry run pytest tests/risk/test_stop_loss.py tests/rl/test_reward.py --cov=src/iatb/risk/stop_loss --cov=src/iatb/rl/reward --cov-report=term-missing 2>&1
        Write-Host "$out" -ForegroundColor Gray
        # Note: Coverage will likely be < 90% due to missing tests
    } catch {
        Write-TestResult "Coverage analysis" $false $_.Exception.Message
    }
}

# Final summary
$duration = ((Get-Date) - $startTime).TotalSeconds
Write-Host "`n=== Verification Summary ===" -ForegroundColor Cyan
Write-Host "Duration: $([math]::Round($duration, 2)) seconds" -ForegroundColor Gray
Write-Host ""

if ($allPassed) {
    Write-Host "✓ ALL CHECKS PASSED" -ForegroundColor Green
    Write-Host "Modules are ready for deployment." -ForegroundColor Green
    exit 0
} else {
    Write-Host "✗ SOME CHECKS FAILED" -ForegroundColor Red
    Write-Host "Please fix the issues above before deployment." -ForegroundColor Red
    exit 1
}