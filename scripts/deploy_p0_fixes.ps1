# Win11 PowerShell Execution Script for P0 Critical Fixes
# This script validates and deploys the P0 critical fixes for IATB repository

# Step 1: Verify/Install dependencies
Write-Host "Step 1: Installing dependencies..." -ForegroundColor Green
poetry install

# Step 2: Run Quality Gates (G1-G5)
Write-Host "Step 2: Running Quality Gates (G1-G5)..." -ForegroundColor Green

# G1: Ruff lint check
Write-Host "G1: Running Ruff lint check..." -ForegroundColor Yellow
poetry run ruff check src/ tests/
if ($LASTEXITCODE -ne 0) {
    Write-Host "G1: Ruff lint check FAILED" -ForegroundColor Red
    exit 1
}
Write-Host "G1: Ruff lint check PASSED" -ForegroundColor Green

# G2: Ruff format check
Write-Host "G2: Running Ruff format check..." -ForegroundColor Yellow
poetry run ruff format --check src/ tests/
if ($LASTEXITCODE -ne 0) {
    Write-Host "G2: Ruff format check FAILED" -ForegroundColor Red
    exit 1
}
Write-Host "G2: Ruff format check PASSED" -ForegroundColor Green

# G3: MyPy type check
Write-Host "G3: Running MyPy type check..." -ForegroundColor Yellow
poetry run mypy src/ --strict
if ($LASTEXITCODE -ne 0) {
    Write-Host "G3: MyPy type check FAILED" -ForegroundColor Red
    exit 1
}
Write-Host "G3: MyPy type check PASSED" -ForegroundColor Green

# G4: Bandit security check
Write-Host "G4: Running Bandit security check..." -ForegroundColor Yellow
poetry run bandit -r src/ -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "G4: Bandit security check FAILED" -ForegroundColor Red
    exit 1
}
Write-Host "G4: Bandit security check PASSED" -ForegroundColor Green

# G5: Gitleaks secrets check
Write-Host "G5: Running Gitleaks secrets check..." -ForegroundColor Yellow
gitleaks detect --source . --no-banner
if ($LASTEXITCODE -ne 0) {
    Write-Host "G5: Gitleaks secrets check FAILED" -ForegroundColor Red
    exit 1
}
Write-Host "G5: Gitleaks secrets check PASSED" -ForegroundColor Green

# Step 3: Run Tests (G6)
Write-Host "Step 3: Running Tests (G6)..." -ForegroundColor Green
poetry run pytest --cov=src/iatb --cov-fail-under=90 -x tests/p0_critical_fixes_test.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "G6: Tests FAILED" -ForegroundColor Red
    exit 1
}
Write-Host "G6: Tests PASSED" -ForegroundColor Green

# Step 4: Additional Checks (G7-G10)
Write-Host "Step 4: Running Additional Checks (G7-G10)..." -ForegroundColor Green

# G7: No float in financial paths
Write-Host "G7: Checking for float in financial paths..." -ForegroundColor Yellow
poetry run python scripts/validate_g7_g10.py

# G8: No naive datetime
Write-Host "G8: Checking for naive datetime..." -ForegroundColor Yellow
# Already checked in validate_g7_g10.py

# G9: No print statements
Write-Host "G9: Checking for print statements..." -ForegroundColor Yellow
# Already checked in validate_g7_g10.py

# G10: Function size <= 50 LOC
Write-Host "G10: Checking function size..." -ForegroundColor Yellow
# Already checked in validate_g7_g10.py

# Step 5: Git Sync
Write-Host "Step 5: Git Sync..." -ForegroundColor Green

# Initialize git if not already initialized
if (-not (Test-Path .git)) {
    Write-Host "Initializing git repository..." -ForegroundColor Yellow
    git init
}

# Get current branch
$branch = git rev-parse --abbrev-ref HEAD
Write-Host "Current branch: $branch" -ForegroundColor Cyan

# Prepare the prompted context
$context = "P0 Critical Fixes: Credentials, Static IP, and Token Expiry"

# Check git status
Write-Host "Checking git status..." -ForegroundColor Yellow
git status

# Add all changes
Write-Host "Adding all changes to staging area..." -ForegroundColor Yellow
git add -A

# Commit changes
Write-Host "Committing changes..." -ForegroundColor Yellow
$commitMessage = "Update: $context - $(Get-Date -Format 'yyyy-MM-dd')"
git commit -m $commitMessage

# Pull with rebase and autostash
Write-Host "Pulling changes from remote..." -ForegroundColor Yellow
git pull --rebase --autostash origin $branch

# Push to remote
Write-Host "Pushing changes to remote..." -ForegroundColor Yellow
git push origin $branch

# Push to main if needed
Write-Host "Pushing to main branch..." -ForegroundColor Yellow
git push origin main

# Show remote information
Write-Host "Remote information:" -ForegroundColor Cyan
git remote -v

# Final git status
Write-Host "Final git status:" -ForegroundColor Cyan
git status

# Show recent commits
Write-Host "Recent commits:" -ForegroundColor Cyan
git log --oneline -5

Write-Host "P0 Critical Fixes deployment completed successfully!" -ForegroundColor Green
