# Risk 4: Migration Regression Mitigation Runbook
# Incremental migration with dual-path support and A/B testing
# /Agnt

Write-Host "=== Risk 4 Migration Regression Mitigation ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Verify/Install dependencies
Write-Host "Step 1: Verifying dependencies..." -ForegroundColor Yellow
poetry install
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: poetry install" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Dependencies installed" -ForegroundColor Green
Write-Host ""

# Step 2: Run Quality Gates (G1-G5)
Write-Host "Step 2: Running Quality Gates (G1-G5)..." -ForegroundColor Yellow

# G1: Lint
Write-Host "  G1: Ruff lint check..." -ForegroundColor Cyan
poetry run ruff check src/iatb/data/migration_provider.py tests/data/test_migration_provider.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: G1 Ruff lint" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G1 passed" -ForegroundColor Green

# G2: Format
Write-Host "  G2: Ruff format check..." -ForegroundColor Cyan
poetry run ruff format --check src/iatb/data/migration_provider.py tests/data/test_migration_provider.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: G2 Ruff format" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G2 passed" -ForegroundColor Green

# G3: Type checking
Write-Host "  G3: MyPy strict type check..." -ForegroundColor Cyan
poetry run mypy src/iatb/data/migration_provider.py --strict
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: G3 MyPy" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G3 passed" -ForegroundColor Green

# G4: Security
Write-Host "  G4: Bandit security check..." -ForegroundColor Cyan
poetry run bandit -r src/iatb/data/migration_provider.py -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: G4 Bandit" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G4 passed" -ForegroundColor Green

# G5: Secrets
Write-Host "  G5: Gitleaks secret scan..." -ForegroundColor Cyan
gitleaks detect --source . --no-banner
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: G5 Gitleaks" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G5 passed" -ForegroundColor Green
Write-Host ""

# Step 3: Run Tests (G6)
Write-Host "Step 3: Running Tests (G6)..." -ForegroundColor Yellow
poetry run pytest tests/data/test_migration_provider.py -v
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED: G6 Tests" -ForegroundColor Red
    exit 1
}
Write-Host "✓ G6 passed" -ForegroundColor Green
Write-Host ""

# Step 4: Additional Checks (G7-G10)
Write-Host "Step 4: Running Additional Checks (G7-G10)..." -ForegroundColor Yellow

# G7: No float in financial paths
Write-Host "  G7: Float check in financial paths..." -ForegroundColor Cyan
$floatCheck = Select-String -Path "src/iatb/data/migration_provider.py" -Pattern "float" -Quiet
if ($floatCheck) {
    Write-Host "FAILED: G7 - Found float keyword" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G7 passed (no float in financial calculations)" -ForegroundColor Green

# G8: No naive datetime
Write-Host "  G8: Naive datetime check..." -ForegroundColor Cyan
$dtCheck = Select-String -Path "src/iatb/data/migration_provider.py" -Pattern "datetime.now\(\)" -Quiet
if ($dtCheck) {
    Write-Host "FAILED: G8 - Found naive datetime.now()" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G8 passed (no naive datetime)" -ForegroundColor Green

# G9: No print statements
Write-Host "  G9: Print statement check..." -ForegroundColor Cyan
$printCheck = Select-String -Path "src/iatb/data/migration_provider.py" -Pattern "print\(" -Quiet
if ($printCheck) {
    Write-Host "FAILED: G9 - Found print() statement" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ G9 passed (no print statements)" -ForegroundColor Green

# G10: Function size check
Write-Host "  G10: Function size check (≤50 LOC)..." -ForegroundColor Cyan
$content = Get-Content "src/iatb/data/migration_provider.py"
$inFunction = $false
$functionName = ""
$functionLines = 0
$maxLines = 0
$maxFunction = ""

foreach ($line in $content) {
    if ($line -match "^\s*def\s+(\w+)\(") {
        if ($inFunction -and $functionLines -gt 50) {
            Write-Host "FAILED: G10 - Function $functionName has $functionLines lines (>50)" -ForegroundColor Red
            exit 1
        }
        if ($functionLines -gt $maxLines) {
            $maxLines = $functionLines
            $maxFunction = $functionName
        }
        $functionName = $matches[1]
        $functionLines = 0
        $inFunction = $true
    } elseif ($inFunction) {
        if ($line -match "^\S") {
            # End of function
            if ($functionLines -gt 50) {
                Write-Host "FAILED: G10 - Function $functionName has $functionLines lines (>50)" -ForegroundColor Red
                exit 1
            }
            if ($functionLines -gt $maxLines) {
                $maxLines = $functionLines
                $maxFunction = $functionName
            }
            $inFunction = $false
            $functionLines = 0
        } else {
            $functionLines++
        }
    }
}

# Check last function
if ($inFunction -and $functionLines -gt 50) {
    Write-Host "FAILED: G10 - Function $functionName has $functionLines lines (>50)" -ForegroundColor Red
    exit 1
}

Write-Host "  ✓ G10 passed (max function: $maxFunction with $maxLines lines)" -ForegroundColor Green
Write-Host ""

# Step 5: Git Sync
Write-Host "Step 5: Git Sync..." -ForegroundColor Yellow

# Get current branch
$branch = git rev-parse --abbrev-ref HEAD
Write-Host "  Current branch: $branch" -ForegroundColor Cyan

# Check status
$status = git status --porcelain
if ($status) {
    Write-Host "  Changes detected:" -ForegroundColor Cyan
    Write-Host $status
    Write-Host ""
    
    # Stage changes
    Write-Host "  Staging changes..." -ForegroundColor Cyan
    git add .
    
    # Commit
    $commitMsg = "feat(data): implement Risk 4 migration regression mitigation

- Add MigrationProvider with dual-path support
- Implement feature flag for data_provider_default
- Add A/B testing comparison logic
- Config-based provider selection
- Safe fallback mechanisms
- Comprehensive test coverage"
    
    git commit -m $commitMsg
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: git commit" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ Committed changes" -ForegroundColor Green
} else {
    Write-Host "  No changes to commit" -ForegroundColor Yellow
}

# Get commit hash
$commitHash = git rev-parse HEAD
Write-Host "  Latest commit: $commitHash" -ForegroundColor Cyan

# Push (requires user confirmation)
Write-Host ""
Write-Host "Ready to push to origin/$branch" -ForegroundColor Yellow
$pushConfirm = Read-Host "Push to remote? (y/n)"
if ($pushConfirm -eq "y" -or $pushConfirm -eq "Y") {
    git push origin $branch
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: git push" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ Pushed to origin/$branch" -ForegroundColor Green
} else {
    Write-Host "  Skipped push (committed locally only)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== All Validation Gates Passed ===" -ForegroundColor Green
Write-Host ""
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  - G1-G5: Quality gates passed" -ForegroundColor Green
Write-Host "  - G6: Tests passed" -ForegroundColor Green
Write-Host "  - G7-G10: Additional checks passed" -ForegroundColor Green
Write-Host "  - Branch: $branch" -ForegroundColor Cyan
Write-Host "  - Commit: $commitHash" -ForegroundColor Cyan
Write-Host ""
Write-Host "Risk 4 mitigation implementation complete!" -ForegroundColor Green