param(
    [Parameter(Mandatory = $true)]
    [string]$RegistryOwner,
    [Parameter(Mandatory = $true)]
    [string]$OracleHost,
    [Parameter(Mandatory = $true)]
    [string]$OracleUser,
    [string]$ImageName = "iatb-trading-engine",
    [string]$ImageTag = "latest",
    [string]$RemoteComposePath = "/opt/iatb/docker-compose.yml",
    [string]$SshKeyPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $env:GHCR_TOKEN) {
    throw "GHCR_TOKEN environment variable is required for registry authentication."
}

$image = "ghcr.io/$RegistryOwner/$ImageName:$ImageTag"
$sshTarget = "$OracleUser@$OracleHost"
$sshArgs = @()

if ($SshKeyPath) {
    $sshArgs = @("-i", $SshKeyPath)
}

docker build --file Dockerfile --tag $image .
$env:GHCR_TOKEN | docker login ghcr.io --username $RegistryOwner --password-stdin
docker push $image

$remoteCommand = @"
set -e
export IATB_IMAGE=$image
docker pull $image
docker compose -f $RemoteComposePath up -d --remove-orphans
docker image prune -f
"@

ssh @sshArgs $sshTarget $remoteCommand

Write-Output "Paper -> Live promotion protocol:"
Write-Output "1) Complete 30-day forward test in paper mode with Sharpe > 1.0."
Write-Output "2) Perform manual audit trail review before enabling live mode."
Write-Output "3) Run live at 10% position size for two weeks."
Write-Output "4) Scale position size only after validation period passes."
