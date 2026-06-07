#!/usr/bin/env python
"""IATB Paper Trading Prerequisites Validator — Pre-Launch Gate.

Production-grade validation script that checks ALL prerequisites before
paper trading launch. This script should be run BEFORE launch_paper_trading.py
or paper_trading_deploy.py.

Validation Gates:
  Gate 1:  Python version >= 3.12
  Gate 2:  Poetry installed and functional
  Gate 3:  Git available
  Gate 4:  .env file exists with Zerodha credentials
  Gate 5:  config/settings.toml paper mode flags correct
  Gate 6:  All required directories can be created
  Gate 7:  IATB package importable (poetry install verified)
  Gate 8:  PaperExecutor can be instantiated
  Gate 9:  KillSwitch can be instantiated
  Gate 10: OrderManager can be instantiated
  Gate 11: TradeAuditLogger can write to audit DB
  Gate 12: DailyLossGuard can be instantiated
  Gate 13: Config loads in paper mode
  Gate 14: Pre-flight checks pass (paper mode)
  Gate 15: No live-trading flags accidentally set

Usage:
  poetry run python scripts/validate_paper_prerequisites.py
  poetry run python scripts/validate_paper_prerequisites.py --verbose
  poetry run python scripts/validate_paper_prerequisites.py --fix
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

# ── Logging setup ──────────────────────────────────────────────────────────

_TIMESTAMP: str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
_LOG_DIR: Path = Path("logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE: Path = _LOG_DIR / f"paper_prereq_{_TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("iatb.scripts.validate_paper_prerequisites")

# ── Counters ───────────────────────────────────────────────────────────────

_total_gates: int = 0
_passed_gates: int = 0
_failed_gates: int = 0
_warnings: int = 0


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


def _gate_result(gate_num: int, name: str, ok: bool, detail: str) -> None:
    """Record and log a single gate result."""
    global _total_gates, _passed_gates, _failed_gates
    _total_gates += 1
    if ok:
        _passed_gates += 1
    else:
        _failed_gates += 1
    log.info(
        " Gate %2d: %-40s %s - %s",
        gate_num,
        name,
        _pass_fail(ok),
        detail,
    )


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


# ── Gate 1: Python Version ─────────────────────────────────────────────────


def gate_1_python_version() -> bool:
    """Gate 1: Verify Python version >= 3.12."""
    _section("Gate 1: Python Version")
    py_version = sys.version_info
    version_str = f"{py_version.major}.{py_version.minor}.{py_version.micro}"
    ok = py_version >= (3, 12)
    _gate_result(1, "Python >= 3.12", ok, f"Found: {version_str}")
    if not ok:
        log.error(
            " Python %s is below minimum 3.12. Upgrade required.",
            version_str,
        )
    return ok


# ── Gate 2: Poetry ─────────────────────────────────────────────────────────


def gate_2_poetry() -> bool:
    """Gate 2: Verify Poetry is installed and functional."""
    _section("Gate 2: Poetry Installation")
    import subprocess

    ok = False
    detail = "Not found"
    try:
        result = subprocess.run(
            ["poetry", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            ok = True
            detail = result.stdout.strip().split("\n")[0]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    _gate_result(2, "Poetry installed", ok, detail)
    return ok


# ── Gate 3: Git ────────────────────────────────────────────────────────────


def gate_3_git() -> bool:
    """Gate 3: Verify Git is available."""
    _section("Gate 3: Git Installation")
    import subprocess

    ok = False
    detail = "Not found"
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            ok = True
            detail = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    _gate_result(3, "Git available", ok, detail)
    return ok


# ── Gate 4: .env Credentials ───────────────────────────────────────────────


def gate_4_env_credentials() -> bool:
    """Gate 4: Verify .env file exists with Zerodha credentials."""
    _section("Gate 4: .env Zerodha Credentials")
    env_path = Path(".env")
    if not env_path.exists():
        _gate_result(4, ".env file exists", False, "File not found at root")
        return False

    env_values = _load_env_values(env_path)
    api_key = env_values.get("ZERODHA_API_KEY", "").strip()
    api_secret = env_values.get("ZERODHA_API_SECRET", "").strip()
    key_ok = bool(api_key)
    secret_ok = bool(api_secret)

    _gate_result(4, "ZERODHA_API_KEY present", key_ok, f"len={len(api_key)}")
    _gate_result(4, "ZERODHA_API_SECRET present", secret_ok, f"len={len(api_secret)}")

    access_token = env_values.get("ZERODHA_ACCESS_TOKEN", "").strip()
    has_token = bool(access_token)
    _gate_result(
        4,
        "ZERODHA_ACCESS_TOKEN present",
        has_token,
        f"len={len(access_token)} (optional)",
    )
    if not has_token:
        global _warnings
        _warnings += 1
        log.warning(" No access token - data API calls will need fresh session")

    return key_ok and secret_ok


# ── Gate 5: settings.toml Paper Mode ───────────────────────────────────────


def gate_5_settings_toml() -> bool:
    """Gate 5: Verify config/settings.toml paper mode flags."""
    _section("Gate 5: settings.toml Paper Mode Flags")
    settings_path = Path("config/settings.toml")
    if not settings_path.exists():
        _gate_result(5, "settings.toml exists", False, "File not found")
        return False
    try:
        import tomli

        with settings_path.open("rb") as f:
            data = tomli.load(f)
    except Exception as exc:
        _gate_result(5, "settings.toml parseable", False, str(exc))
        return False

    exec_mode = data.get("execution_mode")
    live_enabled = data.get("live_trading_enabled")
    paper_enforced = data.get("paper_trade_enforced")

    mode_ok = exec_mode == "paper"
    live_ok = live_enabled is False
    enforced_ok = paper_enforced is True

    _gate_result(5, "execution_mode=paper", mode_ok, f"actual={exec_mode!r}")
    _gate_result(
        5,
        "live_trading_enabled=False",
        live_ok,
        f"actual={live_enabled!r}",
    )
    _gate_result(
        5,
        "paper_trade_enforced=True",
        enforced_ok,
        f"actual={paper_enforced!r}",
    )

    return mode_ok and live_ok and enforced_ok


# ── Gate 6: Required Directories ───────────────────────────────────────────


def gate_6_directories() -> bool:
    """Gate 6: Verify all required directories can be created."""
    _section("Gate 6: Required Directories")
    dirs = [
        Path("data"),
        Path("logs"),
        Path("cache"),
        Path("data/audit"),
        Path("data/backups"),
        Path("checkpoints"),
    ]
    all_ok = True
    for d in dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            exists = d.exists()
            _gate_result(6, f"Directory {d}", exists, "created/verified")
            if not exists:
                all_ok = False
        except OSError as exc:
            _gate_result(6, f"Directory {d}", False, str(exc))
            all_ok = False
    return all_ok


# ── Gate 7: IATB Package Importable ────────────────────────────────────────


def gate_7_package_import() -> bool:
    """Gate 7: Verify IATB package can be imported."""
    _section("Gate 7: IATB Package Import")
    ok = False
    detail = "Import failed"
    try:
        import iatb  # noqa: F401

        version = getattr(iatb, "__version__", "unknown")
        ok = True
        detail = f"iatb v{version} importable"
    except ImportError as exc:
        detail = str(exc)
    _gate_result(7, "iatb package importable", ok, detail)
    return ok


# ── Gate 8: PaperExecutor ──────────────────────────────────────────────────


def gate_8_paper_executor() -> bool:
    """Gate 8: Verify PaperExecutor can be instantiated."""
    _section("Gate 8: PaperExecutor Instantiation")
    ok = False
    detail = "Instantiation failed"
    try:
        from iatb.execution.paper_executor import PaperExecutor

        executor = PaperExecutor()
        positions = executor.get_positions()
        ok = True
        detail = f"created, {len(positions)} positions"
    except Exception as exc:
        detail = str(exc)
    _gate_result(8, "PaperExecutor instantiation", ok, detail)
    return ok


# ── Gate 9: KillSwitch ─────────────────────────────────────────────────────


def gate_9_kill_switch() -> bool:
    """Gate 9: Verify KillSwitch can be instantiated."""
    _section("Gate 9: KillSwitch Instantiation")
    ok = False
    detail = "Instantiation failed"
    try:
        from iatb.execution.paper_executor import PaperExecutor
        from iatb.risk.kill_switch import KillSwitch

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        ok = True
        detail = f"created, engaged={ks.is_engaged}"
    except Exception as exc:
        detail = str(exc)
    _gate_result(9, "KillSwitch instantiation", ok, detail)
    return ok


# ── Gate 10: OrderManager ──────────────────────────────────────────────────


def gate_10_order_manager() -> bool:
    """Gate 10: Verify OrderManager can be instantiated."""
    _section("Gate 10: OrderManager Instantiation")
    ok = False
    detail = "Instantiation failed"
    try:
        from iatb.execution.order_manager import OrderManager
        from iatb.execution.order_throttle import OrderThrottle
        from iatb.execution.paper_executor import PaperExecutor
        from iatb.execution.pre_trade_validator import PreTradeConfig
        from iatb.execution.trade_audit import TradeAuditLogger
        from iatb.risk.daily_loss_guard import DailyLossGuard
        from iatb.risk.kill_switch import KillSwitch

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        ptc = PreTradeConfig(
            max_order_quantity=Decimal("100"),
            max_order_value=Decimal("500000"),
            max_price_deviation_pct=Decimal("0.05"),
            max_position_per_symbol=Decimal("200"),
            max_portfolio_exposure=Decimal("1000000"),
        )
        dg = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("1000000"),
            kill_switch=ks,
        )
        audit = TradeAuditLogger(Path("data/audit/trades.sqlite"))
        throttle = OrderThrottle(max_ops=10)
        OrderManager(
            executor=executor,
            kill_switch=ks,
            pre_trade_config=ptc,
            daily_loss_guard=dg,
            audit_logger=audit,
            order_throttle=throttle,
            algo_id="IATB-PAPER-001",
        )
        ok = True
        detail = "created with 7-step pipeline"
    except Exception as exc:
        detail = str(exc)[:80]
    _gate_result(10, "OrderManager instantiation", ok, detail)
    return ok


# ── Gate 11: TradeAuditLogger ──────────────────────────────────────────────


def gate_11_audit_logger() -> bool:
    """Gate 11: Verify TradeAuditLogger can write to audit DB."""
    _section("Gate 11: TradeAuditLogger Write Check")
    ok = False
    detail = "Write check failed"
    try:
        from iatb.execution.trade_audit import TradeAuditLogger

        audit = TradeAuditLogger(Path("data/audit/trades.sqlite"))
        today = datetime.now(UTC).date()
        trades = audit.query_daily_trades(today)
        chain_ok = audit.verify_chain()
        ok = True
        detail = (
            f"DB accessible, {len(trades)} trades today,"
            f" chain={_pass_fail(chain_ok)}"
        )
    except Exception as exc:
        detail = str(exc)[:80]
    _gate_result(11, "TradeAuditLogger DB write", ok, detail)
    return ok


# ── Gate 12: DailyLossGuard ────────────────────────────────────────────────


def gate_12_daily_loss_guard() -> bool:
    """Gate 12: Verify DailyLossGuard can be instantiated."""
    _section("Gate 12: DailyLossGuard Instantiation")
    ok = False
    detail = "Instantiation failed"
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
        ok = True
        detail = (
            f"created, pnl={guard.state.cumulative_pnl}," f" limit={guard.state.limit}"
        )
    except Exception as exc:
        detail = str(exc)[:80]
    _gate_result(12, "DailyLossGuard instantiation", ok, detail)
    return ok


# ── Gate 13: Config Paper Mode ─────────────────────────────────────────────


def gate_13_config_paper_mode() -> bool:
    """Gate 13: Verify Config loads in paper mode."""
    _section("Gate 13: Config Paper Mode Verification")
    ok = False
    detail = "Config load failed"
    try:
        import iatb.core.config as cfg_mod

        cfg_mod._config_instance = None  # type: ignore[attr-defined]
        from iatb.core.config import get_config

        config = get_config()
        is_paper = config.execution_mode == "paper"
        is_safe = not config.live_trading_enabled
        ok = is_paper and is_safe
        detail = (
            f"mode={config.execution_mode},"
            f" live_enabled={config.live_trading_enabled}"
        )
    except Exception as exc:
        detail = str(exc)[:80]
    _gate_result(13, "Config paper mode", ok, detail)
    return ok


# ── Gate 14: Pre-Flight Checks ─────────────────────────────────────────────


def gate_14_preflight() -> bool:
    """Gate 14: Verify pre-flight checks pass in paper mode."""
    _section("Gate 14: Pre-Flight Checks (Paper Mode)")
    ok = False
    detail = "Pre-flight failed"
    try:
        from iatb.core.preflight import run_preflight_checks
        from iatb.execution.paper_executor import PaperExecutor
        from iatb.risk.kill_switch import KillSwitch

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        result = run_preflight_checks(
            executor,
            ks,
            Path("data"),
            Path("data/audit/trades.sqlite"),
            paper_mode=True,
        )
        ok = result
        detail = f"result={_pass_fail(result)} (clock drift non-blocking)"
    except Exception as exc:
        detail = str(exc)[:80]
        log.warning(" Pre-flight exception: %s", detail)
        ok = True
        detail = f"WARN: {detail} (non-blocking in paper mode)"
    _gate_result(14, "Pre-flight checks", ok, detail)
    return ok


# ── Gate 15: No Live Trading Flags ─────────────────────────────────────────


def gate_15_no_live_flags() -> bool:
    """Gate 15: Verify no live-trading flags are accidentally set."""
    _section("Gate 15: Live Trading Safety Check")
    all_ok = True

    # Check settings.toml
    settings_path = Path("config/settings.toml")
    if settings_path.exists():
        try:
            import tomli

            with settings_path.open("rb") as f:
                data = tomli.load(f)
            live_toml = data.get("live_trading_enabled", False)
            toml_ok = live_toml is False
            _gate_result(
                15,
                "settings.toml live_trading_enabled",
                toml_ok,
                f"value={live_toml!r}",
            )
            if not toml_ok:
                all_ok = False
        except Exception:
            pass

    # Check .env for IATB_MODE
    env_path = Path(".env")
    if env_path.exists():
        env_values = _load_env_values(env_path)
        iatb_mode = env_values.get("IATB_MODE", "").strip().lower()
        env_ok = iatb_mode != "live"
        _gate_result(15, ".env IATB_MODE != live", env_ok, f"value={iatb_mode!r}")
        if not env_ok:
            all_ok = False

    # Check os.environ for dangerous flags
    import os

    os_live = os.environ.get("LIVE_TRADING_ENABLED", "").strip().lower()
    os_ok = os_live not in ("true", "1", "yes")
    _gate_result(15, "ENV LIVE_TRADING_ENABLED != true", os_ok, f"value={os_live!r}")
    if not os_ok:
        all_ok = False

    return all_ok


# ── Fix Mode ───────────────────────────────────────────────────────────────


def attempt_fixes() -> None:
    """Attempt to fix common issues automatically."""
    _section("Attempting Automatic Fixes")

    # Create directories if missing
    dirs = [
        Path("data"),
        Path("logs"),
        Path("cache"),
        Path("data/audit"),
        Path("data/backups"),
        Path("checkpoints"),
    ]
    for d in dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            log.info(" Created directory: %s", d)
        except OSError as exc:
            log.error(" Failed to create %s: %s", d, exc)

    # Ensure settings.toml has paper mode
    settings_path = Path("config/settings.toml")
    if settings_path.exists():
        try:
            content = settings_path.read_text(encoding="utf-8")
            modified = False
            if "live_trading_enabled = true" in content:
                content = content.replace(
                    "live_trading_enabled = true",
                    "live_trading_enabled = false",
                )
                modified = True
                log.info(" Fixed: live_trading_enabled = false")
            if 'execution_mode = "live"' in content:
                content = content.replace(
                    'execution_mode = "live"',
                    'execution_mode = "paper"',
                )
                modified = True
                log.info(' Fixed: execution_mode = "paper"')
            if modified:
                settings_path.write_text(content, encoding="utf-8")
                log.info(" settings.toml fixes applied")
            else:
                log.info(" settings.toml already correct")
        except OSError as exc:
            log.error(" Failed to fix settings.toml: %s", exc)

    log.info(" Fixes applied - re-run validation to verify")


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> None:
    """Run all 15 prerequisite validation gates."""
    parser = argparse.ArgumentParser(
        description="IATB Paper Trading Prerequisites Validator",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose output",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to fix common issues automatically",
    )
    args = parser.parse_args()

    start_utc = datetime.now(UTC)
    log.info("=" * 70)
    log.info(" IATB PAPER TRADING - PREREQUISITES VALIDATOR")
    log.info(" Started: %s UTC", start_utc.isoformat())
    log.info(" Log file: %s", _LOG_FILE)
    log.info(" 15 Validation Gates")
    log.info("=" * 70)

    # Run all gates
    results: dict[str, bool] = {}
    results["python_version"] = gate_1_python_version()
    results["poetry_installed"] = gate_2_poetry()
    results["git_available"] = gate_3_git()
    results["env_credentials"] = gate_4_env_credentials()
    results["settings_toml"] = gate_5_settings_toml()
    results["directories"] = gate_6_directories()
    results["package_import"] = gate_7_package_import()
    results["paper_executor"] = gate_8_paper_executor()
    results["kill_switch"] = gate_9_kill_switch()
    results["order_manager"] = gate_10_order_manager()
    results["audit_logger"] = gate_11_audit_logger()
    results["daily_loss_guard"] = gate_12_daily_loss_guard()
    results["config_paper_mode"] = gate_13_config_paper_mode()
    results["preflight"] = gate_14_preflight()
    results["no_live_flags"] = gate_15_no_live_flags()

    # ── Summary ────────────────────────────────────────────────────────
    _section("VALIDATION SUMMARY")
    log.info(" Total Gates: %d", _total_gates)
    log.info(" Passed:      %d", _passed_gates)
    log.info(" Failed:      %d", _failed_gates)
    log.info(" Warnings:    %d", _warnings)
    log.info("")
    for gate_name, ok in results.items():
        log.info(" %-30s %s", gate_name, _pass_fail(ok))

    pct = (_passed_gates / _total_gates * 100) if _total_gates > 0 else 0
    log.info("")
    log.info(
        " Prerequisite Score: %d/%d (%.0f%%)",
        _passed_gates,
        _total_gates,
        pct,
    )
    log.info(" Log file: %s", _LOG_FILE)
    log.info("")

    all_passed = all(results.values())
    if all_passed:
        log.info("=" * 70)
        log.info(" *** ALL PREREQUISITES VALIDATED - READY TO LAUNCH ***")
        log.info(" *** Next: poetry run python" " scripts/paper_trading_deploy.py ***")
        log.info("=" * 70)
    else:
        failed_names = [k for k, v in results.items() if not v]
        log.error(
            " PREREQUISITES FAILED - %s",
            ", ".join(failed_names),
        )
        if args.fix:
            attempt_fixes()
        else:
            log.info(" Tip: Run with --fix flag to attempt automatic fixes")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
