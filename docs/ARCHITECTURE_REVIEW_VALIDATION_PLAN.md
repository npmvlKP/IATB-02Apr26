# IATB Architecture Review, Validation & Implementation Plan

> **Status**: DRAFT — Awaiting User Approval  
> **Date**: 2026-04-29  
> **Scope**: STRICTLY PLANNING — No code modifications until approved  
> **Reference Architecture**: 7-Layer Paper Trading Platform for Indian Markets

---

## PART 1: VALIDATION MATRIX — Architecture vs Codebase

### Layer 1: Data Ingestion (Zerodha Primary)

| Target Component | Implementation File(s) | Match | Key Gaps |
|-----------------|----------------------|-------|----------|
| Kite Connect REST API | `data/kite_provider.py` | **90%** | Missing `get_ohlcv_batch()`, no `kite.ltp()` endpoint |
| KiteTicker WebSocket | `data/kite_ws_provider.py`, `data/kite_ticker.py` | **75%** | Two overlapping implementations; hardcoded `Exchange.NSE`; placeholder token resolution; neither exported from `__init__.py` |
| Rate Limiter (3 req/sec, burst 10) | `data/rate_limiter.py` | **100% module / 0% integration** | `RateLimiter(3, burst=10)` exists but `KiteProvider` uses its own private `_RateLimiter` with NO burst. Shared limiter is NEVER wired into any provider. |
| Circuit Breaker (5 failures → 60s reset) | `data/rate_limiter.py`, `data/failover_provider.py` | **100% rate_limiter / 20% failover** | `rate_limiter.CircuitBreaker(5, 60s)` matches exactly. `failover_provider.CircuitBreaker` opens on 1 failure (not 5), uses 30s cooldown (not 60s), no HALF_OPEN state. Neither is integrated into KiteProvider. |
| Exponential Backoff (1s, 2s, 4s) | `data/rate_limiter.py`, `data/kite_provider.py` | **100% logic / 0% shared** | Both produce 1s→2s→4s. But KiteProvider has its own inline backoff with no jitter. The shared `retry_with_backoff()` with jitter is NEVER used. |

**CRITICAL INTEGRATION GAPS:**
1. `rate_limiter.py` (RateLimiter + CircuitBreaker + retry_with_backoff) is completely disconnected from `kite_provider.py`
2. Two competing WebSocket implementations (`kite_ws_provider.py` 699 lines vs `kite_ticker.py` 905 lines) with significant overlap
3. Two competing CircuitBreaker implementations (`rate_limiter.CircuitBreaker` vs `failover_provider.CircuitBreaker`) with incompatible semantics
4. No WebSocket provider in `ProviderChain` (factory only creates REST providers)
5. 8 key components missing from `data/__init__.py` exports

---

### Layer 2: Core Engine (Event-Driven)

| Target Component | Implementation File(s) | Match | Key Gaps |
|-----------------|----------------------|-------|----------|
| EventBus (async pub/sub) | `core/event_bus.py`, `core/queue.py` | **85%** | No DLQ, no backpressure, no topic introspection, no retry for failed deliveries |
| Clock (UTC timezone-aware) | `core/clock.py` | **90%** | No injectable mock clock; drift correction is placeholder; `to_ist()` returns naive datetime |
| Config (Pydantic BaseSettings) | `core/config.py` | **70%** | settings.toml NOT loaded by Config; no runtime reload; two disconnected config systems |
| Health Server (FastAPI, port 8000) | `core/health.py`, `fastapi_app.py` | **40%** | HealthServer uses stdlib `http.server`, NOT FastAPI; PORT CONFLICT with fastapi_app.py; no real health aggregation |
| SSE Broadcaster (real-time) | `core/sse_broadcaster.py` | **80%** | Only 2 topics ("scan", "pnl"); no event ID replay; no subscriber limit |

**CRITICAL INTEGRATION GAPS:**
1. **PORT CONFLICT**: `HealthServer` (stdlib) and `fastapi_app.py` both default to port 8000
2. **HealthServer is NOT FastAPI**: Target specifies "FastAPI, port 8000" but `health.py` uses `ThreadingHTTPServer`
3. **settings.toml is ORPHANED**: `Config(BaseSettings)` reads `.env`/env vars only; TOML configs are never loaded
4. **Engine is DISCONNECTED from HealthServer and SSEBroadcaster**: No unified lifecycle
5. **exchange_calendar.py timezone bug**: `check_session_boundary` strips UTC without IST conversion
6. **preflight.py `_check_clock_drift` is a NO-OP**: Compares `datetime.now(UTC)` with itself
7. **`core/__init__.py` missing exports**: `Engine`, `HealthServer`, `SSEBroadcaster`, `EngineError`, `ExecutionError`

---

### Layer 3: Selection Engine (Multi-Factor)

| Target Component | Implementation File(s) | Match | Key Gaps |
|-----------------|----------------------|-------|----------|
| Sentiment Signal (news, social) | `selection/sentiment_signal.py` + `sentiment/aggregator.py` | **80%** | News and social sources NOT connected to aggregation pipeline; `NewsAnalyzer` and `SocialSentimentAnalyzer` are orphaned |
| Market Strength (ADX, ATR, volume) | `selection/strength_signal.py` + `market_strength/strength_scorer.py` | **95%** | Hardcoded weights; ATR used only as penalty |
| Volume Profile (relative volume, spikes) | `selection/volume_profile_signal.py` + `market_strength/volume_profile.py` | **85%** | Volume spike detection missing; profile structure complete |
| DRL Signal (reinforcement learning) | `selection/drl_signal.py` | **70%** | Uses backtest conclusions, NOT live RL agent predictions; no `RLAgent.predict()` → DRL signal path |
| Composite Scorer (regime-aware weights) | `selection/composite_score.py` + `selection/instrument_scorer.py` | **95%** | Dynamic weight optimization disconnected; `weight_optimizer.py` not in pipeline |
| Correlation Filter (diversification) | `selection/correlation_matrix.py` + `selection/ranking.py` | **90%** | Two loosely coupled correlation systems; no sector constraints |
| Top-N Selection (ranked by composite) | `selection/ranking.py` | **95%** | Complete with threshold + correlation filter |

**CRITICAL INTEGRATION GAPS:**
1. **Scanner BYPASSES Selection module**: `InstrumentScanner` has its own composite scoring with hardcoded weights instead of using `InstrumentScorer`
2. **DRL Signal → RL Agent DISCONNECT**: `drl_signal.py` uses backtest conclusions; `rl/agent.py` predictions are never fed into the DRL signal
3. **Sentiment Pipeline FRAGMENTATION**: 3 sentiment systems exist; only `aggregator.py` (FinBERT+AION+VADER) is connected; `NewsAnalyzer` and `SocialSentimentAnalyzer` are orphaned
4. **6 disconnected modules**: `technical_filter.py`, `fundamental_filter.py`, `multi_factor_scorer.py`, `weight_optimizer.py`, `sector_strength.py`, `recency_weighting.py` — all implemented but NOT in pipeline
5. **`selection/__init__.py` has NO exports**

---

### Layer 4: Risk Management (7-Step Pipeline)

| Target Component | Implementation File(s) | Match | Key Gaps |
|-----------------|----------------------|-------|----------|
| 1. Kill Switch Check | `risk/kill_switch.py` | **95%** | Complete. Auto-engages on daily loss breach. No persistence across crashes. |
| 2. Order Throttle (10 orders/sec) | `execution/order_throttle.py` | **70%** | Implemented but default may differ from 10/sec target; not validated as 7-step pipeline step |
| 3. Pre-Trade Validator (5 gates) | `execution/pre_trade_validator.py` | **80%** | Multiple validation gates exist; exact 5-gate mapping unclear; not documented as pipeline step |
| 4. Order Execution (paper fills) | `execution/paper_executor.py` | **85%** | Paper executor exists; deterministic slippage model needs validation |
| 5. Daily Loss Guard (2% NAV limit) | `risk/daily_loss_guard.py` | **95%** | Configurable `max_daily_loss_pct`; auto-engages kill switch; no state persistence across crashes |
| 6. Trade Audit Logger (SQLite) | `execution/trade_audit.py`, `storage/sqlite_store.py` | **80%** | Two implementations; `trade_audit.py` vs `sqlite_store.py`; limited query capability |
| 7. Result Return | (implicit in pipeline) | **60%** | No explicit structured result object from the 7-step pipeline; return paths vary |

**CRITICAL INTEGRATION GAPS:**
1. **No unified 7-step pipeline orchestration**: Individual components exist but are NOT composed into a single ordered pipeline
2. **Two Trade Audit implementations**: `execution/trade_audit.py` and `storage/sqlite_store.py` with overlapping responsibility
3. **DailyLossGuard state is not persisted**: If process restarts, cumulative PnL is lost
4. **Order throttle default may not match 10 orders/sec target** (SEBI validator defaults to 3/sec)
5. **No structured PipelineResult return type** unifying all 7 steps

---

### Layer 5: Execution (Paper Trading Only)

| Target Component | Implementation File(s) | Match | Key Gaps |
|-----------------|----------------------|-------|----------|
| PaperExecutor (deterministic slippage) | `execution/paper_executor.py` | **80%** | Exists; slippage model parameters need validation against target spec |
| OrderManager (lifecycle tracking) | `execution/order_manager.py` | **85%** | Lifecycle tracking exists; daily_loss_guard integration present |
| TradeAuditLogger (SQLite persistence) | `execution/trade_audit.py` | **70%** | Audit logging exists; but `sqlite_store.py` is the "proper" implementation; duplication |
| Position State (crash recovery) | `storage/backup.py` (`export_trading_state`/`load_trading_state`) | **75%** | State export/import exists via backup module; NOT integrated into executor startup |

**CRITICAL INTEGRATION GAPS:**
1. **Position State NOT integrated into executor startup**: `backup.py` has `export_trading_state`/`load_trading_state` but `PaperExecutor` does not call them for crash recovery
2. **Trade audit duplication**: `execution/trade_audit.py` vs `storage/sqlite_store.py` — unclear which is the canonical audit trail
3. **Multiple executor types**: `paper_executor.py`, `live_executor.py`, `ccxt_executor.py`, `openalgo_executor.py` — paper trading target is met but other executors add complexity

---

### Layer 6: Storage & Analytics

| Target Component | Implementation File(s) | Match | Key Gaps |
|-----------------|----------------------|-------|----------|
| DuckDB (analytical queries) | `storage/duckdb_store.py` | **40%** | Only basic SELECT; NO analytical queries (aggregation, window functions, VWAP); no batch insert; no connection pooling; no Parquet integration |
| SQLite (audit trail) | `storage/sqlite_store.py` | **70%** | Basic CRUD; no time-range queries; no filtering; no WAL mode; no full-text search |
| Parquet (historical data) | `storage/parquet_store.py` | **55%** | Partition-based storage; NO cross-file queries; NO compression config; NO retention policy; NO DuckDB integration |
| Git Sync (version control) | `storage/git_sync.py` | **60%** | Push-only; NO pull/fetch/rebase; NO conflict resolution; NO auth handling |

**CRITICAL INTEGRATION GAPS:**
1. **DuckDB has NO analytical queries**: Only `store_bars()` + `load_bars()`. Zero aggregation/window/analytics methods despite DuckDB's core value proposition.
2. **DuckDB ↔ Parquet synergy absent**: DuckDB can natively query Parquet via `read_parquet()` — this powerful integration is completely unused.
3. **No retention policy for Parquet files**: Files accumulate indefinitely.
4. **Git Sync is push-only**: No pull/rebase for multi-machine or collaborative workflows.
5. **Audit export `compress` flag is dead code**: `ExportConfig.compress` exists but no compression logic.

---

### Layer 7: Observability

| Target Component | Implementation File(s) | Match | Key Gaps |
|-----------------|----------------------|-------|----------|
| Structured Logging (JSON) | `core/observability/logging_config.py` | **65%** | No file handler; no rotation; no trace correlation; module-level side effect on import |
| Prometheus Metrics (exposure, PnL, orders) | `core/observability/metrics.py` | **85%** | 25+ metrics; G7 violation: `pnl: float` params; duplicate metric definitions; 4 missing exports |
| OpenTelemetry Tracing (distributed) | `core/observability/tracing.py` | **55%** | No auto-instrumentation; no sampling; no log correlation; hardcoded `insecure=True` |
| Telegram Alerts (kill switch, errors) | `core/observability/alerting.py`, `visualization/alerts.py` | **80%** | Two competing implementations; no `send_kill_switch_alert()`; float in PnL params; no alert persistence |

**CRITICAL INTEGRATION GAPS:**
1. **Two competing Telegram alert systems**: `core/observability/alerting.py` (1235 lines, full-featured) vs `visualization/alerts.py` (81 lines, simple rate-limited). No unified interface.
2. **No kill switch alert**: Target specifically mentions "kill switch, errors" for Telegram. No `send_kill_switch_alert()` exists.
3. **No trace ↔ log correlation**: OTel trace_id and span_id NOT injected into structured logs.
4. **No observability stack in docker-compose**: Missing Prometheus, Grafana, Jaeger/OTel Collector, Alertmanager containers.
5. **G7 violations in metrics/alerting**: `record_trade(pnl: float)`, `update_portfolio_value(value: float)`, `send_trade_alert(price: float)`.
6. **4 metric functions not exported from `__init__.py`**: `record_order_latency`, `update_position_count`, `record_broker_api_call`, `record_risk_check_duration`.

---

## PART 2: CROSS-CUTTING ISSUES

| # | Issue | Severity | Affected Layers |
|---|-------|----------|----------------|
| 1 | **Duplicate implementations** (2 WebSocket feeds, 2 CircuitBreakers, 2 Telegram alerters, 2 Trade Audit loggers, 2 correlation systems, 2 config systems) | CRITICAL | 1, 4, 5, 6, 7 |
| 2 | **Implemented but disconnected modules** (6 selection modules, rate_limiter not wired, weight_optimizer not in pipeline, preflight not called, pipeline_health not used by Engine) | CRITICAL | 1, 2, 3 |
| 3 | **G7 float violations** in metrics/alerting API boundaries | HIGH | 7 |
| 4 | **No unified lifecycle management** (Engine, HealthServer, SSEBroadcaster, FastAPI are separate) | HIGH | 2 |
| 5 | **No 7-step risk pipeline orchestration** (components exist but not composed) | HIGH | 4 |
| 6 | **settings.toml orphaned** from Config(BaseSettings) | HIGH | 2 |
| 7 | **DuckDB analytical queries missing** | HIGH | 6 |
| 8 | **No observability stack in Docker Compose** | MEDIUM | 7 |
| 9 | **Timezone bug in exchange_calendar.py** | MEDIUM | 2 |
| 10 | **preflight.py clock drift check is a no-op** | MEDIUM | 2 |
| 11 | **Missing `__init__.py` exports** across 4 modules | MEDIUM | 1, 2, 3 |
| 12 | **Scanner bypasses Selection pipeline** | HIGH | 3 |

---

## PART 3: DETAILED IMPLEMENTATION SPEC — Sequential Instructions Per Layer

> **IMPORTANT**: These are PLANNING specifications only. No implementation should begin until this plan is APPROVED by the user. Each layer's changes are ordered by dependency — earlier steps must complete before later steps.

---

### LAYER 1: DATA INGESTION — Implementation Spec

#### Step 1.1: Consolidate Rate Limiter Integration
**Priority**: P0 — Foundation for all provider reliability
**Files to Modify**: `src/iatb/data/kite_provider.py`, `src/iatb/data/provider_factory.py`
**What**: Wire `rate_limiter.RateLimiter(3, burst=10)`, `rate_limiter.CircuitBreaker(5, 60s)`, and `rate_limiter.retry_with_backoff()` into `KiteProvider` by:
1. Remove the private `_RateLimiter` class from `kite_provider.py` (lines ~137-170)
2. Add `__init__` parameters: `rate_limiter: RateLimiter`, `circuit_breaker: CircuitBreaker`, `retry_config: RetryConfig`
3. Replace `_retry_with_backoff()` method with delegation to `rate_limiter.retry_with_backoff()`
4. In `provider_factory.py`, instantiate `RateLimiter(3, burst_capacity=10)` and `CircuitBreaker(failure_threshold=5, reset_timeout=60.0)` and inject into `KiteProvider`
5. Validate: Run `poetry run pytest tests/data/ -x` and verify rate limiting behavior

#### Step 1.2: Consolidate WebSocket Implementations
**Priority**: P0 — Eliminates 905+699 lines of overlap
**Files to Modify**: `src/iatb/data/kite_ws_provider.py`, `src/iatb/data/kite_ticker.py`
**What**: Merge `KiteTickerFeed` (kite_ticker.py) features into `KiteWebSocketProvider` (kite_ws_provider.py) since it implements `DataProvider` protocol:
1. Add `ConnectionStats`, `TickBuffer`, and memory monitoring from `kite_ticker.py` into `kite_ws_provider.py`
2. Fix hardcoded `Exchange.NSE` — wire `SymbolTokenResolver` into tick parsing to resolve exchange from instrument token
3. Add `get_stats()`, `is_connected()`, `is_running()` methods
4. Deprecate `kite_ticker.py` (mark as deprecated, redirect imports)
5. Update `provider_factory.py` to include `KiteWebSocketProvider` in the `ProviderChain`
6. Validate: Run WebSocket integration tests

#### Step 1.3: Fix FailoverProvider Circuit Breaker
**Priority**: P1 — Aligns with target architecture
**Files to Modify**: `src/iatb/data/failover_provider.py`
**What**:
1. Change `CircuitBreaker` default `cooldown_seconds` from 30.0 to 60.0
2. Add configurable `failure_threshold` (default 5) instead of opening on 1 failure
3. Add HALF_OPEN state (reuse `rate_limiter.CircuitState` enum) for recovery probing
4. Consider replacing `failover_provider.CircuitBreaker` with `rate_limiter.CircuitBreaker` to eliminate duplication
5. Validate: Run failover provider tests

#### Step 1.4: Fix Missing `__init__.py` Exports
**Priority**: P1
**Files to Modify**: `src/iatb/data/__init__.py`
**What**: Add exports for `KiteWebSocketProvider`, `KiteTickerFeed` (deprecated), `FailoverProvider`, `MigrationProvider`, `RateLimiter`, `CircuitBreaker`, `RetryConfig`, `retry_with_backoff`, `MarketDataCache`

---

### LAYER 2: CORE ENGINE — Implementation Spec

#### Step 2.1: Fix HealthServer → FastAPI Migration
**Priority**: P0 — Resolves port conflict and architecture mismatch
**Files to Modify**: `src/iatb/core/health.py`, `src/iatb/fastapi_app.py`
**What**:
1. Remove `HealthServer` class (stdlib HTTP server) from `health.py`
2. In `fastapi_app.py`, add `/health` endpoint with proper liveness/readiness semantics:
   - `/health/live` → always 200 if process is running
   - `/health/ready` → 200 only if EventBus, DataProvider, and Engine are initialized
3. Add component-level health aggregation: check EventBus running, DataProvider connected, Engine running
4. Remove `runtime.py`'s `HealthServer(port=8000)` startup — FastAPI app now serves health
5. Validate: Start FastAPI, hit `/health/live` and `/health/ready`

#### Step 2.2: Bridge Config Systems
**Priority**: P0 — Unifies TOML and BaseSettings
**Files to Modify**: `src/iatb/core/config.py`, `src/iatb/core/config_manager.py`, `config/settings.toml`
**What**:
1. Add TOML file loading to `Config(BaseSettings)` using `tomli`:
   - Read `config/settings.toml` as base defaults
   - Override with `.env` and environment variables (env wins over TOML)
2. Add `settings_customise_sources` classmethod to merge TOML + env + .env
3. Align `settings.toml` `data_provider_default` with `Config.data_provider_default` (currently "jugaad" vs "kite" mismatch)
4. Add `[observability]` and `[storage]` sections to `settings.toml`
5. Validate: Start engine, verify TOML values loaded into Config

#### Step 2.3: Unify Engine Lifecycle
**Priority**: P1 — Engine should manage all core components
**Files to Modify**: `src/iatb/core/engine.py`, `src/iatb/core/runtime.py`
**What**:
1. `Engine.__init__` should accept and manage: `EventBus`, `SSEBroadcaster`, `Config`
2. `Engine.start()` should: start EventBus, start SSEBroadcaster, run preflight checks
3. `Engine.stop()` should: stop SSEBroadcaster, stop EventBus, cancel all tasks
4. Remove `runtime.py`'s separate HealthServer management
5. Add `health_status()` method returning aggregated component health
6. Validate: Engine start/stop lifecycle test

#### Step 2.4: Fix Bugs
**Priority**: P1
**Files to Modify**: `core/exchange_calendar.py`, `core/preflight.py`, `core/event_persistence.py`
**What**:
1. `exchange_calendar.py`: Fix `check_session_boundary` — convert to IST before stripping timezone
2. `preflight.py`: Fix `_check_clock_drift` — compare local time with NTP time via `ClockDriftDetector`
3. `event_persistence.py`: Fix `_deserialize_event` — reconstruct actual event objects (MarketTickEvent, etc.) instead of returning raw dicts
4. Validate: Run `poetry run pytest tests/core/ -x`

#### Step 2.5: Fix Missing `__init__.py` Exports
**Priority**: P1
**Files to Modify**: `src/iatb/core/__init__.py`
**What**: Add exports for `Engine`, `SSEBroadcaster`, `HealthServer` (deprecated), `EngineError`, `ExecutionError`, `ExchangeHaltError`, `EventPersistence`, `PipelineHealthMonitor`, `PipelineCheckpoint`, `StrategyRunner`, `ClusterManager`, `SecretsRotationManager`, `ClockDriftDetector`, `TradingSessions`

---

### LAYER 3: SELECTION ENGINE — Implementation Spec

#### Step 3.1: Wire Scanner → Selection Pipeline
**Priority**: P0 — Eliminates the most critical architectural gap
**Files to Modify**: `src/iatb/scanner/instrument_scanner.py`, `src/iatb/scanner/scan_cycle.py`
**What**:
1. Remove `_compute_composite_score()` from `InstrumentScanner` — replace with delegation to `InstrumentScorer.score_and_select()`
2. Remove hardcoded composite weights from scanner — use regime-aware weights from `composite_score.py`
3. Wire `RegimeDetector.detect()` into the scan cycle to determine current regime
4. Wire `compute_drl_signal()` instead of mock RL predictor
5. Wire `compute_sentiment_signal()` with `SentimentAggregator` instead of callback-based sentiment
6. Add correlation filtering from `ranking.py` to scanner results
7. Validate: Run `poetry run pytest tests/scanner/ -x`

#### Step 3.2: Connect DRL Signal → RL Agent
**Priority**: P0 — Bridges RL agent predictions to selection pipeline
**Files to Modify**: `src/iatb/selection/drl_signal.py`, `src/iatb/rl/agent.py`
**What**:
1. Add `compute_drl_signal_from_agent()` function that takes `RLAgent.predict()` output (action + confidence) and converts to DRL signal score
2. Define action-to-score mapping: action 0 (HOLD) → low score, action 1 (BUY) → high score, action 2 (SELL) → low score (inverted for long)
3. Add confidence weighting from `predict_with_confidence()`
4. Add fallback to backtest-conclusion-based signal when no trained model is available
5. Validate: Unit test with mock RL agent

#### Step 3.3: Connect News & Social Sentiment to Aggregator
**Priority**: P1 — Fulfills "Sentiment Signal (news, social)" target
**Files to Modify**: `src/iatb/sentiment/aggregator.py`, `src/iatb/sentiment/news_analyzer.py`, `src/iatb/sentiment/social_sentiment.py`, `src/iatb/sentiment/news_scraper.py`
**What**:
1. Add `NewsSource` → `NewsAnalyzer` bridge: `NewsScraper.fetch_headlines()` → convert `NewsHeadline` to `NewsArticle` format → `NewsAnalyzer.analyze()`
2. Add `SocialSource` → aggregator bridge: `SocialSentimentAnalyzer.analyze()` output → weighted input to `SentimentAggregator`
3. Update `SentimentAggregator` to include news and social sub-scores in its weighted ensemble
4. Adjust weights: FinBERT 0.35, AION 0.25, VADER 0.10, News 0.15, Social 0.15
5. Wire `recency_weighting.py` into news article scoring within the aggregator
6. Validate: Integration test with mock news/social sources

#### Step 3.4: Wire Technical/Fundamental Filters as Pre-Selection
**Priority**: P1
**Files to Modify**: `src/iatb/selection/instrument_scorer.py`
**What**:
1. Add optional `TechnicalFilter` and `FundamentalFilter` as pre-filtering steps in `InstrumentScorer.score_instruments()`
2. Pipeline: technical_filter → fundamental_filter → 4-signal scoring → composite → correlation → ranking
3. Make filter usage configurable via `Config`
4. Validate: Score instruments with and without filters

#### Step 3.5: Wire Weight Optimizer Feedback Loop
**Priority**: P2
**Files to Modify**: `src/iatb/selection/instrument_scorer.py`, `src/iatb/selection/weight_optimizer.py`
**What**:
1. Add scheduled weight optimization: run `optimize_weights_for_regime()` weekly
2. Store optimized weights in `ConfigManager` TOML persistence
3. `InstrumentScorer` loads custom weights from config on initialization
4. Validate: Run weight optimization, verify weights persist

#### Step 3.6: Fix `selection/__init__.py` Exports
**Priority**: P1
**Files to Modify**: `src/iatb/selection/__init__.py`
**What**: Export all public API: `compute_composite_score`, `InstrumentScorer`, `rank_and_select`, `compute_drl_signal`, `compute_sentiment_signal`, `compute_strength_signal`, `compute_volume_profile_signal`, etc.

---

### LAYER 4: RISK MANAGEMENT — Implementation Spec

#### Step 4.1: Implement Unified 7-Step Risk Pipeline
**Priority**: P0 — The defining architectural requirement for Layer 4
**Files to Create**: `src/iatb/risk/risk_pipeline.py`
**Files to Modify**: `src/iatb/execution/order_manager.py`, `src/iatb/risk/daily_loss_guard.py`
**What**:
1. Create `RiskPipeline` class with explicit 7-step ordered execution:
   ```python
   class RiskPipelineResult(frozen dataclass):
       order_id: str
       allowed: bool
       kill_switch_engaged: bool
       throttle_accepted: bool
       pre_trade_passed: bool
       execution_result: PaperFillResult | None
       daily_loss_state: DailyLossState
       audit_record_id: str
       rejection_reason: str | None
       timestamp_utc: Timestamp
   
   class RiskPipeline:
       def __init__(self, kill_switch, order_throttle, pre_trade_validator,
                    paper_executor, daily_loss_guard, trade_audit_logger): ...
       async def process_order(self, order, now_utc) -> RiskPipelineResult: ...
   ```
2. Step 1: `kill_switch.check_order_allowed()` — if engaged, reject immediately
3. Step 2: `order_throttle.acquire()` — if throttled, reject
4. Step 3: `pre_trade_validator.validate()` — 5 gates (position limit, margin, product type, session, SEBI)
5. Step 4: `paper_executor.execute()` — deterministic slippage paper fill
6. Step 5: `daily_loss_guard.record_trade()` — check 2% NAV breach, auto-engage kill switch if breached
7. Step 6: `trade_audit_logger.append_trade()` — SQLite persistence
8. Step 7: Return `RiskPipelineResult`
9. Validate: Unit test each step, integration test full pipeline

#### Step 4.2: Consolidate Trade Audit Logging
**Priority**: P1 — Eliminates duplication
**Files to Modify**: `src/iatb/execution/trade_audit.py`, `src/iatb/storage/sqlite_store.py`
**What**:
1. Make `execution/trade_audit.py` delegate to `storage/sqlite_store.py` for actual persistence
2. `trade_audit.py` becomes a thin adapter/wrapper that formats `RiskPipelineResult` into `TradeAuditRecord` and calls `SQLiteStore.append_trade()`
3. Add time-range queries and filtering to `SQLiteStore` (by exchange, symbol, strategy_id, time range)
4. Enable WAL mode on SQLite connections for concurrent read/write
5. Validate: Run audit logging tests

#### Step 4.3: Persist DailyLossGuard State
**Priority**: P1 — Crash recovery for cumulative PnL
**Files to Modify**: `src/iatb/risk/daily_loss_guard.py`
**What**:
1. Add `save_state()` and `load_state()` methods using `SQLiteStore` or a dedicated state file
2. On startup, load previous day's cumulative PnL from persistence
3. On every `record_trade()`, persist updated state
4. Validate: Kill process mid-trading, restart, verify PnL continuity

#### Step 4.4: Align Order Throttle to 10 orders/sec
**Priority**: P1
**Files to Modify**: `src/iatb/execution/order_throttle.py`, `src/iatb/risk/sebi_live_validator.py`
**What**:
1. Verify/fix `OrderThrottle` default to 10 orders/sec
2. Fix `SEBILiveValidationHarness` default `max_order_rate_per_sec` from 3 to 10
3. Validate: Run throttle tests

---

### LAYER 5: EXECUTION — Implementation Spec

#### Step 5.1: Integrate Position State Crash Recovery
**Priority**: P0 — Essential for production reliability
**Files to Modify**: `src/iatb/execution/paper_executor.py`, `src/iatb/execution/order_manager.py`, `src/iatb/storage/backup.py`
**What**:
1. On `PaperExecutor.__init__`, call `load_trading_state()` from `backup.py` to restore positions + pending orders
2. On every order fill, call `export_trading_state()` to persist current state
3. Add `crash_recovery_mode: bool` flag — if True, skip orders that were already filled (idempotency)
4. On `OrderManager.__init__`, reload pending orders from persisted state
5. Validate: Test crash recovery scenario

#### Step 5.2: Validate Deterministic Slippage Model
**Priority**: P1 — Paper trading accuracy
**Files to Modify**: `src/iatb/execution/paper_executor.py`
**What**:
1. Document current slippage model (percentage-based? fixed? market-impact?)
2. Define target: `slippage_bps = Decimal("5")` (5 basis points for liquid, 10 bps for illiquid)
3. Add exchange-specific slippage: NSE EQ 3bps, NSE F&O 2bps, MCX 8bps, BSE 5bps
4. Add volume-based slippage adjustment: higher volume → lower slippage
5. Validate: Compare paper fills with actual market prices

#### Step 5.3: Add `get_ohlcv_batch()` to KiteProvider
**Priority**: P2
**Files to Modify**: `src/iatb/data/kite_provider.py`
**What**:
1. Implement `get_ohlcv_batch()` using parallel `asyncio.gather()` for multiple symbol fetches
2. Rate-limit the batch to respect 3 req/sec with burst=10
3. Validate: Run batch data fetching tests

---

### LAYER 6: STORAGE & ANALYTICS — Implementation Spec

#### Step 6.1: Add DuckDB Analytical Query Methods
**Priority**: P0 — Core value proposition of DuckDB
**Files to Modify**: `src/iatb/storage/duckdb_store.py`
**What**:
1. Add analytical query methods:
   - `query_vwap(symbol, exchange, start, end)` — Volume Weighted Average Price
   - `query_daily_summary(symbol, exchange, start, end)` — OHLCV aggregation per day
   - `query_moving_averages(symbol, exchange, window, start, end)` — SMA/EMA
   - `query_performance_ranking(exchange, start, end, limit)` — Top performers by return
   - `query_volatility(symbol, exchange, window, start, end)` — Rolling standard deviation
   - `query_correlation_matrix(symbols, exchange, start, end)` — Pairwise return correlations
2. Add batch INSERT using DuckDB's `executemany()` or parameter arrays
3. Add connection pooling (persistent connection with reconnection)
4. Validate: Run analytical query tests with sample data

#### Step 6.2: DuckDB ↔ Parquet Integration
**Priority**: P0 — Powerful Layer 6 synergy
**Files to Modify**: `src/iatb/storage/duckdb_store.py`, `src/iatb/storage/parquet_store.py`
**What**:
1. Add `query_parquet(file_pattern)` method to DuckDB — uses `SELECT * FROM read_parquet('path/*.parquet')`
2. Add `migrate_parquet_to_duckdb(parquet_dir)` — bulk load Parquet files into DuckDB for fast analytics
3. Add `archive_to_parquet(symbol, exchange, start, end)` — export DuckDB data to Parquet for long-term storage
4. Validate: Load Parquet via DuckDB, verify results

#### Step 6.3: Enhance SQLite Audit Trail
**Priority**: P1
**Files to Modify**: `src/iatb/storage/sqlite_store.py`
**What**:
1. Add `list_trades_by_range(start_utc, end_utc)` — time-range query
2. Add `list_trades_by_symbol(symbol, exchange, limit)` — symbol filter
3. Add `list_trades_by_strategy(strategy_id, limit)` — strategy filter
4. Enable WAL mode: `PRAGMA journal_mode=WAL`
5. Add batch INSERT for high-throughput audit writes
6. Validate: Run query tests with populated audit data

#### Step 6.4: Enhance Parquet Store
**Priority**: P1
**Files to Modify**: `src/iatb/storage/parquet_store.py`
**What**:
1. Add `read_bars_range(symbol, exchange, timeframe, start, end)` — cross-file query across date-spanning Parquet files
2. Add compression codec configuration (default ZSTD for archival)
3. Add `cleanup_older_than(days)` retention policy
4. Add date-based partition sub-directories (`exchange/symbol/timeframe/YYYY/MM/`)
5. Validate: Write + read across partition boundaries

#### Step 6.5: Enhance Git Sync
**Priority**: P2
**Files to Modify**: `src/iatb/storage/git_sync.py`
**What**:
1. Add `pull_rebase()` method: `git fetch origin && git rebase origin/<branch>`
2. Add `status()` method: `git status --porcelain`
3. Add `resolve_conflicts(strategy)` method: `git checkout --ours/--theirs`
4. Add `check_auth()` method: verify SSH key or token availability
5. Add retry logic on push failures (3 attempts with exponential backoff)
6. Validate: Test git sync with remote repository

---

### LAYER 7: OBSERVABILITY — Implementation Spec

#### Step 7.1: Fix G7 Float Violations in Metrics/Alerting
**Priority**: P0 — Quality gate compliance
**Files to Modify**: `src/iatb/core/observability/metrics.py`, `src/iatb/core/observability/alerting.py`
**What**:
1. `metrics.py`: Change `record_trade(pnl: float)` → `record_trade(pnl: Decimal)` with explicit `float(pnl)` conversion comment at Prometheus boundary
2. `metrics.py`: Change `update_portfolio_value(value: float)` → `update_portfolio_value(value: Decimal)`
3. `metrics.py`: Change `update_daily_pnl(pnl: float)` → `update_daily_pnl(pnl: Decimal)`
4. `alerting.py`: Change `send_trade_alert(price: float)` → `send_trade_alert(price: Decimal)`
5. `alerting.py`: Change `send_pnl_alert(pnl: float, daily_pnl: float)` → `send_pnl_alert(pnl: Decimal, daily_pnl: Decimal)`
6. `alerting.py`: Fix `_check_daily_loss_threshold()` to use Decimal comparison
7. Validate: Run G7 gate check script

#### Step 7.2: Consolidate Telegram Alert Systems
**Priority**: P0 — Eliminates duplicate implementations
**Files to Modify**: `src/iatb/core/observability/alerting.py`, `src/iatb/visualization/alerts.py`
**What**:
1. Merge `visualization/alerts.py` `TelegramAlertDispatcher` rate-limiting into `core/observability/alerting.py` `TelegramAlerter`
2. Add `send_kill_switch_alert(reason, engaged_utc)` to `TelegramAlerter`
3. Add `AlertType.KILL_SWITCH` to the observability alerting layer
4. Wire kill switch engage callback to `send_kill_switch_alert()`
5. Deprecate `visualization/alerts.py` — redirect imports to `core/observability/alerting.py`
6. Consolidate `TelegramAlertLevel` and `AlertLevel` (identical values) into single enum
7. Validate: Trigger kill switch, verify Telegram alert

#### Step 7.3: Add Trace ↔ Log Correlation
**Priority**: P1 — Completes observability triad
**Files to Modify**: `src/iatb/core/observability/logging_config.py`, `src/iatb/core/observability/tracing.py`
**What**:
1. In `logging_config.py` `JsonFormatter.add_fields()`, inject `trace_id` and `span_id` from OTel context:
   ```python
   from opentelemetry import context, trace
   span = trace.get_current_span()
   if span.is_recording():
       log_record["trace_id"] = format(span.context.trace_id, "032x")
       log_record["span_id"] = format(span.context.span_id, "016x")
   ```
2. Add `service.name` resource attribute to all log records
3. Validate: Create span, log within span, verify trace_id in log output

#### Step 7.4: Add Observability Stack to Docker Compose
**Priority**: P1
**Files to Modify**: `docker-compose.yml`
**What**:
1. Add Prometheus container:
   ```yaml
   prometheus:
     image: prom/prometheus:v2.54.1
     ports: ["9090:9090"]
     volumes: ["./config/prometheus.yml:/etc/prometheus/prometheus.yml"]
   ```
2. Add Grafana container:
   ```yaml
   grafana:
     image: grafana/grafana:11.3.0
     ports: ["3000:3000"]
   ```
3. Add OpenTelemetry Collector container:
   ```yaml
   otel-collector:
     image: otel/opentelemetry-collector-contrib:0.110.0
     ports: ["4317:4317", "4318:4318"]
   ```
4. Add Jaeger container:
   ```yaml
   jaeger:
     image: jaegertracing/all-in-one:1.62.0
     ports: ["16686:16686"]
   ```
5. Create `config/prometheus.yml` with scrape targets
6. Validate: `docker-compose up`, verify Prometheus scraping, Jaeger receiving traces

#### Step 7.5: Add File-Based Log Handler
**Priority**: P1
**Files to Modify**: `src/iatb/core/observability/logging_config.py`, `config/logging.toml`
**What**:
1. Add `RotatingFileHandler` with configurable path, max size, backup count
2. Add `[logging.file]` section to `logging.toml`:
   ```toml
   [logging.file]
   enabled = true
   path = "logs/iatb.json"
   max_bytes = 10485760  # 10MB
   backup_count = 5
   ```
3. Add per-module log level configuration:
   ```toml
   [logging.modules]
   "iatb.data" = "INFO"
   "iatb.execution" = "DEBUG"
   "iatb.risk" = "WARNING"
   ```
4. Validate: Start engine, verify log file creation and rotation

#### Step 7.6: Fix Missing `__init__.py` Exports
**Priority**: P1
**Files to Modify**: `src/iatb/core/observability/__init__.py`
**What**: Add exports for `record_order_latency`, `update_position_count`, `record_broker_api_call`, `record_risk_check_duration`

---

## PART 4: IMPLEMENTATION EXECUTION ORDER

The following is the recommended execution sequence across ALL layers, ordered by dependencies:

| Phase | Step | Layer | Description | Estimated Effort |
|-------|------|-------|-------------|------------------|
| **P0-1** | 1.1 | L1 | Consolidate Rate Limiter into KiteProvider | Medium |
| **P0-2** | 2.1 | L2 | Fix HealthServer → FastAPI Migration | Medium |
| **P0-3** | 2.2 | L2 | Bridge Config Systems (TOML + BaseSettings) | Medium |
| **P0-4** | 4.1 | L4 | Implement Unified 7-Step Risk Pipeline | Large |
| **P0-5** | 7.1 | L7 | Fix G7 Float Violations in Metrics/Alerting | Small |
| **P0-6** | 7.2 | L7 | Consolidate Telegram Alert Systems | Medium |
| **P1-1** | 1.2 | L1 | Consolidate WebSocket Implementations | Large |
| **P1-2** | 1.3 | L1 | Fix FailoverProvider Circuit Breaker | Medium |
| **P1-3** | 3.1 | L3 | Wire Scanner → Selection Pipeline | Large |
| **P1-4** | 3.2 | L3 | Connect DRL Signal → RL Agent | Medium |
| **P1-5** | 5.1 | L5 | Integrate Position State Crash Recovery | Medium |
| **P1-6** | 6.1 | L6 | Add DuckDB Analytical Query Methods | Large |
| **P1-7** | 6.2 | L6 | DuckDB ↔ Parquet Integration | Medium |
| **P1-8** | 7.3 | L7 | Add Trace ↔ Log Correlation | Small |
| **P1-9** | 7.4 | L7 | Add Observability Stack to Docker Compose | Medium |
| **P2-1** | 1.4 | L1 | Fix Missing `__init__.py` Exports (L1) | Small |
| **P2-2** | 2.3 | L2 | Unify Engine Lifecycle | Medium |
| **P2-3** | 2.4 | L2 | Fix Bugs (timezone, preflight, persistence) | Small |
| **P2-4** | 2.5 | L2 | Fix Missing `__init__.py` Exports (L2) | Small |
| **P2-5** | 3.3 | L3 | Connect News & Social Sentiment | Medium |
| **P2-6** | 3.4 | L3 | Wire Technical/Fundamental Filters | Medium |
| **P2-7** | 3.6 | L3 | Fix `selection/__init__.py` Exports | Small |
| **P2-8** | 4.2 | L4 | Consolidate Trade Audit Logging | Medium |
| **P2-9** | 4.3 | L4 | Persist DailyLossGuard State | Small |
| **P2-10** | 4.4 | L4 | Align Order Throttle to 10/sec | Small |
| **P2-11** | 5.2 | L5 | Validate Deterministic Slippage Model | Medium |
| **P2-12** | 6.3 | L6 | Enhance SQLite Audit Trail | Medium |
| **P2-13** | 6.4 | L6 | Enhance Parquet Store | Medium |
| **P2-14** | 7.5 | L7 | Add File-Based Log Handler | Small |
| **P2-15** | 7.6 | L7 | Fix Missing `__init__.py` Exports (L7) | Small |
| **P3-1** | 3.5 | L3 | Wire Weight Optimizer Feedback Loop | Medium |
| **P3-2** | 5.3 | L5 | Add `get_ohlcv_batch()` to KiteProvider | Small |
| **P3-3** | 6.5 | L6 | Enhance Git Sync | Medium |

---

## PART 5: RISK ASSESSMENT

| Risk | Impact | Mitigation |
|------|--------|------------|
| Removing private `_RateLimiter` from KiteProvider may break existing tests | Medium | Create KiteProvider tests first, then refactor incrementally |
| Merging WebSocket implementations is a large change (1604 lines affected) | High | Keep both implementations initially, add deprecation path, migrate gradually |
| 7-Step Risk Pipeline creation affects order flow — must not break existing paper trading | Critical | Add pipeline behind feature flag, test extensively before switching |
| Config TOML bridge may override existing env-based values | Medium | Ensure env vars always win over TOML (explicit priority chain) |
| Docker Compose observability stack adds resource requirements | Low | Use resource limits, make observability containers optional |

---

## PART 6: ASSUMPTIONS AND UNKNOWN

1. **KiteConnect API key/secret availability**: Assumes valid Zerodha API credentials exist in `.env`
2. **Telegram bot token**: Assumes `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are configured
3. **DuckDB/Parquet data volume**: Unknown current data volume — affects DuckDB schema and Parquet partition strategy
4. **RL agent training status**: Unknown if a trained RL model exists — DRL signal fallback path needed
5. **Existing test coverage**: Assumed ≥90% per pyproject.toml `cov-fail-under=90` — any refactoring must maintain this
6. **Prometheus/Grafana dashboard templates**: Not in scope — would need separate configuration effort
7. **Docker resource constraints**: Unknown host machine specs — container resource limits are placeholder values

---

## PART 7: APPROVAL CHECKLIST

Before implementation begins, the following must be confirmed:

- [ ] **Layer 1 priority**: Is wiring the shared RateLimiter/CircuitBreaker into KiteProvider the top priority, or should WebSocket consolidation come first?
- [ ] **WebSocket strategy**: Should `kite_ws_provider.py` (DataProvider protocol) absorb `kite_ticker.py` features, or should a new unified class be created?
- [ ] **HealthServer migration**: Confirm removal of stdlib HealthServer in favor of FastAPI `/health` endpoints
- [ ] **Config TOML bridge**: Confirm that env vars should override TOML values (vs TOML as authoritative source)
- [ ] **7-Step Pipeline**: Confirm the 5 pre-trade validation gates (position limit, margin, product type, session, SEBI compliance)
- [ ] **Observability stack**: Confirm Prometheus + Grafana + Jaeger + OTel Collector as the target observability stack
- [ ] **Telegram consolidation**: Confirm merging `visualization/alerts.py` into `core/observability/alerting.py`
- [ ] **Execution order**: Confirm the phased execution order (P0 → P1 → P2 → P3)

---

**END OF ARCHITECTURE REVIEW, VALIDATION & IMPLEMENTATION PLAN**

*This document is STRICTLY PLANNING. No code modifications have been made. All changes await user approval.*
