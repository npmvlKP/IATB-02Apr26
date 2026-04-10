# IATB Streamlit Dashboard Launcher - Production Grade
# Launches Streamlit dashboard on port 8501 with proper error handling
# Win11 PowerShell compatible - ZERO assumptions

param(
    [string]$ConfigPath = ".\config\settings.toml",
    [int]$Port = 8501
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== IATB Streamlit Dashboard Launcher ===" -ForegroundColor Cyan
Write-Host "Configuration: $ConfigPath" -ForegroundColor Gray
Write-Host "Port: $Port" -ForegroundColor Gray
Write-Host ""

# Verify config file exists
if (-not (Test-Path $ConfigPath)) {
    Write-Host "ERROR: Configuration file not found: $ConfigPath" -ForegroundColor Red
    Write-Host "Please ensure config/settings.toml exists." -ForegroundColor Red
    exit 1
}

# Verify dashboard.py exists
$dashboardPath = "src\iatb\visualization\streamlit_app.py"
if (-not (Test-Path $dashboardPath)) {
    Write-Host "ERROR: Dashboard not found: $dashboardPath" -ForegroundColor Red
    exit 1
}

# Check if port is already in use
try {
    $portInUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($portInUse) {
        Write-Host "WARNING: Port $Port is already in use by process $($portInUse.OwningProcess)" -ForegroundColor Yellow
        Write-Host "Attempting to use it anyway, but may cause conflicts." -ForegroundColor Yellow
        Write-Host ""
    }
}
catch {
    # Get-NetTCPConnection may fail on some systems, ignore
}

# Set environment variables
$env:IATB_CONFIG_PATH = $ConfigPath
$env:IATB_MODE = "paper"
$env:LIVE_TRADING_ENABLED = "false"

Write-Host "Environment variables set:" -ForegroundColor Green
Write-Host "  IATB_CONFIG_PATH = $ConfigPath" -ForegroundColor Gray
Write-Host "  IATB_MODE = paper" -ForegroundColor Gray
Write-Host "  LIVE_TRADING_ENABLED = false" -ForegroundColor Gray
Write-Host ""

Write-Host "Starting Streamlit Dashboard..." -ForegroundColor Cyan
Write-Host "Dashboard will be available at: http://localhost:$Port" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Launch Streamlit dashboard with production settings
# --server.headless true: No browser auto-open (better for production)
# --server.port $Port: Explicit port
try {
    poetry run streamlit run $dashboardPath --server.port $Port --server.headless true
}
catch {
    Write-Host "FATAL: Dashboard crashed with error:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    exit 1
}