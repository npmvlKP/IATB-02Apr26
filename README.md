# IATB - Indian Algorithmic Trading Bot

A Python-based algorithmic trading system specifically designed for the Indian market with Zerodha Kite Connect integration, supporting NSE/CDS/MCX exchanges and SEBI-compliant intraday MIS trading.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              IATB SYSTEM ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐  │
│  │   DATA LAYER │────▶│  CORE LAYER  │────▶│ EXECUTION    │────▶│  BROKER API  │  │
│  │              │     │              │     │   LAYER      │     │   (ZERODHA)  │  │
│  │ • Sentiment  │     │ • Engine     │     │ • Order Mgr  │     │              │  │
│  │ • Strength   │     │ • Event Bus  │     │ • Paper/Live │     │ • Kite API   │  │
│  │ • Volume     │     │ • Clock      │     │ • Risk Guard │     │ • WebSockets │  │
│  │ • Market Data│     │ • Config     │     │ • Pre-Trade  │     │              │  │
│  └──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘  │
│         │                     │                     │                                 │
│         ▼                     ▼                     ▼                                 │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                        │
│  │   ML/RL LAYER│     │ STRATEGIES   │     │   STORAGE    │                        │
│  │              │     │              │     │              │                        │
│  │ • LSTM/GNN   │     │ • Momentum   │     │ • DuckDB     │                        │
│  │ • HMM/Trans  │     │ • Breakout   │     │ • SQLite     │                        │
│  │ • PPO/A2C/SAC│     │ • Mean-Rev   │     │ • Parquet    │                        │
│  │ • Optimizer  │     │ • Ensemble   │     │ • Audit Log  │                        │
│  └──────────────┘     └──────────────┘     └──────────────┘                        │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                        SAFETY & COMPLIANCE LAYER                            │  │
│  │  • Kill Switch  • Daily Loss Guard  • Circuit Breaker  • SEBI Compliance   │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Features

- **Zerodha Integration**: Full support for Zerodha Kite Connect API
- **Multi-Exchange Support**: NSE (Equity), CDS (Currency), MCX (Commodities)
- **OpenAlgo Protocol**: Standardized algorithmic trading execution
- **Intraday MIS Only**: Focused on margin intraday square-off (MIS) trading
- **SEBI Compliance**: Built-in SEBI regulatory compliance and risk management
- **Structured Logging**: UTC-aware timestamps with comprehensive audit trails
- **Decimal Precision**: All financial calculations use Decimal type for accuracy
- **Quality Gates**: 90%+ code coverage with strict linting and security checks

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
│       ├── selection/         # Multi-factor instrument auto-selection
│       ├── sentiment/         # FinBERT + AION + VADER ensemble, volume filter
│       ├── storage/           # DuckDB, SQLite, Parquet, Git sync
│       ├── strategies/        # Momentum, breakout, mean-reversion, sentiment, ensemble
│       └── visualization/     # Dashboard, charts, alerts, breakout scanner
├── tests/                     # Test suite (90%+ coverage target)
├── scripts/                   # Setup, quality gates, git sync, verification
├── config/                    # Configuration files (settings, exchanges, holidays)
├── .env.example               # Environment variable template
└── pyproject.toml             # Project configuration
```

## Indian Market Configuration

### Supported Exchanges

| Exchange | Segment | Products | Trading Hours (IST) |
|----------|---------|----------|---------------------|
| **NSE** | Equity (Cash & F&O) | MIS Intraday | 09:15 - 15:30 |
| **CDS** | Currency Derivatives | MIS Intraday | 09:00 - 17:00 |
| **MCX** | Commodities | MIS Intraday | 09:00 - 23:30 |

### Product Types

- **MIS (Margin Intraday Square-off)**: Only supported product type
  - Auto square-off at 3:15 PM for NSE Equity
  - Auto square-off at 3:25 PM for NSE F&O
  - Higher leverage compared to NRML
  - Must square off positions intraday

### Broker Integration

**Zerodha Kite Connect**:
- API-based order placement and execution
- Real-time market data via WebSockets
- Historical data fetch for backtesting
- Margin and position tracking
- Order book and trade book updates

## Instrument Auto-Selection Module

The `selection/` package fuses four signal sources into a regime-aware composite
score per instrument, then ranks and selects the top candidates for trade execution.
Optimized for Indian market volatility and SEBI compliance.

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

## SEBI Compliance

This system implements SEBI-mandated safety features:

1. **Pre-Trade Risk Checks**: All orders validated before execution
2. **Position Limits**: Per-instrument and portfolio-level caps
3. **Intraday Square-Off**: Automatic MIS position closure at market close
4. **Audit Trail**: Complete order and trade history persistence
5. **Circuit Breaker Protection**: Automatic halt on excessive losses
6. **Kill Switch**: Immediate trading halt capability
7. **Real-time Monitoring**: Continuous PnL and exposure tracking

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

### Daily Operations (Indian Market)

1. **Pre-market (08:30-09:00 IST)**: Engine startup runs pre-flight checks automatically
2. **Market open (09:00-09:15 IST)**: `daily_loss_guard.reset(current_nav)` clears intraday PnL
3. **Trading session (09:15-15:30 IST)**: Every order passes the 6-step safety pipeline
4. **Pre-close (15:15-15:30 IST)**: Automatic MIS square-off for Equity positions
5. **Post-session**: `audit_logger.query_daily_trades(date)` for reconciliation
6. **Weekly**: `check_alpha_decay(scores, returns)` for selector validation
7. **Quarterly**: `optimize_weights_for_regime()` for weight recalibration

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
- SEBI compliance validation passed
- Zerodha API rate limits tested and validated

## Setup

### Prerequisites

- Python 3.12+
- Poetry
- Git
- GitHub CLI (optional, for GitHub integration)
- Zerodha Kite Connect API credentials

### Installation

1. Clone the repository
2. Run the setup script:
   ```powershell
   .\scripts\setup.ps1
   ```

3. Copy `.env.example` to `.env` and fill in your Zerodha API keys:
   ```powershell
   Copy-Item .env.example .env
   # Edit .env with your credentials
   ```

### Configuration

Edit `config/settings.toml`:
```toml
[broker]
name = "zerodha"
live_trading_enabled = false  # Set to true only after paper trading validation

[network]
static_ip = "your.static.ip.address"  # Required for Zerodha API whitelisting

[algorithm]
algo_id = "your-unique-algo-id"  # Unique identifier for your trading algorithm
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

## Verification Scripts

### Core Architecture Verification

```powershell
# Verify core module structure and imports
poetry run python scripts/verify_core_architecture.py
```

### Zerodha Connection Test

```powershell
# Test Zerodha API connectivity
poetry run python scripts/zerodha_connect.py
```

### Usage Examples

```powershell
# Run usage examples and demonstrations
poetry run python scripts/usage_examples.py
```

### Dashboard

```powershell
# Launch visualization dashboard
poetry run python scripts/dashboard.py
```

## Development Guidelines

- All functions must be ≤ 50 LOC
- Use `Decimal` for all financial data
- Use UTC-aware datetime only (convert to IST for display)
- Use structured logging (no print statements)
- Follow PEP 8 style guide (enforced by Ruff)
- Frozen dataclasses for all data models
- Fail-closed validation in every public function
- SEBI compliance in all trading logic
- Zerodha API rate limit handling

## Git & GitHub Setup

Initialize Git and sync to remote repository:
```powershell
.\scripts\git_sync.ps1
```

## Testing

Run tests with coverage:
```powershell
poetry run pytest
```

Run specific test suites:
```powershell
# Selection module tests
poetry run pytest tests/selection/ -v --no-cov

# Core engine tests
poetry run pytest tests/core/ -v --no-cov

# Risk management tests
poetry run pytest tests/risk/ -v --no-cov
```

## Trading Hours & Holidays

### NSE Trading Schedule

| Segment | Trading Hours (IST) | Square-Off Time |
|---------|---------------------|-----------------|
| Equity (Cash) | 09:15 - 15:30 | 15:15 |
| Equity (F&O) | 09:15 - 15:30 | 15:25 |
| Currency (CDS) | 09:00 - 17:00 | 16:45 |

### MCX Trading Schedule

| Segment | Trading Hours (IST) | Square-Off Time |
|---------|---------------------|-----------------|
| Commodity | 09:00 - 23:30 | 23:15 |

### Holiday Calendar

NSE/CDS/MCX holidays are defined in `config/nse_holidays.toml` for 2026-2027.
The system automatically checks for trading holidays and prevents order placement
on non-trading days.

## Documentation

### Comprehensive Guides

- **[Architecture Documentation](docs/ARCHITECTURE.md)** - Complete system architecture, data flows, component interactions, and technology stack
- **[API Reference](docs/API_REFERENCE.md)** - Detailed API documentation for all modules and endpoints
- **[Strategy Development Guide](docs/STRATEGY_DEVELOPMENT_GUIDE.md)** - Step-by-step guide for creating, testing, and deploying trading strategies
- **[Deployment Guide](DEPLOYMENT.md)** - Complete deployment checklist and operational procedures

### Quick Start

1. **Read the Architecture** - Understand system design and components
2. **Review API Reference** - Learn available APIs and usage patterns
3. **Develop Strategies** - Follow the Strategy Development Guide
4. **Deploy System** - Use the Deployment Guide for setup

### Developer Onboarding

New developers can get started in under 1 hour by:
1. Reading the Architecture Documentation (15 min)
2. Reviewing API Reference for relevant modules (20 min)
3. Following Strategy Development Guide examples (15 min)
4. Running the Deployment Guide setup (10 min)

## License

Private Project - All rights reserved

## Disclaimer

This software is for educational and research purposes only. Algorithmic trading
involves significant risk of loss. Ensure you understand the risks and have
appropriate risk management in place before trading with real capital. All
trading activities must comply with SEBI regulations and Zerodha's terms of service.