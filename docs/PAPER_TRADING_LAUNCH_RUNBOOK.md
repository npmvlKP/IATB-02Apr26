# IATB Paper Trading Launch Runbook — Local CPU (Windows 11)

Sequential step-by-step procedure to launch the paper trading deployment from the local CPU.

---

## PHASE 1: PREREQUISITES & ENVIRONMENT SETUP

### Step 1: Verify System Prerequisites

Open **PowerShell** in `G:\IATB-02Apr26\IATB`:

```powershell
# Verify Python 3.12+
python --version
# Expected: Python 3.12.x or higher

# Verify Poetry
poetry --version
# Expected: Poetry 1.x+

# Verify Git
git --version
# Expected: git 2.x+

# Confirm working directory
pwd
# Expected: G:\IATB-02Apr26\IATB
```

### Step 2: Install Dependencies

```powershell
poetry install
```

Key packages installed:
- **Core**: pydantic, pydantic-settings, fastapi, uvicorn, pandas, numpy, scipy, duckdb
- **Broker**: ktz (Kite Connect), pyotp (2FA), keyring (token storage)
- **Observability**: opentelemetry-api, prometheus-client
- **Dev**: ruff, mypy, bandit, pytest

### Step 3: Configure Environment Variables

```powershell
# Create .env from template
Copy-Item .env.example .env -Force
```

Edit `.env` with actual values:

```ini
# Broker OAuth
BROKER_OAUTH_2FA_VERIFIED=false

# Zerodha API Credentials (from https://kite.zerodha.com/connect/api)
ZERODHA_API_KEY=your_api_key_here
ZERODHA_API_SECRET=your_api_secret_here

# Request Token (temporary, from OAuth flow)
ZERODHA_REQUEST_TOKEN=
ZERODHA_REQUEST_TOKEN_DATE_UTC=

# Access Token (from OAuth flow)
ZERODHA_ACCESS_TOKEN=
ZERODHA_ACCESS_TOKEN_DATE_UTC=

# TOTP Secret for 2FA (optional, for automated re-login)
ZERODHA_TOTP_SECRET=
```

> **Paper-only mode without Zerodha**: The engine runs in degraded mode without
> credentials. Set `data_provider_default = "yfinance"` in `config/settings.toml`
> for free market data without Zerodha.
>
> **NEVER commit `.env` to git.**

### Step 4: Verify Configuration Files

Config priority (highest → lowest):
1. Environment variables
2. `.env` file
3. `config/settings.toml`
4. Hardcoded defaults in `src/iatb/core/config.py`

Verify paper mode settings:

```powershell
# execution_mode must be "paper"
Get-Content config/settings.toml | Select-String "execution_mode"
# Expected: execution_mode = "paper"

# live_trading_enabled must be false
Get-Content config/settings.toml | Select-String "live_trading_enabled"
# Expected: live_trading_enabled = false

# paper_trade_enforced must be true
Get-Content config/settings.toml | Select-String "paper_trade_enforced"
# Expected: paper_trade_enforced = true
```

Configuration files:

| File | Purpose |
|------|---------|
| `config/settings.toml` | Main: execution mode, broker, engine, data, observability, storage |
| `config/strategies.toml` | Strategy params: MA periods, RSI, Bollinger, Donchian |
| `config/watchlist.toml` | Symbols per exchange: NSE, BSE, MCX, CDS |
| `config/logging.toml` | Logging level, format (JSON), file rotation |
| `config/exchanges.toml` | Exchange-specific settings |
| `config/weights.toml` | Scoring weights for instrument selection |
| `config/nse_holidays.toml` | NSE holiday calendar |

---

## PHASE 2: QUALITY GATES & VALIDATION

### Step 5: Run Quality Gates

```powershell
# Lint
poetry run ruff check src/

# Format
poetry run ruff format --check src/

# Types
poetry run mypy src/ --strict

# Security
poetry run bandit -r src/ -q

# Tests
poetry run pytest tests/ -q --no-cov
```

### Step 6: Create Required Directories

```powershell
New-Item -ItemType Directory -Path data, logs, cache, "data/audit", "data/backups" -Force
```

### Step 7: Run Pre-Flight Checks

```powershell
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

Expected: `Pre-flight: PASS`

Checks performed:
- Clock drift (system clock within 2s of NTP)
- Executor ready (no stale open orders)
- Kill switch clear (not engaged from previous session)
- Data directory exists
- Audit DB path writable

---

## PHASE 3: START PAPER TRADING

### Step 8: Set Paper Trading Environment Variables

```powershell
$env:IATB_MODE = "paper"
$env:LIVE_TRADING_ENABLED = "false"
$env:IATB_CONFIG_PATH = ".\config\settings.toml"
```

> **Safety guarantee**: The `Config` class enforces fail-closed. Even if
> `settings.toml` has `execution_mode = "live"`, setting
> `LIVE_TRADING_ENABLED=false` forces downgrade to paper. Live mode also
> requires explicit `confirm_live_mode()` interactive confirmation — without
> it, the system auto-reverts to paper.

### Step 9: Start the Trading Engine

Choose **one** method:

---

#### Method A: Engine Runtime Only (Minimal, Headless)

```powershell
poetry run python -m iatb.core.runtime
```

Startup sequence (`src/iatb/core/runtime.py`):
1. Loads Config via `get_config()` — env vars → .env → settings.toml → defaults
2. Creates EventBus (async queue, max 1000, batch 100)
3. Creates SSEBroadcaster (real-time event streaming)
4. Creates Engine with all components
5. Calls `engine.start()` -- validates mode, starts EventBus + SSEBroadcaster
6. Logs `Engine is running in 'paper' mode - waiting for events/signals. Press Ctrl+C to stop gracefully.`
7. Enters idle loop with **60-second heartbeat** (engine health, event bus status, uptime, mode)
8. Registers SIGINT/SIGTERM handlers (Ctrl+C = graceful shutdown)

> **This is NOT hung** -- the engine is an async event loop that waits
> indefinitely for trading signals. After startup you will see:
> ```
> IATB runtime started
> Engine is running in 'paper' mode - waiting for events/signals.
> Press Ctrl+C to stop gracefully.
> ```
> Then every 60 seconds a heartbeat line appears:
> ```
> Heartbeat | engine=running | event_bus=ok | uptime=60s | mode=paper
> ```
> This confirms the engine is alive and functioning.
>
> **Note**: No HTTP server on port 8000 with this method. Health endpoints
> are not available. Use Method D if you need HTTP.

---

#### Method B: PowerShell Script (Wraps Method A)

```powershell
.\scripts\start_paper.ps1
```

This sets `$env:IATB_MODE="paper"`, `$env:LIVE_TRADING_ENABLED="false"`,
then runs `poetry run python -m iatb.core.runtime`.

Same limitation as Method A — no HTTP server.

---

#### Method C: Master Startup — Engine + Dashboard (Full UI)

```powershell
poetry run python scripts/start_master.py
```

This starts:
1. Engine (PaperExecutor + KillSwitch + Engine.start())
2. Dashboard on port 8080 (`scripts/dashboard.py`)
3. Monitors both; Ctrl+C stops both gracefully

Open browser: **http://localhost:8080**

Dashboard shows: engine health, trades today, session PnL, sentiment health,
recent trades table, deployment log tail. Auto-refreshes every 5 seconds.

> **Note**: The master script creates Engine programmatically, not via FastAPI.
> HTTP endpoints on port 8000 are not served. Dashboard on 8080 works
> independently via Python calls.

---

#### Method D: FastAPI HTTP Server (For REST API Access)

```powershell
poetry run uvicorn iatb.fastapi_app:app --host 0.0.0.0 --port 8000
```

Available endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Legacy health check |
| `/health/live` | GET | Liveness probe (200 if process running) |
| `/health/ready` | GET | Readiness (engine + event bus + API ready) |
| `/broker/status` | GET | Zerodha connection status + balance |
| `/charts/ohlcv/{ticker}` | GET | OHLCV data (e.g. NIFTY, RELIANCE) |
| `/config/watchlist` | GET | Watchlist symbols per exchange |
| `/config/watchlist` | PUT | Update watchlist dynamically |
| `/ml/status` | GET | ML model availability + health |
| `/metrics` | GET | Prometheus metrics |
| `/events/stream` | GET | SSE real-time event stream |

> **Tip**: Run Method A in one terminal (engine loop) and Method D in a second
> terminal (HTTP endpoints). They coexist.

---

#### Method E: Full 10-Step Deployment Validation

```powershell
poetry run python scripts/deploy_paper_trade.py
```

Executes all 10 steps automatically:

| Step | Action | Validates |
|------|--------|-----------|
| 1 | Verify environment | Python 3.12+, Poetry, Git |
| 2 | Quality gates | Ruff lint/format, Bandit, Pytest |
| 3 | Configure paper trading | .env file exists or created |
| 4 | Create directories | data/, logs/, cache/, data/audit/ |
| 5 | Pre-flight checks | Clock drift, executor, kill switch, paths |
| 6 | Start engine | Engine starts successfully |
| 7 | Health check | Endpoint availability |
| 8 | Sample paper trades | 4 trades through full safety pipeline |
| 9 | Daily PnL summary | Queries audit SQLite |
| 10 | Kill switch drill | Engage → block → disengage → allow |

> Steps 6-7 start and stop the engine (validation only). Use Method A or C
> to keep it running afterward.

---

### Step 10: Verify the Engine is Running

**Method A/B** (runtime only): Look for log lines:
```
Starting engine
Engine started
IATB runtime started
```

**Method C** (master startup): Look for:
```
✓ Engine started (running: True)
✓ Dashboard started on port 8080
```

**Method D** (FastAPI): Open a second PowerShell:
```powershell
# Liveness
Invoke-RestMethod http://localhost:8000/health/live
# Expected: {"status":"alive","timestamp":"..."}

# Readiness
Invoke-RestMethod http://localhost:8000/health/ready
# Expected: {"status":"ready","checks":{"engine":{"status":"ready"},...}}

# Legacy health
Invoke-RestMethod http://localhost:8000/health
# Expected: {"status":"ok"} or {"status":"degraded"} (no broker creds)
```

---

## PHASE 4: MONITOR & OPERATE

### Step 11: Monitor Logs

```powershell
# Real-time log tail
Get-Content logs\iatb.log -Wait -Tail 50

# JSON structured logs
Get-Content logs\iatb.json -Wait -Tail 50
```

Critical log messages:

| Message | Severity | Action |
|---------|----------|--------|
| `KILL SWITCH ENGAGED` | CRITICAL | Investigate immediately |
| `Daily loss limit breached` | CRITICAL | Review trades, auto-halt triggered |
| `OPS throttle` | WARNING | Order rate limit (10/sec), auto-clears |
| `fat-finger` / `notional` / `price deviation` | WARNING | Pre-trade rejection (expected) |
| `Preflight ... FAIL` | ERROR | Startup check failed |
| `Engine started` | INFO | Normal startup |
| `IATB runtime started` | INFO | Normal runtime |
| `Heartbeat` | INFO | Idle loop health check (every 60s) |
| `Engine is running in 'paper' mode` | INFO | Startup confirmation -- not hung |
| `Heartbeat` | INFO | Idle loop health check (every 60s) |
| `Engine is running in 'paper' mode` | INFO | Startup confirmation -- not hung |

### Step 12: Pre-Market Token Validation

```powershell
# Validate Zerodha token immediately
poetry run python scripts/pre_market_token_validator.py

# Scheduled: waits for 9:00 AM IST then validates
poetry run python scripts/pre_market_token_validator.py --scheduled

# Custom time
poetry run python scripts/pre_market_token_validator.py --scheduled --hour 8 --minute 55
```

Validates: token freshness (Zerodha tokens expire 6:00 AM IST daily),
auto-relogin with TOTP if `ZERODHA_TOTP_SECRET` set, alerts on failure.

---

## PHASE 5: PAPER TRADING OPERATIONS

### Step 13: Execute Paper Trades via Python

```powershell
poetry run python -c "
from decimal import Decimal
from iatb.core.enums import Exchange, OrderSide
from iatb.execution.base import OrderRequest
from iatb.execution.order_manager import OrderManager
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.order_throttle import OrderThrottle
from iatb.execution.pre_trade_validator import PreTradeConfig
from iatb.execution.trade_audit import TradeAuditLogger
from iatb.risk.daily_loss_guard import DailyLossGuard
from iatb.risk.kill_switch import KillSwitch
from pathlib import Path

executor = PaperExecutor()
kill_switch = KillSwitch(executor)
config = PreTradeConfig(
    max_order_quantity=Decimal('100'),
    max_order_value=Decimal('500000'),
    max_price_deviation_pct=Decimal('0.05'),
    max_position_per_symbol=Decimal('200'),
    max_portfolio_exposure=Decimal('1000000'),
)
daily_guard = DailyLossGuard(
    max_daily_loss_pct=Decimal('0.02'),
    starting_nav=Decimal('1000000'),
    kill_switch=kill_switch,
)
audit = TradeAuditLogger(Path('data/audit/trades.sqlite'))
throttle = OrderThrottle(max_ops=10)
mgr = OrderManager(
    executor=executor,
    kill_switch=kill_switch,
    pre_trade_config=config,
    daily_loss_guard=daily_guard,
    audit_logger=audit,
    order_throttle=throttle,
    algo_id='IATB-PAPER-001',
)
mgr.update_market_data(
    last_prices={'NIFTY': Decimal('22500'), 'BANKNIFTY': Decimal('48000'), 'RELIANCE': Decimal('2800')},
    positions={},
    total_exposure=Decimal('0'),
)
request = OrderRequest(exchange=Exchange.NSE, symbol='NIFTY', side=OrderSide.BUY, quantity=Decimal('10'), price=Decimal('22500'))
result = mgr.place_order(request, strategy_id='paper_test')
print(f'Order: {result.order_id} | Status: {result.status.value} | Fill: {result.average_price}')
"
```

**7-Step Order Safety Pipeline** (every order):

| Step | Gate | Action |
|------|------|--------|
| 1 | Kill switch check | REJECT if engaged |
| 2 | OPS throttle | REJECT if >10 orders/sec |
| 3 | Pre-trade validation (5 gates) | REJECT: fat-finger qty, max notional, price deviation, position limit, portfolio exposure |
| 4 | Order execution | Paper fill (instant at requested price) |
| 5 | Daily loss guard | Auto-engage kill switch if 2% NAV breached |
| 6 | Audit logging | Persist to `data/audit/trades.sqlite` |
| 7 | Result return | Order ID, fill price, status |

### Step 14: Review Daily Trades (Post-Session)

```powershell
poetry run python -c "
from datetime import UTC, datetime
from pathlib import Path
from iatb.execution.trade_audit import TradeAuditLogger

logger = TradeAuditLogger(Path('data/audit/trades.sqlite'))
trades = logger.query_daily_trades(datetime.now(UTC).date())
print(f'Trades today: {len(trades)}')
for t in trades:
    print(f' {t.order_id} {t.symbol} {t.side} qty={t.quantity} @ {t.price} [{t.status}]')
"
```

---

## PHASE 6: SHUTDOWN & EMERGENCY PROCEDURES

### Step 15: Graceful Shutdown

Press **Ctrl+C** in the engine terminal.

Shutdown sequence:
1. Signal handler sets stop event
2. Engine cancels all running async tasks
3. SSEBroadcaster stops
4. EventBus stops
5. Logs: `IATB runtime stopped` + `Engine stopped`

### Step 16: Emergency Kill Switch

```powershell
# ENGAGE — halt all trading immediately
poetry run python -c "
from iatb.execution.paper_executor import PaperExecutor
from iatb.risk.kill_switch import KillSwitch
from datetime import UTC, datetime

ks = KillSwitch(PaperExecutor())
ks.engage('manual emergency stop', datetime.now(UTC))
print('KILL SWITCH ENGAGED — all orders blocked')
"

# DISENGAGE — resume after investigation
poetry run python -c "
from iatb.execution.paper_executor import PaperExecutor
from iatb.risk.kill_switch import KillSwitch
from datetime import UTC, datetime

ks = KillSwitch(PaperExecutor())
ks.disengage(datetime.now(UTC))
print('Kill switch disengaged — orders allowed')
"
```

---

## TROUBLESHOOTING

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Pre-flight FAIL: data_dir_exists` | `data/` missing | `New-Item -ItemType Directory data -Force` |
| `Pre-flight FAIL: kill_switch_clear` | Kill switch engaged | Disengage via Step 16 |
| `order rejected: kill switch engaged` | Kill switch active | Investigate trigger, then disengage |
| `order rejected: OPS throttle exceeded` | >10 orders/sec | Normal, auto-clears next second |
| `fat-finger: quantity exceeds max` | Order too large | Reduce qty or increase `max_order_quantity` |
| `price deviation exceeds max` | Stale price data | Update via `mgr.update_market_data()` |
| `Daily loss limit breached` | Cumulative loss >2% NAV | Review trades, resets next day |
| `API not configured` on `/health` | Missing KITE creds | Set in `.env` or use yfinance provider |
| `Clock drift exceeds 2s` | System clock unsynced | `w32tm /resync` (admin PowerShell) |
| `poetry install` fails | Python version | Ensure Python 3.10+ |
| `ModuleNotFoundError: iatb` | Not via poetry | Use `poetry run` prefix |
| `Port 8000 already in use` | Stale uvicorn | `Get-Process -Name python \| Stop-Process` |
| Engine appears hung/frozen | Normal async wait loop | Not hung -- look for heartbeat every 60s or Ctrl+C to stop |

---

## QUICK-START (3 Commands)

```powershell
poetry install
$env:IATB_MODE = "paper"; $env:LIVE_TRADING_ENABLED = "false"
poetry run python -m iatb.core.runtime
```

Press **Ctrl+C** to stop gracefully.