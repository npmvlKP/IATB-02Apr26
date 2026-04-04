param(
    [switch]$Confirm,
    [string]$ConfigPath = ".\\config\\settings.toml",
    [string]$BrokerEnvPath = ".\\.env",
    [string]$ZerodhaRequestToken = "",
    [string]$ZerodhaRedirectUrl = ""
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
$env:BROKER_OAUTH_2FA_VERIFIED = "false"

$brokerArgs = @("run", "python", ".\\scripts\\zerodha_connect.py", "--env-file", $BrokerEnvPath, "--save-access-token")
if ($ZerodhaRequestToken) {
    $brokerArgs += @("--request-token", $ZerodhaRequestToken)
}
if ($ZerodhaRedirectUrl) {
    $brokerArgs += @("--redirect-url", $ZerodhaRedirectUrl)
}
& poetry @brokerArgs
if ($LASTEXITCODE -eq 2) {
    Write-Error "Broker login required. Re-run with --ZerodhaRedirectUrl after successful manual login."
    exit 1
}
if ($LASTEXITCODE -ne 0) {
    Write-Error "Broker validation failed. Live runtime launch blocked."
    exit $LASTEXITCODE
}
$env:BROKER_OAUTH_2FA_VERIFIED = "true"

poetry run python -m iatb.core.runtime
