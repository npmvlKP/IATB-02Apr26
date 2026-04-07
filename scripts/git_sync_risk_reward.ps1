# Git sync script for risk stop_loss and rl reward enhancements
# This script commits and pushes changes to the remote repository

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Git Sync: Risk/Reward Enhancement" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check git status
Write-Host "Step 1: Checking git status..." -ForegroundColor Yellow
git status
Write-Host ""

# Step 2: Stage changes
Write-Host "Step 2: Staging changes..." -ForegroundColor Yellow
git add src/iatb/risk/stop_loss.py
git add src/iatb/rl/reward.py
git add tests/risk/test_stop_loss.py
git add tests/rl/test_reward.py
git add scripts/verify_risk_reward_enhancements.ps1
git add scripts/git_sync_risk_reward.ps1
Write-Host "  [OK] Changes staged" -ForegroundColor Green
Write-Host ""

# Step 3: Commit changes
Write-Host "Step 3: Committing changes..." -ForegroundColor Yellow
git commit -m "feat(risk): safe positive exit logic"
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Changes committed" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Commit failed" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 4: Get commit hash
Write-Host "Step 4: Getting commit hash..." -ForegroundColor Yellow
$commitHash = git rev-parse HEAD
Write-Host "  [OK] Commit hash: $commitHash" -ForegroundColor Green
Write-Host ""

# Step 5: Get current branch
Write-Host "Step 5: Getting current branch..." -ForegroundColor Yellow
$branch = git rev-parse --abbrev-ref HEAD
Write-Host "  [OK] Current branch: $branch" -ForegroundColor Green
Write-Host ""

# Step 6: Push to remote
Write-Host "Step 6: Pushing to remote..." -ForegroundColor Yellow
git push origin $branch
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Push successful" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Push failed" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 7: Final status
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Git Sync Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Summary:" -ForegroundColor Yellow
Write-Host "  Commit: $commitHash" -ForegroundColor White
Write-Host "  Branch: $branch" -ForegroundColor White
Write-Host "  Remote: origin" -ForegroundColor White
Write-Host "  Message: feat(risk): safe positive exit logic" -ForegroundColor White
Write-Host ""
Write-Host "Files changed:" -ForegroundColor Yellow
Write-Host "  - src/iatb/risk/stop_loss.py" -ForegroundColor White
Write-Host "  - src/iatb/rl/reward.py" -ForegroundColor White
Write-Host "  - tests/risk/test_stop_loss.py" -ForegroundColor White
Write-Host "  - tests/rl/test_reward.py" -ForegroundColor White
Write-Host "  - scripts/verify_risk_reward_enhancements.ps1" -ForegroundColor White
Write-Host "  - scripts/git_sync_risk_reward.ps1" -ForegroundColor White
Write-Host ""