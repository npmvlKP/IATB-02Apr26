# IATB Project Setup Script
# This script initializes the IATB project with all required dependencies and configurations

Write-Host "=== IATB Project Setup ===" -ForegroundColor Cyan
Write-Host ""

# Check if Poetry is installed
Write-Host "Checking Poetry installation..." -ForegroundColor Yellow
if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Poetry is not installed. Please install Poetry first." -ForegroundColor Red
    Write-Host "Visit: https://python-poetry.org/docs/#installation" -ForegroundColor Cyan
    exit 1
}
Write-Host "Poetry is installed: $(poetry --version)" -ForegroundColor Green
Write-Host ""

# Install dependencies
Write-Host "Installing project dependencies..." -ForegroundColor Yellow
poetry install --with dev
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "Dependencies installed successfully" -ForegroundColor Green
Write-Host ""

# Create project structure
Write-Host "Creating project structure..." -ForegroundColor Yellow
$directories = @("src/iatb", "tests")
foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Created: $dir" -ForegroundColor Green
    }
}

# Create __init__.py files
if (-not (Test-Path "src/iatb/__init__.py")) {
    New-Item -ItemType File -Path "src/iatb/__init__.py" -Force | Out-Null
    Write-Host "Created: src/iatb/__init__.py" -ForegroundColor Green
}
if (-not (Test-Path "tests/__init__.py")) {
    New-Item -ItemType File -Path "tests/__init__.py" -Force | Out-Null
    Write-Host "Created: tests/__init__.py" -ForegroundColor Green
}
Write-Host ""

# Install pre-commit hooks
Write-Host "Installing pre-commit hooks..." -ForegroundColor Yellow
poetry run pre-commit install
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Failed to install pre-commit hooks" -ForegroundColor Yellow
} else {
    Write-Host "Pre-commit hooks installed successfully" -ForegroundColor Green
}
Write-Host ""

# Create .env file from .env.example if it doesn't exist
if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Write-Host "Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "Created: .env" -ForegroundColor Green
    Write-Host "Please update .env with your actual API keys" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Update .env with your broker API keys" -ForegroundColor White
Write-Host "2. Run '.\scripts\quality_gate.ps1' to verify setup" -ForegroundColor White
Write-Host "3. Run '.\scripts\git_sync.ps1' to initialize Git and GitHub" -ForegroundColor White
Write-Host ""