# IATB Test Coverage Proposal — 0%-30% Coverage Modules

> **Status**: PROPOSAL — Sequential Test Implementation Plan
> **Date**: 2026-05-08
> **Current Coverage**: 25.37% (18240 statements, 4504 missing)
> **Target Coverage**: ≥90% per pyproject.toml `cov-fail-under=90`
> **Total Modules Below 30%**: 109 out of 158 source modules
> **Reference**: ARCHITECTURE_REVIEW_VALIDATION_PLAN.md

---

## Executive Summary

The current test coverage at 25.37% is critically below the 90% gate threshold (G6). This proposal identifies **109 modules** below 30% coverage, organized into **5 priority tiers** based on architectural criticality, mocking complexity, and dependency chain order. Each tier is sequenced so that foundational modules are tested first, enabling downstream modules to reuse test fixtures and mocks.

**Strategy**: Start with pure-Decimal math modules (zero external dependencies) → build mock infrastructure → tackle I/O-heavy and async modules → finally cover UI/integration modules. This maximizes coverage gains per effort unit and establishes reusable test patterns.

---

## TIER 1: Pure Logic — Zero External Dependencies (Priority: P0-CRITICAL)

These modules use only Decimal arithmetic with no I/O, network, database, or file dependencies. They are the **fastest coverage wins** and should be implemented first.

### 1.1 `selection/correlation_matrix.py` — Coverage: 10.29%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/selection/correlation_matrix.py` (75 LOC) |
| **Test File** | `tests/selection/test_correlation_matrix_coverage.py` (NEW) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\selection\test_correlation_matrix_coverage.py` |
| **Existing Test** | `tests/selection/test_correlation_matrix.py` — exists but insufficient coverage |

**Public Functions to Test:**

| Function | Line | Coverage Intent |
|----------|------|-----------------|
| `compute_pairwise_correlations()` | 11 | All branch paths: 0, 1, 2, 3+ instruments |
| `_returns()` | 31 | Zero previous price, normal returns |
| `_pearson()` | 45 | Perfect +1, -1, 0 correlation; zero variance; clamping |
| `_mean()` | 72 | Normal mean, empty list edge case |

**Test Scenarios (Sequential):**

1. **Happy path**: Two instruments with known price series → verify correlation value within tolerance
2. **Happy path**: Three instruments → verify all three pairs computed
3. **Perfect correlation**: Identical price series → correlation ≈ 1.0
4. **Perfect anti-correlation**: Inverse series → correlation ≈ -1.0
5. **Edge: Single symbol** → returns empty dict
6. **Edge: Zero variance series** → correlation 0 (division by zero handled)
7. **Edge: Different length series** → trimmed to min length
8. **Edge: Clamping** → correlation result outside [-1,1] gets clamped
9. **Error: Price series <2 points** → `ConfigError`
10. **Error: Empty price series** → `ConfigError`

**Mocking Required**: None — pure Decimal math

---

### 1.2 `risk/position_sizer.py` — Coverage: 11.94%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/risk/position_sizer.py` (128 LOC) |
| **Test File** | `tests/risk/test_position_sizer_coverage.py` (NEW) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\risk\test_position_sizer_coverage.py` |
| **Existing Test** | None found — no dedicated test file |

**Public Functions to Test:**

| Function | Line | Coverage Intent |
|----------|------|-----------------|
| `lot_rounded_size()` | 20 | All branches: below lot, exact multiple, remainder |
| `freeze_limit_slices()` | 31 | Single slice, multiple slices, freeze < lot error |
| `fixed_fractional_size()` | 57 | Standard calculation with lot_size rounding |
| `kelly_fraction()` | 71 | Positive, negative, > max_fraction, bounded |
| `volatility_adjusted_size()` | 91 | High vol floored, low vol capped, standard |
| `_validate_inputs()` | 116 | All validation branches |

**Test Scenarios (Sequential):**

1. **Happy path**: `lot_rounded_size(150, 50)` → 150
2. **Happy path**: `freeze_limit_slices(300, 50, 200)` → [200, 100]
3. **Happy path**: `fixed_fractional_size` with typical Decimal inputs
4. **Happy path**: `kelly_fraction(0.6, 2.0)` → positive bounded result
5. **Happy path**: `volatility_adjusted_size` with standard inputs
6. **Edge: `lot_rounded_size` raw < lot** → 0
7. **Edge: `kelly_fraction` negative** → returns 0
8. **Edge: `kelly_fraction` > max_fraction** → returns max_fraction
9. **Edge: `volatility_adjusted_size` high vol** → fraction floored at 0.01
10. **Edge: `volatility_adjusted_size` low vol** → fraction capped at 0.5
11. **Error: `lot_size <= 0`** → `ConfigError`
12. **Error: `freeze_limit <= 0`** → `ConfigError`
13. **Error: stop distance = 0** → `ConfigError`
14. **Error: equity ≤ 0** → `ConfigError`
15. **Error: risk_fraction outside (0, 0.5]** → `ConfigError`
16. **Error: realized_volatility ≤ 0** → `ConfigError`

**Mocking Required**: None — pure Decimal math

---

### 1.3 `market_strength/breadth.py` — Coverage: 12.07%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/market_strength/breadth.py` (62 LOC) |
| **Test File** | `tests/market_strength/test_breadth_coverage.py` (NEW) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\market_strength\test_breadth_coverage.py` |
| **Existing Test** | `tests/market_strength/test_breadth.py` — exists but insufficient |

**Public Functions to Test:**

| Function | Line | Coverage Intent |
|----------|------|-----------------|
| `advance_decline_ratio()` | 11 | Normal, zero advancers, zero decliners |
| `up_down_volume_ratio()` | 22 | Normal, zero up_volume, zero down_volume |
| `mcclellan_oscillator()` | 33 | Full computation, short series, EMA validation |
| `_ema()` | 54 | Known values, single element, empty |

**Test Scenarios (Sequential):**

1. **Happy path**: `advance_decline_ratio(3, 2)` → Decimal("1.5")
2. **Happy path**: `up_down_volume_ratio(100, 50)` → Decimal("2")
3. **Happy path**: `mcclellan_oscillator` with typical advance/decline sequences
4. **Edge: advancers=0** → returns 0
5. **Edge: up_volume=0** → returns 0
6. **Edge: Very short advance/decline series** for McClellan
7. **Edge: Single-element series** for `_ema`
8. **Error: Negative advancers** → `ConfigError`
9. **Error: decliners=0** → `ConfigError`
10. **Error: Negative volumes** → `ConfigError`
11. **Error: empty advances/declines** → `ConfigError`
12. **Error: unequal lengths** → `ConfigError`
13. **Error: short_period ≤ 0 or ≥ long_period** → `ConfigError`

**Mocking Required**: None — pure Decimal math

---

### 1.4 `selection/sector_strength.py` — Coverage: 18.52%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/selection/sector_strength.py` (21 LOC) |
| **Test File** | `tests/selection/test_sector_strength_coverage.py` (NEW) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\selection\test_sector_strength_coverage.py` |

**Test Scenarios**: Compute sector strength, empty sectors, single sector, Decimal precision validation.

**Mocking Required**: None

---

### 1.5 `selection/decay.py` — Coverage: 22.73%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/selection/decay.py` (34 LOC) |
| **Test File** | `tests/selection/test_decay_coverage.py` (NEW) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\selection\test_decay_coverage.py` |

**Test Scenarios**: Exponential/time decay computation, half-life boundary, zero/negative inputs, Decimal output validation.

**Mocking Required**: None

---

### 1.6 `selection/_util.py` — Coverage: 25.64%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/selection/_util.py` (29 LOC) |
| **Test File** | `tests/selection/test_util_coverage.py` (NEW — augment existing `test_util.py`) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\selection\test_util_coverage.py` |

**Test Scenarios**: Utility functions for safe Decimal extraction, None handling, type coercion.

**Mocking Required**: None

---

### 1.7 `visualization/alerts.py` — Coverage: 18.46%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/visualization/alerts.py` (51 LOC) |
| **Test File** | `tests/visualization/test_alerts_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\visualization\test_alerts_coverage.py` |

**Test Scenarios**: TelegramAlertDispatcher rate-limiting, send methods, initialization. Mock: `httpx`/`requests` for Telegram API.

**Mocking Required**: `httpx` or `requests` HTTP POST for Telegram Bot API

---

### 1.8 `sentiment/volume_filter.py` — Coverage: 26.67%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/sentiment/volume_filter.py` (11 LOC) |
| **Test File** | `tests/sentiment/test_volume_filter_coverage.py` (NEW) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\sentiment\test_volume_filter_coverage.py` |

**Test Scenarios**: Volume threshold filtering, zero volume, Decimal precision.

**Mocking Required**: None

---

**TIER 1 Summary**: 8 modules, ~411 LOC total, estimated **+12% coverage gain** with minimal effort.

---

## TIER 2: Internal Validation & Computation — Minimal Mocking (Priority: P0-HIGH)

These modules require only internal type/enum mocking (already available in the codebase). No external APIs, databases, or network calls.

### 2.1 `core/event_validation.py` — Coverage: 10.70%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/core/event_validation.py` (305 LOC) |
| **Test File** | `tests/core/test_event_validation_coverage.py` (NEW) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\core\test_event_validation_coverage.py` |
| **Existing Test** | `tests/core/test_event_validation.py` — exists but 10.70% coverage |

**Public Functions to Test:**

| Function | Line | Coverage Intent |
|----------|------|-----------------|
| `validate_event()` | 34 | All 6 event type dispatches + unsupported type |
| `_validate_timestamp()` | 57 | UTC-aware pass, naive fail |
| `_validate_exchange()` | 70 | Valid Exchange enum pass, invalid fail |
| `_validate_order_side()` | 78 | Valid/invalid OrderSide |
| `_validate_order_type()` | 86 | Valid/invalid OrderType |
| `_validate_market_tick_event()` | 94 | Full validation: price ranges, bid≤ask, volume |
| `_validate_order_update_event()` | 125 | Status-specific: FILLED with zero fill, filled>quantity |
| `_validate_signal_event()` | 160 | Confidence [0,1] bounds, optional price |
| `_validate_scan_update_event()` | 176 | Count ordering: total≥approved≥trades |
| `_validate_pnl_update_event()` | 217 | Decimal ranges, negative trade_pnl |
| `_validate_regime_change_event()` | 239 | Metadata dict str keys/values |
| `_as_decimal()` | 259 | Type conversion + fail-closed |
| `_validate_decimal_range()` | 267 | Inclusive bounds, boundary values |
| `_validate_non_empty_text()` | 279 | Empty after strip, max length |
| `_get_attr()` | 293 | Missing attribute → ValidationError |
| `_get_optional_attr()` | 301 | Missing → None, present → value |

**Test Scenarios (Sequential — 24 minimum):**

1. Valid `MarketTickEvent` with all fields including optional bid/ask
2. Valid `OrderUpdateEvent` with FILLED status and positive filled_quantity
3. Valid `SignalEvent` with optional price
4. Valid `ScanUpdateEvent` with zero errors list
5. Valid `PnLUpdateEvent` with negative trade_pnl
6. Valid `RegimeChangeEvent` with metadata
7. **Edge: Unsupported event type name** → `ValidationError`
8. **Edge: Missing required attribute** → `ValidationError`
9. **Edge: Timestamp without tzinfo** → `ValidationError`
10. **Edge: bid_price > ask_price** → `ValidationError`
11. **Edge: filled_quantity > quantity** → `ValidationError`
12. **Edge: FILLED status with zero filled_quantity** → `ValidationError`
13. **Edge: approved_candidates > total_candidates** → `ValidationError`
14. **Edge: Empty symbol string** → `ValidationError`
15. **Edge: confidence exactly 0 and exactly 1** → pass
16. **Edge: confidence > 1** → `ValidationError`
17. **Error: Non-Decimal price** → `ValidationError`
18. **Error: Invalid exchange type** → `ValidationError`
19. **Error: errors field is not a list** → `ValidationError`
20. **Error: errors list contains non-string** → `ValidationError`
21. **Error: Non-string metadata key** → `ValidationError`
22. **Error: `_as_decimal` with bool** → `ValidationError`
23. **Edge: `_validate_decimal_range` at boundary** → pass
24. **Edge: `_validate_non_empty_text` at max length** → pass

**Mocking Required**: Internal only — `Exchange`, `OrderSide`, `OrderStatus`, `OrderType` enums; `ValidationError`; `create_timestamp`. All available in codebase.

---

### 2.2 `data/validator.py` — Coverage: 13.33%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/data/validator.py` (90 LOC) |
| **Test File** | `tests/data/test_validator_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\data\test_validator_coverage.py` |

**Public Functions to Test:**

| Function | Line | Coverage Intent |
|----------|------|-----------------|
| `validate_ohlcv_bar()` | 33 | OHLCV relationships: high≥max, low≤min, non-negative |
| `validate_ohlcv_series()` | 54 | Series consistency: single symbol, increasing timestamps |
| `validate_ticker_snapshot()` | 75 | bid≤ask, last within spread, non-negative |
| `_require_non_empty_text()` | 15 | Empty/whitespace-only → ValidationError |
| `_validate_non_negative()` | 21 | Negative value → ValidationError |
| `_validate_timestamp_not_far_future()` | 27 | Future > 2min → ValidationError |

**Test Scenarios (Sequential — 18 minimum):**

1. Valid OHLCV bar with high=max, low=min, past timestamp
2. Valid series with strictly increasing timestamps
3. Valid TickerSnapshot with bid≤ask and last within spread
4. **Edge: high exactly = max(open, close, low)** → pass
5. **Edge: low exactly = min(open, close, high)** → pass
6. **Edge: timestamp at exactly now+2min boundary** → pass
7. **Edge: bid=ask** (zero spread) → pass
8. **Edge: volume=0** → pass (non-negative)
9. **Error: Empty symbol** → `ValidationError`
10. **Error: Negative price** → `ValidationError`
11. **Error: high < open/close/low** → `ValidationError`
12. **Error: low > open/close/high** → `ValidationError`
13. **Error: Future timestamp beyond skew** → `ValidationError`
14. **Error: Mixed symbols in series** → `ValidationError`
15. **Error: Mixed exchanges in series** → `ValidationError`
16. **Error: Non-increasing timestamps** → `ValidationError`
17. **Error: bid > ask** → `ValidationError`
18. **Error: last outside spread** → `ValidationError`

**Mocking Required**: `freezegun` or manual `datetime.now(UTC)` override for timestamp tests. Internal: `OHLCVBar`, `TickerSnapshot`, `ValidationError`.

---

### 2.3 `sentiment/helpers.py` — Coverage: 11.70%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/sentiment/helpers.py` (111 LOC) |
| **Test File** | `tests/sentiment/test_helpers_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\sentiment\test_helpers_coverage.py` |

**Public Functions to Test:**

| Function | Line | Coverage Intent |
|----------|------|-----------------|
| `resolve_aion_predictor()` | 18 | Module with predict/analyze/AionSentiment class |
| `validate_and_parse_aion_prediction()` | 40 | Dict, tuple, string parsing paths |
| `resolve_finbert_predictor()` | 58 | Transformers pipeline resolution |
| `parse_finbert_label_score()` | 85 | Prediction list parsing |
| `compute_weighted_ensemble()` | 95 | Weighted score + confidence computation |

**Test Scenarios (Sequential — 16 minimum):**

1. `resolve_aion_predictor` with module exposing `predict` function
2. `resolve_aion_predictor` with `AionSentiment` class
3. `validate_and_parse_aion_prediction` with dict (label+score)
4. `validate_and_parse_aion_prediction` with dict (sentiment+confidence)
5. `validate_and_parse_aion_prediction` with tuple input
6. `validate_and_parse_aion_prediction` with string input → label=string, confidence=0.70
7. `resolve_finbert_predictor` with valid transformers mock
8. `parse_finbert_label_score` with valid prediction list
9. `compute_weighted_ensemble` with multiple components
10. **Edge: AION dict with only "label" key** → defaults confidence to "0.70"
11. **Edge: Empty predictions list** → `ConfigError`
12. **Edge: Zero total_weight** (division by zero)
13. **Error: `aion_sentiment` not installed** → `ConfigError`
14. **Error: Module installed but no usable interface** → `ConfigError`
15. **Error: `transformers` not installed** → `ConfigError`
16. **Error: Unsupported AION prediction format** → `ConfigError`

**Mocking Required**: `aion_sentiment` module (MagicMock), `transformers` module (MagicMock with `pipeline()` callable)

---

### 2.4 `ml/feature_engine.py` — Coverage: 14.66%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/ml/feature_engine.py` (160 LOC) |
| **Test File** | `tests/ml/test_feature_engine_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\ml\test_feature_engine_coverage.py` |

**Public Functions to Test:**

| Function | Line | Coverage Intent |
|----------|------|-----------------|
| `FeatureEngineer.__init__()` | 14 | volatility_window validation (min 2) |
| `FeatureEngineer.build_features()` | 20 | Full pipeline with OHLCV/sentiment/regime/time |
| `_validate_lengths()` | 38 | Mismatched lengths, <2 rows, non-UTC timestamps |
| `_build_raw_vectors()` | 56 | Returns, rolling dispersion, MA trend, volume ratio |
| `_regime_one_hot()` | 114 | BULL/BEAR/NEUTRAL encoding |
| `_time_features()` | 123 | Hour/minute normalization to [0,1] |
| `_robust_scale()` | 129 | IQR scaling, zero IQR handled |
| `_median()` / `_iqr()` / `_mean()` | 143-159 | Decimal stats utilities |

**Test Scenarios (Sequential — 12 minimum):**

1. 3+ rows of valid OHLCV/sentiment/regime/timestamps → correctly shaped feature vectors
2. Regime "BULL"/"BEAR"/"NEUTRAL" one-hot encoding verification
3. Time features normalized to [0,1] range
4. **Edge: `volatility_window=2`** (minimum)
5. **Edge: Exactly 2 rows** (minimum for returns)
6. **Edge: IQR=0** → divisor replaced with 1
7. **Edge: volume_prev=0** → divisor replaced with 1
8. **Error: `volatility_window < 2`** → `ConfigError`
9. **Error: Mismatched input lengths** → `ConfigError`
10. **Error: Fewer than 2 rows** → `ConfigError`
11. **Error: Non-UTC timestamps** → `ConfigError`
12. **Error: Missing OHLCV key** → `ConfigError`

**Mocking Required**: None — pure computation with internal `ConfigError`

---

### 2.5 `ml/readiness.py` — Coverage: 14.63%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/ml/readiness.py` (95 LOC) |
| **Test File** | `tests/ml/test_readiness_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\ml\test_readiness_coverage.py` |

**Test Scenarios**: All models available → AVAILABLE; some unavailable → DEGRADED; zero available → ERROR; registry exception → ERROR. Mock: `get_registry()` + `RegistryStatus`.

**Mocking Required**: `iatb.ml.model_registry.get_registry()` → returns mock `RegistryStatus`

---

### 2.6 `data/normalizer.py` — Coverage: 14.29%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/data/normalizer.py` (139 LOC) |
| **Test File** | `tests/data/test_normalizer_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\data\test_normalizer_coverage.py` |

**Test Scenarios**: Valid OHLCV record with datetime/unix/ISO timestamps; batch normalization; missing required key → ValidationError; boolean value → ValidationError; non-finite Decimal → ValidationError; unsupported timestamp type → ValidationError; batch error with index context.

**Mocking Required**: Internal: `create_price`, `create_quantity`, `create_timestamp`, `OHLCVBar`, `validate_ohlcv_bar/series`

---

**TIER 2 Summary**: 6 modules, ~900 LOC total, estimated **+8% coverage gain**.

---

## TIER 3: File I/O & Database — Moderate Mocking (Priority: P1-HIGH)

These modules require mocking file I/O, DuckDB, SQLite, or asyncio patterns. Test infrastructure (fixtures, temp directories) must be built first.

### 3.1 `storage/duckdb_store.py` — Coverage: 10.27%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/storage/duckdb_store.py` (628 LOC) |
| **Test File** | `tests/storage/test_duckdb_store_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\storage\test_duckdb_store_coverage.py` |
| **Existing Test** | `tests/storage/test_duckdb_store.py` — exists but 10.27% |

**Public Functions to Test:**

| Function | Line | Coverage Intent |
|----------|------|-----------------|
| `_normalize_timestamp()` | 18 | datetime, str, Z-suffixed, invalid types |
| `DuckDBStore.__init__()` | 38 | db_path, reconnect limits |
| `DuckDBStore.close()` | 69 | Safe close, already closed |
| `DuckDBStore.initialize()` | 78 | Table creation, idempotent |
| `DuckDBStore.store_bars()` | 100 | Upsert with delete+insert |
| `DuckDBStore.load_bars()` | 146 | Time range, limit, symbol filter |
| `DuckDBStore.query_vwap()` | 220 | VWAP computation |
| `DuckDBStore.query_daily_summary()` | 249 | Daily OHLCV aggregation |
| `DuckDBStore.query_performance_ranking()` | 334 | Top N by return % |
| `DuckDBStore.query_volatility()` | 377 | Rolling std deviation |
| `DuckDBStore.query_moving_averages()` | 420 | SMA computation |
| `DuckDBStore.query_correlation_matrix()` | 460 | Pairwise correlations |
| `DuckDBStore.query_parquet()` | 563 | Parquet file read via DuckDB |
| `DuckDBStore.migrate_parquet_to_duckdb()` | 572 | Parquet → DuckDB migration |
| `DuckDBStore.archive_to_parquet()` | 597 | DuckDB → Parquet export |

**Test Scenarios (Sequential — 25 minimum):**

1. Initialize store, store bars, load bars back → round-trip
2. query_vwap with data → correct VWAP
3. query_daily_summary → daily OHLCV aggregation
4. query_performance_ranking with multiple symbols
5. query_volatility with rolling window
6. query_moving_averages → SMA values
7. query_correlation_matrix with 2+ symbols
8. query_parquet → read from parquet file
9. migrate_parquet_to_duckdb → data loaded into DuckDB
10. archive_to_parquet → data exported to parquet
11. **Edge: Empty bars list** for store_bars
12. **Edge: limit=0** → ConfigError
13. **Edge: window<=0** → ConfigError
14. **Edge: Fewer than 2 symbols** for correlation → ConfigError
15. **Edge: Connection already closed** during close()
16. **Edge: Reconnect exhaustion** after max attempts
17. **Error: DuckDB module not installed** → ConfigError
18. **Error: Invalid timestamp string** → ConfigError
19. **Error: SQL execution errors** → handled
20. **Error: Path permission errors** on archive

**Mocking Required**: `duckdb` module (in-memory `:memory:` connection for testing), `Path` for parquet file I/O. Use `tmp_path` pytest fixture.

---

### 3.2 `storage/sqlite_store.py` — Coverage: 19.07%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/storage/sqlite_store.py` (192 LOC) |
| **Test File** | `tests/storage/test_sqlite_store_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\storage\test_sqlite_store_coverage.py` |

**Test Scenarios**: CRUD operations, time-range queries, symbol/strategy filters, WAL mode, batch INSERT. Use `tmp_path` fixture for temp DB files.

**Mocking Required**: `sqlite3` (use real in-memory SQLite for integration tests)

---

### 3.3 `storage/parquet_store.py` — Coverage: 18.96%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/storage/parquet_store.py` (167 LOC) |
| **Test File** | `tests/storage/test_parquet_store_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\storage\test_parquet_store_coverage.py` |

**Test Scenarios**: Write/read round-trip, cross-file queries, compression codec, retention policy cleanup, date-based partition sub-directories.

**Mocking Required**: `pyarrow` / `pandas` for parquet I/O (use real parquet with `tmp_path`)

---

### 3.4 `storage/backup.py` — Coverage: 19.88%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/storage/backup.py` (263 LOC) |
| **Test File** | `tests/storage/test_backup_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\storage\test_backup_coverage.py` |

**Test Scenarios**: `export_trading_state`/`load_trading_state` round-trip, JSON serialization of positions/orders, corrupt state file handling, missing directory creation.

**Mocking Required**: File I/O (`Path.write_text/read_text`), `json` — use `tmp_path`

---

### 3.5 `storage/git_sync.py` — Coverage: 22.54%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/storage/git_sync.py` (112 LOC) |
| **Test File** | `tests/storage/test_git_sync_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\storage\test_git_sync_coverage.py` |

**Test Scenarios**: Push, pull_rebase, status, conflict resolution, auth check, retry logic. Use real git repo in `tmp_path`.

**Mocking Required**: `subprocess.run` for git commands (or use real git in temp dir)

---

### 3.6 `storage/audit_exporter.py` — Coverage: 27.57%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/storage/audit_exporter.py` (201 LOC) |
| **Test File** | `tests/storage/test_audit_exporter_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\storage\test_audit_exporter_coverage.py` |

**Test Scenarios**: Export formats (JSON, CSV), compress flag (dead code per architecture review), date range filtering, empty results.

**Mocking Required**: File I/O, `json`/`csv` — use `tmp_path`

---

### 3.7 `storage/audit_scheduler.py` — Coverage: 27.52%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/storage/audit_scheduler.py` (117 LOC) |
| **Test File** | `tests/storage/test_audit_scheduler_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\storage\test_audit_scheduler_coverage.py` |

**Test Scenarios**: Schedule creation, periodic execution, cancel, missed schedule handling, timezone-aware scheduling.

**Mocking Required**: `asyncio` event loop, `AuditExporter`

---

### 3.8 `core/event_persistence.py` — Coverage: 15.07%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/core/event_persistence.py` (496 LOC) |
| **Test File** | `tests/core/test_event_persistence_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\core\test_event_persistence_coverage.py` |

**Public Functions to Test:**

| Function | Line | Coverage Intent |
|----------|------|-----------------|
| `EventPersistence.save_event()` | 89 | JSON file creation with correct structure |
| `EventPersistence.load_events()` | 132 | Sequence range filtering, topic directory |
| `EventPersistence.replay_events()` | 197 | Callback invocation, delay, deserialized objects |
| `EventPersistence.clear_events()` | 231 | Topic-specific and full clear |
| `EventPersistence.get_event_count()` | 267 | Count for topic |
| `_serialize_event()` | 288 | model_dump, __dict__, dict, fallback paths |
| `_deserialize_event()` | 314 | 6 specific deserializers + fallback |
| 6 `_deserialize_*_event()` | 390-487 | Each event type reconstruction |

**Test Scenarios (Sequential — 18 minimum):**

1. Save event → JSON file created with correct structure
2. Load events → returns list sorted by sequence
3. Replay events → callback called with deserialized event objects
4. Clear events for specific topic
5. get_event_count returns correct count
6. **Edge: Load with start_sequence/end_sequence filtering**
7. **Edge: Topic directory doesn't exist** → empty list
8. **Edge: Replay with delay_ms > 0**
9. **Edge: Save Pydantic model** (has `model_dump`)
10. **Edge: Save plain dict**
11. **Error: Save event fails** → EventBusError
12. **Error: Invalid JSON in event file** → _parse_event_file returns None
13. **Error: Load events fails** → EventBusError
14. **Error: Replay single event fails** → returns False, count not incremented

**Mocking Required**: File I/O (`Path.open/mkdir/glob/unlink`, `json.load/dump`) — use `tmp_path`. Internal: event classes, enums, types.

---

### 3.9 `core/sse_broadcaster.py` — Coverage: 14.19%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/core/sse_broadcaster.py` (269 LOC) |
| **Test File** | `tests/core/test_sse_broadcaster_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\core\test_sse_broadcaster_coverage.py` |

**Test Scenarios**: Start/stop lifecycle, subscribe/unsubscribe, event forwarding, queue full → dead subscriber removal, keepalive, generic event fallback, singleton `get_broadcaster()`.

**Mocking Required**: `EventBus` (subscribe method), `asyncio.Queue`, `asyncio.Task`

---

**TIER 3 Summary**: 9 modules, ~2,645 LOC total, estimated **+10% coverage gain**.

---

## TIER 4: External APIs & Async — Heavy Mocking (Priority: P1-MEDIUM)

These modules require mocking external APIs (KiteConnect, Redis, Telegram, OpenAlgo) and async test patterns.

### 4.1 `data/token_resolver.py` — Coverage: 11.98%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/data/token_resolver.py` (532 LOC) |
| **Test File** | `tests/data/test_token_resolver_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\data\test_token_resolver_coverage.py` |

**Test Scenarios (Sequential — 20 minimum):**

1. `resolve_token` with symbol found in InstrumentMaster cache
2. `resolve_token` with cache miss → API fallback → success
3. `resolve_multiple_tokens` with mix of cached and API-resolved symbols
4. `_extract_instrument_from_api` with valid dict
5. `_parse_instrument_token` with int and str inputs
6. **Edge: Empty symbol** → ConfigError
7. **Edge: Unsupported exchange** → ConfigError
8. **Edge: force_refresh=True** bypasses cache
9. **Edge: Rate-limit** — second refresh within 1 minute
10. **Edge: kite_provider is None and cache miss** → ConfigError
11. **Edge: Partial failures** in resolve_multiple_tokens
12. **Edge: _safe_decimal** with int, str, float, Decimal, invalid types
13. **Edge: _parse_expiry** with datetime, ISO string, None, empty
14. **Error: Kite API returns non-list** → ConfigError
15. **Error: Kite API exception** → ConfigError
16. **Error: SQLite connection failure** → logged, returns 0
17. **Error: All symbols fail** → ConfigError

**Mocking Required**: `kite_provider._get_client()` → mock with `instruments()` method; `InstrumentMaster.get_instrument()`; `sqlite3` (use in-memory); `asyncio.to_thread`

---

### 4.2 `execution/order_manager.py` — Coverage: 12.94%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/execution/order_manager.py` (565 LOC) |
| **Test File** | `tests/execution/test_order_manager_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\execution\test_order_manager_coverage.py` |

**Test Scenarios (Sequential — 22 minimum):**

1. `place_order` with all gates passing → ExecutionResult returned
2. `place_order_async` equivalent behavior
3. `update_market_data` propagates to risk pipeline
4. `receive_heartbeat` with valid UTC datetime
5. `save_state`/`load_state` round-trip
6. `check_dead_man_switch` with fresh heartbeat → False
7. Duplicate detection for OPEN/PENDING orders → returns existing result
8. **Edge: heartbeat_timeout_seconds <= 0** → ConfigError
9. **Edge: check_dead_man_switch with no prior heartbeat** → cancels all
10. **Edge: Stale heartbeat** triggers cancel
11. **Edge: load_state with missing file** → logged warning
12. **Edge: Corrupt JSON** → logged error
13. **Edge: Partial fill scenarios**
14. **Edge: Position flip (long→short, short→long)**
15. **Edge: Weighted average entry price calculation**
16. **Error: Kill switch engaged** → ConfigError
17. **Error: Throttle exceeded** → ConfigError
18. **Error: Risk pipeline rejects** → ConfigError
19. **Error: save_state path permission error**

**Mocking Required**: Executor (cancel_all), KillSwitch, OrderThrottle, PreTradeConfig, DailyLossGuard, TradeAuditLogger, RiskPipeline, `export_trading_state`, File I/O. Use `tmp_path`.

---

### 4.3 `broker/token_manager.py` — Coverage: 13.35%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/broker/token_manager.py` (726 LOC) |
| **Test File** | `tests/broker/test_token_manager_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\broker\test_token_manager_coverage.py` |

**Test Scenarios (Sequential — 20 minimum):**

1. `is_token_fresh()` with token created before 6 AM IST → True
2. `is_token_fresh()` with token created after 6 AM IST → False (next day)
3. `is_token_valid_for_pre_market()` at various IST times
4. `should_refresh_token()` with buffer_minutes
5. `auto_refresh_token()` with TOTP secret
6. `exchange_request_token()` → access token
7. `store_access_token()` → keyring + .env persistence
8. `get_access_token()` with keyring → env → .env fallback chain
9. `get_kite_client()` → KiteConnect instance
10. `persist_session_tokens()` → both keyring and .env
11. **Edge: Token at 6 AM IST boundary**
12. **Edge: Token at 9 AM IST pre-market boundary**
13. **Edge: Empty .env file**
14. **Edge: .env.example resolves to .env path**
15. **Error: No token in keyring** → is_token_fresh returns False
16. **Error: TOTP secret not configured** → auto_refresh fails
17. **Error: API response missing access_token** → ConfigError
18. **Error: keyring PasswordDeleteError** during clear_token()
19. **Error: OSError reading .env** → handled

**Mocking Required**: `keyring` (get_password, set_password, delete_password), `pyotp` (TOTP), `kiteconnect.KiteConnect`, `urllib.request.urlopen`, File I/O for .env, `datetime.now(UTC)` injection

---

### 4.4 `data/kite_provider.py` — Coverage: 16.79%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/data/kite_provider.py` (637 LOC) |
| **Test File** | `tests/data/test_kite_provider_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\data\test_kite_provider_coverage.py` |

**Test Scenarios**: get_ohlcv, get_ohlcv_batch, get_ticker, from_env, rate limiter integration, retry with backoff, circuit breaker interaction, unsupported timeframe/exchange, batch partial failures.

**Mocking Required**: `kiteconnect.KiteConnect` (historical_data, quote), `RateLimiter`, `CircuitBreaker`, `retry_with_backoff`, `asyncio.to_thread`, `os.getenv`

---

### 4.5 `data/openalgo_provider.py` — Coverage: 15.48%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/data/openalgo_provider.py` (271 LOC) |
| **Test File** | `tests/data/test_openalgo_provider_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\data\test_openalgo_provider_coverage.py` |

**Test Scenarios**: get_ohlcv, get_ticker, connection pooling, HTTP GET, API key from env, JSON decode error, invalid URL.

**Mocking Required**: `http.client.HTTPConnection/HTTPSConnection`, `os.getenv`, `asyncio.to_thread`

---

### 4.6 `core/queue.py` — Coverage: 16.15%

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/core/queue.py` (421 LOC) |
| **Test File** | `tests/core/test_queue_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\core\test_queue_coverage.py` |

**Test Scenarios**: InProcessBackend start/stop/subscribe/publish/publish_batch/unsubscribe lifecycle; RedisStreamBackend lifecycle (mock Redis); create_backend factory; max_queue_size validation; backend not running error; publish to topic with no subscribers.

**Mocking Required**: `redis.asyncio` (for RedisStreamBackend), `asyncio.Queue/Task/Lock`

---

### 4.7 `visualization/dashboard.py` — Coverage: 9.75% (LOWEST)

| Item | Detail |
|------|--------|
| **Source** | `src/iatb/visualization/dashboard.py` (396 LOC) |
| **Test File** | `tests/visualization/test_dashboard_coverage.py` (NEW — augment existing) |
| **Storage** | `G:\IATB-02Apr26\IATB\tests\visualization\test_dashboard_coverage.py` |

**Test Scenarios**: build_dashboard_payload with all/missing tabs; render_dashboard with Streamlit mock; build_scanner_payload; render_health_matrix_table; render_approved_charts with/without OHLCV data; convert_candidates_to_health_matrix.

**Mocking Required**: `streamlit` (title, tabs, write, info, dataframe, subheader, header, divider, metric, columns, plotly_chart), `plotly.graph_objects` (Figure, Candlestick, Bar)

---

**TIER 4 Summary**: 7 modules, ~3,348 LOC total, estimated **+8% coverage gain**.

---

## TIER 5: Remaining Modules 20-30% Coverage (Priority: P2-MEDIUM)

These 86 remaining modules between 20-30% coverage follow the same patterns established in Tiers 1-4. Implementation is sequential within each sub-category.

### 5A: Pure Logic / Minimal Mocking (20 modules)

| Module | Coverage | Test File | Key Focus |
|--------|----------|-----------|-----------|
| `selection/selection_bridge.py` | 19.40% | `tests/selection/test_selection_bridge_coverage.py` | Bridge pattern, delegation |
| `selection/weight_optimizer.py` | 19.89% | `tests/selection/test_weight_optimizer_coverage.py` | Weight optimization, regime mapping |
| `selection/fundamental_filter.py` | 20.88% | `tests/selection/test_fundamental_filter_coverage.py` | PE/PB/ROE filters |
| `selection/technical_filter.py` | 21.28% | `tests/selection/test_technical_filter_coverage.py` | ADX/ATR/RSI filters |
| `selection/ic_monitor.py` | 26.87% | `tests/selection/test_ic_monitor_coverage.py` | Information coefficient tracking |
| `selection/selector_validator.py` | 28.12% | `tests/selection/test_selector_validator_coverage.py` | Pre-selection validation |
| `selection/multi_factor_scorer.py` | 33.22% | `tests/selection/test_multi_factor_scorer_coverage.py` | Factor scoring |
| `selection/drl_signal.py` | 25.00% | `tests/selection/test_drl_signal_coverage.py` | DRL signal computation |
| `rl/reward.py` | 18.81% | `tests/rl/test_reward_coverage.py` | Reward function, Sharpe |
| `rl/optimizer.py` | 17.74% | `tests/rl/test_optimizer_coverage.py` | Hyperparameter optimization |
| `rl/agent.py` | 18.39% | `tests/rl/test_agent_coverage.py` | RL agent predict/train |
| `rl/environment.py` | 24.00% | `tests/rl/test_environment_coverage.py` | Trading environment step/reset |
| `rl/callbacks.py` | 29.03% | `tests/rl/test_callbacks_coverage.py` | Training callbacks |
| `sentiment/recency_weighting.py` | 17.39% | `tests/sentiment/test_recency_weighting_coverage.py` | Time decay |
| `sentiment/base.py` | 28.89% | `tests/sentiment/test_base_coverage.py` | Base sentiment analyzer |
| `sentiment/aggregator.py` | 23.46% | `tests/sentiment/test_aggregator_coverage.py` | Weighted ensemble |
| `sentiment/news_analyzer.py` | 32.34% | `tests/sentiment/test_news_analyzer_coverage.py` | News sentiment |
| `sentiment/social_sentiment.py` | 29.49% | `tests/sentiment/test_social_sentiment_coverage.py` | Social media sentiment |
| `sentiment/vader_analyzer.py` | 30.23% | `tests/sentiment/test_vader_analyzer_coverage.py` | VADER compound scores |
| `sentiment/news_scraper.py` | 22.15% | `tests/sentiment/test_news_scraper_coverage.py` | Headline scraping |

### 5B: Risk & Execution Modules (15 modules)

| Module | Coverage | Test File | Key Focus |
|--------|----------|-----------|-----------|
| `risk/stop_loss.py` | 17.61% | `tests/risk/test_stop_loss_coverage.py` | Stop-loss computation |
| `risk/trailing_stop.py` | 22.16% | `tests/risk/test_trailing_stop_coverage.py` | Trailing stop update |
| `risk/daily_loss_guard.py` | 21.29% | `tests/risk/test_daily_loss_guard_coverage.py` | 2% NAV breach, kill switch engage |
| `risk/position_limit_guard.py` | 20.14% | `tests/risk/test_position_limit_guard_coverage.py` | Position limit enforcement |
| `risk/portfolio_risk.py` | 26.42% | `tests/risk/test_portfolio_risk_coverage.py` | Portfolio risk metrics |
| `risk/risk_disclosure.py` | 26.58% | `tests/risk/test_risk_disclosure_coverage.py` | Disclosure generation |
| `risk/risk_pipeline.py` | 24.15% | `tests/risk/test_risk_pipeline_coverage.py` | 7-step pipeline orchestration |
| `risk/risk_report.py` | 34.41% | `tests/risk/test_risk_report_coverage.py` | Risk report generation |
| `risk/kill_switch.py` | 34.25% | `tests/risk/test_kill_switch_coverage.py` | Kill switch engage/disengage |
| `risk/sebi_compliance.py` | 23.58% | `tests/risk/test_sebi_compliance_coverage.py` | SEBI compliance checks |
| `risk/sebi_live_validator.py` | 36.30% | `tests/risk/test_sebi_live_validator_coverage.py` | Live SEBI validation harness |
| `risk/circuit_breaker.py` | 35.90% | `tests/risk/test_circuit_breaker_coverage.py` | Circuit breaker states |
| `execution/paper_executor.py` | 23.57% | `tests/execution/test_paper_executor_coverage.py` | Paper fill, slippage |
| `execution/pre_trade_validator.py` | 25.81% | `tests/execution/test_pre_trade_validator_coverage.py` | 5 validation gates |
| `execution/order_throttle.py` | 27.03% | `tests/execution/test_order_throttle_coverage.py` | 10 orders/sec throttle |

### 5C: Core & Data Modules (12 modules)

| Module | Coverage | Test File | Key Focus |
|--------|----------|-----------|-----------|
| `core/clock.py` | 23.95% | `tests/core/test_clock_coverage.py` | UTC clock, IST conversion, drift |
| `core/preflight.py` | 22.39% | `tests/core/test_preflight_coverage.py` | Preflight checks, clock drift |
| `core/observability/tracing.py` | 22.22% | `tests/core/test_observability_tracing_coverage.py` | OTel tracing setup |
| `core/observability/alerting.py` | 23.27% | `tests/core/test_observability_alerting_coverage.py` | Telegram alerting |
| `core/pipeline_checkpoint.py` | 26.36% | `tests/core/test_pipeline_checkpoint_coverage.py` | Checkpoint save/restore |
| `core/config_manager.py` | 27.50% | `tests/core/test_config_manager_coverage.py` | TOML persistence |
| `core/runtime.py` | 27.52% | `tests/core/test_runtime_coverage.py` | Application lifecycle |
| `core/scaling.py` | 27.86% | `tests/core/test_scaling_coverage.py` | Cluster scaling |
| `core/types.py` | 26.47% | `tests/core/test_types_coverage.py` | create_price/quantity/timestamp |
| `core/strategy_runner.py` | 24.61% | `tests/core/test_strategy_runner_coverage.py` | Strategy execution |
| `core/pipeline_health.py` | 36.84% | `tests/core/test_pipeline_health_coverage.py` | Health monitoring |
| `core/secrets_rotation.py` | 35.36% | `tests/core/test_secrets_rotation_coverage.py` | Secret rotation |

### 5D: ML & Backtesting Modules (12 modules)

| Module | Coverage | Test File | Key Focus |
|--------|----------|-----------|-----------|
| `ml/trainer.py` | 20.00% | `tests/ml/test_trainer_coverage.py` | Model training loop |
| `ml/predictor.py` | 20.00% | `tests/ml/test_predictor_coverage.py` | Model prediction |
| `ml/hmm_model.py` | 20.25% | `tests/ml/test_hmm_model_coverage.py` | HMM model |
| `ml/gnn_model.py` | 22.09% | `tests/ml/test_gnn_model_coverage.py` | GNN model |
| `ml/transformer_model.py` | 25.93% | `tests/ml/test_transformer_model_coverage.py` | Transformer model |
| `ml/model_registry.py` | 22.28% | `tests/ml/test_model_registry_coverage.py` | Model registry |
| `ml/tracking.py` | 18.18% | `tests/ml/test_tracking_coverage.py` | Experiment tracking |
| `ml/lstm_model.py` | 26.58% | `tests/ml/test_lstm_model_coverage.py` | LSTM model |
| `ml/base.py` | 33.33% | `tests/ml/test_base_coverage.py` | ML base class |
| `backtesting/session_masks.py` | 14.68% | `tests/backtesting/test_session_masks_coverage.py` | Session masking |
| `backtesting/vectorbt_engine.py` | 24.84% | `tests/backtesting/test_vectorbt_engine_coverage.py` | VectorBT engine |
| `backtesting/walk_forward.py` | 28.89% | `tests/backtesting/test_walk_forward_coverage.py` | Walk-forward analysis |

### 5E: Scanner, Broker, Strategies & Viz (27 modules)

| Module | Coverage | Test File |
|--------|----------|-----------|
| `scanner/scan_cycle.py` | 20.49% | `tests/scanner/test_scan_cycle_coverage.py` |
| `scanner/instrument_scanner.py` | 26.59% | `tests/scanner/test_instrument_scanner_coverage.py` |
| `broker/zerodha_broker.py` | 17.99% | `tests/broker/test_zerodha_broker_coverage.py` |
| `data/jugaad_provider.py` | 16.98% | `tests/data/test_jugaad_provider_coverage.py` |
| `data/kite_ws_provider.py` | 17.70% | `tests/data/test_kite_ws_provider_coverage.py` |
| `data/rate_limiter.py` | 17.26% | `tests/data/test_rate_limiter_coverage.py` |
| `data/yfinance_provider.py` | 18.75% | `tests/data/test_yfinance_provider_coverage.py` |
| `data/failover_provider.py` | 22.22% | `tests/data/test_failover_provider_coverage.py` |
| `data/ccxt_provider.py` | 20.74% | `tests/data/test_ccxt_provider_coverage.py` |
| `data/instrument_master.py` | 19.67% | `tests/data/test_instrument_master_coverage.py` |
| `data/market_data_cache.py` | 26.47% | `tests/data/test_market_data_cache_coverage.py` |
| `data/migration_provider.py` | 25.81% | `tests/data/test_migration_provider_coverage.py` |
| `data/price_reconciler.py` | 24.42% | `tests/data/test_price_reconciler_coverage.py` |
| `execution/token_helpers.py` | 18.75% | `tests/execution/test_token_helpers_coverage.py` |
| `execution/live_executor.py` | 19.70% | `tests/execution/test_live_executor_coverage.py` |
| `execution/zerodha_connection.py` | 20.19% | `tests/execution/test_zerodha_connection_coverage.py` |
| `execution/strike_selector.py` | 25.23% | `tests/execution/test_strike_selector_coverage.py` |
| `execution/instrument_resolver.py` | 26.87% | `tests/execution/test_instrument_resolver_coverage.py` |
| `execution/ccxt_executor.py` | 27.86% | `tests/execution/test_ccxt_executor_coverage.py` |
| `execution/openalgo_executor.py` | 24.78% | `tests/execution/test_openalgo_executor_coverage.py` |
| `execution/transaction_costs.py` | 38.46% | `tests/execution/test_transaction_costs_coverage.py` |
| `execution/trade_audit.py` | 44.19% | `tests/execution/test_trade_audit_coverage.py` |
| `strategies/ensemble.py` | 21.05% | `tests/strategies/test_ensemble_coverage.py` |
| `visualization/charts.py` | 17.05% | `tests/visualization/test_charts_coverage.py` |
| `visualization/breakout_scanner.py` | 29.63% | `tests/visualization/test_breakout_scanner_coverage.py` |
| `visualization/deployment_dashboard.py` | 33.33% | `tests/visualization/test_deployment_dashboard_coverage.py` |
| `api.py` | 17.56% | `tests/test_api_coverage.py` |

---

## IMPLEMENTATION EXECUTION ORDER

The following table defines the strict sequential order for test implementation. Each step must pass G6 before proceeding.

| Phase | Step | Tier | Module | LOC | Est. Tests | Est. Coverage Gain |
|-------|------|------|--------|-----|------------|-------------------|
| **PH-1** | 1 | T1 | `selection/correlation_matrix.py` | 75 | 10 | +0.4% |
| **PH-1** | 2 | T1 | `risk/position_sizer.py` | 128 | 16 | +0.7% |
| **PH-1** | 3 | T1 | `market_strength/breadth.py` | 62 | 13 | +0.3% |
| **PH-1** | 4 | T1 | `selection/sector_strength.py` | 21 | 5 | +0.1% |
| **PH-1** | 5 | T1 | `selection/decay.py` | 34 | 6 | +0.2% |
| **PH-1** | 6 | T1 | `selection/_util.py` | 29 | 5 | +0.1% |
| **PH-1** | 7 | T1 | `sentiment/volume_filter.py` | 11 | 4 | +0.1% |
| **PH-1** | 8 | T1 | `visualization/alerts.py` | 51 | 8 | +0.3% |
| **PH-2** | 9 | T2 | `core/event_validation.py` | 305 | 24 | +1.6% |
| **PH-2** | 10 | T2 | `data/validator.py` | 90 | 18 | +0.5% |
| **PH-2** | 11 | T2 | `sentiment/helpers.py` | 111 | 16 | +0.6% |
| **PH-2** | 12 | T2 | `ml/feature_engine.py` | 160 | 12 | +0.9% |
| **PH-2** | 13 | T2 | `ml/readiness.py` | 95 | 4 | +0.5% |
| **PH-2** | 14 | T2 | `data/normalizer.py` | 139 | 10 | +0.7% |
| **PH-3** | 15 | T3 | `storage/duckdb_store.py` | 628 | 25 | +3.4% |
| **PH-3** | 16 | T3 | `core/event_persistence.py` | 496 | 18 | +2.7% |
| **PH-3** | 17 | T3 | `core/sse_broadcaster.py` | 269 | 12 | +1.5% |
| **PH-3** | 18 | T3 | `storage/sqlite_store.py` | 192 | 14 | +1.0% |
| **PH-3** | 19 | T3 | `storage/parquet_store.py` | 167 | 10 | +0.9% |
| **PH-3** | 20 | T3 | `storage/backup.py` | 263 | 12 | +1.4% |
| **PH-3** | 21 | T3 | `storage/git_sync.py` | 112 | 8 | +0.6% |
| **PH-3** | 22 | T3 | `storage/audit_exporter.py` | 201 | 8 | +1.1% |
| **PH-3** | 23 | T3 | `storage/audit_scheduler.py` | 117 | 6 | +0.6% |
| **PH-4** | 24 | T4 | `data/token_resolver.py` | 532 | 20 | +2.9% |
| **PH-4** | 25 | T4 | `execution/order_manager.py` | 565 | 22 | +3.1% |
| **PH-4** | 26 | T4 | `broker/token_manager.py` | 726 | 20 | +3.9% |
| **PH-4** | 27 | T4 | `data/kite_provider.py` | 637 | 16 | +3.5% |
| **PH-4** | 28 | T4 | `data/openalgo_provider.py` | 271 | 12 | +1.5% |
| **PH-4** | 29 | T4 | `core/queue.py` | 421 | 14 | +2.3% |
| **PH-4** | 30 | T4 | `visualization/dashboard.py` | 396 | 12 | +2.1% |
| **PH-5** | 31-109 | T5 | 86 remaining modules | ~10,000 | ~680 | +36% |

**Estimated Total Coverage After All Phases**: 25.37% + ~64% → **~90%**

---

## TEST INFRASTRUCTURE REQUIREMENTS

### Shared Fixtures (`tests/conftest.py` additions)

1. **`tmp_storage_dir`** — Temporary directory for DuckDB/SQLite/Parquet/file tests
2. **`mock_kite_client`** — Pre-configured mock of KiteConnect with historical_data/quote stubs
3. **`mock_event_bus`** — Pre-configured mock EventBus with subscribe/publish stubs
4. **`mock_redis_client`** — Pre-configured mock of redis.asyncio.Redis
5. **`mock_streamlit`** — Pre-configured mock of streamlit module with all UI methods
6. **`sample_ohlcv_bars`** — Fixture providing valid OHLCVBar list for reuse
7. **`sample_ticker_snapshot`** — Fixture providing valid TickerSnapshot
8. **`sample_market_tick_event`** — Fixture providing valid MarketTickEvent
9. **`sample_order_update_event`** — Fixture providing valid OrderUpdateEvent

### Required Test Dependencies

| Package | Purpose | Already in pyproject.toml? |
|---------|---------|---------------------------|
| `pytest-asyncio` | Async test support | Yes |
| `pytest-cov` | Coverage reporting | Yes |
| `freezegun` | Time mocking for timestamp tests | To be added |
| `pytest-mock` | Enhanced mocking (mocker fixture) | To be verified |
| `pytest-xdist` | Parallel test execution | Yes |

---

## CROSS-CUTTING TEST PATTERN RULES

1. **Decimal-only in financial paths** — All price/quantity/PnL assertions must use `Decimal`, never `float`
2. **UTC-aware datetime** — All timestamp assertions must use `datetime(..., tzinfo=UTC)`, never naive `datetime.now()`
3. **Structured logging** — No `print()` in test files; use `caplog` for log assertions
4. **External APIs mocked** — All HTTP/WebSocket/Redis/Telegram calls must be mocked
5. **File I/O isolated** — All file operations use `tmp_path` fixture; no writes to project dir
6. **Async tests** — Use `@pytest.mark.asyncio` decorator for all async test functions
7. **Error path coverage** — Every `ConfigError`/`ValidationError`/`EventBusError` raise must have a corresponding test
8. **Boundary values** — Test at exact boundary values (e.g., `confidence=0`, `confidence=1`, `risk_fraction=0.5`)

---

*This proposal is PLANNING ONLY. No test files have been created. Implementation requires user approval.*
