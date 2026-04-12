#Requires -Version 5.1
<#
.SYNOPSIS
    Start all IATB services (API, Engine, Paper Runtime, Dashboard).
.DESCRIPTION
    Starts the IATB trading bot components in sequence:
    1. API server (FastAPI)
    2. Trading engine
    3. Paper trading runtime
    4. Dashboard (Streamlit)
.PARAMETER ApiPort
    Port for the FastAPI server (default: 8000).
.PARAMETER DashboardPort
    Port for the Streamlit dashboard (default: 8501).
.PARAMETER SkipDashboard
    Skip starting the dashboard component.
.PARAMETER SkipPaper
    Skip starting the paper trading runtime.
.EXAMPLE
    .\start_all.ps1 -ApiPort 8000 -DashboardPort 8501
#>

param(
    [int]$ApiPort = 8000,
    [int]$DashboardPort = 8501,
    [switch]$SkipDashboard,
    [switch]$SkipPaper
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

Write-Host "=== IATB Start All Services ===" -ForegroundColor Cyan
Write-Host "Root: $RootDir" -ForegroundColor Gray
Write-Host "API Port: $ApiPort" -ForegroundColor Gray
Write-Host "Dashboard Port: $DashboardPort" -ForegroundColor Gray

# Track started processes
$script:Processes = @()

function Stop-StartedProcesses {
    <# Clean up started processes on error #>
    foreach ($proc in $script:Processes) {
        if ($proc -and -not $proc.HasExited) {
            Write-Host "Stopping PID $($proc.Id)..." -ForegroundColor Yellow
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

trap {
    Write-Host "`n[ERROR] $_" -ForegroundColor Red
    Stop-StartedProcesses
    break
}

# Step 1: Verify dependencies
Write-Host "`n[Step 1] Verifying dependencies..." -ForegroundColor Green
$poetryCheck = Get-Command poetry -ErrorAction SilentlyContinue
if (-not $poetryCheck) {
    throw "poetry not found. Install from https://python-poetry.org/"
}

poetry install --no-interaction 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "poetry install failed"
}
Write-Host "[OK] Dependencies installed" -ForegroundColor Green

# Step 2: Start API server
Write-Host "`n[Step 2] Starting API server on port $ApiPort..." -ForegroundColor Green
$apiProc = Start-Process -FilePath "poetry" `
    -ArgumentList "run", "uvicorn", "iatb.fastapi_app:app", `
        "--host", "0.0.0.0", "--port", $ApiPort `
    -PassThru -NoNewWindow
$script:Processes += $apiProc
Start-Sleep -Seconds 3

# Verify API is reachable
$apiReachable = $false
for ($i = 0; $i -lt 5; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$ApiPort/health" `
            -TimeoutSec 5 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $apiReachable = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if ($apiReachable) {
    Write-Host "[OK] API server running (PID: $($apiProc.Id))" -ForegroundColor Green
} else {
    Write-Host "[WARN] API server may not be ready yet" -ForegroundColor Yellow
}

# Step 3: Start Paper Runtime (if not skipped)
if (-not $SkipPaper) {
    Write-Host "`n[Step 3] Starting paper trading runtime..." -ForegroundColor Green
    $paperProc = Start-Process -FilePath "poetry" `
        -ArgumentList "run", "python", "-m", "iatb.core.paper_runtime" `
        -PassThru -NoNewWindow
    $script:Processes += $paperProc
    Write-Host "[OK] Paper runtime started (PID: $($paperProc.Id))" -ForegroundColor Green
} else {
    Write-Host "`n[Step 3] Skipping paper runtime" -ForegroundColor Yellow
}

# Step 4: Start Dashboard (if not skipped)
if (-not $SkipDashboard) {
    Write-Host "`n[Step 4] Starting dashboard on port $DashboardPort..." -ForegroundColor Green
    $dashProc = Start-Process -FilePath "poetry" `
        -ArgumentList "run", "streamlit", "run", `
            "scripts/dashboard.py", `
            "--server.port", $DashboardPort, `
            "--server.headless", "true" `
        -PassThru -NoNewWindow
    $script:Processes += $dashProc
    Write-Host "[OK] Dashboard started (PID: $($dashProc.Id))" -ForegroundColor Green
} else {
    Write-Host "`n[Step 4] Skipping dashboard" -ForegroundColor Yellow
}

# Summary
Write-Host "`n=== IATB Services Started ===" -ForegroundColor Cyan
Write-Host "API:       http://localhost:$ApiPort" -ForegroundColor White
Write-Host "Health:    http://localhost:$ApiPort/health" -ForegroundColor White
Write-Host "Broker:    http://localhost:$ApiPort/broker/status" -ForegroundColor White
Write-Host "OHLCV:     http://localhost:$ApiPort/charts/ohlcv/RELIANCE" -ForegroundColor White
if (-not $SkipDashboard) {
    Write-Host "Dashboard: http://localhost:$DashboardPort" -ForegroundColor White
}
Write-Host ""
Write-Host "Process IDs: $($script:Processes | ForEach-Object { $_.Id } | Join-String ', ')" -ForegroundColor Gray
Write-Host "Press Ctrl+C to stop all services`n" -ForegroundColor Yellow

# Keep script running until Ctrl+C
try {
    while ($true) {
        # Check if any process has exited unexpectedly
        foreach ($proc in $script:Processes) {
            if ($proc.HasExited) {
                Write-Host "[WARN] Process $($proc.Id) has exited" -ForegroundColor Yellow
            }
        }
        Start-Sleep -Seconds 10
    }
} finally {
    Write-Host "`nStopping all services..." -ForegroundColor Yellow
    Stop-StartedProcesses
    Write-Host "All services stopped." -ForegroundColor Green
}