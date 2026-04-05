# IATB - Interactive Algorithmic Trading Bot

A Python-based algorithmic trading system with support for multiple brokerage platforms and comprehensive quality gates.

## Features

- Multi-broker support (Interactive Brokers, Alpaca, TD Ameritrade, Binance, Coinbase, Kraken)
- Comprehensive data provider integrations (Alpha Vantage, Polygon.io, Quandl, IEX Cloud, Finnhub)
- Structured logging with UTC-aware timestamps
- Decimal precision for all financial calculations
- Notification services (Slack, Telegram, Email)
- Risk management and position sizing
- Quality gates with 90% code coverage requirement

## Project Structure

```
IATB/
├── src/
│   └── iatb/
│       ├── backtesting/       # Event-driven, vectorized, walk-forward, Monte Carlo
│       ├── core/              # Engine, event bus, clock, enums, types, exceptions
│       ├── data/              # Instrument model, instrument master, data providers
│       ├── execution/         # Order management, paper/live executors, Zerodha
│       ├── market_strength/   # Regime detector, strength scorer, volume profile, indicators
│       ├── ml/                # Feature engine, LSTM/GNN/HMM/Transformer, ensemble predictor
│       ├── risk/              # Position sizing, stop loss, circuit breaker, SEBI compliance
│       ├── rl/                # PPO/A2C/SAC agent, trading environment, Optuna optimizer
│       ├── selection/         # Multi-factor instrument auto-selection (see below)
│       ├── sentiment/         # FinBERT + AION + VADER ensemble, volume filter
│       ├── storage/           # DuckDB, SQLite, Parquet, Git sync
│       ├── strategies/        # Momentum, breakout, mean-reversion, sentiment, ensemble
│       └── visualization/     # Dashboard, charts, alerts, breakout scanner
├── tests/                     # Test suite (90%+ coverage target)
├── scripts/                   # Setup, quality gates, git sync
├── .github/workflows/         # CI/CD pipelines
├── .env.example               # Environment variable template
└── pyproject.toml             # Project configuration
```

## Instrument Auto-Selection Module

The `selection/` package fuses four signal sources into a regime-aware composite
score per instrument, then ranks and selects the top candidates for trade execution.
Built with industry-standard practices from multi-factor scoring (FinClaw, CAFPO),
volume profile analysis (AVPT/CME), and sentiment-regime switching (arXiv 2402.01441).

### Data Flow

```
  DATA LAYER                     SELECTION LAYER                    STRATEGY LAYER
  ───────────                    ───────────────                    ──────────────
  SentimentAggregator ──→ sentiment_signal ──┐
  StrengthScorer      ──→ strength_signal  ──┤                     Engine.select_instruments()
  VolumeProfile       ──→ vp_signal        ──┼→ rank_normalize →       │
  BacktestConclusion  ──→ drl_signal       ──┘   composite_score →     ▼
                              ↑                    ranking →       StrategyContext
                         decay (per-signal)          │             .composite_score
                         _util (shared)              │             .selection_rank
                         correlation_matrix ──────→──┘                  │
                         ic_monitor ─────────── (alpha decay alert)    ▼
                                                                  StrategyBase
                                                                  .can_emit_signal()
```

### Signal Sources

**Sentiment** (`sentiment_signal.py`) — FinBERT+AION+VADER ensemble composite
normalized from [-1, 1] → [0, 1]. Direction-aware: inverts for SHORT intent
so strongly bearish sentiment scores high when evaluating short candidates.
Decay λ=0.25 (half-life ~2.8h, configurable via overrides).

**Market Strength** (`strength_signal.py`) — Promotes `StrengthScorer.score()`
from a binary `is_tradable()` gate to a continuous [0, 1] selection input,
weighted by HMM regime confidence. ADX uses concave (sqrt) normalization
to emphasize early trend emergence (ADX 15→25). Decay λ=0.10 (half-life ~6.9h).

**Volume Profile** (`volume_profile_signal.py`) — Three sub-metrics from
POC/VAH/VAL structure:
- POC proximity (weight 0.40): regime-dependent — near-POC in SIDEWAYS, far-from-POC in BULL/BEAR
- Value area width ratio (weight 0.35): narrower VA = stronger trend signal
- Profile shape (weight 0.25): P=0.80, D=0.50, b=0.20 (inverted for SHORT)

Decay λ=0.15 (half-life ~4.6h).

**DRL Backtesting** (`drl_signal.py`) — `BacktestConclusion` aggregates outputs
from the walk-forward, Monte Carlo, and event-driven backtesting suites.
`build_conclusion()` factory automates construction from upstream results.
Score = sigmoid(Sharpe) × robustness × drawdown_factor ± graduated_overfit_penalty.
Drawdown ≥20% zeroes the signal. Overfit penalty scales continuously from
-0.05 at ratio 2.5 to -0.50 at ratio 7+. Decay λ=0.05 (half-life ~13.9h).

`RLAgent.predict_with_confidence()` extracts the PPO/A2C/SAC policy
network's softmax action probability as a live inference confidence signal.

### Composite Scoring

Each signal's contribution = `weight × score × confidence_ramp(confidence)`.
The soft ramp is zero below 0.20, then linearly scales to 1.0 at confidence 1.0.
Scores are zero-indexed rank-percentile normalized across the instrument universe
before fusion (lowest → 0.0, highest → 1.0).

Weights shift by market regime:

- **BULL**: DRL 0.40, Strength 0.25, Sentiment 0.20, Volume Profile 0.15
- **SIDEWAYS**: Volume Profile 0.35, DRL 0.30, Strength 0.20, Sentiment 0.15
- **BEAR**: Sentiment 0.30, Strength 0.30, DRL 0.30, Volume Profile 0.10

Custom per-regime weight overrides via `InstrumentScorer(custom_weights={...})`.

### Ranking & Selection

1. Threshold filter: composite ≥ 0.20 (configurable)
2. Descending sort by composite score
3. Top-N selection (default 5)
4. Correlation diversification filter (|ρ| > 0.80 drops lower-scored instrument)

Correlation data is computed by `correlation_matrix.py` from Decimal close-price
sequences using Pearson return correlation.

### Alpha Decay Monitoring

`ic_monitor.py` measures the Spearman rank-correlation (Information Coefficient)
between composite selection scores and realised forward returns.
`check_alpha_decay()` returns True and logs a warning when IC drops below 0.03,
signalling that the selector's predictive power has degraded and weight
recalibration is needed.

### Weight Optimization

`weight_optimizer.py` uses Optuna TPE search to find optimal regime-specific
weight vectors. The objective maximizes Spearman IC between composite scores
and realized forward returns. Call `optimize_weights_for_regime()` per regime
to replace static presets with data-driven weights.

### Engine Integration

```python
from iatb.core.engine import Engine
from iatb.market_strength.regime_detector import MarketRegime

engine = Engine()  # InstrumentScorer created automatically
await engine.start()

# One-call pipeline: score → select → build StrategyContext list
# strength_map auto-extracted from InstrumentSignals.strength_inputs
contexts = engine.run_selection_cycle(signals, MarketRegime.BULL)

# Async variant for live data feeds (runs in executor)
contexts = await engine.run_selection_cycle_async(signals, MarketRegime.BULL)

# Each context carries composite_score and selection_rank
for ctx in contexts:
    strategy.on_tick(ctx, tick)
```

`StrategyBase.can_emit_signal()` checks `selection_rank` — instruments with
rank < 1 (not selected) are blocked from signal emission.
`scale_quantity_by_rank()` provides rank-proportional position sizing.

### Upstream Integration Points

- **`SentimentAggregator.evaluate_instrument()`** → sentiment_signal
- **`StrengthScorer.score()` + `RegimeDetector.detect()`** → strength_signal (sqrt ADX)
- **`build_volume_profile()`** → volume_profile_signal (regime-dependent POC)
- **`WalkForwardOptimizer` + `MonteCarloAnalyzer` + `EventDrivenBacktester`** → `build_conclusion()` → drl_signal
- **`RLAgent.predict_with_confidence()`** → live DRL inference confidence
- **OHLCV close prices** → `compute_pairwise_correlations()` → ranking correlation filter

### Downstream Integration Points

- **`Engine.run_selection_cycle()`** — one-call score → select → StrategyContext pipeline
- **`Engine.run_selection_cycle_async()`** — non-blocking variant for live data feeds
- **`StrategyContext.composite_score` / `.selection_rank`** — carried into all strategy methods
- **`StrategyBase.can_emit_signal()`** — blocks unselected instruments
- **`check_alpha_decay()`** — monitors selector predictive quality over time
- **`optimize_weights_for_regime()`** — Optuna-based weight retraining when IC decays

### Files

```
selection/
├── __init__.py                 # Package docstring
├── _util.py                    # DirectionalIntent, clamp_01, confidence_ramp, rank_percentile
├── decay.py                    # Temporal decay: exp(-λ × hours), configurable overrides
├── sentiment_signal.py         # SentimentAggregator → [0, 1], direction-aware
├── strength_signal.py          # StrengthScorer → [0, 1], regime-confidence weighted
├── volume_profile_signal.py    # POC/VAH/VAL → shape + proximity + width, regime-dependent
├── drl_signal.py               # BacktestConclusion + build_conclusion() factory
├── composite_score.py          # Regime-aware weighted fusion with soft confidence ramp
├── ranking.py                  # Threshold → top-N → correlation filter
├── correlation_matrix.py       # Pairwise Pearson return correlation from prices
├── ic_monitor.py               # Information Coefficient / alpha decay monitoring
├── selection_bridge.py         # SelectionResult → StrategyContext + rank sizing
├── weight_optimizer.py         # Optuna TPE weight search with IC objective
└── instrument_scorer.py        # InstrumentScorer: orchestrator + rank normalization
```

Modified upstream files:
- `rl/agent.py` — `predict_with_confidence()` for live DRL confidence
- `market_strength/strength_scorer.py` — `_normalize_concave()` for sqrt ADX
- `core/engine.py` — `run_selection_cycle()`, async variant, auto strength_map
- `strategies/base.py` — `composite_score` / `selection_rank` in `StrategyContext`

### Verification

```powershell
poetry run pytest tests/selection/ -v --no-cov    # 77 passed
poetry run pytest tests/ -q --no-cov              # 662 passed (system-wide)
poetry run ruff check src/iatb/selection/          # 0 errors
poetry run mypy src/iatb/selection/ --strict        # 0 errors
poetry run bandit -r src/iatb/selection/ -q         # 0 issues
```

## Safety Infrastructure

The execution layer implements a 6-step safety pipeline per FIA, SEBI, and PRA standards.

### Order Execution Safety Chain

```
OrderManager.place_order(request)
  1. kill_switch.check_order_allowed()     → REJECT if engaged
  2. validate_order(5 gates)               → REJECT if any fails
  3. executor.execute_order(request)        → ExecutionResult
  4. daily_loss_guard.record_trade(pnl)     → AUTO-ENGAGE kill switch if breached
  5. audit_logger.log_order(...)            → SQLite persistence
  6. return result
```

### Kill Switch (`risk/kill_switch.py`)

Immediate trading halt. Cancels all open orders, blocks all new orders,
fires alert callback (e.g., Telegram). Manual-reset only via `disengage()`.
Accessible via `Engine.engage_kill_switch(reason)` and
`Engine.disengage_kill_switch()`.

### Daily Loss Guard (`risk/daily_loss_guard.py`)

Tracks cumulative intraday PnL. Auto-engages kill switch when loss exceeds
configurable threshold (default 2% NAV). Resets at market open.

### Pre-Trade Validator (`execution/pre_trade_validator.py`)

5 gates before any order reaches the executor:
1. Fat-finger quantity limit
2. Max notional value
3. Price deviation tolerance vs last known price
4. Position limit per instrument
5. Portfolio exposure cap

### Trade Audit Logger (`execution/trade_audit.py`)

SQLite persistence for every order + result: timestamp, symbol, side, quantity,
price, status, strategy_id, algo_id. Queryable by date for reconciliation.

### Pre-Flight Checks (`core/preflight.py`)

Runs before engine start. Fail-closed — engine does not start if any fails:
1. System clock drift < 2s
2. Executor connectivity
3. Kill switch disengaged
4. Data directory exists
5. Audit database writable

## Operational Guidelines

### Paper-Trade Deployment

```powershell
# 1. Run pre-flight + start engine
poetry run python -m iatb.core.runtime

# 2. Verify health endpoint
curl http://localhost:8000/health

# 3. Monitor logs for kill switch, daily loss, or pre-trade rejections
# 4. Run for 5+ sessions with selection logging enabled
# 5. Compare selection outputs against manual instrument picks
```

### Daily Operations

1. **Pre-market**: Engine startup runs pre-flight checks automatically
2. **Market open**: `daily_loss_guard.reset(current_nav)` clears intraday PnL
3. **During session**: Every order passes the 6-step safety pipeline
4. **Post-session**: `audit_logger.query_daily_trades(date)` for reconciliation
5. **Weekly**: `check_alpha_decay(scores, returns)` for selector validation
6. **Quarterly**: `optimize_weights_for_regime()` for weight recalibration

### Emergency Procedures

```python
# Immediate halt from code
engine.engage_kill_switch("manual emergency stop")

# Resume after investigation
engine.disengage_kill_switch()
```

### Graduation Criteria (Paper → Live)

- 30 clean paper days (0 errors, daily drawdown < configured limit)
- Kill switch tested (at least 2 drills with successful recovery)
- Paper PnL tracking within ±0.3% of model expectations
- IC above 0.03 for composite score vs 5-day forward returns

## Setup

### Prerequisites

- Python 3.12+
- Poetry
- Git
- GitHub CLI (optional, for GitHub integration)

### Installation

1. Clone the repository
2. Run the setup script:
   ```powershell
   .\scripts\setup.ps1
   ```

3. Copy `.env.example` to `.env` and fill in your API keys:
   ```powershell
   Copy-Item .env.example .env
   # Edit .env with your credentials
   ```

## Quality Gates

This project enforces strict quality standards:

- **Ruff**: Linting and formatting
- **MyPy**: Strict type checking
- **Bandit**: Security analysis
- **Pytest**: 90%+ code coverage
- **Gitleaks**: Secret detection

Run quality gates:
```powershell
.\scripts\quality_gate.ps1
```

Full system verification:
```powershell
poetry run pytest tests/ -q --no-cov    # 684 passed
poetry run ruff check src/              # 0 errors
poetry run mypy src/ --strict            # 0 errors
poetry run bandit -r src/ -q             # 0 issues
```

## Development Guidelines

- All functions must be ≤ 50 LOC
- Use `Decimal` for all financial data
- Use UTC-aware datetime only
- Use structured logging (no print statements)
- Follow PEP 8 style guide (enforced by Ruff)
- Frozen dataclasses for all data models
- Fail-closed validation in every public function

## Git & GitHub Setup

Initialize Git and create a private GitHub repository:
```powershell
.\scripts\git_sync.ps1
```

## Testing

Run tests with coverage:
```powershell
poetry run pytest
```

## License

Private Project - All rights reserved
