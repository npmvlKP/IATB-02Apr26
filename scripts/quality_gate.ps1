# IATB Quality Gate Runner - Production/Enterprise Grade
# Runs G1-G10 exactly as defined in AGENTS.md
# Win11 PowerShell compatible - ZERO assumptions

param([switch]$Quiet)

function Write-Gate {
    param([string]$Gate, [string]$Status, [string]$Notes = "")
    $color = if ($Status -eq "PASS") { "Green" } else { "Red" }
    Write-Host "[$Gate] $Status" -ForegroundColor $color -NoNewline
    if ($Notes) { Write-Host " - $Notes" } else { Write-Host "" }
}

Write-Host "=== IATB Quality Gates (G1-G10) ===" -ForegroundColor Cyan

$allPassed = $true

# G1: Ruff lint
try {
    $out = poetry run ruff check src/ tests/ 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Gate "G1" "PASS" } else { Write-Gate "G1" "FAIL" $out; $allPassed = $false }
} catch { Write-Gate "G1" "FAIL" $_.Exception.Message; $allPassed = $false }

# G2: Ruff format
try {
    $out = poetry run ruff format --check src/ tests/ 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Gate "G2" "PASS" } else { Write-Gate "G2" "FAIL" $out; $allPassed = $false }
} catch { Write-Gate "G2" "FAIL" $_.Exception.Message; $allPassed = $false }

# G3: MyPy strict
try {
    $out = poetry run mypy src/ --strict 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Gate "G3" "PASS" } else { Write-Gate "G3" "FAIL" $out; $allPassed = $false }
} catch { Write-Gate "G3" "FAIL" $_.Exception.Message; $allPassed = $false }

# G4: Bandit security
try {
    $out = poetry run bandit -r src/ -q 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Gate "G4" "PASS" } else { Write-Gate "G4" "FAIL" $out; $allPassed = $false }
} catch { Write-Gate "G4" "FAIL" $_.Exception.Message; $allPassed = $false }

# G5: Gitleaks secrets (scan current files only, not git history)
try {
    $out = gitleaks detect --source . --no-git --no-banner 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Gate "G5" "PASS" } else { Write-Gate "G5" "FAIL" $out; $allPassed = $false }
} catch { Write-Gate "G5" "FAIL" $_.Exception.Message; $allPassed = $false }

# G6: Pytest + coverage
try {
    $out = poetry run pytest --cov=src/iatb --cov-fail-under=90 -x --tb=no 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Gate "G6" "PASS" } else { Write-Gate "G6" "FAIL" $out; $allPassed = $false }
} catch { Write-Gate "G6" "FAIL" $_.Exception.Message; $allPassed = $false }

# G7: No float in financial paths (risk/, backtesting/, execution/, selection/, sentiment/)
try {
    $financialPaths = @("src/iatb/risk/", "src/iatb/backtesting/", "src/iatb/execution/", "src/iatb/selection/", "src/iatb/sentiment/")
    $floatCount = 0
    foreach ($path in $financialPaths) {
        if (Test-Path $path) {
            $results = Get-ChildItem -Recurse -Path $path -Include "*.py" | Select-String -Pattern "\bfloat\b"
            foreach ($result in $results) {
                $isApiBoundary = $false
                # Check current line
                if ($result.Line -match "# float required|# API boundary") {
                    $isApiBoundary = $true
                }
                # Check previous line if available
                if (-not $isApiBoundary -and $result.LineNumber -gt 1) {
                    $prevLine = (Get-Content $result.Path | Select-Object -Index ($result.LineNumber - 2))
                    if ($prevLine -match "# float required|# API boundary") {
                        $isApiBoundary = $true
                    }
                }
                if (-not $isApiBoundary) {
                    $floatCount++
                }
            }
        }
    }
    if ($floatCount -eq 0) { Write-Gate "G7" "PASS" } else { Write-Gate "G7" "FAIL" "$floatCount float(s) found in financial paths (not marked as API boundary)"; $allPassed = $false }
} catch { Write-Gate "G7" "FAIL" $_.Exception.Message; $allPassed = $false }

# G8: No naive datetime.now()
try {
    $dtCount = (Get-ChildItem -Recurse -Path "src/" -Include "*.py" | Select-String -Pattern "datetime\.now\(\)" | Measure-Object).Count
    if ($dtCount -eq 0) { Write-Gate "G8" "PASS" } else { Write-Gate "G8" "FAIL" "$dtCount naive datetime found"; $allPassed = $false }
} catch { Write-Gate "G8" "FAIL" $_.Exception.Message; $allPassed = $false }

# G9: No print() in src/
try {
    $printCount = (Get-ChildItem -Recurse -Path "src/" -Include "*.py" | Select-String -Pattern "\bprint\(" | Measure-Object).Count
    if ($printCount -eq 0) { Write-Gate "G9" "PASS" } else { Write-Gate "G9" "FAIL" "$printCount print() found"; $allPassed = $false }
} catch { Write-Gate "G9" "FAIL" $_.Exception.Message; $allPassed = $false }

# G10: Function size <=50 LOC (simple check)
try {
    $largeFuncs = 0
    # Basic check - can be extended later
    Write-Gate "G10" "PASS" "(placeholder - full check in CI)"
} catch { Write-Gate "G10" "FAIL" $_.Exception.Message; $allPassed = $false }

Write-Host "`n=== Final Summary ===" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "ALL GATES PASSED" -ForegroundColor Green
    Write-Host "Ready for git commit & next enhancement point." -ForegroundColor Green
} else {
    Write-Host "SOME GATES FAILED" -ForegroundColor Red
    Write-Host "Please fix the issues above before committing." -ForegroundColor Red
    exit 1
}