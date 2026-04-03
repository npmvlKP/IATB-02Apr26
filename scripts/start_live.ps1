param(
    [switch]$Confirm,
    [string]$ConfigPath = ".\\config\\settings.toml"
)

if (-not $Confirm) {
    Write-Error "Live trading launch blocked. Re-run with --Confirm to proceed."
    exit 1
}

Write-Host "Starting IATB in LIVE mode..." -ForegroundColor Red
$env:IATB_MODE = "live"
poetry run python -m iatb.core.engine
