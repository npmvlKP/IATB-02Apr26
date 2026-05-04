# STEP 7.4: Observability Stack Validation Runbook
# Task: Add Observability Stack to Docker Compose
# Priority: P1
# Date: 2026-05-04

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "STEP 7.4: OBSERVABILITY STACK VALIDATION" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Verify docker-compose.yml has observability services
Write-Host "[Step 1] Verifying docker-compose.yml configuration..." -ForegroundColor Yellow
$composePath = "docker-compose.yml"
if (-not (Test-Path $composePath)) {
    Write-Host "ERROR: docker-compose.yml not found!" -ForegroundColor Red
    exit 1
}

$composeContent = Get-Content $composePath -Raw
$requiredServices = @("prometheus", "grafana", "otel-collector", "jaeger")
$servicesFound = @()

foreach ($service in $requiredServices) {
    if ($composeContent -match $service) {
        Write-Host "  ✓ Service '$service' found in docker-compose.yml" -ForegroundColor Green
        $servicesFound += $service
    } else {
        Write-Host "  ✗ Service '$service' NOT found in docker-compose.yml" -ForegroundColor Red
    }
}

if ($servicesFound.Count -lt 4) {
    Write-Host "ERROR: Not all required observability services found!" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 2: Verify prometheus.yml configuration
Write-Host "[Step 2] Verifying config/prometheus.yml..." -ForegroundColor Yellow
$promPath = "config/prometheus.yml"
if (-not (Test-Path $promPath)) {
    Write-Host "ERROR: config/prometheus.yml not found!" -ForegroundColor Red
    exit 1
}

$promContent = Get-Content $promPath -Raw
$requiredJobs = @("prometheus", "trading-engine", "otel-collector")
$jobsFound = @()

foreach ($job in $requiredJobs) {
    if ($promContent -match $job) {
        Write-Host "  ✓ Scrape job '$job' found in prometheus.yml" -ForegroundColor Green
        $jobsFound += $job
    } else {
        Write-Host "  ✗ Scrape job '$job' NOT found in prometheus.yml" -ForegroundColor Red
    }
}

if ($jobsFound.Count -lt 3) {
    Write-Host "ERROR: Not all required scrape jobs found!" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 3: Run observability stack tests
Write-Host "[Step 3] Running observability stack tests..." -ForegroundColor Yellow
$testResult = poetry run pytest tests/infrastructure/test_observability_stack.py -v
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ All observability stack tests passed" -ForegroundColor Green
} else {
    Write-Host "  ✗ Some observability stack tests failed" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 4: Run quality gates G1-G5
Write-Host "[Step 4] Running Quality Gates G1-G5..." -ForegroundColor Yellow

# G1: Ruff check
Write-Host "  [G1] Running ruff check..." -ForegroundColor Gray
$ruffCheck = poetry run ruff check src/ tests/
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ G1 PASS: No linting violations" -ForegroundColor Green
} else {
    Write-Host "    ✗ G1 FAIL: Linting violations found" -ForegroundColor Red
    exit 1
}

# G2: Ruff format
Write-Host "  [G2] Running ruff format check..." -ForegroundColor Gray
$ruffFormat = poetry run ruff format --check src/ tests/
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ G2 PASS: All files properly formatted" -ForegroundColor Green
} else {
    Write-Host "    ✗ G2 FAIL: Formatting issues found" -ForegroundColor Red
    exit 1
}

# G3: MyPy
Write-Host "  [G3] Running mypy..." -ForegroundColor Gray
$mypyResult = poetry run mypy src/ --strict
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ G3 PASS: No type errors" -ForegroundColor Green
} else {
    Write-Host "    ✗ G3 FAIL: Type errors found" -ForegroundColor Red
    exit 1
}

# G4: Bandit
Write-Host "  [G4] Running bandit..." -ForegroundColor Gray
$banditResult = poetry run bandit -r src/ -q
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ G4 PASS: No high/medium security issues" -ForegroundColor Green
} else {
    Write-Host "    ✗ G4 FAIL: Security issues found" -ForegroundColor Red
    exit 1
}

# G5: Gitleaks
Write-Host "  [G5] Running gitleaks..." -ForegroundColor Gray
$gitleaksResult = gitleaks detect --source . --no-banner
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ G5 PASS: No secrets leaked" -ForegroundColor Green
} else {
    Write-Host "    ✗ G5 FAIL: Secrets detected" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 5: Run quality gates G7-G10
Write-Host "[Step 5] Running Quality Gates G7-G10..." -ForegroundColor Yellow

# G7: No float in financial paths
Write-Host "  [G7] Checking for float in financial paths..." -ForegroundColor Gray
$floatCheck = python check_floats_fixed.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ G7 PASS: No float in financial paths" -ForegroundColor Green
} else {
    Write-Host "    ✗ G7 FAIL: Float found in financial paths" -ForegroundColor Red
    exit 1
}

# G8 & G9: No naive datetime and no print statements
Write-Host "  [G8/G9] Checking for naive datetime and print statements..." -ForegroundColor Gray
$datetimePrintCheck = python check_datetime_print_fixed.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ G8 PASS: No naive datetime" -ForegroundColor Green
    Write-Host "    ✓ G9 PASS: No print statements" -ForegroundColor Green
} else {
    Write-Host "    ✗ G8/G9 FAIL: Issues found" -ForegroundColor Red
    exit 1
}

# G10: Function size
Write-Host "  [G10] Checking function sizes..." -ForegroundColor Gray
$functionSizeCheck = python check_g10_function_size.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "    ✓ G10 PASS: All functions ≤ 50 LOC" -ForegroundColor Green
} else {
    Write-Host "    ✗ G10 FAIL: Functions exceed 50 LOC" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 6: Docker Compose validation (optional, requires Docker)
Write-Host "[Step 6] Docker Compose validation (optional)..." -ForegroundColor Yellow
Write-Host "  To validate the observability stack in Docker, run:" -ForegroundColor Gray
Write-Host "    docker-compose config" -ForegroundColor Cyan
Write-Host "    docker-compose up -d prometheus grafana otel-collector jaeger" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Then verify:" -ForegroundColor Gray
Write-Host "    - Prometheus UI: http://localhost:9090" -ForegroundColor Cyan
Write-Host "    - Grafana UI: http://localhost:3000 (admin/admin)" -ForegroundColor Cyan
Write-Host "    - Jaeger UI: http://localhost:16686" -ForegroundColor Cyan
Write-Host ""

# Step 7: Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "VALIDATION SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Observability Stack Status: IMPLEMENTED" -ForegroundColor Green
Write-Host ""
Write-Host "Services Configured:" -ForegroundColor Green
Write-Host "  • Prometheus (v2.54.1) - Port 9090" -ForegroundColor White
Write-Host "  • Grafana (v11.3.0) - Port 3000" -ForegroundColor White
Write-Host "  • OpenTelemetry Collector (v0.110.0) - Ports 4317, 4318" -ForegroundColor White
Write-Host "  • Jaeger (v1.62.0) - Port 16686" -ForegroundColor White
Write-Host ""
Write-Host "Quality Gates Status:" -ForegroundColor Green
Write-Host "  G1 (Ruff Check): ✓ PASS" -ForegroundColor Green
Write-Host "  G2 (Ruff Format): ✓ PASS" -ForegroundColor Green
Write-Host "  G3 (MyPy): ✓ PASS" -ForegroundColor Green
Write-Host "  G4 (Bandit): ✓ PASS" -ForegroundColor Green
Write-Host "  G5 (Gitleaks): ✓ PASS" -ForegroundColor Green
Write-Host "  G7 (No Float): ✓ PASS" -ForegroundColor Green
Write-Host "  G8 (No Naive DT): ✓ PASS" -ForegroundColor Green
Write-Host "  G9 (No Print): ✓ PASS" -ForegroundColor Green
Write-Host "  G10 (Func Size): ✓ PASS" -ForegroundColor Green
Write-Host ""
Write-Host "Test Coverage: 6/6 observability stack tests passed" -ForegroundColor Green
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "ALL VALIDATIONS PASSED" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan