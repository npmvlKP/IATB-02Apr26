# Sprint 2: Data Provider Testing Plan

## Sprint Overview

| Field | Value |
|-------|-------|
| Sprint Number | 2 |
| Duration | April 21-25, 2026 (5 days) |
| Total Effort | 20-30 hours |
| Focus | Data Provider Modules |
| Target Coverage | 85% overall (from 76.58%) |
| Success Criteria | All target modules ≥85% coverage |

---

## Objectives

### Primary Objectives
1. Achieve 85% test coverage for data provider modules
2. Ensure all external API calls are properly mocked
3. Validate error handling (rate limits, network failures)
4. Test data transformation and caching mechanisms
5. Verify timezone handling (IST/UTC)

### Secondary Objectives
1. Create reusable test fixtures for data providers
2. Establish patterns for mocking external APIs
3. Document best practices for data provider testing
4. Set up integration tests for end-to-end data flow

---

## Target Modules

| Priority | Module | Current Coverage | Target Coverage | Tests Needed | Est. Hours |
|----------|--------|------------------|-----------------|--------------|------------|
| P0 | `data/providers/zerodha.py` | 11% | 85% | ~40 tests | 8h |
| P0 | `data/providers/binance.py` | 15% | 85% | ~35 tests | 7h |
| P1 | `data/historical_data.py` | 50% | 85% | ~25 tests | 5h |
| P1 | `data/market_data.py` | 45% | 85% | ~30 tests | 6h |
| **Total** | - | - | - | **~130 tests** | **26h** |

---

## Daily Plan

### Day 1: Setup & Zerodha Provider (April 21)
**Goal**: Complete test infrastructure and Zerodha provider tests (50%)
**Effort**: 6 hours

**Tasks**:
- [ ] Setup test fixtures for market data
- [ ] Configure `responses` library for HTTP mocking
- [ ] Create Zerodha API response fixtures
- [ ] Implement tests for Zerodha authentication
- [ ] Implement tests for instrument token retrieval
- [ ] Implement tests for market data fetching

**Deliverables**:
- Test fixture library created
- Zerodha provider: 20 tests
- Coverage: 50%

### Day 2: Zerodha Provider Completion (April 22)
**Goal**: Complete Zerodha provider tests to 85%
**Effort**: 6 hours

**Tasks**:
- [ ] Implement tests for historical data fetching
- [ ] Implement tests for order placement
- [ ] Implement tests for error handling (rate limits, auth failures)
- [ ] Implement tests for retry logic
- [ ] Run quality gates (G1-G10)
- [ ] Fix any failing tests

**Deliverables**:
- Zerodha provider: 40 tests
- Coverage: ≥85%
- All quality gates passing

### Day 3: Binance Provider (April 23)
**Goal**: Complete Binance provider tests to 85%
**Effort**: 7 hours

**Tasks**:
- [ ] Create Binance API response fixtures
- [ ] Implement tests for Binance authentication
- [ ] Implement tests for market data fetching
- [ ] Implement tests for historical data
- [ ] Implement tests for error handling
- [ ] Implement tests for WebSocket connections (if applicable)
- [ ] Run quality gates

**Deliverables**:
- Binance provider: 35 tests
- Coverage: ≥85%
- All quality gates passing

### Day 4: Historical & Market Data (April 24)
**Goal**: Complete historical_data.py and market_data.py tests
**Effort**: 6 hours

**Tasks**:
- [ ] Implement tests for historical data caching
- [ ] Implement tests for data normalization
- [ ] Implement tests for timezone conversion (IST ↔ UTC)
- [ ] Implement tests for market data aggregation
- [ ] Implement tests for real-time data updates
- [ ] Integration test: end-to-end data flow
- [ ] Run quality gates

**Deliverables**:
- Historical data: 25 tests, ≥85% coverage
- Market data: 30 tests, ≥85% coverage
- Integration tests: 5 tests

### Day 5: Review & Documentation (April 25)
**Goal**: Final verification and documentation
**Effort**: 5 hours

**Tasks**:
- [ ] Run full test suite with coverage
- [ ] Verify all modules meet 85% target
- [ ] Run all quality gates (G1-G10)
- [ ] Document testing patterns and best practices
- [ ] Create Sprint 2 completion report
- [ ] Update coverage roadmap
- [ ] Git commit and push

**Deliverables**:
- All target modules: ≥85% coverage
- Overall coverage: ≥85%
- Sprint 2 completion report
- Updated documentation

---

## Test Strategy

### 1. Unit Tests (70%)
Focus on individual functions and methods with mocked dependencies.

**Example**:
```python
import pytest
from unittest.mock import patch, Mock
from iatb.data.providers.zerodha import ZerodhaProvider

@patch('iatb.data.providers.zerodha.KiteConnect')
def test_get_instrument_token_success(kite_mock):
    """Test successful instrument token retrieval"""
    # Arrange
    kite_instance = Mock()
    kite_instance.instruments.return_value = [
        {'instrument_token': 123456, 'tradingsymbol': 'INFY'}
    ]
    kite_mock.return_value = kite_instance
    
    provider = ZerodhaProvider(api_key="test", api_secret="test")
    
    # Act
    result = provider.get_instrument_token('INFY')
    
    # Assert
    assert result == 123456
    kite_instance.instruments.assert_called_once_with('NSE')
```

### 2. Integration Tests (20%)
Test data flow between multiple components.

**Example**:
```python
def test_end_to_end_data_flow():
    """Test data from provider to consumer"""
    # Arrange
    provider = ZerodhaProvider(api_key="test", api_secret="test")
    cache = DataCache()
    
    # Act
    data = provider.fetch_market_data('INFY')
    cache.store('INFY', data)
    retrieved = cache.retrieve('INFY')
    
    # Assert
    assert retrieved['last_price'] > 0
    assert retrieved['timestamp'] is not None
```

### 3. Error Handling Tests (10%)
Test edge cases and error scenarios.

**Example**:
```python
@patch('iatb.data.providers.zerodha.requests.get')
def test_rate_limit_handling(get_mock):
    """Test rate limit error handling"""
    # Arrange
    get_mock.return_value.status_code = 429
    get_mock.return_value.headers = {'Retry-After': '60'}
    
    provider = ZerodhaProvider(api_key="test", api_secret="test")
    
    # Act & Assert
    with pytest.raises(RateLimitError) as exc_info:
        provider.fetch_market_data('INFY')
    
    assert 'retry_after' in str(exc_info.value)
```

---

## Test Fixtures

### Market Data Fixture
```python
@pytest.fixture
def sample_market_data():
    """Sample market data for testing"""
    return {
        'instrument_token': '123456',
        'last_price': Decimal('100.50'),
        'timestamp': datetime.now(UTC),
        'volume': 10000,
        'oi': 5000
    }
```

### Zerodha API Response Fixture
```python
@pytest.fixture
def zerodha_instruments_response():
    """Mock Zerodha instruments API response"""
    return [
        {
            'instrument_token': 123456,
            'tradingsymbol': 'INFY',
            'name': 'INFOSYS',
            'last_price': 100.50,
            'expiry': None,
            'strike': None,
            'tick_size': 0.05,
            'lot_size': 1,
            'instrument_type': 'EQ',
            'segment': 'NSE',
            'exchange': 'NSE'
        }
    ]
```

### Binance API Response Fixture
```python
@pytest.fixture
def binance_ticker_response():
    """Mock Binance ticker API response"""
    return {
        'symbol': 'BTCUSDT',
        'lastPrice': '50000.50',
        'volume': '1000.50',
        'quoteVolume': '50000000.00',
        'timestamp': 1713564000000
    }
```

---

## Mocking Strategy

### HTTP Request Mocking with `responses`
```python
import responses

@responses.activate
def test_zerodha_api_call_with_responses():
    """Test using responses library for HTTP mocking"""
    # Arrange
    responses.add(
        responses.GET,
        'https://api.kite.trade/instruments/NSE',
        json=[{'instrument_token': 123456, 'tradingsymbol': 'INFY'}],
        status=200
    )
    
    provider = ZerodhaProvider(api_key="test", api_secret="test")
    
    # Act
    result = provider.get_instruments('NSE')
    
    # Assert
    assert len(result) == 1
    assert result[0]['tradingsymbol'] == 'INFY'
```

### WebSocket Mocking
```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
@patch('iatb.data.providers.binance.BinanceSocketManager')
async def test_binance_webstream(mock_ws_manager):
    """Test WebSocket connection mocking"""
    # Arrange
    mock_socket = AsyncMock()
    mock_socket.__aiter__.return_value = [
        {'s': 'BTCUSDT', 'c': '50000.50'}
    ]
    mock_ws_manager.return_value.trade_socket.return_value = mock_socket
    
    provider = BinanceProvider()
    
    # Act
    messages = []
    async for msg in provider.stream_ticker('BTCUSDT'):
        messages.append(msg)
        break
    
    # Assert
    assert len(messages) == 1
    assert messages[0]['s'] == 'BTCUSDT'
```

---

## Error Scenarios to Test

### Network Errors
- [ ] Connection timeout
- [ ] DNS resolution failure
- [ ] SSL certificate error
- [ ] Network unreachable

### API Errors
- [ ] 401 Unauthorized (invalid credentials)
- [ ] 403 Forbidden (insufficient permissions)
- [ ] 404 Not Found (invalid symbol)
- [ ] 429 Too Many Requests (rate limit)
- [ ] 500 Internal Server Error
- [ ] 503 Service Unavailable

### Data Errors
- [ ] Missing required fields
- [ ] Invalid data types
- [ ] Out-of-range values
- [ ] Null/None values
- [ ] Malformed JSON

### Business Logic Errors
- [ ] Invalid symbol format
- [ ] Invalid date range
- [ ] Invalid exchange
- [ ] Expired session token
- [ ] Invalid timezone

---

## Timezone Testing

### IST to UTC Conversion
```python
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

def test_ist_to_utc_conversion():
    """Test IST to UTC conversion"""
    # Arrange
    ist_time = datetime(2024, 4, 20, 9, 15, 0, tzinfo=ZoneInfo('Asia/Kolkata'))
    expected_utc = datetime(2024, 4, 20, 3, 45, 0, tzinfo=timezone.utc)
    
    # Act
    utc_time = ist_time.astimezone(timezone.utc)
    
    # Assert
    assert utc_time == expected_utc
```

### Market Hours Validation
```python
def test_market_hours_in_ist():
    """Test market hours validation in IST"""
    # Arrange
    market_open = time(9, 15, tzinfo=ZoneInfo('Asia/Kolkata'))
    market_close = time(15, 30, tzinfo=ZoneInfo('Asia/Kolkata'))
    
    # Test during market hours
    during_market = time(10, 30, tzinfo=ZoneInfo('Asia/Kolkata'))
    assert is_market_open(during_market)
    
    # Test before market hours
    before_market = time(9, 0, tzinfo=ZoneInfo('Asia/Kolkata'))
    assert not is_market_open(before_market)
    
    # Test after market hours
    after_market = time(16, 0, tzinfo=ZoneInfo('Asia/Kolkata'))
    assert not is_market_open(after_market)
```

---

## Performance Tests

### Data Fetching Performance
```python
import time

def test_data_fetching_performance():
    """Test data fetching meets performance requirements"""
    # Arrange
    provider = ZerodhaProvider(api_key="test", api_secret="test")
    
    # Act
    start_time = time.time()
    data = provider.fetch_market_data('INFY')
    elapsed_time = time.time() - start_time
    
    # Assert
    assert elapsed_time < 1.0  # Should complete within 1 second
    assert data is not None
```

### Caching Performance
```python
def test_cache_performance():
    """Test caching improves performance"""
    # Arrange
    provider = ZerodhaProvider(api_key="test", api_secret="test")
    
    # First call (cache miss)
    start_time = time.time()
    provider.fetch_market_data('INFY')
    first_call_time = time.time() - start_time
    
    # Second call (cache hit)
    start_time = time.time()
    provider.fetch_market_data('INFY')
    second_call_time = time.time() - start_time
    
    # Assert
    assert second_call_time < first_call_time
    assert second_call_time < 0.1  # Cache should be fast
```

---

## Quality Gates

### Pre-Commit Checks
```bash
# Run before each commit
poetry run ruff check src/iatb/data/ tests/data/
poetry run ruff format --check src/iatb/data/ tests/data/
poetry run mypy src/iatb/data/ --strict
```

### Pre-Push Checks
```bash
# Run before each push
poetry run pytest tests/data/ -v --cov=src/iatb/data --cov-report=term-missing
poetry run bandit -r src/iatb/data/ -q
```

### Daily Validation
```powershell
# Run daily
.\scripts\validate_g7_g8_g9_g10.ps1
poetry run pytest tests/data/ --cov=src/iatb/data --cov-fail-under=85 -x
```

---

## Success Criteria

### Functional Requirements
- [ ] All 130+ tests passing
- [ ] All target modules ≥85% coverage
- [ ] Overall coverage ≥85%
- [ ] External APIs properly mocked
- [ ] Error handling tested for all scenarios
- [ ] Timezone handling validated

### Quality Requirements
- [ ] All quality gates (G1-G10) passing
- [ ] No linting errors
- [ ] No type checking errors
- [ ] No security vulnerabilities
- [ ] All functions ≤50 LOC
- [ ] Test execution time < 5 minutes

### Documentation Requirements
- [ ] Test patterns documented
- [ ] Mocking strategy documented
- [ ] Fixture library documented
- [ ] Sprint completion report created
- [ ] Coverage roadmap updated

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| API rate limits during testing | Medium | Medium | Use mocking, offline fixtures |
| Complex data structures | High | Medium | Create comprehensive fixtures |
| Time-sensitive tests | Medium | Low | Use `freezegun` for time mocking |
| Flaky tests | Low | High | Deterministic test data, proper setup |
| Insufficient time | Low | High | Prioritize P0 modules, defer P1 |

---

## Deliverables

### Code
- [ ] `tests/data/providers/test_zerodha.py` (40 tests)
- [ ] `tests/data/providers/test_binance.py` (35 tests)
- [ ] `tests/data/test_historical_data.py` (25 tests)
- [ ] `tests/data/test_market_data.py` (30 tests)
- [ ] `tests/data/conftest.py` (fixtures)

### Documentation
- [ ] Sprint 2 completion report
- [ ] Data provider testing guide
- [ ] Mocking patterns document
- [ ] Updated coverage roadmap

### Artifacts
- [ ] Coverage reports (HTML + text)
- [ ] Quality gate results
- [ ] Performance test results
- [ ] Integration test logs

---

## Next Steps (Post-Sprint 2)

1. **Sprint 3 Planning**
   - Review Sprint 2 results
   - Identify lessons learned
   - Plan Sprint 3: Core Infrastructure

2. **CI/CD Integration**
   - Add data provider tests to CI pipeline
   - Set up coverage trend monitoring
   - Configure quality gate automation

3. **Production Readiness**
   - Verify all data providers work in production
   - Test with real API credentials (staging)
   - Validate data quality in production

---

## References

- [Coverage Roadmap](./COVERAGE_ROADMAP.md)
- [Testing Infrastructure Improvements](../TESTING_INFRASTRUCTURE_IMPROVEMENTS.md)
- [Validation Checklist Fix Report](../VALIDATION_CHECKLIST_FIX_REPORT.md)
- [Deployment Guide](../DEPLOYMENT.md)

---

**Sprint Owner**: Development Team  
**Sprint Start**: April 21, 2026  
**Sprint End**: April 25, 2026  
**Status**: 🚀 Ready to Start

**Expected Outcome**: 
- 130+ new tests
- 85%+ coverage for data provider modules
- Overall coverage: 85%+ (from 76.58%)
- All quality gates passing