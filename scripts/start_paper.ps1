param(
    [string]$ConfigPath = ".\\config\\settings.toml"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$env:IATB_CONFIG_PATH = $ConfigPath
$env:IATB_MODE = "paper"
$env:LIVE_TRADING_ENABLED = "false"

poetry run python -m iatb.core.runtime
