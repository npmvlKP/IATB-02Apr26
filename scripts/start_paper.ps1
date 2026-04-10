# IATB Paper Trading Engine Launcher - Production Grade
# Enforces LIVE_TRADING_ENABLED=false, structured logging, error handling, non-daemon
# Win11 PowerShell compatible - ZERO assumptions

param(
    [string]$ConfigPath = ".\config\settings.toml"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== IATB Paper Trading Engine Launcher ===" -ForegroundColor Cyan
Write-Host "Configuration: $ConfigPath" -ForegroundColor Gray
Write-Host ""

# Verify config file exists
if (-not (Test-Path $ConfigPath)) {
    Write-Host "ERROR: Configuration file not found: $ConfigPath" -ForegroundColor Red
    Write-Host "Please ensure config/settings.toml exists." -ForegroundColor Red
    exit 1
}

# Verify paper mode is enforced
$configContent = Get-Content $ConfigPath -Raw
if ($configContent -match "live_trading_enabled\s*=\s*true") {
    Write-Host "ERROR: live_trading_enabled is set to true in config!" -ForegroundColor Red
    Write-Host "Paper trading requires live_trading_enabled = false" -ForegroundColor Red
    exit 1
}

if ($configContent -notmatch "paper_trade_enforced\s*=\s*true") {
    Write-Host "WARNING: paper_trade_enforced is not set to true" -ForegroundColor Yellow
    Write-Host "Proceeding anyway, but verify configuration." -ForegroundColor Yellow
}

# Verify paper_runtime.py exists
$paperRuntimePath = "src\iatb\core\paper_runtime.py"
if (-not (Test-Path $paperRuntimePath)) {
    Write-Host "ERROR: Paper runtime not found: $paperRuntimePath" -ForegroundColor Red
    exit 1
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

Write-Host "Starting Paper Trading Engine..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop (graceful shutdown)" -ForegroundColor Yellow
Write-Host ""

# Launch paper trading engine with continuous scan loop
try {
    poetry run python -m iatb.core.paper_runtime
}
catch {
    Write-Host "FATAL: Paper trading engine crashed with error:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    exit 1
}
