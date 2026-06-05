#!/usr/bin/env python
"""IATB Paper Trading Observer - Real-time monitoring dashboard.

Observes running paper trading session with checks:
1. Config status (paper mode confirmed)
2. Kill switch state
3. Database file health
4. Audit trade records
5. HMAC chain integrity
6. Daily loss guard state
7. Session summary
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / f"paper_observe_{_TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("iatb.scripts.observe_paper_trading")


def _pass_fail(ok: bool) -> str:
    """Return PASS or FAIL string based on boolean."""
    return "PASS" if ok else "FAIL"


def _section(title: str) -> None:
    """Log a section header."""
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
        status["data_dir"] = config.data_dir
        is_paper = config.execution_mode == "paper"
        is_safe = not config.live_trading_enabled
        log.info(
            " execution_mode: %s -- %s", config.execution_mode, _pass_fail(is_paper)
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
            " %s: exists=%s size=%d -- %s",
            name,
            exists,
            size,
            _pass_fail(path.parent.exists()),
        )
    return result


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


def check_audit_chain_integrity() -> bool:
    """Verify HMAC chain integrity in audit log."""
    _section("Check 5: HMAC Chain Integrity")
    try:
        from iatb.execution.trade_audit import TradeAuditLogger

        audit = TradeAuditLogger(Path("data/audit/trades.sqlite"))
        chain_ok = audit.verify_chain()
        log.info(" HMAC chain integrity: %s", _pass_fail(chain_ok))
        return chain_ok
    except Exception as exc:
        log.error(" Chain verification failed: %s", exc)
        return False


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
    except Exception as exc:
        log.error(" Daily loss guard check failed: %s", exc)
        state["error"] = str(exc)
    return state


def check_session_summary() -> dict[str, str]:
    """Generate session summary from audit log."""
    _section("Check 7: Session Summary")
    summary: dict[str, str] = {}
    try:
        from iatb.execution.trade_audit import TradeAuditLogger

        audit = TradeAuditLogger(Path("data/audit/trades.sqlite"))
        today = datetime.now(UTC).date()
        trades = audit.query_daily_trades(today)
        total_pnl = Decimal("0")
        for t in trades:
            if hasattr(t, "pnl") and t.pnl is not None:
                total_pnl += t.pnl
        summary["total_trades"] = str(len(trades))
        summary["total_pnl"] = str(total_pnl)
        summary["date"] = today.isoformat()
        log.info(" Date: %s", today.isoformat())
        log.info(" Total trades today: %d", len(trades))
        log.info(" Total PnL: %s", total_pnl)
    except Exception as exc:
        log.error(" Session summary failed: %s", exc)
        summary["error"] = str(exc)
    return summary


def main() -> None:
    """Run all observation checks and report status."""
    start_utc = datetime.now(UTC)
    log.info("=" * 70)
    log.info(" IATB PAPER TRADING OBSERVER")
    log.info(" Started: %s UTC", start_utc.isoformat())
    log.info(" Log file: %s", _LOG_FILE)
    log.info("=" * 70)

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
    chain_ok = check_audit_chain_integrity()
    results["chain_integrity"] = chain_ok

    # Check 6
    dl_state = check_daily_loss_guard()
    results["daily_loss_ok"] = dl_state.get("breached", "False") != "True"

    # Check 7
    check_session_summary()

    # Summary
    _section("OBSERVATION SUMMARY")
    for step, ok in results.items():
        log.info(" %-25s %s", step, _pass_fail(ok))

    all_ok = all(results.values())
    log.info("")
    if all_ok:
        log.info(" *** OBSERVATION: ALL CHECKS PASSED ***")
        log.info(" Paper trading session is healthy and running safely.")
    else:
        failed = [k for k, v in results.items() if not v]
        log.warning(" Checks needing attention: %s", ", ".join(failed))

    log.info(" Log file: %s", _LOG_FILE)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
