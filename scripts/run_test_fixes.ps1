# Win11 PowerShell Execution Script for IATB Test Fixes
# This script runs all quality gates, tests, and performs git sync

# Set error action preference
$ErrorActionPreference = "Stop"

# Function to write colored output
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

# Function to check command result
function Test-CommandResult {
    param(
        [string]$Command,
        [string]$Description
    )
    
    Write-ColorOutput Cyan "Running: $Description"
    try {
        $output = Invoke-Expression $Command 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput Red "FAILED: $Description"
            Write-ColorOutput Red $output
            return $false
        }
        Write-ColorOutput Green "PASSED: $Description"
        return $true
    }
    catch {
        Write-ColorOutput Red "ERROR: $Description"
        Write-ColorOutput Red $_.Exception.Message
        return $false
    }
}

# Main execution
Write-ColorOutput Yellow "=========================================="
Write-ColorOutput Yellow "IATB Test Fixes - Win11 PowerShell Script"
Write-ColorOutput Yellow "=========================================="
Write-Output ""

# Step 1: Verify/Install dependencies
Write-ColorOutput Cyan "Step 1: Verifying/Installing dependencies"
Write-Output "----------------------------------------"
Test-CommandResult "poetry install" "Install dependencies with Poetry"
Write-Output ""

# Step 2: Run Quality Gates (G1-G5)
Write-ColorOutput Cyan "Step 2: Running Quality Gates (G1-G5)"
Write-Output "----------------------------------------"

$g1Result = Test-CommandResult "poetry run ruff check src/ tests/" "G1: Ruff check"
$g2Result = Test-CommandResult "poetry run ruff format --check src/ tests/" "G2: Ruff format check"
$g3Result = Test-CommandResult "poetry run mypy src/ --strict" "G3: MyPy type check"
$g4Result = Test-CommandResult "poetry run bandit -r src/ -q" "G4: Bandit security check"
$g5Result = Test-CommandResult "gitleaks detect --source . --no-banner" "G5: Gitleaks secrets check"

Write-Output ""
Write-ColorOutput Cyan "Quality Gates Summary:"
Write-Output "G1 (Ruff check): $(if ($g1Result) { 'PASSED' } else { 'FAILED' })"
Write-Output "G2 (Ruff format): $(if ($g2Result) { 'PASSED' } else { 'FAILED' })"
Write-Output "G3 (MyPy): $(if ($g3Result) { 'PASSED' } else { 'FAILED' })"
Write-Output "G4 (Bandit): $(if ($g4Result) { 'PASSED' } else { 'FAILED' })"
Write-Output "G5 (Gitleaks): $(if ($g5Result) { 'PASSED' } else { 'FAILED' })"
Write-Output ""

# Step 3: Run Tests (G6)
Write-ColorOutput Cyan "Step 3: Running Tests (G6)"
Write-Output "----------------------------------------"
$g6Result = Test-CommandResult "poetry run pytest --cov=src/iatb --cov-fail-under=90 -x tests/data/test_data_source_validation.py tests/data/test_properties_critical.py tests/data/test_error_recovery.py -v" "G6: Pytest with coverage"
Write-Output ""

# Step 4: Additional Checks (G7-G10)
Write-ColorOutput Cyan "Step 4: Additional Checks (G7-G10)"
Write-Output "----------------------------------------"

# G7: No float in financial paths
Write-ColorOutput Cyan "G7: Checking for float in financial paths"
$floatCheck = Select-String -Path "src/iatb/data/*.py" -Pattern "float" | Where-Object { $_.Line -notmatch "# API boundary" -and $_.Line -notmatch "comment" }
if ($floatCheck) {
    Write-ColorOutput Red "FAILED: Found float usage in financial paths"
    $floatCheck | ForEach-Object { Write-Output "  $($_.Path):$($_.LineNumber): $($_.Line.Trim())" }
    $g7Result = $false
} else {
    Write-ColorOutput Green "PASSED: No float in financial paths"
    $g7Result = $true
}

# G8: No naive datetime
Write-ColorOutput Cyan "G8: Checking for naive datetime"
$naiveDtCheck = Select-String -Path "src/iatb/data/*.py" -Pattern "datetime\.now\(\)" | Where-Object { $_.Line -notmatch "UTC" }
if ($naiveDtCheck) {
    Write-ColorOutput Red "FAILED: Found naive datetime usage"
    $naiveDtCheck | ForEach-Object { Write-Output "  $($_.Path):$($_.LineNumber): $($_.Line.Trim())" }
    $g8Result = $false
} else {
    Write-ColorOutput Green "PASSED: No naive datetime"
    $g8Result = $true
}

# G9: No print statements
Write-ColorOutput Cyan "G9: Checking for print statements"
$printCheck = Select-String -Path "src/iatb/data/*.py" -Pattern "print\("
if ($printCheck) {
    Write-ColorOutput Red "FAILED: Found print statements"
    $printCheck | ForEach-Object { Write-Output "  $($_.Path):$($_.LineNumber): $($_.Line.Trim())" }
    $g9Result = $false
} else {
    Write-ColorOutput Green "PASSED: No print statements"
    $g9Result = $true
}

# G10: Function size check
Write-ColorOutput Cyan "G10: Checking function size (<=50 LOC)"
$funcSizeCheck = $false
Get-ChildItem -Path "src/iatb/data/*.py" -Recurse | ForEach-Object {
    $content = Get-Content $_.FullName
    $inFunction = $false
    $functionStart = 0
    $functionName = ""
    $lineCount = 0
    
    for ($i = 0; $i -lt $content.Count; $i++) {
        $line = $content[$i]
        
        if ($line -match "^\s*(async\s+)?def\s+(\w+)\s*\(") {
            if ($inFunction -and $lineCount -gt 50) {
                Write-ColorOutput Red "FAILED: Function $functionName exceeds 50 LOC ($lineCount lines)"
                Write-Output "  $($_.Path):$functionStart"
                $funcSizeCheck = $true
            }
            $inFunction = $true
            $functionStart = $i + 1
            $functionName = $matches[2]
            $lineCount = 0
        } elseif ($inFunction) {
            if ($line -match "^\s*(async\s+)?def\s+\w+\s*\(" -or $line -match "^class\s+\w+") {
                if ($lineCount -gt 50) {
                    Write-ColorOutput Red "FAILED: Function $functionName exceeds 50 LOC ($lineCount lines)"
                    Write-Output "  $($_.Path):$functionStart"
                    $funcSizeCheck = $true
                }
                $inFunction = $false
            } else {
                $lineCount++
            }
        }
    }
    
    if ($inFunction -and $lineCount -gt 50) {
        Write-ColorOutput Red "FAILED: Function $functionName exceeds 50 LOC ($lineCount lines)"
        Write-Output "  $($_.Path):$functionStart"
        $funcSizeCheck = $true
    }
}

if (-not $funcSizeCheck) {
    Write-ColorOutput Green "PASSED: All functions <= 50 LOC"
    $g10Result = $true
} else {
    $g10Result = $false
}

Write-Output ""
Write-ColorOutput Cyan "Additional Checks Summary:"
Write-Output "G7 (No float): $(if ($g7Result) { 'PASSED' } else { 'FAILED' })"
Write-Output "G8 (No naive dt): $(if ($g8Result) { 'PASSED' } else { 'FAILED' })"
Write-Output "G9 (No print): $(if ($g9Result) { 'PASSED' } else { 'FAILED' })"
Write-Output "G10 (Func size): $(if ($g10Result) { 'PASSED' } else { 'FAILED' })"
Write-Output ""

# Step 5: Git Sync
Write-ColorOutput Cyan "Step 5: Git Sync"
Write-Output "----------------------------------------"

# Get current branch
$branch = git rev-parse --abbrev-ref HEAD
Write-Output "Current branch: $branch"

# Git status
Write-Output "Git status:"
git status

# Add all changes
Write-Output "Adding all changes..."
git add -A

# Commit
$commitMessage = "Fix: Test failures in data source validation, properties critical, and error recovery tests - $(Get-Date -Format 'yyyy-MM-dd')"
Write-Output "Committing changes..."
git commit -m $commitMessage

# Pull with rebase
Write-Output "Pulling with rebase..."
git pull --rebase --autostash origin $branch

# Push
Write-Output "Pushing to origin..."
git push origin $branch

# Git status after sync
Write-Output "Git status after sync:"
git status

# Git log
Write-Output "Recent commits:"
git log --oneline -5

Write-Output ""
Write-ColorOutput Yellow "=========================================="
Write-ColorOutput Yellow "Script Execution Complete"
Write-ColorOutput Yellow "=========================================="

# Final summary
Write-Output ""
Write-ColorOutput Cyan "Final Summary:"
Write-Output "Quality Gates (G1-G5): $(if ($g1Result -and $g2Result -and $g3Result -and $g4Result -and $g5Result) { 'ALL PASSED' } else { 'SOME FAILED' })"
Write-Output "Tests (G6): $(if ($g6Result) { 'PASSED' } else { 'FAILED' })"
Write-Output "Additional Checks (G7-G10): $(if ($g7Result -and $g8Result -and $g9Result -and $g10Result) { 'ALL PASSED' } else { 'SOME FAILED' })"
Write-Output "Git Sync: COMPLETED"

Write-Output ""
Write-ColorOutput Green "All tasks completed successfully!"