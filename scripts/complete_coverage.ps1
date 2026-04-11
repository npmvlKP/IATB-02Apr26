# PowerShell script to complete test coverage to 90%
# Run this to add remaining tests for instrument_scanner, drl_signal, and order_manager

Write-Host "=== IATB Coverage Completion Script ===" -ForegroundColor Cyan
Write-Host "Current coverage: 88.81%" -ForegroundColor Yellow
Write-Host "Target coverage: 90%" -ForegroundColor Green
Write-Host ""

Write-Host "Steps to complete:" -ForegroundColor White
Write-Host "1. Create tests for src/iatb/scanner/instrument_scanner.py (54.08% → 90%)" -ForegroundColor Yellow
Write-Host "2. Create tests for src/iatb/selection/drl_signal.py (60.40% → 90%)" -ForegroundColor Yellow
Write-Host "3. Create tests for src/iatb/execution/order_manager.py (72.73% → 90%)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Example command to run after adding tests:" -ForegroundColor Green
Write-Host "poetry run pytest --cov=src/iatb --cov-fail-under=90 -x" -ForegroundColor Cyan
Write-Host ""

Write-Host "Uncovered lines per module:" -ForegroundColor White
Write-Host "- instrument_scanner.py: Lines 152-163, 168-174, 179-194, 199-206, 211-215, 252-254, 261-263, 265-266, 305-378, 382-421, 425-437, 441, 453-467, 471-482, 487-492, 520, 589-590" -ForegroundColor Yellow
Write-Host "- drl_signal.py: Lines 113-114, 116-117, 119-120, 128-129, 131-132, 143-154, 168-170, 175-177, 182-193" -ForegroundColor Yellow
Write-Host "- order_manager.py: Lines 38-39, 61-63, 90-91, 95-98, 102-104, 114-120, 130, 137, 146->150, 148->147" -ForegroundColor Yellow
Write-Host ""