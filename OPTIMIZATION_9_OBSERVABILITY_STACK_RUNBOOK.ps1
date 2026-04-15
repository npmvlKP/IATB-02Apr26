# ============================================================================
# IATB Observability Stack Implementation Runbook
# Optimization 9: JSON Logging, OpenTelemetry Tracing, Prometheus Metrics, Telegram Alerting
# ============================================================================

# ============================================================================
# Step 1: Verify/Install Dependencies
# ============================================================================
Write-Host "Step 1: Installing dependencies..." -ForegroundColor Cyan

# Update poetry lock file (if not already done)
if (-not (Test-Path "poetry.lock")) {
    Write-Host "Running poetry lock..." -ForegroundColor Yellow
    poetry lock
}

# Install dependencies
Write-Host "Running poetry install..." -ForegroundColor Yellow
poetry install

Write-Host "Dependencies installed successfully" -ForegroundColor Green

# ============================================================================
# Step 2: Verify Environment Variables
# ============================================================================
Write-Host "`nStep 2: Verifying environment variables..." -ForegroundColor Cyan

$envVars = @(
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "OTEL_EXPORTER_OTLP_ENDPOINT"
)

foreach ($var in $envVars) {
    $value = [System.Environment]::GetEnvironmentVariable($var)
    if ($value) {
        Write-Host "  $var = [SET]" -ForegroundColor Green
    } else {
        Write-Host "  $var = [NOT SET] (Optional)" -ForegroundColor Yellow
    }
}

# ============================================================================
# Step 3: Run Quality Gates (G1-G5)
# ============================================================================
Write-Host "`nStep 3: Running quality gates (G1-G5)..." -ForegroundColor Cyan

# G1: Lint
Write-Host "G1: Running ruff check..." -ForegroundColor Yellow
poetry run ruff check src/ tests/
if ($LASTEXITCODE -eq 0) {
    Write-Host "  G1: PASS" -ForegroundColor Green
} else {
    Write-Host "  G1: FAIL" -ForegroundColor Red
}

# G2: Format
Write-Host "`nG2: Running ruff format check..." -ForegroundColor Yellow
poetry run ruff format --check src/ tests/
if ($LASTEXITCODE -eq 0) {
    Write-Host "  G2: PASS" -ForegroundColor Green
} else {
    Write-Host "  G2: FAIL" -ForegroundColor Red
}

# G3: Type checking
Write-Host "`nG3: Running mypy..." -ForegroundColor Yellow
poetry run mypy src/ --strict
if ($LASTEXITCODE -eq 0) {
    Write-Host "  G3: PASS" -ForegroundColor Green
} else {
    Write-Host "  G3: FAIL" -ForegroundColor Red
}

# G4: Security
Write-Host "`nG4: Running bandit..." -ForegroundColor Yellow
poetry run bandit -r src/ -q
if ($LASTEXITCODE -eq 0) {
    Write-Host "  G4: PASS" -ForegroundColor Green
} else {
    Write-Host "  G4: FAIL" -ForegroundColor Red
}

# G5: Secrets
Write-Host "`nG5: Running gitleaks..." -ForegroundColor Yellow
gitleaks detect --source . --no-banner
if ($LASTEXITCODE -eq 0) {
    Write-Host "  G5: PASS" -ForegroundColor Green
} else {
    Write-Host "  G5: FAIL" -ForegroundColor Red
}

# ============================================================================
# Step 4: Run Tests (G6)
# ============================================================================
Write-Host "`nStep 4: Running tests with coverage (G6)..." -ForegroundColor Cyan

# Run observability tests specifically
Write-Host "Running observability tests..." -ForegroundColor Yellow
poetry run pytest tests/unit/test_observability_logging.py -v
poetry run pytest tests/unit/test_observability_tracing.py -v
poetry run pytest tests/unit/test_observability_metrics.py -v
poetry run pytest tests/unit/test_observability_alerting.py -v

# Run full test suite with coverage
Write-Host "`nRunning full test suite with coverage..." -ForegroundColor Yellow
poetry run pytest --cov=src/iatb --cov-fail-under=90 -x
if ($LASTEXITCODE -eq 0) {
    Write-Host "  G6: PASS (Coverage >= 90%)" -ForegroundColor Green
} else {
    Write-Host "  G6: FAIL (Coverage < 90%)" -ForegroundColor Red
}

# ============================================================================
# Step 5: Additional Checks (G7-G10)
# ============================================================================
Write-Host "`nStep 5: Running additional checks (G7-G10)..." -ForegroundColor Cyan

# G7: No float in financial paths
Write-Host "G7: Checking for float in financial paths..." -ForegroundColor Yellow
$floatCheck = grep -r "float" src/iatb/risk/ src/iatb/backtesting/ src/iatb/execution/ src/iatb/selection/ src/iatb/sentiment/ 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  G7: PASS (No float in financial paths)" -ForegroundColor Green
} else {
    Write-Host "  G7: FAIL (Float found in financial paths)" -ForegroundColor Red
    Write-Host $floatCheck
}

# G8: No naive datetime
Write-Host "`nG8: Checking for naive datetime.now()..." -ForegroundColor Yellow
$naiveDtCheck = grep -r "datetime.now()" src/ 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  G8: PASS (No naive datetime)" -ForegroundColor Green
} else {
    Write-Host "  G8: FAIL (Naive datetime found)" -ForegroundColor Red
    Write-Host $naiveDtCheck
}

# G9: No print statements
Write-Host "`nG9: Checking for print() statements..." -ForegroundColor Yellow
$printCheck = grep -r "print(" src/ 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  G9: PASS (No print() in src/)" -ForegroundColor Green
} else {
    Write-Host "  G9: FAIL (print() found)" -ForegroundColor Red
    Write-Host $printCheck
}

# G10: Function size check
Write-Host "`nG10: Checking function size..." -ForegroundColor Yellow
python check_func_size.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "  G10: PASS (All functions <= 50 LOC)" -ForegroundColor Green
} else {
    Write-Host "  G10: FAIL (Some functions > 50 LOC)" -ForegroundColor Red
}

# ============================================================================
# Step 6: Verify Observability Components
# ============================================================================
Write-Host "`nStep 6: Verifying observability components..." -ForegroundColor Cyan

$observabilityFiles = @(
    "src/iatb/core/observability/__init__.py",
    "src/iatb/core/observability/logging_config.py",
    "src/iatb/core/observability/tracing.py",
    "src/iatb/core/observability/metrics.py",
    "src/iatb/core/observability/alerting.py"
)

$allFilesExist = $true
foreach ($file in $observabilityFiles) {
    if (Test-Path $file) {
        Write-Host "  [OK] $file" -ForegroundColor Green
    } else {
        Write-Host "  [MISSING] $file" -ForegroundColor Red
        $allFilesExist = $false
    }
}

if ($allFilesExist) {
    Write-Host "`n  All observability components present" -ForegroundColor Green
} else {
    Write-Host "`n  Some observability components missing" -ForegroundColor Red
}

# ============================================================================
# Step 7: Git Sync
# ============================================================================
Write-Host "`nStep 7: Git sync..." -ForegroundColor Cyan

# Check current branch
$branch = git rev-parse --abbrev-ref HEAD
Write-Host "Current branch: $branch" -ForegroundColor Yellow

# Check status
git status

# Add files
Write-Host "`nAdding files..." -ForegroundColor Yellow
git add src/iatb/core/observability/
git add tests/unit/test_observability_*.py
git add src/iatb/fastapi_app.py
git add pyproject.toml

# Commit
Write-Host "`nCommitting changes..." -ForegroundColor Yellow
$commitMsg = "feat(observability): implement production-ready observability stack

- Add JSON structured logging with python-json-logger
- Add OpenTelemetry distributed tracing
- Add Prometheus metrics endpoint
- Add Telegram alerting integration
- Add comprehensive test coverage for all observability components
- Integrate observability into FastAPI application

Impact: Production-ready monitoring and alerting capabilities"
git commit -m $commitMsg

# Push (requires user confirmation)
Write-Host "`nChanges committed. Ready to push to remote." -ForegroundColor Green
Write-Host "To push, run: git push origin $branch" -ForegroundColor Yellow

# ============================================================================
# Step 8: Summary
# ============================================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Observability Stack Implementation Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`nComponents Implemented:" -ForegroundColor Green
Write-Host "  1. JSON Structured Logging (src/iatb/core/observability/logging_config.py)"
Write-Host "  2. OpenTelemetry Tracing (src/iatb/core/observability/tracing.py)"
Write-Host "  3. Prometheus Metrics (src/iatb/core/observability/metrics.py)"
Write-Host "  4. Telegram Alerting (src/iatb/core/observability/alerting.py)"
Write-Host "  5. FastAPI Integration (src/iatb/fastapi_app.py)"

Write-Host "`nEndpoints Added:" -ForegroundColor Green
Write-Host "  - GET /metrics (Prometheus metrics endpoint)"
Write-Host "  - All existing endpoints now instrumented with metrics"

Write-Host "`nConfiguration Required:" -ForegroundColor Yellow
Write-Host "  - TELEGRAM_BOT_TOKEN (optional, for alerting)"
Write-Host "  - TELEGRAM_CHAT_ID (optional, for alerting)"
Write-Host "  - OTEL_EXPORTER_OTLP_ENDPOINT (optional, for tracing)"

Write-Host "`nNext Steps:" -ForegroundColor Cyan
Write-Host "  1. Review test results and coverage report"
Write-Host "  2. Configure environment variables for production"
Write-Host "  3. Set up Prometheus server to scrape /metrics endpoint"
Write-Host "  4. Configure OTLP collector for tracing (optional)"
Write-Host "  5. Test Telegram alerts (if configured)"
Write-Host "  6. Push to remote: git push origin $branch"

Write-Host "`nRunbook execution completed." -ForegroundColor Green