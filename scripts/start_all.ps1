# IATB Master Startup Script - Sequential orchestration
# Usage: .\scripts\start_all.ps1
# Prerequisites: poetry installed, .env configured, zerodha_login.ps1 run at least once
#
# Sequence:
#   1. Token refresh (zerodha_login.ps1)
#   2. Start engine on port 8000 (background job)
#   3. Poll /health up to 10 retries with 2s wait
#   4. Start deployment dashboard on port 8080 (background job)
#   5. Display PIDs

$ErrorActionPreference = "Stop"

Write-Host "=== IATB Master Startup ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Token refresh
Write-Host "[1/5] Refreshing Zerodha tokens..." -ForegroundColor Yellow
try {
    & .\scripts\zerodha_login.ps1
} catch {
    Write-Host "WARNING: Token refresh failed (may already be valid): $_" -ForegroundColor Yellow
}
Write-Host ""

# Step 2: Start engine on port 8000
Write-Host "[2/5] Starting engine API on port 8000..." -ForegroundColor Yellow
$engineJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    poetry run uvicorn src.iatb.api:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info 2>&1
}
$enginePid = $engineJob.Id
Write-Host "  Engine job started (Job ID: $enginePid)" -ForegroundColor Green
Write-Host ""

# Step 3: Poll /health up to 10 retries
Write-Host "[3/5] Waiting for engine /health endpoint..." -ForegroundColor Yellow
$engineReady = $false
for ($i = 1; $i -le 10; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "  Engine healthy after $i attempt(s)" -ForegroundColor Green
            $engineReady = $true
            break
        }
    } catch {
        Write-Host "  Attempt $i/10 - engine not ready, waiting 2s..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 2
    }
}

if (-not $engineReady) {
    Write-Host "ERROR: Engine failed to start within 20s" -ForegroundColor Red
    Write-Host "Check engine job output:" -ForegroundColor Red
    Receive-Job -Job $engineJob 2>&1 | Select-Object -Last 20
    Stop-Job -Job $engineJob
    Remove-Job -Job $engineJob
    exit 1
}
Write-Host ""

# Step 4: Start deployment dashboard on port 8080
Write-Host "[4/5] Starting deployment dashboard on port 8080..." -ForegroundColor Yellow
$dashJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    poetry run uvicorn src.iatb.deployment_dashboard:app --host 127.0.0.1 --port 8080 --workers 1 --log-level info 2>&1
}
$dashPid = $dashJob.Id
Write-Host "  Dashboard job started (Job ID: $dashPid)" -ForegroundColor Green
Write-Host ""

# Step 5: Display PIDs and URLs
Write-Host "[5/5] Startup complete" -ForegroundColor Green
Write-Host ""
Write-Host "=== Running Services ===" -ForegroundColor Cyan
Write-Host "  Engine API:     http://127.0.0.1:8000  (Job ID: $enginePid)" -ForegroundColor White
Write-Host "  Dashboard:      http://127.0.0.1:8080  (Job ID: $dashPid)" -ForegroundColor White
Write-Host ""
Write-Host "To stop all services:" -ForegroundColor Yellow
Write-Host "  Stop-Job -Job $enginePid, $dashPid; Remove-Job -Job $enginePid, $dashPid" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop monitoring (jobs continue in background)" -ForegroundColor DarkGray

try {
    while ($true) {
        Receive-Job -Job $engineJob -ErrorAction SilentlyContinue | Select-Object -Last 1
        Receive-Job -Job $dashJob -ErrorAction SilentlyContinue | Select-Object -Last 1
        Start-Sleep -Seconds 10
    }
} catch {
    # User pressed Ctrl+C
}

Write-Host ""
Write-Host "Stopping background jobs..." -ForegroundColor Yellow
Stop-Job -Job $engineJob, $dashJob -ErrorAction SilentlyContinue
Remove-Job -Job $engineJob, $dashJob -ErrorAction SilentlyContinue
Write-Host "Done." -ForegroundColor Green
