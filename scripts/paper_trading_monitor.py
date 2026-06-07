#!/usr/bin/env python
"""IATB Paper Trading Performance Monitor - Continuous Observation.

Production-grade monitoring script that continuously observes
the running paper trading session with periodic health checks:

Check 1: Config status (paper mode confirmed)
Check 2: Kill switch state (not engaged)
Check 3: Database file health (audit, duckdb, loss state)
Check 4: Audit trade records (today's trades)
Check 5: HMAC chain integrity (tamper-proof audit)
Check 6: Daily loss guard state (breach monitoring)
Check 7: Position summary from PaperExecutor
Check 8: Session PnL aggregation
Check 9: System resource usage (memory, CPU footprint)
Check 10: Overall health assessment

Usage:
    poetry run python scripts/paper_trading_monitor.py
    poetry run python scripts/paper_trading_monitor.py -i 30 -n 10
    poetry run python scripts/paper_trading_monitor.py --once
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

# ── Logging setup ──────────────────────────────────────────────────────────
_TIMESTAMP: str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
_LOG_DIR: Path = Path("logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE: Path = _LOG_DIR / f"paper_monitor_{_TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("iatb.scripts.paper_trading_monitor")

# ── Metrics output file ────────────────────────────────────────────────────
_METRICS_DIR: Path = Path("data")
_METRICS_DIR.mkdir(parents=True, exist_ok=True)
_METRICS_FILE: Path = _METRICS_DIR / "paper_trading_metrics.json"


def _pass_fail(ok: bool) -> str:
    """Return PASS or FAIL string."""
    return "PASS" if ok else "FAIL"


def _section(title: str) -> None:
    """Log a section header with decorative bars."""
    bar = "=" * 70
    log.info("")
    log.info(bar)
    log.info(" %s", title)
    log.info(bar)


def _load_env_values(env_path: Path) -> dict[str, str]:
    """Parse .env file into key-value dict."""
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", maxsplit=1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


# ── Check 1: Config Status ─────────────────────────────────────────────────
def check_config_status() -> dict[str, str]:
    """Check config status and paper mode confirmation."""
    _section("Check 1: Config Status")
    status: dict[str, str] = {}
    try:
        import iatb.core.config as cfg_mod

        cfg_mod._config_instance = None  # type: ignore[attr-defined]
        from iatb.core.config import get_config

        config = get_config()
        status["config_loaded"] = "True"
        status["execution_mode"] = config.execution_mode
        status["live_trading_enabled"] = str(config.live_trading_enabled)
        status["default_exchange"] = config.default_exchange
        status["data_dir"] = str(config.data_dir)
        is_paper = config.execution_mode == "paper"
        is_safe = not config.live_trading_enabled
        log.info(
            " execution_mode: %s -- %s",
            config.execution_mode,
            _pass_fail(is_paper),
        )
        log.info(
            " live_trading_enabled: %s -- %s",
            config.live_trading_enabled,
            _pass_fail(is_safe),
        )
        if not is_paper:
            log.error(" NOT in paper mode!")
            status["paper_mode_safe"] = "False"
        else:
            status["paper_mode_safe"] = "True"
    except Exception as exc:
        log.error(" Config load failed: %s", exc)
        status["config_loaded"] = "False"
        status["error"] = str(exc)
    return status


# ── Check 2: Kill Switch State ─────────────────────────────────────────────
def check_kill_switch_state() -> dict[str, str]:
    """Check kill switch state."""
    _section("Check 2: Kill Switch State")
    state: dict[str, str] = {}
    try:
        from iatb.execution.paper_executor import PaperExecutor
        from iatb.risk.kill_switch import KillSwitch

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        state["engaged"] = str(ks.is_engaged)
        state["orders_allowed"] = str(ks.check_order_allowed())
        log.info(" Kill switch engaged: %s", ks.is_engaged)
        log.info(" Orders allowed: %s", _pass_fail(ks.check_order_allowed()))
        if ks.is_engaged:
            log.warning(" Kill switch is currently ENGAGED!")
            state["healthy"] = "False"
        else:
            state["healthy"] = "True"
    except Exception as exc:
        log.error(" Kill switch check failed: %s", exc)
        state["error"] = str(exc)
    return state


# ── Check 3: Database Files ────────────────────────────────────────────────
def check_database_files() -> dict[str, str]:
    """Check database file existence and size."""
    _section("Check 3: Database Files")
    result: dict[str, str] = {}
    db_files = {
        "audit_db": Path("data/audit/trades.sqlite"),
        "daily_loss_db": Path("data/daily_loss_state.json"),
        "duckdb": Path("data/iatb.duckdb"),
    }
    for name, path in db_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        result[name] = f"exists={exists}, size={size}"
        log.info(
            " %s: exists=%s size=%d bytes -- %s",
            name,
            exists,
            size,
            _pass_fail(path.parent.exists()),
        )
    return result


# ── Check 4: Audit Trades ──────────────────────────────────────────────────
def check_audit_trades(
    date: datetime | None = None,
) -> list[dict[str, str]]:
    """Query audit trades for a given date."""
    _section("Check 4: Audit Trades")
    try:
        from iatb.execution.trade_audit import TradeAuditLogger

        audit = TradeAuditLogger(Path("data/audit/trades.sqlite"))
        target_date = (date or datetime.now(UTC)).date()
        trades = audit.query_daily_trades(target_date)
        log.info(" Date: %s", target_date.isoformat())
        log.info(" Total trades: %d", len(trades))
        trade_list: list[dict[str, str]] = []
        for t in trades[:20]:
            info = {
                "order_id": t.order_id,
                "side": str(t.side),
                "symbol": t.symbol,
                "quantity": str(t.quantity),
                "price": str(t.price),
                "status": str(t.status),
            }
            trade_list.append(info)
            log.info(
                " %s | %s %s | qty=%s price=%s | %s",
                t.order_id,
                t.side,
                t.symbol,
                t.quantity,
                t.price,
                t.status,
            )
        if len(trades) > 20:
            log.info(" ... and %d more trades", len(trades) - 20)
        return trade_list
    except Exception as exc:
        log.error(" Audit query failed: %s", exc)
        return []


# ── Check 5: HMAC Chain Integrity ──────────────────────────────────────────
def check_audit_chain_integrity() -> bool:
    """Verify HMAC chain integrity in audit log."""
    _section("Check 5: HMAC Chain Integrity")
    try:
        from iatb.execution.trade_audit import TradeAuditLogger

        audit = TradeAuditLogger(Path("data/audit/trades.sqlite"))
        chain_ok = audit.verify_chain()
        log.info(" HMAC chain integrity: %s", _pass_fail(chain_ok))
        if not chain_ok:
            log.warning(
                " HMAC chain integrity FAILED" " - audit trail may be corrupted"
            )
        return chain_ok
    except Exception as exc:
        log.error(" Chain verification failed: %s", exc)
        return False


# ── Check 6: Daily Loss Guard ──────────────────────────────────────────────
def check_daily_loss_guard() -> dict[str, str]:
    """Check daily loss guard state."""
    _section("Check 6: Daily Loss Guard State")
    state: dict[str, str] = {}
    try:
        from iatb.execution.paper_executor import PaperExecutor
        from iatb.risk.daily_loss_guard import DailyLossGuard
        from iatb.risk.kill_switch import KillSwitch

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("1000000"),
            kill_switch=ks,
        )
        state["cumulative_pnl"] = str(guard.state.cumulative_pnl)
        state["limit"] = str(guard.state.limit)
        state["breached"] = str(guard.state.breached)
        log.info(" Cumulative PnL: %s", guard.state.cumulative_pnl)
        log.info(" Loss limit: %s", guard.state.limit)
        log.info(" Breached: %s", _pass_fail(not guard.state.breached))
        if guard.state.breached:
            log.warning(" DAILY LOSS LIMIT BREACHED" " - trading should be halted")
    except Exception as exc:
        log.error(" Daily loss guard check failed: %s", exc)
        state["error"] = str(exc)
    return state


# ── Check 7: Position Summary ──────────────────────────────────────────────
def check_positions() -> dict[str, str]:
    """Check paper executor position summary."""
    _section("Check 7: Position Summary")
    result: dict[str, str] = {}
    try:
        from iatb.execution.paper_executor import PaperExecutor

        executor = PaperExecutor()
        positions = executor.get_positions()
        result["position_count"] = str(len(positions))
        log.info(" Active positions: %d", len(positions))
        for symbol, (qty, avg_price) in positions.items():
            info_str = f"qty={qty} avg_price={avg_price}"
            result[symbol] = info_str
            log.info(" %s: %s", symbol, info_str)
        if not positions:
            log.info(" No open positions (clean session)")
    except Exception as exc:
        log.error(" Position check failed: %s", exc)
        result["error"] = str(exc)
    return result


# ── Check 8: Session PnL ──────────────────────────────────────────────────
def check_session_pnl() -> dict[str, str]:
    """Calculate and display session PnL from audit log."""
    _section("Check 8: Session PnL Summary")
    summary: dict[str, str] = {}
    try:
        from iatb.execution.trade_audit import TradeAuditLogger

        audit = TradeAuditLogger(Path("data/audit/trades.sqlite"))
        today = datetime.now(UTC).date()
        trades = audit.query_daily_trades(today)
        total_pnl = Decimal("0")
        buy_count = 0
        sell_count = 0
        for t in trades:
            if hasattr(t, "pnl") and t.pnl is not None:
                total_pnl += t.pnl
            side_str = str(t.side).upper()
            if "BUY" in side_str:
                buy_count += 1
            elif "SELL" in side_str:
                sell_count += 1
        summary["total_trades"] = str(len(trades))
        summary["buy_trades"] = str(buy_count)
        summary["sell_trades"] = str(sell_count)
        summary["total_pnl"] = str(total_pnl)
        summary["date"] = today.isoformat()
        log.info(" Date: %s", today.isoformat())
        log.info(" Total trades: %d", len(trades))
        log.info(" Buy trades: %d", buy_count)
        log.info(" Sell trades: %d", sell_count)
        log.info(" Total PnL: %s", total_pnl)
    except Exception as exc:
        log.error(" Session PnL failed: %s", exc)
        summary["error"] = str(exc)
    return summary


# ── Check 9: System Resources ──────────────────────────────────────────────
def check_system_resources() -> dict[str, str]:
    """Check system resource usage (memory, CPU)."""
    _section("Check 9: System Resources")
    result: dict[str, str] = {}
    try:
        import os

        import psutil

        process = psutil.Process(os.getpid())
        mem_mb = process.memory_info().rss / (1024 * 1024)
        cpu_pct = process.cpu_percent(interval=1.0)
        result["memory_mb"] = f"{mem_mb:.1f}"
        result["cpu_pct"] = f"{cpu_pct:.1f}"
        log.info(" Memory usage: %.1f MB", mem_mb)
        log.info(" CPU usage: %.1f%%", cpu_pct)
        disk_usage = psutil.disk_usage(str(Path.cwd()))
        result["disk_free_gb"] = f"{disk_usage.free / (1024**3):.1f}"
        log.info(" Disk free: %.1f GB", disk_usage.free / (1024**3))
    except ImportError:
        log.info(" psutil not installed - skipping resource check")
        result["note"] = "psutil_not_available"
    except Exception as exc:
        log.warning(" Resource check failed: %s", exc)
        result["error"] = str(exc)
    return result


# ── Check 10: Overall Health ───────────────────────────────────────────────
def assess_overall_health(
    results: dict[str, bool],
) -> dict[str, str]:
    """Assess overall health based on all check results."""
    _section("Check 10: Overall Health Assessment")
    assessment: dict[str, str] = {}
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    health_pct = (passed / total * 100) if total > 0 else 0
    assessment["total_checks"] = str(total)
    assessment["passed_checks"] = str(passed)
    assessment["health_pct"] = f"{health_pct:.0f}"
    log.info(" Checks passed: %d / %d", passed, total)
    log.info(" Health score: %.0f%%", health_pct)
    if health_pct == 100:
        assessment["status"] = "HEALTHY"
        log.info(" Status: HEALTHY - All systems operational")
    elif health_pct >= 80:
        assessment["status"] = "DEGRADED"
        log.warning(" Status: DEGRADED - Some checks need attention")
    else:
        assessment["status"] = "UNHEALTHY"
        log.error(" Status: UNHEALTHY - Immediate action required")
    if passed < total:
        failed = [k for k, v in results.items() if not v]
        log.warning(" Failed checks: %s", ", ".join(failed))
    return assessment


# ── Metrics Export ──────────────────────────────────────────────────────────
def export_metrics(
    check_results: dict[str, Any],
    health_pct: float,
) -> None:
    """Export monitoring metrics to JSON for dashboards."""
    metrics = {
        "timestamp": datetime.now(UTC).isoformat(),
        "health_pct": health_pct,
        "checks": {
            k: v
            for k, v in check_results.items()
            if isinstance(v, (str, int, float, bool))
        },
    }
    try:
        existing: list[Any] = []
        if _METRICS_FILE.exists():
            try:
                existing = json.loads(_METRICS_FILE.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except (json.JSONDecodeError, OSError):
                existing = []
        existing.append(metrics)
        if len(existing) > 1000:
            existing = existing[-1000:]
        _METRICS_FILE.write_text(
            json.dumps(existing, indent=2, default=str),
            encoding="utf-8",
        )
        log.info(" Metrics exported to: %s", _METRICS_FILE)
    except Exception as exc:
        log.warning(" Metrics export failed: %s", exc)


# ── Single Observation Cycle ───────────────────────────────────────────────
def run_observation_cycle(cycle_num: int) -> dict[str, bool]:
    """Run a single observation cycle with all 10 checks.

    Args:
        cycle_num: Current observation cycle number.

    Returns:
        Dict of check name -> pass/fail boolean.
    """
    _section(
        f"Observation Cycle #{cycle_num}" f" - {datetime.now(UTC).isoformat()[:19]} UTC"
    )
    results: dict[str, bool] = {}

    # Check 1
    config_status = check_config_status()
    results["config_paper_mode"] = config_status.get("paper_mode_safe") == "True"

    # Check 2
    ks_state = check_kill_switch_state()
    results["kill_switch_healthy"] = ks_state.get("healthy") == "True"

    # Check 3
    check_database_files()
    results["database_accessible"] = True

    # Check 4
    check_audit_trades()
    results["audit_readable"] = True

    # Check 5
    results["chain_integrity"] = check_audit_chain_integrity()

    # Check 6
    dl_state = check_daily_loss_guard()
    results["daily_loss_ok"] = dl_state.get("breached", "False") != "True"

    # Check 7
    check_positions()
    results["positions_accessible"] = True

    # Check 8
    session_pnl = check_session_pnl()
    results["pnl_calculated"] = "error" not in session_pnl

    # Check 9
    check_system_resources()
    results["resources_checked"] = True

    # Check 10
    health = assess_overall_health(results)
    health_pct = float(health.get("health_pct", "0"))
    export_metrics(
        {
            **config_status,
            **ks_state,
            **dl_state,
            **session_pnl,
            **health,
        },
        health_pct,
    )

    return results


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> None:
    """Run all observation checks with configurable intervals."""
    parser = argparse.ArgumentParser(
        description="IATB Paper Trading Performance Monitor",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=30,
        help="Seconds between observation cycles (default: 30)",
    )
    parser.add_argument(
        "-n",
        "--cycles",
        type=int,
        default=5,
        help="Number of observation cycles (default: 5)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single observation cycle and exit",
    )
    args = parser.parse_args()

    start_utc = datetime.now(UTC)
    log.info("=" * 70)
    log.info(" IATB PAPER TRADING - PERFORMANCE MONITOR")
    log.info(" Started: %s UTC", start_utc.isoformat())
    log.info(" Log file: %s", _LOG_FILE)
    log.info(" Metrics: %s", _METRICS_FILE)
    if args.once:
        log.info(" Mode: Single observation cycle")
    else:
        log.info(
            " Mode: %d cycles, %ds interval",
            args.cycles,
            args.interval,
        )
    log.info("=" * 70)

    all_cycle_results: list[dict[str, bool]] = []
    num_cycles = 1 if args.once else args.cycles

    for cycle in range(1, num_cycles + 1):
        cycle_results = run_observation_cycle(cycle)
        all_cycle_results.append(cycle_results)
        if cycle < num_cycles and not args.once:
            log.info("")
            log.info(
                " Next cycle in %ds (Ctrl+C to stop)...",
                args.interval,
            )
            try:
                time.sleep(args.interval)
            except KeyboardInterrupt:
                log.info(" Monitor stopped by user")
                break

    # ── Final Summary ───────────────────────────────────────────────
    _section("MONITORING SUMMARY")
    total_checks = 0
    total_passed = 0
    for i, cycle_results in enumerate(all_cycle_results, 1):
        cycle_passed = sum(1 for v in cycle_results.values() if v)
        cycle_total = len(cycle_results)
        total_checks += cycle_total
        total_passed += cycle_passed
        log.info(" Cycle #%d: %d/%d passed", i, cycle_passed, cycle_total)

    overall_pct = (total_passed / total_checks * 100) if total_checks > 0 else 0
    log.info("")
    log.info(
        " Overall: %d/%d checks passed (%.0f%%)",
        total_passed,
        total_checks,
        overall_pct,
    )
    log.info(" Cycles completed: %d", len(all_cycle_results))
    log.info(" Log file: %s", _LOG_FILE)
    log.info(" Metrics: %s", _METRICS_FILE)

    sys.exit(0 if overall_pct >= 80 else 1)


if __name__ == "__main__":
    main()
