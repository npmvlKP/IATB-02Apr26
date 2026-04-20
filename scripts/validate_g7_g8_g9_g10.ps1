# PowerShell validation script for G7, G8, G9, G10 gates
# Fixed version that works correctly on Windows PowerShell

$ErrorActionPreference = "Stop"

Write-Host "=" * 70
Write-Host "  IATB G7, G8, G9, G10 GATES VERIFICATION (PowerShell)"
Write-Host "=" * 70

# G7: No float in financial paths
Write-Host ""
Write-Host "=" * 70
Write-Host "  G7 - No Float in Financial Paths"
Write-Host "=" * 70

$financialPaths = @(
    "src/iatb/scanner/",
    "src/iatb/risk/",
    "src/iatb/backtesting/",
    "src/iatb/execution/",
    "src/iatb/selection/",
    "src/iatb/sentiment/"
)

$floatFound = $false
foreach ($path in $financialPaths) {
    if (Test-Path $path) {
        $matches = Get-ChildItem -Path $path -Filter "*.py" -Recurse | 
                   Select-String -Pattern "float" | 
                   Where-Object { $_.Line -notmatch "# API boundary" -and $_.Line -notmatch "#.*API.*boundary" }
        
        if ($matches) {
            $floatFound = $true
            Write-Host "[FAIL] G7: FAILED - Found float in $path"
            $matches | Select-Object -First 10 | ForEach-Object {
                Write-Host "  $($_.Path):$($_.LineNumber): $($_.Line.Trim())"
            }
        }
    }
}

if (-not $floatFound) {
    Write-Host "[PASS] No float found in financial paths (PASS)"
}

# G8: No naive datetime.now()
Write-Host ""
Write-Host "=" * 70
Write-Host "  G8 - No Naive Datetime"
Write-Host "=" * 70

$dtMatches = Get-ChildItem -Path "src/" -Filter "*.py" -Recurse | 
             Select-String -Pattern "datetime\.now\(\)" | 
             Where-Object { $_.Line -notmatch "UTC" }

if ($dtMatches) {
    Write-Host "[FAIL] G8: FAILED - Found naive datetime.now()"
    $dtMatches | Select-Object -First 10 | ForEach-Object {
        Write-Host "  $($_.Path):$($_.LineNumber): $($_.Line.Trim())"
    }
} else {
    Write-Host "[PASS] No naive datetime.now() found (PASS)"
}

# G9: No print() statements
Write-Host ""
Write-Host "=" * 70
Write-Host "  G9 - No Print Statements"
Write-Host "=" * 70

$printMatches = Get-ChildItem -Path "src/" -Filter "*.py" -Recurse | 
                Select-String -Pattern "print\("

if ($printMatches) {
    Write-Host "[FAIL] G9: FAILED - Found print() statements"
    $printMatches | Select-Object -First 10 | ForEach-Object {
        Write-Host "  $($_.Path):$($_.LineNumber): $($_.Line.Trim())"
    }
} else {
    Write-Host "[PASS] No print() found (PASS)"
}

# G10: Function size <= 50 LOC (use Python script for this)
Write-Host ""
Write-Host "=" * 70
Write-Host "  G10 - Function Size <= 50 LOC"
Write-Host "=" * 70
Write-Host "[INFO] Running Python script for G10 verification..."
python scripts/verify_g7_g8_g9_g10.py

Write-Host ""
Write-Host "=" * 70
Write-Host "  SUMMARY"
Write-Host "=" * 70
Write-Host "Gates passed: See output above"