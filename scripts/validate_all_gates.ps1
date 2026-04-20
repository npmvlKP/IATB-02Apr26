#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Complete validation runbook for IATB G1-G10 gates (Windows PowerShell)
.DESCRIPTION
    Runs all 10 validation gates for the IATB project on Windows.
    This replaces grep commands with PowerShell equivalents and uses Python scripts.
    Author: IATB Automation
    Date: 2026-04-20
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$StartTime = Get-Date

Write-Host "`n==========================================================================" -ForegroundColor Cyan
Write-Host "  IATB COMPLETE VALIDATION RUNBOOK (G1-G10)" -ForegroundColor Cyan
Write-Host "  Windows PowerShell Edition" -ForegroundColor Cyan
Write-Host "  Started: $($StartTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan

# Track results
$GateResults = @{}

function Invoke-Gate {
    param(
        [string]$Name,
        [string]$Command,
        [string]$Description
    )
    
    Write-Host "`n==========================================================================" -ForegroundColor Yellow
    Write-Host "  $Name" -ForegroundColor Yellow
    Write-Host "  $Description" -ForegroundColor Gray
    Write-Host "==========================================================================" -ForegroundColor Yellow
    
    $Output = Invoke-Expression $Command 2>&1
    $ExitCode = $LASTEXITCODE
    
    if ($ExitCode -eq 0) {
        Write-Host "[PASS] $Name - All checks passed" -ForegroundColor Green
        $GateResults[$Name] = "PASS"
        return $true
    } else {
        Write-Host "[FAIL] $Name - Validation failed" -ForegroundColor Red
        Write-Host $Output -ForegroundColor Red
        $GateResults[$Name] = "FAIL"
        return $false
    }
}

# Step 1: Verify Poetry Installation
Write-Host "`n==========================================================================" -ForegroundColor Cyan
Write-Host "  PRE-STEP: Verify Poetry Installation" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan

try {
    $PoetryVersion = poetry --version 2>&1
    Write-Host "[PASS] Poetry found: $PoetryVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Poetry not found. Please install Poetry first." -ForegroundColor Red
    Write-Host "Install from: https://python-poetry.org/docs/#installation" -ForegroundColor Yellow
    exit 1
}

# Step 2: Install Dependencies
Write-Host "`n==========================================================================" -ForegroundColor Cyan
Write-Host "  PRE-STEP: Install Dependencies" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan

Write-Host "Running: poetry install..." -ForegroundColor Gray
poetry install --no-interaction 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[PASS] Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "[WARN] Some dependency issues detected, continuing..." -ForegroundColor Yellow
}

# Step 3: Run Quality Gates (G1-G5)
Write-Host "`n==========================================================================" -ForegroundColor Cyan
Write-Host "  PHASE 1: Quality Gates (G1-G5)" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan

Invoke-Gate -Name "G1 - Lint Check" -Command "poetry run ruff check src/ tests/" -Description "Check for code style violations"
Invoke-Gate -Name "G2 - Format Check" -Command "poetry run ruff format --check src/ tests/" -Description "Check code formatting"
Invoke-Gate -Name "G3 - Type Check" -Command "poetry run mypy src/ --strict" -Description "Strict type checking with mypy"
Invoke-Gate -Name "G4 - Security Check" -Command "poetry run bandit -r src/ -q" -Description "Security vulnerability scan"
Invoke-Gate -Name "G5 - Secrets Check" -Command "gitleaks detect --source . --no-banner" -Description "Secret leak detection"

# Step 4: Run Tests (G6)
Write-Host "`n==========================================================================" -ForegroundColor Cyan
Write-Host "  PHASE 2: Test Coverage (G6)" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan

Invoke-Gate -Name "G6 - Test Coverage" -Command "poetry run pytest --cov=src/iatb --cov-fail-under=90 -x" -Description "Run tests with >=90% coverage"

# Step 5: Additional Checks (G7-G10)
Write-Host "`n==========================================================================" -ForegroundColor Cyan
Write-Host "  PHASE 3: Additional Checks (G7-G10)" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan

Invoke-Gate -Name "G7 - No Float in Financial Paths" -Command "python scripts/verify_g7_g8_g9_g10.py" -Description "AST-based check for float usage in financial modules"
Invoke-Gate -Name "G8 - No Naive Datetime" -Command "python scripts/verify_g7_g8_g9_g10.py" -Description "Check for datetime.now() usage"
Invoke-Gate -Name "G9 - No Print Statements" -Command "python scripts/verify_g7_g8_g9_g10.py" -Description "Check for print() statements in src/"
Invoke-Gate -Name "G10 - Function Size" -Command "python scripts/verify_g7_g8_g9_g10.py" -Description "Check all functions <= 50 LOC"

# Step 6: Generate Summary
Write-Host "`n==========================================================================" -ForegroundColor Cyan
Write-Host "  VALIDATION SUMMARY" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan

$TotalGates = $GateResults.Count
$PassedGates = ($GateResults.Values | Where-Object { $_ -eq "PASS" }).Count
$FailedGates = $TotalGates - $PassedGates

Write-Host "`nTotal Gates: $TotalGates" -ForegroundColor White
Write-Host "Passed: $PassedGates" -ForegroundColor Green
Write-Host "Failed: $FailedGates" -ForegroundColor $(if ($FailedGates -gt 0) { "Red" } else { "Green" })

Write-Host "`nDetailed Results:" -ForegroundColor White
foreach ($Gate in $GateResults.GetEnumerator()) {
    $Color = if ($Gate.Value -eq "PASS") { "Green" } else { "Red" }
    Write-Host "  $($Gate.Key): $($Gate.Value)" -ForegroundColor $Color
}

$EndTime = Get-Date
$Duration = $EndTime - $StartTime
Write-Host "`nCompleted: $($EndTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Cyan
Write-Host "Duration: $($Duration.ToString('mm\:ss\.fff'))" -ForegroundColor Cyan

# Step 7: Git Status (Pre-sync)
Write-Host "`n==========================================================================" -ForegroundColor Cyan
Write-Host "  GIT STATUS (Pre-Sync)" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan

git status --short

# Exit with appropriate code
if ($FailedGates -eq 0) {
    Write-Host "`n==========================================================================" -ForegroundColor Green
    Write-Host "  [SUCCESS] ALL VALIDATION GATES PASSED!" -ForegroundColor Green
    Write-Host "  Ready for git sync and deployment" -ForegroundColor Green
    Write-Host "==========================================================================" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n==========================================================================" -ForegroundColor Red
    Write-Host "  [FAILURE] $FailedGate(s) GATE(S) FAILED" -ForegroundColor Red
    Write-Host "  Please fix failures before proceeding" -ForegroundColor Red
    Write-Host "==========================================================================" -ForegroundColor Red
    exit 1
}