# Test Coverage Improvement Roadmap

## Executive Summary

| Metric | Previous | Current | Status |
|--------|----------|---------|--------|
| Overall Coverage | 76.58% | **93.08%** | ✅ EXCEEDS 90% target |
| Statements | 12,037 total, 2,511 missed | 13,250 total, 742 missed | ✅ 94.40% covered |
| Branches | 2,926 total | 3,320 total, 360 missed | ✅ 89.16% covered |
| Test Count | 2,727 tests | **3,107 tests** (3107 passed, 6 skipped) | ✅ All pass |

**Status**: ✅ ALL SPRINTS COMPLETE — Coverage target of 90% exceeded  
**Coverage Gate (G6)**: `poetry run pytest --cov=src/iatb --cov-fail-under=90 -x` → **PASS (93.08%)**

---

## Current Coverage Snapshot (April 22, 2026)

**Overall: 93.08% (3,107 tests passed, 6 skipped)**

### All Modules Now Above 82% Coverage ✅

All previously low/medium coverage modules have been brought above 82%.
Below is a summary of key coverage achievements across all sprints:

| Module Group | Coverage Range | Status |
|-------------|----------------|--------|
| `core/` (clock, config, engine, events, health, observability, preflight, runtime) | 87–100% | ✅ All ≥87% |
| `data/` (providers, cache, normalizer, instrument_master, rate_limiter) | 82–100% | ✅ All ≥82% |
| `execution/` (paper_executor, order_manager, trade_audit, throttle) | 91–100% | ✅ All ≥91% |
| `scanner/` (instrument_scanner, scan_cycle) | 92%+ | ✅ All ≥92% |
| `selection/` (composite_score, correlation, decay, multi_factor, ranking, etc.) | 90–100% | ✅ All ≥90% |
| `sentiment/` (aggregator, analyzers, news, social) | 92–100% | ✅ All ≥92% |
| `risk/` (circuit_breaker, kill_switch, position_sizer, sebi_compliance) | 95–100% | ✅ All ≥95% |
| `market_strength/` (breadth, indicators, regime, volume_profile) | 96–100% | ✅ All ≥96% |
| `backtesting/` (event_driven, monte_carlo, walk_forward, vectorized) | 90–100% | ✅ All ≥90% |
| `storage/` (duckdb, git_sync, parquet, sqlite) | 83–100% | ✅ All ≥83% |
| `strategies/` (base, breakout, ensemble, mean_reversion, momentum) | 85–100% | ✅ All ≥85% |
| `visualization/` (alerts, charts, dashboard, breakout_scanner) | 87–100% | ✅ All ≥87% |
| `broker/token_manager.py` | 94.80% | ✅ Excellent |

### Modules Below 90% (Improvement Opportunities)

| Module | Coverage | Missing Lines |
|--------|----------|---------------|
| `storage/parquet_store.py` | 82.80% | 19-20, 25-27, 30-31, 43-44, 84, 121-122 |
| `storage/sqlite_store.py` | 88.89% | 25-26, 76-78, 80, 87-88, 191 |
| `storage/duckdb_store.py` | 90.32% | 19-20, 25-27, 30-31 |
| `strategies/ensemble.py` | 85.53% | 32, 34, 37, 67->60, 71, 79 |
| `strategies/mean_reversion.py` | 88.00% | 35, 40, 55 |
| `visualization/dashboard.py` | 87.29% | Multiple branches |

---

## Sprint Roadmap

### Sprint 1: Token Management ✅ COMPLETE
**Duration**: Complete (April 20, 2026)  
**Focus**: Broker authentication and token management  
**Target**: 90% coverage for token manager  
**Achieved**: 94.80% coverage ✅

**Deliverables**:
- ✅ Consolidated token manager (single implementation)
- ✅ 64 tests with 94.80% coverage
- ✅ All quality gates (G1-G10) passing
- ✅ Decision record documented
- ✅ Migration guide provided

---

### Sprint 2: Data Provider Testing ✅ COMPLETE
**Duration**: Complete (April 21-22, 2026)  
**Focus**: Data provider modules and market data infrastructure  
**Target**: 85% overall coverage (from 76.58%)  
**Achieved**: 93.08% overall coverage ✅
**Key Modules**:
- `data/providers/` (11-50% → 85%)
- `data/historical_data.py` (50% → 85%)
- `data/market_data.py` (45% → 85%)

**Test Strategy**:
1. Mock external API calls (Zerodha, Binance)
2. Test error handling (rate limits, network failures)
3. Validate data transformation logic
4. Test caching mechanisms
5. Verify timezone handling (IST/UTC)

**Test Coverage Targets**:
| Module | Current | Target | Tests Needed |
|--------|---------|--------|--------------|
| `data/providers/zerodha.py` | 11% | 85% | ~40 tests |
| `data/providers/binance.py` | 15% | 85% | ~35 tests |
| `data/historical_data.py` | 50% | 85% | ~25 tests |
| `data/market_data.py` | 45% | 85% | ~30 tests |
| **Total** | - | - | **~130 tests** |

**Success Criteria**:
- [x] All data provider tests pass
- [x] External APIs properly mocked
- [x] Coverage ≥85% for all target modules
- [x] All quality gates (G1-G10) pass
- [x] Integration tests for data flow
- [x] Performance tests for data fetching

**Risks**:
- External API rate limits during testing
- Complex data structures difficult to mock
- Time-sensitive data (market hours)

**Mitigations**:
- Use `responses` library for HTTP mocking
- Create comprehensive test fixtures
- Test with cached data when possible

---

### Sprint 3: Core Infrastructure ✅ COMPLETE
**Duration**: Complete (April 21-22, 2026)  
**Focus**: Core engine, configuration, and runtime  
**Target**: 88% overall coverage  
**Achieved**: All core modules ≥87% coverage ✅
**Key Modules**:
- `api.py` (0% → 80%)
- `core/engine.py` (0% → 85%)
- `core/config_manager.py` (0% → 85%)
- `core/preflight.py` (0% → 90%)
- `core/runtime.py` (0% → 85%)
- `fastapi_app.py` (0% → 80%)

**Test Strategy**:
1. Test FastAPI endpoints with `TestClient`
2. Mock database and external dependencies
3. Test startup/shutdown sequences
4. Validate configuration loading
5. Test pre-flight checks

**Test Coverage Targets**:
| Module | Current | Target | Tests Needed |
|--------|---------|--------|--------------|
| `api.py` | 0% | 80% | ~50 tests |
| `core/engine.py` | 0% | 85% | ~40 tests |
| `core/config_manager.py` | 0% | 85% | ~30 tests |
| `core/preflight.py` | 0% | 90% | ~25 tests |
| `core/runtime.py` | 0% | 85% | ~35 tests |
| `fastapi_app.py` | 0% | 80% | ~60 tests |
| **Total** | - | - | **~240 tests** |

---

### Sprint 4: Selection & Sentiment ✅ COMPLETE
**Duration**: Complete (April 21-22, 2026)  
**Focus**: Stock selection and sentiment analysis  
**Target**: 90% overall coverage  
**Achieved**: selection/ ≥90%, sentiment/ ≥92% ✅
**Key Modules**:
- `selection/multi_factor_scorer.py` (35% → 90%)
- `selection/fundamental_filter.py` (60% → 90%)
- `selection/technical_filter.py` (65% → 90%)
- `sentiment/news_analyzer.py` (17% → 85%)
- `sentiment/social_sentiment.py` (25% → 85%)

**Test Strategy**:
1. Mock external data sources (news APIs, social media)
2. Test scoring algorithms with synthetic data
3. Validate filter logic edge cases
4. Test sentiment accuracy with labeled data

**Test Coverage Targets**:
| Module | Current | Target | Tests Needed |
|--------|---------|--------|--------------|
| `selection/multi_factor_scorer.py` | 35% | 90% | ~45 tests |
| `selection/fundamental_filter.py` | 60% | 90% | ~30 tests |
| `selection/technical_filter.py` | 65% | 90% | ~35 tests |
| `sentiment/news_analyzer.py` | 17% | 85% | ~40 tests |
| `sentiment/social_sentiment.py` | 25% | 85% | ~35 tests |
| **Total** | - | - | **~185 tests** |

---

### Sprint 5: Backtesting & Visualization ✅ COMPLETE
**Duration**: Complete (April 21-22, 2026)  
**Focus**: Backtesting engine and visualization tools  
**Target**: 92% overall coverage (exceeds 90% goal)  
**Achieved**: backtesting/ ≥90%, visualization/ ≥87% ✅
**Key Modules**:
- `backtesting/engine.py` (48% → 85%)
- `backtesting/performance.py` (35% → 85%)
- `visualization/charts.py` (43% → 80%)
- `visualization/dashboard.py` (0% → 80%)

**Test Strategy**:
1. Test backtesting with historical data
2. Validate performance calculations
3. Test visualization generation (mock charts)
4. Integration tests for end-to-backtesting

**Test Coverage Targets**:
| Module | Current | Target | Tests Needed |
|--------|---------|--------|--------------|
| `backtesting/engine.py` | 48% | 85% | ~50 tests |
| `backtesting/performance.py` | 35% | 85% | ~40 tests |
| `visualization/charts.py` | 43% | 80% | ~30 tests |
| `visualization/dashboard.py` | 0% | 80% | ~40 tests |
| **Total** | - | - | **~160 tests** |

---

## Testing Best Practices

### 1. Test Pyramid

```
         /\
        /E2E\       10% (Integration)
       /------\
      / Unit   \    70% (Unit tests)
     /----------\
    /   Component \  20% (Component tests)
   /--------------\
```

### 2. Test Naming Convention

```python
def test_<function>_<scenario>_<expected>():
    """
    Example: test_token_expiry_at_6am_ist_returns_false
    """
```

### 3. AAA Pattern (Arrange-Act-Assert)

```python
def test_token_expiry_detection():
    # Arrange
    manager = ZerodhaTokenManager(api_key="test", api_secret="test")
    old_token_date = datetime.now(UTC) - timedelta(days=1)
    
    # Act
    is_fresh = manager._is_token_date_valid(old_token_date)
    
    # Assert
    assert is_fresh is False
```

### 4. Mock External Dependencies

```python
from unittest.mock import Mock, patch

@patch('iatb.broker.token_manager.KiteConnect')
def test_get_kite_client_with_mock(kite_mock):
    # Arrange
    kite_mock.return_value = Mock()
    manager = ZerodhaTokenManager(api_key="test", api_secret="test")
    
    # Act
    client = manager.get_kite_client()
    
    # Assert
    assert client is not None
    kite_mock.assert_called_once()
```

### 5. Test Data Fixtures

```python
@pytest.fixture
def sample_market_data():
    return {
        "instrument_token": "123456",
        "last_price": Decimal("100.50"),
        "timestamp": datetime.now(UTC)
    }

def test_market_data_processing(sample_market_data):
    # Test with fixture data
    result = process_market_data(sample_market_data)
    assert result["price"] == Decimal("100.50")
```

### 6. Parameterized Tests

```python
@pytest.mark.parametrize("input_value,expected", [
    (100, Decimal("100.00")),
    (100.50, Decimal("100.50")),
    (0.01, Decimal("0.01")),
])
def test_decimal_conversion(input_value, expected):
    result = convert_to_decimal(input_value)
    assert result == expected
```

---

## Quality Gates (Per Sprint)

Each sprint must pass all gates before proceeding:

| Gate | Command | Requirement |
|------|---------|-------------|
| G1 | `poetry run ruff check src/ tests/` | 0 violations |
| G2 | `poetry run ruff format --check src/ tests/` | 0 reformats |
| G3 | `poetry run mypy src/ --strict` | 0 errors |
| G4 | `poetry run bandit -r src/ -q` | 0 high/medium |
| G5 | `gitleaks detect --source . --no-banner` | 0 leaks |
| G6 | `poetry run pytest --cov=src/iatb --cov-fail-under=<target> -x` | All pass |
| G7 | `grep -r "float" src/iatb/<module>/` | 0 float in financial paths |
| G8 | `grep -r "datetime.now()" src/` | 0 naive datetime |
| G9 | `grep -r "print(" src/` | 0 print() statements |
| G10 | Function LOC check | ≤50 LOC each |

---

## Coverage Tracking

### Weekly Coverage Report

```bash
# Generate coverage report
poetry run pytest --cov=src/iatb --cov-report=html --cov-report=term

# Track coverage trend
poetry run pytest --cov=src/iatb --cov-report=term-missing | tee coverage_report.txt
```

### Coverage Dashboard (Planned)

- **Overall Coverage**: Trend chart over time
- **Module Coverage**: Heatmap showing coverage by module
- **Test Execution Time**: Performance tracking
- **Flaky Tests**: Identification and tracking

---

## Resource Allocation

### Sprint 2: Data Provider Testing

| Role | Hours | Focus |
|------|-------|-------|
| Senior Developer | 15h | Architecture, complex test scenarios |
| Mid-level Developer | 10h | Unit tests, mocking |
| QA Engineer | 5h | Test review, edge case identification |

**Total**: 30 hours

---

## Success Metrics

### Sprint-Level Metrics
- Test coverage target met for target modules
- All quality gates (G1-G10) passing
- No regression in existing tests
- Test execution time < 5 minutes per module

### Overall Metrics (by Sprint 5 completion)
- Overall coverage ≥90%
- Zero critical bugs in production
- Test suite execution time < 10 minutes
- 95% of new code covered by tests

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| External API changes break tests | Medium | High | Use versioned mocks, contract tests |
| Test flakiness due to timing | Medium | Medium | Deterministic test data, proper mocking |
| Coverage target not met | Low | High | Prioritize critical paths, adjust targets |
| Resource constraints | Low | Medium | Phased approach, focus on high-impact modules |
| Technical debt in legacy code | High | Medium | Refactor as part of testing effort |

---

## Next Steps (Immediate)

### Sprint 2 Kickoff (April 21, 2026)

1. **Setup Sprint Board**
   - Create tasks for each module
   - Assign owners and due dates
   - Define acceptance criteria

2. **Test Environment**
   - Set up test data fixtures
   - Configure mock servers for external APIs
   - Create test database schema

3. **Development**
   - Start with `data/providers/zerodha.py`
   - Follow test-driven development (TDD) where possible
   - Daily standups to track progress

4. **Quality Assurance**
   - Run quality gates daily
   - Code review for all test changes
   - Continuous integration (CI) integration

---

## Appendices

### A. Test Coverage Calculation

```
Coverage = (Statements Covered / Total Statements) × 100
Branch Coverage = (Branches Covered / Total Branches) × 100
```

### B. Tools and Libraries

- **pytest**: Test framework
- **pytest-cov**: Coverage reporting
- **pytest-mock**: Mocking utilities
- **responses**: HTTP mocking
- **freezegun**: Time mocking for datetime tests
- **faker**: Test data generation

### C. References

- [IATB Test Coverage Best Practices](../coverage_best_practices_research.json)
- [Testing Infrastructure Improvements](../TESTING_INFRASTRUCTURE_IMPROVEMENTS.md)
- [Validation Checklist Fix Report](../VALIDATION_CHECKLIST_FIX_REPORT.md)

---

**Document Owner**: Development Team  
**Last Updated**: April 22, 2026  
**Next Review**: Ongoing maintenance

**Status**: ✅ ALL SPRINTS COMPLETE (93.08% coverage, 3,107 tests passing)
