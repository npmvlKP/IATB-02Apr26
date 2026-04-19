# Windows PowerShell Quality Gates Script
# Compatible with Windows 11 PowerShell

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "IATB Quality Gates (PowerShell)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Continue"
$OverallPass = $true

# G1: Lint
Write-Host "G1: Running Ruff Linter..." -ForegroundColor Yellow
poetry run ruff check src/ tests/
if ($LASTEXITCODE -eq 0) {
    Write-Host "G1: Lint PASSED" -ForegroundColor Green
} else {
    Write-Host "G1: Lint FAILED" -ForegroundColor Red
    $OverallPass = $false
}
Write-Host ""

# G2: Format
Write-Host "G2: Checking Ruff Formatting..." -ForegroundColor Yellow
poetry run ruff format --check src/ tests/
if ($LASTEXITCODE -eq 0) {
    Write-Host "G2: Format PASSED" -ForegroundColor Green
} else {
    Write-Host "G2: Format FAILED" -ForegroundColor Red
    $OverallPass = $false
}
Write-Host ""

# G3: Types
Write-Host "G3: Running MyPy Type Checker..." -ForegroundColor Yellow
poetry run mypy src/ --strict
if ($LASTEXITCODE -eq 0) {
    Write-Host "G3: Types PASSED" -ForegroundColor Green
} else {
    Write-Host "G3: Types FAILED" -ForegroundColor Red
    $OverallPass = $false
}
Write-Host ""

# G4: Security
Write-Host "G4: Running Bandit Security Scan..." -ForegroundColor Yellow
poetry run bandit -r src/ -q
if ($LASTEXITCODE -eq 0) {
    Write-Host "G4: Security PASSED" -ForegroundColor Green
} else {
    Write-Host "G4: Security FAILED" -ForegroundColor Red
    $OverallPass = $false
}
Write-Host ""

# G5: Secrets
Write-Host "G5: Running Gitleaks Secret Scan..." -ForegroundColor Yellow
gitleaks detect --source . --no-banner
if ($LASTEXITCODE -eq 0) {
    Write-Host "G5: Secrets PASSED" -ForegroundColor Green
} else {
    Write-Host "G5: Secrets FAILED" -ForegroundColor Red
    $OverallPass = $false
}
Write-Host ""

# G7: No float in financial paths (PowerShell compatible)
Write-Host "G7: Checking for float in financial paths..." -ForegroundColor Yellow
$FloatFound = $false
$FinancialPaths = @(
    "src\iatb\risk\",
    "src\iatb\backtesting\",
    "src\iatb\execution\",
    "src\iatb\selection\",
    "src\iatb\sentiment\",
    "src\iatb\scanner\"
)

foreach ($path in $FinancialPaths) {
    if (Test-Path $path) {
        $files = Get-ChildItem -Path $path -Filter "*.py" -Recurse -ErrorAction SilentlyContinue
        foreach ($file in $files) {
            $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
            if ($content) {
                $lines = $content -split "`n"
                for ($i = 0; $i -lt $lines.Count; $i++) {
                    $line = $lines[$i].Trim()
                    # Skip comments and lines with API boundary justification
                    if ($line -match "float" -and -not $line.StartsWith("#") -and $line -notmatch "# API boundary" -and $line -notmatch "float required:" -and $line -notmatch "type: ignore") {
                        # Check if this line or the previous line has an API boundary comment
                        $prevLine = if ($i -gt 0) { $lines[$i-1].Trim() } else { "" }
                        if ($prevLine -notmatch "# API boundary" -and $prevLine -notmatch "float required:") {
                            Write-Host "  Found 'float' in: $($file.FullName):$($i+1)" -ForegroundColor Red
                            Write-Host "    $line" -ForegroundColor DarkRed
                            $FloatFound = $true
                        }
                    }
                }
            }
        }
    }
}

if (-not $FloatFound) {
    Write-Host "G7: No float in financial paths PASSED" -ForegroundColor Green
} else {
    Write-Host "G7: No float in financial paths FAILED" -ForegroundColor Red
    $OverallPass = $false
}
Write-Host ""

# G8: No naive datetime
Write-Host "G8: Checking for naive datetime.now()..." -ForegroundColor Yellow
$NaiveDtFound = $false
$files = Get-ChildItem -Path "src\iatb" -Filter "*.py" -Recurse -ErrorAction SilentlyContinue
foreach ($file in $files) {
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    if ($content) {
        $lines = $content -split "`n"
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i].Trim()
            if ($line -match "datetime\.now\(\)" -and -not $line.StartsWith("#") -and $line -notmatch "tzinfo=" -and $line -notmatch "UTC") {
                Write-Host "  Found naive datetime.now() in: $($file.FullName):$($i+1)" -ForegroundColor Red
                Write-Host "    $line" -ForegroundColor DarkRed
                $NaiveDtFound = $true
            }
        }
    }
}

if (-not $NaiveDtFound) {
    Write-Host "G8: No naive datetime PASSED" -ForegroundColor Green
} else {
    Write-Host "G8: No naive datetime FAILED" -ForegroundColor Red
    $OverallPass = $false
}
Write-Host ""

# G9: No print statements
Write-Host "G9: Checking for print() statements..." -ForegroundColor Yellow
$PrintFound = $false
$files = Get-ChildItem -Path "src\iatb" -Filter "*.py" -Recurse -ErrorAction SilentlyContinue
foreach ($file in $files) {
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    if ($content) {
        $lines = $content -split "`n"
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = $lines[$i].Trim()
            if ($line -match "print\(" -and -not $line.StartsWith("#")) {
                Write-Host "  Found print() in: $($file.FullName):$($i+1)" -ForegroundColor Red
                Write-Host "    $line" -ForegroundColor DarkRed
                $PrintFound = $true
            }
        }
    }
}

if (-not $PrintFound) {
    Write-Host "G9: No print statements PASSED" -ForegroundColor Green
} else {
    Write-Host "G9: No print statements FAILED" -ForegroundColor Red
    $OverallPass = $false
}
Write-Host ""

# G6: Tests (run last as it takes longest)
Write-Host "G6: Running Tests with Coverage..." -ForegroundColor Yellow
poetry run pytest --cov=src/iatb --cov-fail-under=90 -x
if ($LASTEXITCODE -eq 0) {
    Write-Host "G6: Tests PASSED (coverage 90% or above)" -ForegroundColor Green
} else {
    Write-Host "G6: Tests FAILED or coverage below 90%" -ForegroundColor Red
    $OverallPass = $false
}
Write-Host ""

# G10: Function size (simplified check)
Write-Host "G10: Checking function size (50 LOC or less)..." -ForegroundColor Yellow
$FuncSizeViolations = 0
$files = Get-ChildItem -Path "src\iatb" -Filter "*.py" -Recurse -ErrorAction SilentlyContinue
foreach ($file in $files) {
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    if ($content) {
        # Simple heuristic: count lines in function definitions
        $pattern = "def \w+\([^)]*\):[\s\S]*?(?=\ndef |\nclass |\Z)"
        $matches = [regex]::Matches($content, $pattern)
        foreach ($match in $matches) {
            $funcLines = ($match.Value -split "`n").Count
            if ($funcLines -gt 50) {
                Write-Host "  Large function detected in: $($file.Name) (~$funcLines lines)" -ForegroundColor Red
                $FuncSizeViolations++
            }
        }
    }
}

if ($FuncSizeViolations -eq 0) {
    Write-Host "G10: Function size check PASSED" -ForegroundColor Green
} else {
    Write-Host "G10: Function size check FAILED ($FuncSizeViolations violations)" -ForegroundColor Red
    $OverallPass = $false
}
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
if ($OverallPass) {
    Write-Host "ALL QUALITY GATES PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host "SOME QUALITY GATES FAILED" -ForegroundColor Red
    exit 1
}