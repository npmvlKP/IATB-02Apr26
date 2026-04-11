#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Zerodha login automation with TOTP generation.

.DESCRIPTION
    Automates Zerodha OAuth login flow:
    1. Generates TOTP code using pyotp
    2. Opens Zerodha login URL in browser
    3. Prompts user to paste redirect URL
    4. Extracts request_token from URL
    5. Exchanges for access_token
    6. Stores access_token in keyring

.PARAMETER ApiKey
    Zerodha API key (reads from env ZERODHA_API_KEY if not provided)

.PARAMETER ApiSecret
    Zerodha API secret (reads from env ZERODHA_API_SECRET if not provided)

.PARAMETER TotpSecret
    TOTP secret for 2FA (reads from env ZERODHA_TOTP_SECRET if not provided)

.EXAMPLE
    .\scripts\zerodha_login.ps1

.EXAMPLE
    .\scripts\zerodha_login.ps1 -ApiKey "xyz" -ApiSecret "abc" -TotpSecret "JBSWY3DPEHPK3PXP"
#>

param(
    [string]$ApiKey,
    [string]$ApiSecret,
    [string]$TotpSecret
)

$ErrorActionPreference = "Stop"

# Helper function to get environment variable
function Get-EnvVar {
    param([string]$Name)
    $value = [System.Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrEmpty($value)) {
        Write-Error "Environment variable $Name not set"
        exit 1
    }
    return $value
}

# Get credentials from parameters or environment
if ([string]::IsNullOrEmpty($ApiKey)) {
    $ApiKey = Get-EnvVar -Name "ZERODHA_API_KEY"
}
if ([string]::IsNullOrEmpty($ApiSecret)) {
    $ApiSecret = Get-EnvVar -Name "ZERODHA_API_SECRET"
}
if ([string]::IsNullOrEmpty($TotpSecret)) {
    $TotpSecret = Get-EnvVar -Name "ZERODHA_TOTP_SECRET"
}

Write-Host "=== Zerodha Login Automation ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Generate TOTP
Write-Host "[1/6] Generating TOTP code..." -ForegroundColor Yellow
try {
    $totpResult = poetry run python -c "import pyotp; print(pyotp.TOTP('$TotpSecret').now())" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to generate TOTP: $totpResult"
        exit 1
    }
    $totpCode = $totpResult.Trim()
    Write-Host "  TOTP Code: $totpCode" -ForegroundColor Green
    Write-Host "  (Use this code when prompted in Zerodha login)" -ForegroundColor Gray
    Write-Host ""
}
catch {
    Write-Error "Failed to generate TOTP: $_"
    exit 1
}

# Step 2: Generate login URL
Write-Host "[2/6] Generating login URL..." -ForegroundColor Yellow
$loginUrl = "https://kite.zerodha.com/connect/login?v=3&api_key=$ApiKey"
Write-Host "  Login URL: $loginUrl" -ForegroundColor Green
Write-Host ""

# Step 3: Open browser
Write-Host "[3/6] Opening browser..." -ForegroundColor Yellow
try {
    Start-Process $loginUrl
    Write-Host "  Browser opened. Please complete the login in the browser." -ForegroundColor Green
    Write-Host ""
}
catch {
    Write-Error "Failed to open browser: $_"
    exit 1
}

# Step 4: Prompt for redirect URL
Write-Host "[4/6] Waiting for redirect URL..." -ForegroundColor Yellow
Write-Host "  After completing login, you will be redirected to a URL."
Write-Host "  Copy the entire redirect URL and paste it below."
Write-Host ""
$redirectUrl = Read-Host "  Enter redirect URL"

if ([string]::IsNullOrEmpty($redirectUrl)) {
    Write-Error "Redirect URL is required"
    exit 1
}

# Step 5: Extract request_token
Write-Host "[5/6] Extracting request_token..." -ForegroundColor Yellow
try {
    $extractResult = poetry run python -c "
from urllib.parse import urlparse, parse_qs
import sys
url = '$redirectUrl'
parsed = urlparse(url)
params = parse_qs(parsed.query)
if 'request_token' in params:
    print(params['request_token'][0])
else:
    print('ERROR: No request_token found in URL', file=sys.stderr)
    sys.exit(1)
" 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to extract request_token: $extractResult"
        exit 1
    }

    $requestToken = $extractResult.Trim()
    Write-Host "  Request Token: $requestToken" -ForegroundColor Green
    Write-Host ""
}
catch {
    Write-Error "Failed to extract request_token: $_"
    exit 1
}

# Step 6: Exchange for access_token and store
Write-Host "[6/6] Exchanging for access_token and storing..." -ForegroundColor Yellow
try {
    $exchangeResult = poetry run python -c "
import sys
sys.path.insert(0, 'src')
from iatb.broker.token_manager import ZerodhaTokenManager
manager = ZerodhaTokenManager(
    api_key='$ApiKey',
    api_secret='$ApiSecret',
    totp_secret='$TotpSecret'
)
access_token = manager.exchange_request_token('$requestToken')
manager.store_access_token(access_token)
print('SUCCESS: Access token stored successfully')
print(f'Access Token: {access_token}')
" 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to exchange request_token: $exchangeResult"
        exit 1
    }

    Write-Host "  Access token exchanged and stored successfully!" -ForegroundColor Green
    Write-Host ""
}
catch {
    Write-Error "Failed to exchange request_token: $_"
    exit 1
}

# Success
Write-Host "=== Login Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Your Zerodha session is now active." -ForegroundColor Cyan
Write-Host "The access token will be valid until 6 AM IST tomorrow." -ForegroundColor Gray
Write-Host ""
Write-Host "To verify, run:" -ForegroundColor Yellow
Write-Host "  poetry run python -c \`"from iatb.broker.token_manager import ZerodhaTokenManager; print(ZerodhaTokenManager(api_key='$ApiKey', api_secret='$ApiSecret').is_token_fresh())\`"" -ForegroundColor Gray
