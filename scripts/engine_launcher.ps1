# IATB Engine Launcher - Starts the FastAPI backend on port 8000
# Usage: .\scripts\engine_launcher.ps1

$ErrorActionPreference = "Stop"

Write-Host "Starting IATB Engine API on http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor DarkGray

poetry run uvicorn src.iatb.api:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info
