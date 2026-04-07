# iATB Paper-Trade Deployment Guide — Windows 11

Step-by-step instructions for deploying iATB on a local Windows 11 PC
for paper-trading validation.

## Prerequisites

- Windows 11 with PowerShell 5.1+
- Python 3.12+ installed and on PATH
- Poetry installed (`pip install poetry`)
- Git installed
- Static IP configured (required for SEBI API compliance)
- `.env` file with broker API credentials

## Step 1: Clone and Setup

```powershell
# Clone the repository
git clone git@github.com:npmvlKP/IATB-02Apr26.git
cd IATB-02Apr26\IATB

# Install dependencies
poetry install

# Copy environment template and fill in credentials
Copy-Item .env.example .env
# Edit .env with your API keys (Zerodha, Binance, etc.)
# NEVER commit .env to git
```

## Step 2: Verify Installation

```powershell
# Run quality gates
poetry run ruff check src/
poetry run mypy src/ --strict
poetry run bandit -r src/ -q

# Run full test suite (all 684 tests must pass)
poetry run pytest tests/ -q --no-cov
```

Expected output: `684 passed`

## Step 3: Configure Paper Trading

Edit `.env` to set paper-trading mode:

```
IATB_MODE=paper
IATB_DEFAULT_EXCHANGE=NSE
IATB_DATA_DIR=data
IATB_LOG_DIR=logs
IATB_CACHE_DIR=cache
IATB_AUDIT_DB=data/audit/trades.sqlite

# Kill switch defaults
IATB_MAX_DAILY_LOSS_PCT=0.02
IATB_MAX_ORDER_QUANTITY=100
IATB_MAX_ORDER_VALUE=500000
IATB_MAX_PRICE_DEVIATION_PCT=0.05
IATB_MAX_POSITION_PER_SYMBOL=200
IATB_MAX_PORTFOLIO_EXPOSURE=1000000
```

## Step 4: Create Required Directories

```powershell
New-Item -ItemType Directory -Path data, logs, cache, "data/audit" -Force
```

## Step 5: Run Pre-Flight Checks

```powershell
# Verify pre-flight passes before starting engine
poetry run python -c "
from pathlib import Path
from iatb.execution.paper_executor import PaperExecutor
from iatb.risk.kill_switch import KillSwitch
from iatb.core.preflight import run_preflight_checks

executor = PaperExecutor()
ks = KillSwitch(executor)
result = run_preflight_checks(executor, ks, Path('data'), Path('data/audit/trades.sqlite'))
print(f'Pre-flight: {\"PASS\" if result else \"FAIL\"}')
"
```

Expected output: `Pre-flight: PASS`

## Step 6: Start the Engine

```powershell
# Start engine with health server on port 8000
poetry run python -m iatb.core.runtime
```

The engine will:
1. Run pre-flight checks
2. Start the health server on http://localhost:8000/health
3. Start the event bus
4. Wait for signals (Ctrl+C to stop gracefully)

## Step 7: Verify Health Endpoint

In a separate PowerShell window:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected output: `{"status":"ok"}`

## Step 8: Monitor Logs

```powershell
# Watch logs in real-time
Get-Content logs/iatb.log -Wait -Tail 50
```

Key log messages to watch for:
- `KILL SWITCH ENGAGED` — trading halted (investigate immediately)
- `Daily loss limit breached` — auto-halt triggered
- `OPS throttle` — order rate limit hit
- `fat-finger` / `notional` / `price deviation` — pre-trade rejection
- `Preflight ... FAIL` — startup check failed

## Step 9: Daily Operations

### Morning (Pre-Market)

```powershell
# 1. Start engine (runs pre-flight automatically)
poetry run python -m iatb.core.runtime

# 2. Verify health
Invoke-RestMethod http://localhost:8000/health
```

### During Session

The engine runs automatically. The 7-step order pipeline handles:
1. Kill switch check
2. OPS throttle (10 orders/second max)
3. Pre-trade validation (5 gates)
4. Order execution (paper fills)
5. Daily loss tracking
6. Audit logging (SQLite)
7. Result return

### Evening (Post-Session)

```powershell
# 1. Stop engine (Ctrl+C in engine window)

# 2. Review daily trades
poetry run python -c "
from datetime import UTC, datetime
from pathlib import Path
from iatb.execution.trade_audit import TradeAuditLogger

logger = TradeAuditLogger(Path('data/audit/trades.sqlite'))
trades = logger.query_daily_trades(datetime.now(UTC).date())
print(f'Trades today: {len(trades)}')
for t in trades:
    print(f'  {t.order_id} {t.symbol} {t.side} {t.quantity} @ {t.price} [{t.status}]')
"

# 3. Check selection IC (weekly)
# Compare composite scores against 5-day forward returns
```

## Step 10: Emergency Procedures

### Immediate Halt

```powershell
# From Python:
poetry run python -c "
from iatb.execution.paper_executor import PaperExecutor
from iatb.risk.kill_switch import KillSwitch
from datetime import UTC, datetime

ks = KillSwitch(PaperExecutor())
ks.engage('manual emergency stop', datetime.now(UTC))
print('KILL SWITCH ENGAGED')
"
```

### Resume After Investigation

```powershell
poetry run python -c "
from iatb.execution.paper_executor import PaperExecutor
from iatb.risk.kill_switch import KillSwitch
from datetime import UTC, datetime

ks = KillSwitch(PaperExecutor())
ks.disengage(datetime.now(UTC))
print('Kill switch disengaged')
"
```

## Graduation Criteria (Paper → Live)

Before moving to live capital:

- [ ] 30 clean paper days (0 errors, drawdown < 2%)
- [ ] Kill switch tested (2+ drills with successful recovery)
- [ ] Paper PnL within ±0.3% of model expectations
- [ ] IC above 0.03 for composite score vs 5-day forward returns
- [ ] All SEBI compliance checks pass (algo ID, static IP, 2FA)
- [ ] Order rate stays below 10 OPS threshold
- [ ] Audit trail complete (every order persisted in SQLite)

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Pre-flight FAIL: data_dir_exists` | `data/` directory missing | `New-Item -ItemType Directory data -Force` |
| `Pre-flight FAIL: kill_switch_clear` | Kill switch engaged from previous session | Disengage via emergency procedure above |
| `order rejected: kill switch engaged` | Kill switch active | Investigate trigger, then disengage |
| `order rejected: OPS throttle exceeded` | >10 orders in 1 second | Normal rate limiting, will auto-clear next second |
| `fat-finger: quantity exceeds max` | Order too large | Reduce quantity or increase `max_order_quantity` |
| `price deviation exceeds max` | Stale price data | Update `last_prices` via `update_market_data()` |
| `Daily loss limit breached` | Cumulative loss exceeded 2% NAV | Review trades, reset next trading day |
