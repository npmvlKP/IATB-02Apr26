# Zerodha Credential Setup - Stores API keys securely in OS keyring
# Usage: .\scripts\zerodha_login.ps1
# Prerequisites: Set ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_TOTP_SECRET in .env

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Write-Error ".env file not found. Copy .env.example to .env and fill in credentials."
    exit 1
}

Write-Host "Storing Zerodha credentials in OS keyring..." -ForegroundColor Cyan

poetry run python -c "
import keyring, os, sys
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv('ZERODHA_API_KEY', '')
api_secret = os.getenv('ZERODHA_API_SECRET', '')
totp_secret = os.getenv('ZERODHA_TOTP_SECRET', '')

missing = []
if not api_key:
    missing.append('ZERODHA_API_KEY')
if not api_secret:
    missing.append('ZERODHA_API_SECRET')
if not totp_secret:
    missing.append('ZERODHA_TOTP_SECRET')

if missing:
    print(f'ERROR: Missing required env vars: {', '.join(missing)}')
    print('Set them in .env and re-run this script.')
    sys.exit(1)

keyring.set_password('iatb', 'zerodha_api_key', api_key)
keyring.set_password('iatb', 'zerodha_api_secret', api_secret)
keyring.set_password('iatb', 'zerodha_totp_secret', totp_secret)
print('Zerodha credentials stored securely in OS keyring.')
"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to store credentials. Check .env file."
    exit 1
}

Write-Host "Done. You can now start the engine with .\scripts\engine_launcher.ps1" -ForegroundColor Green
