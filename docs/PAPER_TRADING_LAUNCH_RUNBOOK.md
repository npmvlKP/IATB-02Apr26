# IATB Paper Trading Launch Runbook — Production Guide

## Overview

This runbook provides **production-grade, error-free, sequential steps** to launch and deploy the IATB Paper Trading mode through local CPU for clear observation of functioning and performance.

Zerodha credentials are pre-configured in the `.env` file.

---

## Quick Start (3 Commands)

```powershell
# Step 1: Validate setup
poetry run python scripts/validate_paper_setup.py

# Step 2: Launch paper trading (13-step pipeline)
poetry run python scripts/launch_paper_trading.py

# Step 3: Monitor performance
poetry run python scripts/observe_paper_trading.py -i 30 -n 5
```

---

## Full PowerShell Runbook

```powershell
# Execute complete runbook (all 11 steps)
.\scripts\PAPER_TRADING_LAUNCH_RUNBOOK.ps1

# With options
.\scripts\PAPER_TRADING_LAUNCH_RUNBOOK.ps1 -ObserveCycles 5 -ObserveInterval 30

# Dry run (validate without executing)
.\scripts\PAPER_TRADING_LAUNCH_RUNBOOK.ps1 -DryRun

# Skip quality gates (faster launch)
.\scripts\PAPER_TRADING_LAUNCH_RUNBOOK.ps1 -SkipQualityGates -SkipTests
```

---

## Script Descriptions

### 1. `scripts/validate_paper_setup.py` — Pre-flight Setup Validator

Validates 8 checks before engine launch:

| Step | Check | Purpose |
|------|-------|---------|
| 1 | `.env` file exists | Zerodha credentials present |
| 2 | `config/settings.toml` paper mode | `execution_mode="paper"`, `live_trading_enabled=false` |
| 3 | Required directories | `data/`, `logs/`, `cache/`, `data/audit/` |
| 4 | Zerodha credentials | `ZERODHA_API_KEY` + `ZERODHA_API_SECRET` non-empty |
| 5 | Token manager instantiation | `ZerodhaTokenManager` can be created |
| 6 | Config singleton load | `get_config()` loads without error |
| 7 | Database paths writable | `data/audit/trades.sqlite`, `data/iatb.duckdb` |
| 8 | No live-mode conflicts | No `IATB_MODE=live` or `LIVE_TRADING_ENABLED=true` |

**Exit code:** 0 = all pass, 1 = any failure

```powershell
poetry run python scripts/validate_paper_setup.py
```

### 2. `scripts/launch_paper_trading.py` — Main Launcher (13 Steps)

Production-grade sequential deployment with fail-fast on critical steps:

| Step | Function | Critical | Description |
|------|----------|----------|-------------|
| 1 | `step_1_verify_environment` | Yes | Python 3.12+, Poetry, Git |
| 2 | `step_2_validate_credentials` | Yes | `.env` Zerodha keys present |
| 3 | `step_3_verify_settings_toml` | Yes | Paper mode flags in `settings.toml` |
| 4 | `step_4_create_directories` | No | `data/`, `logs/`, `cache/`, `data/audit/`, `data/backups/` |
| 5 | `step_5_apply_env_defaults` | No | Apply `.env` values to `os.environ` |
| 6 | `step_6_validate_token` | No | Zerodha token availability check |
| 7 | `step_7_load_config` | Yes | Config singleton, paper mode confirmed |
| 8 | `step_8_preflight` | Yes | Clock drift, executor, kill switch, paths |
| 9 | `step_9_build_safety_pipeline` | Yes | PaperExecutor + KillSwitch + OrderManager + 7-step risk pipeline |
| 10 | `step_10_start_engine` | No | Engine with EventBus + SSEBroadcaster + health check |
| 11 | `step_11_sample_trades` | No | 6 sample paper trades via risk pipeline |
| 12 | `step_12_kill_switch_drill` | No | Emergency engage/disengage verification |
| 13 | `step_13_audit_verification` | No | HMAC chain integrity check |

**Safety Pipeline Architecture (7-step risk pipeline per trade):**
1. Kill switch check → 2. Order throttle → 3. Pre-trade validation → 4. Paper execution → 5. Daily loss recording → 6. Trade audit logging → 7. Return result

```powershell
poetry run python scripts/launch_paper_trading.py
```

### 3. `scripts/observe_paper_trading.py` — Real-time Monitoring

Continuous observation dashboard with configurable refresh interval:

| Check | Source | Information |
|-------|--------|-------------|
| Config Status | `get_config()` | execution_mode, live_trading_enabled |
| Kill Switch | `KillSwitch` | engaged, orders_allowed |
| Daily Loss Guard | `DailyLossGuard` | cumulative_pnl, limit, breached, trade_count |
| Audit Trail | `TradeAuditLogger` | Today's trades, HMAC chain integrity |
| Zerodha Connection | `ZerodhaTokenManager` | Token availability, freshness |
| Database Files | File system | SQLite, DuckDB sizes |
| Paper Positions | State file | Symbol, quantity, average price |

```powershell
# Continuous monitoring (30s interval)
poetry run python scripts/observe_paper_trading.py

# 5 cycles at 60s interval
poetry run python scripts/observe_paper_trading.py -n 5 -i 60

# Verbose/debug mode
poetry run python scripts/observe_paper_trading.py -v
```

### 4. `scripts/PAPER_TRADING_LAUNCH_RUNBOOK.ps1` — Full PowerShell Runbook

End-to-end deployment with 11 automated steps:

| Step | Action |
|------|--------|
| 1 | Verify prerequisites (Python, Poetry, Git, `.env` credentials) |
| 2 | Install dependencies (`poetry install`) |
| 3 | Validate paper setup (`validate_paper_setup.py`) |
| 4 | Quality gates G1-G4 (ruff lint, format, bandit) |
| 5 | Run tests (G6: pytest) |
| 6 | Create required directories |
| 7 | Launch paper trading (`launch_paper_trading.py`) |
| 8 | Start continuous engine (`iatb.core.runtime`) |
| 9 | Observe performance (`observe_paper_trading.py`) |
| 10 | Additional checks (G7-G9: no float, no naive dt, no print) |
| 11 | Git sync (add, commit, push) |

**Parameters:**
- `-ObserveCycles <int>` — Number of observation cycles (default: 3)
- `-ObserveInterval <int>` — Seconds between observations (default: 30)
- `-SkipQualityGates` — Skip ruff/bandit checks
- `-SkipTests` — Skip pytest
- `-DryRun` — Validate without executing

---

## Architecture: Paper Trading Safety Pipeline

```
┌──────────────────────────────────────────────────────┐
│                  OrderManager                         │
│  ┌─────────────────────────────────────────────────┐ │
│  │           7-Step Risk Pipeline                   │ │
│  │                                                   │ │
│  │  1. KillSwitch ──── engaged? → REJECT            │ │
│  │  2. OrderThrottle ─ exceeded? → REJECT           │ │
│  │  3. PreTradeValidator ── 5 gates → REJECT        │ │
│  │  4. PaperExecutor ── deterministic slippage       │ │
│  │  5. DailyLossGuard ── limit breach? → KILL       │ │
│  │  6. TradeAuditLogger ── HMAC chain → SQLite      │ │
│  │  7. Return ExecutionResult                       │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  Engine: EventBus + SSEBroadcaster                    │
│  Config: execution_mode=paper, live_trading_enabled=false │
└──────────────────────────────────────────────────────┘
```

## Paper Executor Slippage Model

| Exchange | Segment | Base Slippage (bps) |
|----------|---------|---------------------|
| NSE | SPOT | 3 |
| NSE | FUTURES | 2 |
| NSE | OPTIONS | 2 |
| BSE | SPOT | 5 |
| MCX | All | 8 |
| Default | — | 5 |

Volume adjustment: `factor = 1 / (1 + 0.1 * log10(quantity + 1))`, bounded [0.5, 1.0]

---

## Emergency Procedures

### Kill Switch Activation

```python
# From Python
from iatb.risk.kill_switch import KillSwitch
from datetime import UTC, datetime

ks.engage("emergency: manual halt", datetime.now(UTC))
```

### Stop Engine

```powershell
# Find and kill the engine process
Get-Process -Name python | Where-Object { $_.CommandLine -like "*iatb*" } | Stop-Process
```

### Monitor Zerodha Connection

```powershell
poetry run python scripts/monitor_zerodha_connection.py
```

---

## Log Files

| File | Location | Purpose |
|------|----------|---------|
| Setup validation | `logs/paper_setup_validation_*.log` | Pre-flight check results |
| Launch log | `logs/paper_launch_*.log` | 13-step launch pipeline output |
| Observation log | `logs/paper_observe_*.log` | Continuous monitoring snapshots |
| Engine runtime | `logs/` | Engine heartbeat and event logs |
| Audit trail | `data/audit/trades.sqlite` | HMAC-chained trade records |
| Daily loss state | `data/audit/daily_loss.sqlite` | Intraday PnL tracking |

---

## Configuration Files

| File | Key Settings |
|------|-------------|
| `.env` | `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, `ZERODHA_ACCESS_TOKEN` |
| `config/settings.toml` | `execution_mode="paper"`, `live_trading_enabled=false`, `paper_trade_enforced=true` |
| `config/strategies.toml` | Strategy parameters |
| `config/watchlist.toml` | Traded instruments |
| `config/logging.toml` | Log levels and handlers |