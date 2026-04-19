# Risk 3: Rate Limiting Mitigation Strategy - Validation Runbook
# Validates all mitigation components for Kite API 3 req/sec limit

Write-Host "=== Risk 3: Rate Limiting Mitigation Validation ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Verify dependencies
Write-Host "[Step 1/6] Verifying dependencies..." -ForegroundColor Yellow
poetry install --no-root
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Dependency installation failed" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Dependencies installed" -ForegroundColor Green
Write-Host ""

# Step 2: Run quality gates (G1-G5)
Write-Host "[Step 2/6] Running quality gates (G1-G5)..." -ForegroundColor Yellow

Write-Host "  G1: Lint check..."
poetry run ruff check src/ tests/
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌ G1 failed" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G1 passed" -ForegroundColor Green

Write-Host "  G2: Format check..."
poetry run ruff format --check src/ tests/
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌ G2 failed" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G2 passed" -ForegroundColor Green

Write-Host "  G3: Type check..."
poetry run mypy src/ --strict
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌ G3 failed" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G3 passed" -ForegroundColor Green

Write-Host "  G4: Security check..."
poetry run bandit -r src/ -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌ G4 failed" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G4 passed" -ForegroundColor Green

Write-Host "  G5: Secrets check..."
gitleaks detect --source . --no-banner
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌ G5 failed" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G5 passed" -ForegroundColor Green
Write-Host ""

# Step 3: Run rate limiting mitigation tests (G6)
Write-Host "[Step 3/6] Running rate limiting mitigation tests (G6)..." -ForegroundColor Yellow
poetry run pytest tests/integration/test_rate_limiting_mitigation.py -xvs --cov=src/iatb --cov-fail-under=90
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ G6 failed - Tests did not pass or coverage < 90%" -ForegroundColor Red
    exit 1
}
Write-Host "✓ G6 passed - All tests passed with ≥90% coverage" -ForegroundColor Green
Write-Host ""

# Step 4: Additional checks (G7-G10)
Write-Host "[Step 4/6] Running additional checks (G7-G10)..." -ForegroundColor Yellow

Write-Host "  G7: No float in financial paths..."
$floatCheck = Get-ChildItem -Path 'src/iatb/risk/','src/iatb/backtesting/','src/iatb/execution/','src/iatb/selection/','src/iatb/sentiment/' -Filter '*.py' -Recurse -ErrorAction SilentlyContinue | Select-String -Pattern 'float' | Where-Object { $_.Line -notmatch "# API boundary" }
if ($floatCheck) {
    Write-Host "  ❌ G7 failed - Found float usage without API boundary comment:" -ForegroundColor Red
    $floatCheck | ForEach-Object { Write-Host "    $($_.Path):$($_.LineNumber): $($_.Line.Trim())" -ForegroundColor Red }
    exit 1
}
Write-Host "  ✓ G7 passed - All float usage has API boundary comments" -ForegroundColor Green

Write-Host "  G8: No naive datetime..."
$naiveDtCheck = Get-ChildItem -Path 'src/' -Filter '*.py' -Recurse | Select-String -Pattern 'datetime\.now\(\)'
if ($naiveDtCheck) {
    Write-Host "  ❌ G8 failed - Found naive datetime.now():" -ForegroundColor Red
    $naiveDtCheck | ForEach-Object { Write-Host "    $($_.Path):$($_.LineNumber): $($_.Line.Trim())" -ForegroundColor Red }
    exit 1
}
Write-Host "  ✓ G8 passed - No naive datetime.now() found" -ForegroundColor Green

Write-Host "  G9: No print statements..."
$printCheck = Get-ChildItem -Path 'src/' -Filter '*.py' -Recurse | Select-String -Pattern 'print\('
if ($printCheck) {
    Write-Host "  ❌ G9 failed - Found print() statements:" -ForegroundColor Red
    $printCheck | ForEach-Object { Write-Host "    $($_.Path):$($_.LineNumber): $($_.Line.Trim())" -ForegroundColor Red }
    exit 1
}
Write-Host "  ✓ G9 passed - No print() statements found" -ForegroundColor Green

Write-Host "  G10: Function size check (≤50 LOC)..."
$complexFunctions = Get-ChildItem -Path 'src/iatb/data/kite_provider.py','src/iatb/data/market_data_cache.py','src/iatb/data/token_resolver.py','src/iatb/data/kite_ws_provider.py' -Filter '*.py' | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $lines = $content -split "`n"
    $inFunction = $false
    $functionName = ""
    $startLine = 0
    $indentLevel = 0
    
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        if ($line -match '^\s*def\s+(\w+)\s*\(' -and $line -notmatch '# noqa: C901') {
            if ($inFunction) {
                $loc = $i - $startLine
                if ($loc -gt 50) {
                    [PSCustomObject]@{
                        File = $_.Name
                        Function = $functionName
                        Line = $startLine + 1
                        LOC = $loc
                    }
                }
            }
            $inFunction = $true
            $functionName = $matches[1]
            $startLine = $i
            $indentLevel = $line.Length - $line.TrimStart().Length
        } elseif ($inFunction -and $line.Length - $line.TrimStart().Length -le $indentLevel -and $line.Trim() -ne "" -and $line -notmatch '^\s*#') {
            $loc = $i - $startLine
            if ($loc -gt 50) {
                [PSCustomObject]@{
                    File = $_.Name
                    Function = $functionName
                    Line = $startLine + 1
                    LOC = $loc
                }
            }
            $inFunction = $false
        }
    }
}

if ($complexFunctions) {
    Write-Host "  ❌ G10 failed - Functions exceeding 50 LOC:" -ForegroundColor Red
    $complexFunctions | ForEach-Object { Write-Host "    $($_.File):$($_.Line): $($_.Function) - $($_.LOC) LOC" -ForegroundColor Red }
    exit 1
}
Write-Host "  ✓ G10 passed - All functions ≤50 LOC (or have noqa: C901)" -ForegroundColor Green
Write-Host ""

# Step 5: Verify mitigation components exist
Write-Host "[Step 5/6] Verifying mitigation components..." -ForegroundColor Yellow

Write-Host "  Checking Mitigation 1: Token bucket rate limiter..."
if (-not (Test-Path 'src/iatb/data/kite_provider.py') -or -not (Select-String -Path 'src/iatb/data/kite_provider.py' -Pattern 'class _RateLimiter')) {
    Write-Host "  ❌ Token bucket rate limiter not found" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Token bucket rate limiter found" -ForegroundColor Green

Write-Host "  Checking Mitigation 2: Batch token resolution..."
if (-not (Test-Path 'src/iatb/data/token_resolver.py') -or -not (Select-String -Path 'src/iatb/data/token_resolver.py' -Pattern 'resolve_multiple_tokens')) {
    Write-Host "  ❌ Batch token resolution not found" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Batch token resolution found" -ForegroundColor Green

Write-Host "  Checking Mitigation 3: Historical data cache..."
if (-not (Test-Path 'src/iatb/data/market_data_cache.py') -or -not (Select-String -Path 'src/iatb/data/market_data_cache.py' -Pattern 'class MarketDataCache')) {
    Write-Host "  ❌ Historical data cache not found" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Historical data cache found" -ForegroundColor Green

Write-Host "  Checking Mitigation 4: WebSocket for live data..."
if (-not (Test-Path 'src/iatb/data/kite_ws_provider.py') -or -not (Select-String -Path 'src/iatb/data/kite_ws_provider.py' -Pattern 'class KiteWebSocketProvider')) {
    Write-Host "  ❌ WebSocket provider not found" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ WebSocket provider found" -ForegroundColor Green
Write-Host ""

# Step 6: Git sync
Write-Host "[Step 6/6] Git sync..." -ForegroundColor Yellow

# Check current branch
$currentBranch = git rev-parse --abbrev-ref HEAD
Write-Host "  Current branch: $currentBranch" -ForegroundColor Cyan

# Stage changes
git add tests/integration/test_rate_limiting_mitigation.py RISK_3_RATE_LIMITING_MITIGATION_RUNBOOK.ps1

# Check status
$status = git status --short
if ($status) {
    Write-Host "  Changes to commit:" -ForegroundColor Cyan
    $status | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    
    # Commit
    $commitMsg = "feat(risk): add rate limiting mitigation integration tests and validation"
    git commit -m $commitMsg
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ❌ Commit failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ Committed changes" -ForegroundColor Green
    
    # Get commit hash
    $commitHash = git rev-parse HEAD
    Write-Host "  Commit hash: $commitHash" -ForegroundColor Cyan
    
    # Push (require confirmation)
    Write-Host ""
    Write-Host "Ready to push to origin/$currentBranch" -ForegroundColor Yellow
    $push = Read-Host "Push changes? (y/n)"
    if ($push -eq 'y') {
        git push origin $currentBranch
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ❌ Push failed" -ForegroundColor Red
            exit 1
        }
        Write-Host "  ✓ Pushed to origin/$currentBranch" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Push skipped" -ForegroundColor Yellow
    }
} else {
    Write-Host "  No changes to commit" -ForegroundColor Gray
}
Write-Host ""

# Summary
Write-Host "=== Validation Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "All quality gates passed (G1-G10)" -ForegroundColor Green
Write-Host "All mitigation components verified:" -ForegroundColor Green
Write-Host "  1. Token bucket rate limiter (KiteProvider._RateLimiter)" -ForegroundColor Green
Write-Host "  2. Batch token resolution (SymbolTokenResolver.resolve_multiple_tokens)" -ForegroundColor Green
Write-Host "  3. Historical data cache (MarketDataCache)" -ForegroundColor Green
Write-Host "  4. WebSocket for live data (KiteWebSocketProvider)" -ForegroundColor Green
Write-Host ""
Write-Host "Risk 3 mitigation strategy is fully implemented and tested." -ForegroundColor Cyan