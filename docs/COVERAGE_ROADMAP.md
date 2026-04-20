# Test Coverage Improvement Roadmap

## Executive Summary

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| Overall Coverage | 76.58% | 90.00% | -13.42% |
| Statements | 12,037 total, 2,511 missed | - | 20.86% uncovered |
| Branches | 2,926 total | - | Need branch coverage data |
| Test Count | 2,727 tests | - | - |

**Status**: Sprint 1 Complete (Token Manager: 94.80%)  
**Next Milestone**: Sprint 2 - Data Provider Testing (Target: 85% overall)

---

## Current Coverage Snapshot (April 20, 2026)

### High Coverage Modules (>90%) ✅

| Module | Coverage | Status |
|--------|----------|--------|
| `execution/order_throttle.py` | 100.00% | ✅ Excellent |
| `execution/paper_executor.py` | 100.00% | ✅ Excellent |
| `execution/trade_audit.py` | 100.00% | ✅ Excellent |
| `execution/transaction_costs.py` | 100.00% | ✅ Excellent |
| `market_strength/breadth.py` | 100.00% | ✅ Excellent |
| `market_strength/indicators.py` | 100.00% | ✅ Excellent |
| `market_strength/volume_profile.py` | 100.00% | ✅ Excellent |
| `risk/circuit_breaker.py` | 100.00% | ✅ Excellent |
| `risk/daily_loss_guard.py` | 100.00% | ✅ Excellent |
| `risk/stop_loss.py` | 100.00% | ✅ Excellent |
| `broker/token_manager.py` | 94.80% | ✅ Excellent (Sprint 1) |
| `execution/order_manager.py` | 96.59% | ✅ Excellent |
| `execution/zerodha_connection.py` | 91.17% | ✅ Good |
| `market_strength/regime_detector.py` | 99.08% | ✅ Excellent |
| `market_strength/strength_scorer.py` | 96.03% | ✅ Excellent |
| `risk/kill_switch.py` | 95.45% | ✅ Excellent |
| `risk/portfolio_risk.py` | 96.23% | ✅ Excellent |
| `risk/position_sizer.py` | 95.52% | ✅ Excellent |
| `risk/sebi_compliance.py` | 99.19% | ✅ Excellent |
| `scanner/instrument_scanner.py` | 92.29% | ✅ Good |
| `scanner/scan_cycle.py` | 92.28% | ✅ Good |

### Medium Coverage Modules (50-90%) ⚠️

| Module | Coverage | Priority |
|--------|----------|----------|
| `core/exchange_calendar.py` | 66.47% | Medium |
| `data/historical_data.py` | 50.00% | High (Sprint 2) |
| `data/market_data.py` | 45.00% | High (Sprint 2) |
| `selection/fundamental_filter.py` | 60.00% | Medium |
| `selection/technical_filter.py` | 65.00% | Medium |
| `storage/db_manager.py` | 68.00% | Medium |

### Low Coverage Modules (<50%) ❌

| Module | Coverage | Priority | Sprint |
|--------|----------|----------|--------|
| `api.py` | 0.00% | Critical | Sprint 3 |
| `core/config_manager.py` | 0.00% | High | Sprint 3 |
| `core/engine.py` | 0.00% | High | Sprint 3 |
| `core/health.py` | 0.00% | Medium | Sprint 3 |
| `core/observability/metrics.py` | 0.00% | Medium | Sprint 3 |
| `core/observability/tracing.py` | 0.00% | Medium | Sprint 3 |
| `core/preflight.py` | 0.00% | High | Sprint 3 |
| `core/runtime.py` | 0.00% | High | Sprint 3 |
| `core/sse_broadcaster.py` | 0.00% | Medium | Sprint 3 |
| `fastapi_app.py` | 0.00% | Critical | Sprint 3 |
| `data/providers/` | 11-50% | High | Sprint 2 |
| `selection/multi_factor_scorer.py` | 35.00% | High | Sprint 4 |
| `sentiment/` | 17-35% | Medium | Sprint 4 |
| `strategies/` | 0-37% | High | Sprint 4 |
| `backtesting/` | 14-48% | Medium | Sprint 5 |
| `visualization/` | 0-43% | Low | Sprint 5 |

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

### Sprint 2: Data Provider Testing 🚀 CURRENT
**Duration**: 20-30 hours (April 21-25, 2026)  
**Focus**: Data provider modules and market data infrastructure  
**Target**: 85% overall coverage (from 76.58%)  
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
- [ ] All data provider tests pass
- [ ] External APIs properly mocked
- [ ] Coverage ≥85% for all target modules
- [ ] All quality gates (G1-G10) pass
- [ ] Integration tests for data flow
- [ ] Performance tests for data fetching

**Risks**:
- External API rate limits during testing
- Complex data structures difficult to mock
- Time-sensitive data (market hours)

**Mitigations**:
- Use `responses` library for HTTP mocking
- Create comprehensive test fixtures
- Test with cached data when possible

---

### Sprint 3: Core Infrastructure
**Duration**: 30-40 hours (April 26 - May 5, 2026)  
**Focus**: Core engine, configuration, and runtime  
**Target**: 88% overall coverage  
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

### Sprint 4: Selection & Sentiment
**Duration**: 25-35 hours (May 6-15, 2026)  
**Focus**: Stock selection and sentiment analysis  
**Target**: 90% overall coverage  
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

### Sprint 5: Backtesting & Visualization
**Duration**: 20-30 hours (May 16-25, 2026)  
**Focus**: Backtesting engine and visualization tools  
**Target**: 92% overall coverage (exceeds 90% goal)  
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
**Last Updated**: April 20, 2026  
**Next Review**: End of Sprint 2 (April 25, 2026)

**Status**: ✅ Sprint 1 Complete, 🚀 Sprint 2 In Progress