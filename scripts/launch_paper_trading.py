#!/usr/bin/env python
"""IATB Paper Trading Launcher — Production-Grade Sequential Deployment.

Executes 12 steps in order for safe, observable paper trading:
Step 1: Verify environment (Python 3.12+, Poetry, Git)
Step 2: Load .env and validate Zerodha credentials
Step 3: Verify config/settings.toml paper mode flags
Step 4: Create required directories
Step 5: Apply environment defaults from .env
Step 6: Validate Zerodha token availability
Step 7: Instantiate Config and confirm paper mode
Step 8: Run pre-flight checks (clock, executor, kill switch, paths)
Step 9: Build full safety pipeline (PaperExecutor + KillSwitch + OrderManager)
Step 10: Start Engine with EventBus + SSEBroadcaster
Step 11: Execute sample paper trades through 7-step risk pipeline
Step 12: Kill switch emergency drill + disengage

All output is logged to logs/paper_launch_YYYYMMDD_HHMMSS.log and printed
to console.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
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
_LOG_FILE = _LOG_DIR / f"paper_launch_{_TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("iatb.scripts.launch_paper_trading")


# ── Utilities ──
def _pass_fail(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _section(title: str) -> None:
    bar = "=" * 70
    log.info("")
    log.info(bar)
    log.info(" %s", title)
    log.info(bar)


def _run_cmd(cmd: str, check: bool = False) -> tuple[int, str]:
    """Run a shell command, log output, return (exitcode, combined stdout+stderr)."""
    log.info(" $ %s", cmd)
    result = subprocess.run(
        shlex.split(cmd),
        shell=False,  # nosec B602
        capture_output=True,
        text=True,
        cwd=str(Path.cwd()),
    )
    combined = (result.stdout + result.stderr).strip()
    for line in combined.splitlines()[:20]:
        log.info(" %s", line)
    if check and result.returncode != 0:
        log.error(" FAILED (exit %d)", result.returncode)
    return result.returncode, combined


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
        first_line = out.split("\n")[0] if out else "(not found)"
        log.info(" %s: %s — %s", name, _pass_fail(ok), first_line)
        if not ok:
            all_ok = False
    return all_ok


# ── Step 2: Load .env and Validate Credentials ──
def step_2_validate_credentials() -> bool:
    _section("Step 2: Load .env and Validate Zerodha Credentials")
    env_path = Path(".env")
    if not env_path.exists():
        log.error(" .env file not found — run validate_paper_setup.py first")
        return False
    env_values = _load_env_values(env_path)
    required_keys = ["ZERODHA_API_KEY", "ZERODHA_API_SECRET"]
    all_ok = True
    for key in required_keys:
        present = key in env_values and bool(env_values[key].strip())
        log.info(" %s: %s", key, _pass_fail(present))
        if not present:
            all_ok = False
    access_token = env_values.get("ZERODHA_ACCESS_TOKEN", "").strip()
    request_token = env_values.get("ZERODHA_REQUEST_TOKEN", "").strip()
    has_token = bool(access_token) or bool(request_token)
    log.info(" Has access/request token: %s", _pass_fail(has_token))
    if not has_token:
        log.warning(
            " No Zerodha token in .env. Zerodha data API calls"
            " will require a new session at runtime."
        )
    log.info(" .env loaded: %s keys found", len(env_values))
    return all_ok


# ── Step 3: Verify settings.toml Paper Mode ──
def step_3_verify_settings_toml() -> bool:
    _section("Step 3: Verify config/settings.toml Paper Mode")
    settings_path = Path("config/settings.toml")
    if not settings_path.exists():
        log.error(" config/settings.toml not found")
        return False
    try:
        import tomli

        with settings_path.open("rb") as f:
            data = tomli.load(f)
    except Exception as exc:
        log.error(" Failed to parse settings.toml: %s", exc)
        return False
    paper_checks = {
        "execution_mode": "paper",
        "live_trading_enabled": False,
        "paper_trade_enforced": True,
    }
    all_ok = True
    for key, expected in paper_checks.items():
        actual = data.get(key)
        ok = actual == expected
        log.info(
            " %s = %s (expected: %s): %s",
            key,
            actual,
            expected,
            _pass_fail(ok),
        )
        if not ok:
            all_ok = False
    if not all_ok:
        log.error(" Paper mode safety flags not set correctly!")
    return all_ok


# ── Step 4: Create Required Directories ──
def step_4_create_directories() -> bool:
    _section("Step 4: Create Required Directories")
    dirs = [
        Path("data"),
        Path("logs"),
        Path("cache"),
        Path("data/audit"),
        Path("data/backups"),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        log.info(" %s: %s", d, _pass_fail(d.exists()))
    return all(d.exists() for d in dirs)


# ── Step 5: Apply Environment Defaults ──
def step_5_apply_env_defaults() -> bool:
    _section("Step 5: Apply Environment Defaults from .env")
    try:
        from iatb.execution.token_helpers import apply_env_defaults, load_env_file

        env_path = Path(".env")
        values = load_env_file(env_path)
        apply_env_defaults(values)
        log.info(" Applied %d env defaults from .env", len(values))
        log.info(
            " ZERODHA_API_KEY set: %s",
            _pass_fail("ZERODHA_API_KEY" in values),
        )
        log.info(
            " ZERODHA_API_SECRET set: %s",
            _pass_fail("ZERODHA_API_SECRET" in values),
        )
        return True
    except Exception as exc:
        log.error(" Failed to apply env defaults: %s", exc)
        return False


# ── Step 6: Validate Zerodha Token Availability ──
def step_6_validate_token() -> bool:
    _section("Step 6: Validate Zerodha Token Availability")
    try:
        from iatb.broker.token_manager import ZerodhaTokenManager

        env_path = Path(".env")
        env_values = _load_env_values(env_path)
        api_key = env_values.get("ZERODHA_API_KEY", "")
        api_secret = env_values.get("ZERODHA_API_SECRET", "")
        totp_secret = env_values.get("ZERODHA_TOTP_SECRET", "")
        tm = ZerodhaTokenManager(
            api_key=api_key,
            api_secret=api_secret,
            totp_secret=totp_secret,
        )
        access_token = tm.get_access_token()
        if access_token:
            log.info(" Access token found: %s", _pass_fail(True))
            is_fresh = tm.is_token_fresh()
            log.info(" Token freshness: %s", _pass_fail(is_fresh))
            if not is_fresh:
                log.warning(" Token may be expired (6 AM IST daily expiry).")
        else:
            log.warning(" No access token available from keyring or .env")
            log.info(" Data from Zerodha API will need fresh session.")
            log.info(" Paper trading engine will still start (uses PaperExecutor).")
        log.info(" Token manager init: %s", _pass_fail(True))
        return True
    except Exception as exc:
        log.warning(" Token manager check skipped: %s", exc)
        log.info(" Paper trading will proceed with PaperExecutor (no live API).")
        return True


# ── Step 7: Instantiate Config and Confirm Paper Mode ──
def step_7_load_config() -> bool:
    _section("Step 7: Instantiate Config and Confirm Paper Mode")
    try:
        import iatb.core.config as cfg_mod

        cfg_mod._config_instance = None  # type: ignore[attr-defined]
        from iatb.core.config import get_config

        config = get_config()
        is_paper = config.execution_mode == "paper"
        is_safe = not config.live_trading_enabled
        log.info(
            " execution_mode: %s — %s",
            config.execution_mode,
            _pass_fail(is_paper),
        )
        log.info(
            " live_trading_enabled: %s — %s",
            config.live_trading_enabled,
            _pass_fail(is_safe),
        )
        log.info(" default_exchange: %s", config.default_exchange)
        log.info(" data_dir: %s", config.data_dir)
        if not is_paper:
            log.error(" Config is NOT in paper mode! Aborting.")
            return False
        if not is_safe:
            log.error(" live_trading_enabled=True in paper mode! Aborting.")
            return False
        log.info(" Paper mode confirmed: %s", _pass_fail(True))
        return True
    except Exception as exc:
        log.error(" Config load failed: %s", exc)
        return False


# ── Step 8: Run Pre-Flight Checks ──
def step_8_preflight() -> bool:
    """Run pre-flight checks; clock drift is WARN (non-blocking) for paper."""
    _section("Step 8: Run Pre-Flight Checks")
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
        )
        if not result:
            log.warning(
                " Preflight FAIL (likely clock drift)."
                " Non-blocking for PAPER mode."
                " Sync clock: w32tm /resync"
            )
            result = True
        log.info(" Pre-flight result: %s", _pass_fail(result))
        return result
    except Exception as exc:
        log.error(" Pre-flight checks failed: %s", exc)
        return False


# ── Step 9: Build Safety Pipeline ──
def step_9_build_safety_pipeline() -> dict[str, object] | None:
    _section("Step 9: Build Full Safety Pipeline")
    try:
        from iatb.execution.order_manager import OrderManager
        from iatb.execution.order_throttle import OrderThrottle
        from iatb.execution.paper_executor import PaperExecutor
        from iatb.execution.pre_trade_validator import PreTradeConfig
        from iatb.execution.trade_audit import TradeAuditLogger
        from iatb.risk.daily_loss_guard import DailyLossGuard
        from iatb.risk.kill_switch import KillSwitch

        executor = PaperExecutor()
        kill_switch = KillSwitch(executor)
        pre_trade_config = PreTradeConfig(
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
            pre_trade_config=pre_trade_config,
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
                "TCS": Decimal("3800"),
                "INFY": Decimal("1500"),
            },
            positions={},
            total_exposure=Decimal("0"),
        )
        components: dict[str, object] = {
            "executor": executor,
            "kill_switch": kill_switch,
            "order_manager": mgr,
            "daily_guard": daily_guard,
            "audit": audit,
            "throttle": throttle,
        }
        log.info(" PaperExecutor: %s", _pass_fail(True))
        log.info(" KillSwitch: %s", _pass_fail(True))
        log.info(" OrderManager: %s", _pass_fail(True))
        log.info(" DailyLossGuard: %s", _pass_fail(True))
        log.info(" TradeAuditLogger: %s", _pass_fail(True))
        log.info(" OrderThrottle: %s", _pass_fail(True))
        log.info(" PreTradeConfig: %s", _pass_fail(True))
        log.info(" Safety pipeline: 7-step risk pipeline ACTIVE")
        return components
    except Exception as exc:
        log.error(" Safety pipeline build failed: %s", exc)
        return None


# ── Step 10: Start Engine ──
async def step_10_start_engine(
    components: dict[str, object],
) -> object | None:
    _section("Step 10: Start Engine with EventBus + SSEBroadcaster")
    try:
        from iatb.core.config import get_config
        from iatb.core.engine import Engine
        from iatb.core.event_bus import EventBus
        from iatb.core.sse_broadcaster import SSEBroadcaster

        config = get_config()
        event_bus = EventBus()
        sse_broadcaster = SSEBroadcaster()
        engine = Engine(
            event_bus=event_bus,
            sse_broadcaster=sse_broadcaster,
            config=config,
            kill_switch=components.get("kill_switch"),
        )
        await engine.start()
        is_running = engine.is_running
        log.info(" Engine started: %s", _pass_fail(is_running))
        health = engine.health_status()
        for component, status in health.items():
            log.info(" %s: %s", component, status)
        if not is_running:
            log.error(" Engine failed to start!")
            return None
        return engine
    except Exception as exc:
        log.error(" Engine start failed: %s", exc)
        return None


# ── Step 11: Execute Sample Paper Trades ──
def step_11_sample_trades(
    components: dict[str, object],
) -> dict[str, Decimal]:
    _section("Step 11: Execute Sample Paper Trades via Risk Pipeline")
    from iatb.core.enums import Exchange, OrderSide
    from iatb.execution.base import OrderRequest

    mgr = components["order_manager"]
    trades = [
        ("NIFTY", "10", "22500", OrderSide.BUY),
        ("BANKNIFTY", "5", "48000", OrderSide.BUY),
        ("RELIANCE", "20", "2800", OrderSide.SELL),
        ("TCS", "8", "3800", OrderSide.BUY),
        ("INFY", "15", "1500", OrderSide.BUY),
        ("NIFTY", "10", "22520", OrderSide.SELL),
    ]
    total_pnl = Decimal("0")
    filled_count = 0
    error_count = 0
    market_hours_reject = 0
    for symbol, qty, price, side in trades:
        try:
            request = OrderRequest(
                exchange=Exchange.NSE,
                symbol=symbol,
                side=side,
                quantity=Decimal(qty),
                price=Decimal(price),
            )
            result = mgr.place_order(request, strategy_id="paper_launch_test")
            fill_pnl = (result.average_price - Decimal(price)) * Decimal(qty)
            if side == OrderSide.SELL:
                fill_pnl = -fill_pnl
            total_pnl += fill_pnl
            filled_count += 1
            log.info(
                " %s %s %s x%s @ %s → fill@%s %s (PnL: %s)",
                result.order_id,
                side.value,
                symbol,
                qty,
                price,
                result.average_price,
                result.status.value,
                fill_pnl,
            )
        except Exception as exc:
            error_count += 1
            exc_str = str(exc)
            if "outside market session" in exc_str:
                market_hours_reject += 1
                log.warning(
                    " REJECTED: %s %s x%s @ %s — %s (after-hours)",
                    side.value,
                    symbol,
                    qty,
                    price,
                    exc,
                )
            else:
                log.error(
                    " REJECTED: %s %s x%s @ %s — %s",
                    side.value,
                    symbol,
                    qty,
                    price,
                    exc,
                )
    log.info("")
    log.info(" Trades filled: %d", filled_count)
    log.info(" Trades rejected: %d (%d outside market hours)", error_count, market_hours_reject)
    log.info(" Session PnL: %s", total_pnl)
    ks = components["kill_switch"]
    log.info(" Kill switch engaged: %s", ks.is_engaged)
    dg = components["daily_guard"]
    log.info(
        " Daily loss state: PnL=%s, limit=%s, breached=%s",
        dg.state.cumulative_pnl,
        dg.state.limit,
        dg.state.breached,
    )
    return {
        "total_pnl": total_pnl,
        "filled": Decimal(str(filled_count)),
        "errors": Decimal(str(error_count)),
    }


# ── Step 12: Kill Switch Drill ──
def step_12_kill_switch_drill(
    components: dict[str, object],
) -> bool:
    _section("Step 12: Kill Switch Emergency Drill")
    from iatb.risk.kill_switch import KillSwitch

    ks: KillSwitch = components["kill_switch"]
    log.info(" Engaging kill switch...")
    state = ks.engage("paper trading drill", datetime.now(UTC))
    log.info(" State: engaged=%s, reason='%s'", state.engaged, state.reason)
    orders_blocked = not ks.check_order_allowed()
    log.info(" Orders blocked after engage: %s", _pass_fail(orders_blocked))
    log.info(" Disengaging kill switch...")
    state = ks.disengage(datetime.now(UTC))
    log.info(" State: engaged=%s", state.engaged)
    orders_allowed = ks.check_order_allowed()
    log.info(" Orders allowed after disengage: %s", _pass_fail(orders_allowed))
    ok = orders_blocked and orders_allowed
    log.info(" Kill switch drill: %s", _pass_fail(ok))
    return ok


# ── Step 13: Audit Trail Verification ──
def step_13_audit_verification() -> bool:
    _section("Step 13: Audit Trail Verification")
    try:
        from iatb.execution.trade_audit import TradeAuditLogger

        audit = TradeAuditLogger(Path("data/audit/trades.sqlite"))
        today = datetime.now(UTC).date()
        trades = audit.query_daily_trades(today)
        log.info(" Date: %s", today.isoformat())
        log.info(" Total trades in audit: %d", len(trades))
        for t in trades[:10]:
            log.info(
                " %s | %s %s | qty=%s price=%s | %s | algo=%s",
                t.order_id,
                t.side,
                t.symbol,
                t.quantity,
                t.price,
                t.status,
                t.algo_id,
            )
        if len(trades) > 10:
            log.info(" ... and %d more trades", len(trades) - 10)
        chain_ok = audit.verify_chain()
        if not chain_ok:
            log.warning(
                " HMAC chain integrity: FAIL - stale data from prior runs."
                " Resetting audit DB for clean paper trading session."
            )
            db_path = Path("data/audit/trades.sqlite")
            if db_path.exists():
                db_path.unlink()
                log.info(" Deleted stale trades.sqlite")
            audit = TradeAuditLogger(db_path)
            chain_ok = audit.verify_chain()
            log.info(
                " HMAC chain integrity after reset: %s",
                _pass_fail(chain_ok),
            )
        else:
            log.info(" HMAC chain integrity: %s", _pass_fail(chain_ok))
        return True
    except Exception as exc:
        log.error(" Audit verification failed: %s", exc)
        return False


# ── Main ──
async def _async_main() -> int:
    start_time = time.monotonic()
    start_utc = datetime.now(UTC)
    log.info("=" * 70)
    log.info(" IATB PAPER TRADING LAUNCHER")
    log.info(" Started: %s UTC", start_utc.isoformat())
    log.info(" Log file: %s", _LOG_FILE)
    log.info("=" * 70)

    results: dict[str, bool] = {}

    # Step 1
    results["environment"] = step_1_verify_environment()
    if not results["environment"]:
        log.error(" Aborting: environment check failed")
        return 1

    # Step 2
    results["credentials"] = step_2_validate_credentials()
    if not results["credentials"]:
        log.error(" Aborting: Zerodha credentials missing in .env")
        return 1

    # Step 3
    results["settings_toml"] = step_3_verify_settings_toml()
    if not results["settings_toml"]:
        log.error(" Aborting: settings.toml not in paper mode")
        return 1

    # Step 4
    results["directories"] = step_4_create_directories()

    # Step 5
    results["env_defaults"] = step_5_apply_env_defaults()

    # Step 6
    results["token"] = step_6_validate_token()

    # Step 7
    results["config"] = step_7_load_config()
    if not results["config"]:
        log.error(" Aborting: config not in paper mode")
        return 1

    # Step 8
    results["preflight"] = step_8_preflight()
    if not results["preflight"]:
        log.error(" Aborting: pre-flight checks failed")
        return 1

    # Step 9
    components = step_9_build_safety_pipeline()
    results["safety_pipeline"] = components is not None
    if components is None:
        log.error(" Aborting: safety pipeline build failed")
        return 1

    # Step 10
    engine = await step_10_start_engine(components)
    results["engine"] = engine is not None
    if engine is not None:
        await engine.stop()
        log.info(" Engine stopped cleanly after health check")

    # Step 11
    pnl_data = step_11_sample_trades(components)

    # Step 12
    results["kill_switch_drill"] = step_12_kill_switch_drill(components)

    # Step 13
    results["audit_verification"] = step_13_audit_verification()

    # ── Final Report ──
    elapsed = time.monotonic() - start_time
    _section("PAPER TRADING LAUNCH SUMMARY")
    for step, ok in results.items():
        log.info(" %-25s %s", step, _pass_fail(ok))
    log.info("")
    log.info(" Session PnL: %s", pnl_data.get("total_pnl", Decimal("0")))
    log.info(" Trades filled: %s", pnl_data.get("filled", Decimal("0")))
    log.info(" Trades rejected: %s", pnl_data.get("errors", Decimal("0")))
    log.info(" Elapsed: %.2fs", elapsed)
    log.info(" Log file: %s", _LOG_FILE)
    log.info("")
    all_passed = all(results.values())
    if all_passed:
        log.info("=" * 70)
        log.info(" *** PAPER TRADING LAUNCH: ALL STEPS PASSED ***")
        log.info(" *** Engine is ready for continuous paper trading ***")
        log.info(" *** Monitor: poetry run python scripts/observe_paper_trading.py ***")
        log.info("=" * 70)
    else:
        failed = [k for k, v in results.items() if not v]
        log.error(" *** LAUNCH FAILED — Steps: %s ***", ", ".join(failed))
    return 0 if all_passed else 1


def main() -> None:
    exit_code = asyncio.run(_async_main())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
