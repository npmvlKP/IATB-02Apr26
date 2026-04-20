# Quick PowerShell equivalents for grep commands (G7, G8, G9)
# Run from project root directory

Write-Host "`n==========================================================================" -ForegroundColor Cyan
Write-Host "  QUICK VALIDATION (G7, G8, G9) - PowerShell Equivalents" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan

# G7: No float in financial paths
Write-Host "`n[G7] Checking for 'float' in financial paths..." -ForegroundColor Yellow
$g7_results = @("src/iatb/risk", "src/iatb/backtesting", "src/iatb/execution", "src/iatb/selection", "src/iatb/sentiment" | ForEach-Object {
    $path = $_
    if (Test-Path $path) {
        Get-ChildItem -Path $path -Filter "*.py" -Recurse -ErrorAction SilentlyContinue | Select-String -Pattern "float" -ErrorAction SilentlyContinue
    }
})

if ($g7_results) {
    Write-Host "[FAIL] G7: Found 'float' in financial paths:" -ForegroundColor Red
    $g7_results | ForEach-Object { Write-Host "  $($_.Path):$($_.LineNumber): $($_.Line.Trim())" -ForegroundColor Red }
} else {
    Write-Host "[PASS] G7: No 'float' found in financial paths" -ForegroundColor Green
}

# G8: No naive datetime.now()
Write-Host "`n[G8] Checking for 'datetime.now()' in src/..." -ForegroundColor Yellow
$g8_results = Get-ChildItem -Path "src" -Filter "*.py" -Recurse -ErrorAction SilentlyContinue | Select-String -Pattern "datetime\.now\(\)" -ErrorAction SilentlyContinue

if ($g8_results) {
    Write-Host "[FAIL] G8: Found 'datetime.now()' in src/:" -ForegroundColor Red
    $g8_results | ForEach-Object { Write-Host "  $($_.Path):$($_.LineNumber): $($_.Line.Trim())" -ForegroundColor Red }
} else {
    Write-Host "[PASS] G8: No 'datetime.now()' found in src/" -ForegroundColor Green
}

# G9: No print() statements
Write-Host "`n[G9] Checking for 'print(' in src/..." -ForegroundColor Yellow
$g9_results = Get-ChildItem -Path "src" -Filter "*.py" -Recurse -ErrorAction SilentlyContinue | Select-String -Pattern "print\(" -ErrorAction SilentlyContinue

if ($g9_results) {
    Write-Host "[FAIL] G9: Found 'print(' in src/:" -ForegroundColor Red
    $g9_results | ForEach-Object { Write-Host "  $($_.Path):$($_.LineNumber): $($_.Line.Trim())" -ForegroundColor Red }
} else {
    Write-Host "[PASS] G9: No 'print(' found in src/" -ForegroundColor Green
}

Write-Host "`n==========================================================================" -ForegroundColor Cyan
Write-Host "  For comprehensive validation (G1-G10), run: .\scripts\validate_all_gates.ps1" -ForegroundColor Cyan
Write-Host "  For Python-based validation, run: python scripts/verify_g7_g8_g9_g10.py" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan