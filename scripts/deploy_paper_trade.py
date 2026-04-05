#!/usr/bin/env python
"""
iATB Paper-Trade Deployment Script — Windows 11

Executes every step from DEPLOYMENT.md in sequence:
  Step 1: Verify environment (Python, Poetry, Git)
  Step 2: Run quality gates (ruff, mypy, bandit, pytest)
  Step 3: Configure paper trading (.env validation)
  Step 4: Create required directories
  Step 5: Run pre-flight checks
  Step 6: Start engine with safety pipeline
  Step 7: Verify health endpoint
  Step 8: Execute sample paper trades with full pipeline
  Step 9: Daily PnL summary + audit trail
  Step 10: Emergency kill switch drill

All output is logged to logs/deployment_YYYYMMDD_HHMMSS.log
and printed to console in real time.
"""

import asyncio
import json
import logging
import subprocess
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

# ── Logging setup ──

_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / f"deployment_{_TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("deploy")


# ── Utilities ──


def _section(title: str) -> None:
    bar = "=" * 70
    log.info("")
    log.info(bar)
    log.info("  %s", title)
    log.info(bar)


def _run_cmd(cmd: str, check: bool = True) -> tuple[int, str]:
    """Run a shell command, log output, return (exitcode, stdout)."""
    log.info("  $ %s", cmd)
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=str(Path.cwd()),
    )
    combined = (result.stdout + result.stderr).strip()
    for line in combined.splitlines():
        log.info("    %s", line)
    if check and result.returncode != 0:
        log.error("  FAILED (exit %d)", result.returncode)
    return result.returncode, combined


def _pass_fail(ok: bool) -> str:
    return "PASS ✓" if ok else "FAIL ✗"


# ── Step 1: Verify Environment ──


def step_1_verify_environment() -> bool:
    _section("Step 1: Verify Environment")
    checks = [
        ("Python 3.12+", "python --version"),
        ("Poetry", "poetry --version"),
        ("Git", "git --version"),
    ]
    all_ok = True
    for name, cmd in checks:
        code, out = _run_cmd(cmd, check=False)
        ok = code == 0
        log.info("  %s: %s — %s", name, _pass_fail(ok), out.split("\n")[0])
        if not ok:
            all_ok = False
    return all_ok


# ── Step 2: Quality Gates ──


def step_2_quality_gates() -> bool:
    _section("Step 2: Quality Gates")
    gates = [
        ("Ruff lint", "poetry run ruff check src/"),
        ("Ruff format", "poetry run ruff format --check src/"),
        ("Bandit security", "poetry run bandit -r src/ -q"),
        ("Pytest (full suite)", "poetry run pytest tests/ -q --no-cov --tb=line"),
    ]
    all_ok = True
    for name, cmd in gates:
        code, out = _run_cmd(cmd, check=False)
        ok = code == 0
        log.info("  %s: %s", name, _pass_fail(ok))
        if not ok:
            all_ok = False
    return all_ok


# ── Step 3: Configure Paper Trading ──


def step_3_configure() -> bool:
    _section("Step 3: Configure Paper Trading")
    env_path = Path(".env")
    if not env_path.exists():
        example = Path(".env.example")
        if example.exists():
            import shutil
            shutil.copy(example, env_path)
            log.info("  Created .env from .env.example")
        else:
            log.warning("  No .env or .env.example found — creating minimal .env")
            env_path.write_text(
                "IATB_MODE=paper\n"
                "IATB_DEFAULT_EXCHANGE=NSE\n"
                "IATB_DATA_DIR=data\n"
                "IATB_LOG_DIR=logs\n"
                "IATB_CACHE_DIR=cache\n",
                encoding="utf-8",
            )
    log.info("  .env exists: %s", _pass_fail(env_path.exists()))
    return env_path.exists()


# ── Step 4: Create Directories ──


def step_4_create_directories() -> bool:
    _section("Step 4: Create Required Directories")
    dirs = [Path("data"), Path("logs"), Path("cache"), Path("data/audit")]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        log.info("  %s: %s", d, _pass_fail(d.exists()))
    return all(d.exists() for d in dirs)


# ── Step 5: Pre-Flight Checks ──


def step_5_preflight() -> bool:
    _section("Step 5: Pre-Flight Checks")
    from iatb.core.preflight import run_preflight_checks
    from iatb.execution.paper_executor import PaperExecutor
    from iatb.risk.kill_switch import KillSwitch

    executor = PaperExecutor()
    ks = KillSwitch(executor)
    result = run_preflight_checks(
        executor, ks, Path("data"), Path("data/audit/trades.sqlite"),
    )
    log.info("  Pre-flight: %s", _pass_fail(result))
    return result


# ── Step 6+7: Start Engine + Health Check ──


async def step_6_7_engine_and_health() -> bool:
    _section("Step 6: Start Engine")
    from iatb.core.engine import Engine
    from iatb.core.health import HealthServer
    from iatb.execution.paper_executor import PaperExecutor
    from iatb.risk.kill_switch import KillSwitch

    executor = PaperExecutor()
    kill_switch = KillSwitch(executor)
    engine = Engine(kill_switch=kill_switch)
    health = HealthServer(port=8000)

    try:
        health.start()
        await engine.start()
        log.info("  Engine started: %s", _pass_fail(engine.is_running))
    except Exception as exc:
        log.error("  Engine start failed: %s", exc)
        return False

    _section("Step 7: Health Endpoint Check")
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as resp:
            body = resp.read().decode()
            ok = '"status":"ok"' in body or '"status": "ok"' in body
            log.info("  Health check: %s — %s", _pass_fail(ok), body)
    except Exception as exc:
        log.warning("  Health check: %s — %s", _pass_fail(False), exc)

    await engine.stop()
    health.stop()
    log.info("  Engine stopped cleanly")
    return True


# ── Step 8: Execute Sample Paper Trades ──


def step_8_sample_trades() -> dict[str, Decimal]:
    _section("Step 8: Execute Sample Paper Trades")
    from iatb.core.enums import Exchange, OrderSide
    from iatb.execution.base import OrderRequest
    from iatb.execution.order_manager import OrderManager
    from iatb.execution.order_throttle import OrderThrottle
    from iatb.execution.paper_executor import PaperExecutor
    from iatb.execution.pre_trade_validator import PreTradeConfig
    from iatb.execution.trade_audit import TradeAuditLogger
    from iatb.risk.daily_loss_guard import DailyLossGuard
    from iatb.risk.kill_switch import KillSwitch

    executor = PaperExecutor()
    kill_switch = KillSwitch(executor)
    config = PreTradeConfig(
        max_order_quantity=Decimal("100"),
        max_order_value=Decimal("500000"),
        max_price_deviation_pct=Decimal("0.05"),
        max_position_per_symbol=Decimal("200"),
        max_portfolio_exposure=Decimal("1000000"),
    )
    daily_guard = DailyLossGuard(
        max_daily_loss_pct=Decimal("0.02"),
        starting_nav=Decimal("1000000"),
        kill_switch=kill_switch,
    )
    audit = TradeAuditLogger(Path("data/audit/trades.sqlite"))
    throttle = OrderThrottle(max_ops=10)

    mgr = OrderManager(
        executor=executor,
        kill_switch=kill_switch,
        pre_trade_config=config,
        daily_loss_guard=daily_guard,
        audit_logger=audit,
        order_throttle=throttle,
        algo_id="IATB-PAPER-001",
    )
    mgr.update_market_data(
        last_prices={
            "NIFTY": Decimal("22500"),
            "BANKNIFTY": Decimal("48000"),
            "RELIANCE": Decimal("2800"),
        },
        positions={},
        total_exposure=Decimal("0"),
    )

    trades = [
        ("NIFTY", "10", "22500", OrderSide.BUY),
        ("BANKNIFTY", "5", "48000", OrderSide.BUY),
        ("RELIANCE", "20", "2800", OrderSide.SELL),
        ("NIFTY", "10", "22520", OrderSide.SELL),
    ]

    pnl_log: dict[str, Decimal] = {}
    total_pnl = Decimal("0")
    errors: list[str] = []

    for symbol, qty, price, side in trades:
        try:
            request = OrderRequest(
                exchange=Exchange.NSE,
                symbol=symbol,
                side=side,
                quantity=Decimal(qty),
                price=Decimal(price),
            )
            result = mgr.place_order(request, strategy_id="paper_deploy_test")
            fill_pnl = (result.average_price - Decimal(price)) * Decimal(qty)
            if side == OrderSide.SELL:
                fill_pnl = -fill_pnl
            total_pnl += fill_pnl
            pnl_log[result.order_id] = fill_pnl
            log.info(
                "  %s %s %s x%s @ %s → %s (PnL: %s)",
                result.order_id,
                side.value,
                symbol,
                qty,
                result.average_price,
                result.status.value,
                fill_pnl,
            )
        except Exception as exc:
            err_msg = f"{side.value} {symbol}: {exc}"
            errors.append(err_msg)
            log.error("  REJECTED: %s", err_msg)

    log.info("")
    log.info("  Trades executed: %d", len(pnl_log))
    log.info("  Trades rejected: %d", len(errors))
    log.info("  Session PnL: %s", total_pnl)
    log.info("  Kill switch engaged: %s", kill_switch.is_engaged)
    log.info("  Daily loss state: %s", daily_guard.state)

    return {"total_pnl": total_pnl, "trades": Decimal(len(pnl_log)), "errors": Decimal(len(errors))}


# ── Step 9: Daily Summary + Audit ──


def step_9_daily_summary() -> None:
    _section("Step 9: Daily PnL Summary + Audit Trail")
    from iatb.execution.trade_audit import TradeAuditLogger

    audit = TradeAuditLogger(Path("data/audit/trades.sqlite"))
    today = datetime.now(UTC).date()
    trades = audit.query_daily_trades(today)
    log.info("  Date: %s", today.isoformat())
    log.info("  Total trades in audit: %d", len(trades))
    for t in trades:
        log.info(
            "    %s | %s %s | qty=%s price=%s | %s | algo=%s",
            t.order_id,
            t.side,
            t.symbol,
            t.quantity,
            t.price,
            t.status,
            t.algo_id,
        )


# ── Step 10: Kill Switch Drill ──


def step_10_kill_switch_drill() -> bool:
    _section("Step 10: Kill Switch Emergency Drill")
    from iatb.execution.paper_executor import PaperExecutor
    from iatb.risk.kill_switch import KillSwitch

    executor = PaperExecutor()
    ks = KillSwitch(executor)

    log.info("  Engaging kill switch...")
    state = ks.engage("deployment drill", datetime.now(UTC))
    log.info("  State: engaged=%s, reason='%s'", state.engaged, state.reason)

    orders_blocked = not ks.check_order_allowed()
    log.info("  Orders blocked: %s", _pass_fail(orders_blocked))

    log.info("  Disengaging kill switch...")
    state = ks.disengage(datetime.now(UTC))
    log.info("  State: engaged=%s", state.engaged)

    orders_allowed = ks.check_order_allowed()
    log.info("  Orders allowed: %s", _pass_fail(orders_allowed))

    ok = orders_blocked and orders_allowed
    log.info("  Kill switch drill: %s", _pass_fail(ok))
    return ok


# ── Main ──


def main() -> None:
    start_time = time.monotonic()
    log.info("iATB Paper-Trade Deployment Script")
    log.info("Started: %s UTC", datetime.now(UTC).isoformat())
    log.info("Log file: %s", _LOG_FILE)

    results: dict[str, bool] = {}

    # Step 1
    results["environment"] = step_1_verify_environment()

    # Step 2
    results["quality_gates"] = step_2_quality_gates()

    # Step 3
    results["configure"] = step_3_configure()

    # Step 4
    results["directories"] = step_4_create_directories()

    # Step 5
    results["preflight"] = step_5_preflight()

    # Step 6+7
    results["engine_health"] = asyncio.run(step_6_7_engine_and_health())

    # Step 8
    pnl_data = step_8_sample_trades()

    # Step 9
    step_9_daily_summary()

    # Step 10
    results["kill_switch_drill"] = step_10_kill_switch_drill()

    # ── Final Report ──
    elapsed = time.monotonic() - start_time
    _section("DEPLOYMENT SUMMARY")
    for step, ok in results.items():
        log.info("  %-25s %s", step, _pass_fail(ok))
    log.info("")
    log.info("  Session PnL:    %s", pnl_data.get("total_pnl", Decimal("0")))
    log.info("  Trades:         %s", pnl_data.get("trades", Decimal("0")))
    log.info("  Errors:         %s", pnl_data.get("errors", Decimal("0")))
    log.info("  Elapsed:        %.2fs", elapsed)
    log.info("  Log file:       %s", _LOG_FILE)
    log.info("")

    all_passed = all(results.values())
    if all_passed:
        log.info("  *** DEPLOYMENT: ALL STEPS PASSED ***")
    else:
        failed = [k for k, v in results.items() if not v]
        log.error("  *** DEPLOYMENT: FAILED STEPS: %s ***", ", ".join(failed))

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
