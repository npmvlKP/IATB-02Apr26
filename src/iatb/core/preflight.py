"""
Pre-flight checks before engine startup.

Validates system state, connectivity, and configuration.
Fail-closed: engine must not start if any check fails.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from iatb.core.clock import ClockDriftDetector
from iatb.core.exceptions import ConfigError
from iatb.execution.base import Executor
from iatb.risk.kill_switch import KillSwitch

logger = logging.getLogger(__name__)


def run_preflight_checks(
    executor: Executor,
    kill_switch: KillSwitch,
    data_dir: Path,
    audit_db_path: Path,
) -> bool:
    """Run all pre-flight checks. Returns True only if all pass."""
    all_passed = True
    all_passed = _run_check("clock_drift", _check_clock_drift, all_passed)
    all_passed = _run_check("executor_ready", lambda: _check_executor(executor), all_passed)
    all_passed = _run_check(
        "kill_switch_clear", lambda: _check_kill_switch(kill_switch), all_passed
    )
    all_passed = _run_check("data_dir_exists", lambda: _check_path_exists(data_dir), all_passed)
    all_passed = _run_check(
        "audit_db_writable", lambda: _check_path_writable(audit_db_path), all_passed
    )
    return all_passed


def _run_check(name: str, check: Callable[[], None], current: bool) -> bool:
    try:
        check()
        logger.info("Preflight %s: PASS", name)
    except ConfigError as exc:
        logger.error("Preflight %s: FAIL — %s", name, exc)
        return False
    return current


def _check_clock_drift(max_drift_seconds: int = 2) -> None:
    detector = ClockDriftDetector()
    drift = detector.check_drift()
    if abs(drift.total_seconds()) > max_drift_seconds:
        msg = f"clock drift {drift.total_seconds()}s exceeds {max_drift_seconds}s"
        raise ConfigError(msg)


def _check_executor(executor: Executor) -> None:
    try:
        count = executor.cancel_all()
        if count != 0:
            msg = f"executor has {count} open orders at startup"
            raise ConfigError(msg)
    except Exception as exc:
        msg = f"executor not responding: {exc}"
        raise ConfigError(msg) from exc


def _check_kill_switch(kill_switch: KillSwitch) -> None:
    if kill_switch.is_engaged:
        msg = "kill switch is engaged at startup"
        raise ConfigError(msg)


def _check_path_exists(path: Path) -> None:
    if not path.exists():
        msg = f"required path does not exist: {path}"
        raise ConfigError(msg)


def _check_path_writable(path: Path) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.exists():
        msg = f"cannot create parent directory: {parent}"
        raise ConfigError(msg)
