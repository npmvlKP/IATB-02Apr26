# Zerodha OAuth Login - Generates access_token via browser-based flow
# Usage: .\scripts\zerodha_login.ps1
# Prerequisites: Set ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_TOTP_SECRET in .env
# Flow: Generate TOTP -> Open browser -> User logs in -> Paste redirect URL -> Exchange token

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Write-Error ".env file not found. Copy .env.example to .env and fill in credentials."
    exit 1
}

Write-Host "Zerodha OAuth Login Flow" -ForegroundColor Cyan
Write-Host "========================" -ForegroundColor Cyan

# Step 1: Store static credentials in keyring
Write-Host "`n[1/5] Storing credentials in OS keyring..." -ForegroundColor Yellow

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
print('Credentials stored successfully.')
"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to store credentials. Check .env file."
    exit 1
}

Write-Host "Credentials stored." -ForegroundColor Green

# Step 2: Generate TOTP
Write-Host "`n[2/5] Generating TOTP code..." -ForegroundColor Yellow

$totp = poetry run python -c "
import keyring
from iatb.broker.token_manager import ZerodhaTokenManager
tm = ZerodhaTokenManager()
print(tm.generate_totp())
"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to generate TOTP. Ensure credentials are stored."
    exit 1
}

Write-Host "Your TOTP code: $totp" -ForegroundColor Cyan
Write-Host "This code expires in 30 seconds." -ForegroundColor Yellow

# Step 3: Get login URL and open browser
Write-Host "`n[3/5] Opening Zerodha login page..." -ForegroundColor Yellow

$loginUrl = poetry run python -c "
from iatb.broker.token_manager import ZerodhaTokenManager
tm = ZerodhaTokenManager()
print(tm.get_login_url())
"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to get login URL."
    exit 1
}

Write-Host "Login URL: $loginUrl" -ForegroundColor Cyan
Start-Process $loginUrl

# Step 4: Prompt for redirect URL
Write-Host "`n[4/5] Complete login in browser and paste redirect URL below." -ForegroundColor Yellow
Write-Host "The redirect URL will look like: http://localhost:5000/callback?request_token=YOUR_TOKEN&status=success" -ForegroundColor Gray
Write-Host ""

$redirectUrl = Read-Host "Paste the redirect URL here"

if ([string]::IsNullOrWhiteSpace($redirectUrl)) {
    Write-Error "Redirect URL cannot be empty."
    exit 1
}

# Extract request_token from URL
if ($redirectUrl -match "request_token=([^&]+)") {
    $requestToken = $matches[1]
    Write-Host "Extracted request_token: $requestToken" -ForegroundColor Green
} else {
    Write-Error "Could not find 'request_token' in the URL. Please paste the complete redirect URL."
    exit 1
}

# Step 5: Exchange request_token for access_token and store
Write-Host "`n[5/5] Exchanging request_token for access_token..." -ForegroundColor Yellow

poetry run python -c "
import sys
from iatb.broker.token_manager import ZerodhaTokenManager
tm = ZerodhaTokenManager()
try:
    access_token = tm.exchange_request_token('$requestToken')
    tm.store_access_token(access_token)
    print(f'Access token obtained and stored successfully.')
    print(f'Token expires at 6:00 AM IST tomorrow.')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to exchange request_token. Check error messages above."
    exit 1
}

Write-Host "`n" -NoNewline
Write-Host "========================================" -ForegroundColor Green
Write-Host "Login successful!" -ForegroundColor Green
Write-Host "Access token stored in keyring." -ForegroundColor Green
Write-Host "Valid until 6:00 AM IST tomorrow." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
