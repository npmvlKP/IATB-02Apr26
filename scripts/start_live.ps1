param(
    [switch]$Confirm,
    [string]$ConfigPath = ".\\config\\settings.toml"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $Confirm) {
    Write-Error "Live trading launch blocked. Re-run with --confirm to proceed."
    exit 1
}

$env:IATB_CONFIG_PATH = $ConfigPath
$env:IATB_MODE = "live"
$env:LIVE_TRADING_ENABLED = "true"

poetry run python -m iatb.core.runtime
