param(
    [string]$ConfigPath = ".\\config\\settings.toml"
)

Write-Host "Starting IATB in PAPER mode..." -ForegroundColor Cyan
$env:IATB_MODE = "paper"
poetry run python -m iatb.core.engine
