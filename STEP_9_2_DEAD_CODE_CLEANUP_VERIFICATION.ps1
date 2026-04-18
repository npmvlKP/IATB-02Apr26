# ============================================================================
# STEP 9-2: Dead Code Cleanup Verification Script
# ============================================================================
# Purpose: Verify that all dead code from AUDIT_REPORT.md STEP 9 has been cleaned
# Author: Cline (Automated Codebase Intelligence)
# Date: 2026-04-17
# ============================================================================

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "STEP 9-2: Dead Code Cleanup Verification" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$cleanupStatus = @{}
$allPassed = $true

# ============================================================================
# Item 1: Check if scripts/historical directory exists
# ============================================================================
Write-Host "[1/5] Checking scripts/historical directory..." -ForegroundColor Yellow
if (Test-Path "scripts\historical") {
    Write-Host "  FAIL: Directory still exists" -ForegroundColor Red
    $cleanupStatus["scripts/historical"] = "FAIL - Directory exists"
    $allPassed = $false
} else {
    Write-Host "  PASS: Directory removed" -ForegroundColor Green
    $cleanupStatus["scripts/historical"] = "PASS"
}

# ============================================================================
# Item 2: Check for scan_cycle.py.fixed file
# ============================================================================
Write-Host "[2/5] Checking scan_cycle.py.fixed..." -ForegroundColor Yellow
if (Test-Path "src\iatb\scanner\scan_cycle.py.fixed") {
    Write-Host "  FAIL: scan_cycle.py.fixed still exists" -ForegroundColor Red
    $cleanupStatus["scan_cycle.py.fixed"] = "FAIL - File exists"
    $allPassed = $false
} else {
    Write-Host "  PASS: scan_cycle.py.fixed removed" -ForegroundColor Green
    $cleanupStatus["scan_cycle.py.fixed"] = "PASS"
}

# ============================================================================
# Item 3: Check for $null file in root
# ============================================================================
Write-Host "[3/5] Checking for `$null file in root..." -ForegroundColor Yellow
$nullFileExists = Get-ChildItem -Path "." -Filter "*null*" -ErrorAction SilentlyContinue | 
                  Where-Object { $_.Name -match '^\$null$' }
if ($nullFileExists) {
    Write-Host "  FAIL: `$null file still exists" -ForegroundColor Red
    $cleanupStatus["`$null file"] = "FAIL - File exists"
    $allPassed = $false
} else {
    Write-Host "  PASS: `$null file removed" -ForegroundColor Green
    $cleanupStatus["`$null file"] = "PASS"
}

# ============================================================================
# Item 4: Check for fix_*.py scripts in root
# ============================================================================
Write-Host "[4/5] Checking for fix_*.py scripts in root..." -ForegroundColor Yellow
$fixScripts = Get-ChildItem -Path "." -Filter "fix_*.py" -ErrorAction SilentlyContinue
if ($fixScripts) {
    Write-Host "  FAIL: Found $($fixScripts.Count) fix_*.py script(s):" -ForegroundColor Red
    foreach ($script in $fixScripts) {
        Write-Host "    - $($script.Name)" -ForegroundColor Red
    }
    $cleanupStatus["fix_*.py scripts"] = "FAIL - $($fixScripts.Count) files found"
    $allPassed = $false
} else {
    Write-Host "  PASS: No fix_*.py scripts in root" -ForegroundColor Green
    $cleanupStatus["fix_*.py scripts"] = "PASS"
}

# ============================================================================
# Item 5: Check for pyproject.toml.bak* files
# ============================================================================
Write-Host "[5/5] Checking for pyproject.toml.bak* files..." -ForegroundColor Yellow
$bakFiles = Get-ChildItem -Path "." -Filter "pyproject.toml.bak*" -ErrorAction SilentlyContinue
if ($bakFiles) {
    Write-Host "  FAIL: Found $($bakFiles.Count) pyproject.toml.bak* file(s):" -ForegroundColor Red
    foreach ($file in $bakFiles) {
        Write-Host "    - $($file.Name)" -ForegroundColor Red
    }
    $cleanupStatus["pyproject.toml.bak*"] = "FAIL - $($bakFiles.Count) files found"
    $allPassed = $false
} else {
    Write-Host "  PASS: No pyproject.toml.bak* files" -ForegroundColor Green
    $cleanupStatus["pyproject.toml.bak*"] = "PASS"
}

# ============================================================================
# Summary Report
# ============================================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "CLEANUP VERIFICATION SUMMARY" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

foreach ($item in $cleanupStatus.Keys) {
    $status = $cleanupStatus[$item]
    if ($status -eq "PASS") {
        Write-Host "  [PASS] $item" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] $item - $status" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "OVERALL RESULT: ALL CLEANUP ITEMS VERIFIED" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "PowerShell Syntax Analysis:" -ForegroundColor Yellow
    Write-Host "  Original command used CMD batch syntax:" -ForegroundColor Yellow
    Write-Host "    if exist ... (echo ...) else (echo ...)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Correct PowerShell syntax:" -ForegroundColor Yellow
    Write-Host "    if (Test-Path ...) { Write-Host ... } else { Write-Host ... }" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Example for your specific check:" -ForegroundColor Yellow
    Write-Host "    if (Test-Path 'scripts\historical') {" -ForegroundColor Yellow
    Write-Host "        Write-Host 'ERROR: Directory still exists'" -ForegroundColor Yellow
    Write-Host "    } else {" -ForegroundColor Yellow
    Write-Host "        Write-Host 'SUCCESS: Directory removed'" -ForegroundColor Yellow
    Write-Host "    }" -ForegroundColor Yellow
    Write-Host ""
    exit 0
} else {
    Write-Host "OVERALL RESULT: CLEANUP INCOMPLETE" -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please remove the items listed above as FAIL." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}