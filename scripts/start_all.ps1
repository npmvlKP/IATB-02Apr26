# IATB Master Startup Script - Sequential orchestration
# Usage: .\scripts\start_all.ps1
# Prerequisites: poetry installed, .env configured with ZERODHA_API_KEY/SECRET/TOTP_SECRET
#
# Sequence:
#   1. Store static Zerodha credentials to OS keyring
#   2. OAuth login via zerodha_connect.py (browser → request_token → access_token)
#   3. Sync access_token from .env to keyring (api.py reads from keyring)
#   4. Start engine on port 8000 (background job)
#   5. Poll /health up to 10 retries with 2s wait
#   6. Start deployment dashboard on port 8080 (background job)
#   7. Display PIDs

$ErrorActionPreference = "Stop"

Write-Host "=== IATB Master Startup ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Store static credentials in keyring
Write-Host "[1/7] Storing static Zerodha credentials in keyring..." -ForegroundColor Yellow
try {
    & .\scripts\zerodha_login.ps1
} catch {
    Write-Host "WARNING: Static credential storage failed: $_" -ForegroundColor Yellow
}
Write-Host ""

# Step 2: OAuth login flow - obtains access_token via browser login
Write-Host "[2/7] Running Zerodha OAuth login (opens browser)..." -ForegroundColor Yellow
Write-Host "  This will open your browser for Zerodha login + 2FA." -ForegroundColor DarkGray
Write-Host "  Complete login to generate access_token for today." -ForegroundColor DarkGray

$oauthResult = $null
try {
    $oauthResult = poetry run python scripts/zerodha_connect.py --save-access-token 2>&1
    $oauthOutput = $oauthResult | Out-String
    Write-Host $oauthOutput

    if ($LASTEXITCODE -eq 2) {
        Write-Host "WARNING: OAuth login required but browser flow incomplete." -ForegroundColor Yellow
        Write-Host "  The engine will start with limited broker functionality." -ForegroundColor Yellow
    } elseif ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
        Write-Host "WARNING: OAuth login failed (exit code $LASTEXITCODE)." -ForegroundColor Yellow
        Write-Host "  Engine will start but broker endpoints may return 401/503." -ForegroundColor Yellow
    }
} catch {
    Write-Host "WARNING: OAuth login failed: $_" -ForegroundColor Yellow
    Write-Host "  Engine will start with limited broker functionality." -ForegroundColor Yellow
}
Write-Host ""

# Step 3: Sync access_token from .env to keyring (api.py reads from keyring)
Write-Host "[3/7] Syncing access_token to OS keyring..." -ForegroundColor Yellow
poetry run python -c "
import keyring, os, sys
from dotenv import load_dotenv
load_dotenv()

access_token = os.getenv('ZERODHA_ACCESS_TOKEN', '').strip()
if access_token:
    keyring.set_password('iatb', 'zerodha_access_token', access_token)
    print('access_token synced to keyring.')
else:
    print('No access_token found in .env - broker endpoints will be limited.')
    sys.exit(0)
"

if ($LASTEXITCODE -eq 0) {
    Write-Host "  Keyring sync complete." -ForegroundColor Green
} else {
    Write-Host "  WARNING: Keyring sync failed." -ForegroundColor Yellow
}
Write-Host ""

# Step 4: Start engine on port 8000
Write-Host "[4/7] Starting engine API on port 8000..." -ForegroundColor Yellow
$engineJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    poetry run uvicorn src.iatb.api:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info 2>&1
}
$enginePid = $engineJob.Id
Write-Host "  Engine job started (Job ID: $enginePid)" -ForegroundColor Green
Write-Host ""

# Step 5: Poll /health up to 10 retries
Write-Host "[5/7] Waiting for engine /health endpoint..." -ForegroundColor Yellow
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

# Step 6: Start deployment dashboard on port 8080
Write-Host "[6/7] Starting deployment dashboard on port 8080..." -ForegroundColor Yellow
$dashJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    poetry run uvicorn src.iatb.deployment_dashboard:app --host 127.0.0.1 --port 8080 --workers 1 --log-level info 2>&1
}
$dashPid = $dashJob.Id
Write-Host "  Dashboard job started (Job ID: $dashPid)" -ForegroundColor Green
Write-Host ""

# Step 7: Display PIDs and URLs
Write-Host "[7/7] Startup complete" -ForegroundColor Green
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