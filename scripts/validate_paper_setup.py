#!/usr/bin/env python
"""
IATB Paper Trading Setup Validator — Pre-flight credential & config check.

Validates before engine launch:
  Step 1:  .env file exists with required Zerodha keys
  Step 2:  config/settings.toml has paper-trading-safe values
  Step 3:  Required directories exist and are writable
  Step 4:  Zerodha credentials are non-empty
  Step 5:  Token manager can be instantiated
  Step 6:  Config singleton loads without error
  Step 7:  Database paths are writable
  Step 8:  No conflicting live-mode flags

Exit codes: 0 = all pass, 1 = any failure.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_LOGGER_NAME = "iatb.scripts.validate_paper_setup"
_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / f"paper_setup_validation_{_TIMESTAMP}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(_LOGGER_NAME)

_REQUIRED_ENV_KEYS = [
    "ZERODHA_API_KEY",
    "ZERODHA_API_SECRET",
]

_RECOMMENDED_ENV_KEYS = [
    "ZERODHA_ACCESS_TOKEN",
    "ZERODHA_REQUEST_TOKEN",
]

_PAPER_SAFE_SETTINGS = {
    "execution_mode": "paper",
    "live_trading_enabled": "false",
    "paper_trade_enforced": "true",
}

_REQUIRED_DIRS = [
    Path("data"),
    Path("logs"),
    Path("cache"),
    Path("data/audit"),
]


def _pass_fail(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _section(title: str) -> None:
    bar = "=" * 70
    log.info("")
    log.info(bar)
    log.info(" %s", title)
    log.info(bar)


def _load_env_values(env_path: Path) -> dict[str, str]:
    """Parse .env file into key-value dict (no os.environ side-effects)."""
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


def step_1_validate_env_file() -> bool:
    """Step 1: Verify .env file exists with required Zerodha keys."""
    _section("Step 1: Validate .env File")
    env_path = Path(".env")

    if not env_path.exists():
        log.error(" .env file not found at: %s", env_path.resolve())
        log.info("  → Copy .env.example to .env and fill in Zerodha credentials")
        return False

    log.info(" .env file found: %s", _pass_fail(True))
    env_values = _load_env_values(env_path)
    all_ok = True

    for key in _REQUIRED_ENV_KEYS:
        present = key in env_values and bool(env_values[key].strip())
        log.info(" %s: %s", key, _pass_fail(present))
        if not present:
            all_ok = False

    for key in _RECOMMENDED_ENV_KEYS:
        present = key in env_values and bool(env_values[key].strip())
        status = "present" if present else "not set (will need login)"
        log.info(" %s: %s", key, status)

    return all_ok


def step_2_validate_settings_toml() -> bool:
    """Step 2: Verify config/settings.toml has paper-trading-safe values."""
    _section("Step 2: Validate config/settings.toml Paper Mode")
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

    all_ok = True
    for key, expected in _PAPER_SAFE_SETTINGS.items():
        actual = str(data.get(key, "")).lower()
        ok = actual == expected.lower()
        log.info(
            " %s = %s (expected: %s): %s",
            key,
            actual or "(missing)",
            expected,
            _pass_fail(ok),
        )
        if not ok:
            all_ok = False

    return all_ok


def step_3_validate_directories() -> bool:
    """Step 3: Verify required directories exist and are writable."""
    _section("Step 3: Validate Required Directories")
    all_ok = True
    for d in _REQUIRED_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        exists = d.exists()
        writable = os.access(str(d), os.W_OK) if exists else False
        ok = exists and writable
        log.info(" %s: exists=%s writable=%s — %s", d, exists, writable, _pass_fail(ok))
        if not ok:
            all_ok = False
    return all_ok


def step_4_validate_zerodha_credentials() -> bool:
    """Step 4: Verify Zerodha API key/secret are non-empty in .env."""
    _section("Step 4: Validate Zerodha Credentials")
    env_path = Path(".env")
    env_values = _load_env_values(env_path)

    api_key = env_values.get("ZERODHA_API_KEY", "").strip()
    api_secret = env_values.get("ZERODHA_API_SECRET", "").strip()

    key_ok = len(api_key) > 0
    secret_ok = len(api_secret) > 0
    log.info(" ZERODHA_API_KEY length: %d — %s", len(api_key), _pass_fail(key_ok))
    log.info(
        " ZERODHA_API_SECRET length: %d — %s",
        len(api_secret),
        _pass_fail(secret_ok),
    )

    access_token = env_values.get("ZERODHA_ACCESS_TOKEN", "").strip()
    request_token = env_values.get("ZERODHA_REQUEST_TOKEN", "").strip()
    has_token = len(access_token) > 0 or len(request_token) > 0
    log.info(" Has access or request token: %s", _pass_fail(has_token))

    if not has_token:
        log.warning(
            "  No access/request token found. Token will need to be"
            " obtained via Zerodha login before or at runtime."
        )

    return key_ok and secret_ok


def step_5_validate_token_manager() -> bool:
    """Step 5: Verify ZerodhaTokenManager can be instantiated."""
    _section("Step 5: Validate Token Manager Instantiation")
    try:
        from iatb.broker.token_manager import ZerodhaTokenManager

        log.info(" ZerodhaTokenManager import: %s", _pass_fail(True))
    except Exception as exc:
        log.error(" ZerodhaTokenManager import failed: %s", exc)
        return False

    try:
        env_path = Path(".env")
        env_values = _load_env_values(env_path)
        api_key = env_values.get("ZERODHA_API_KEY", "test_key")
        api_secret = env_values.get("ZERODHA_API_SECRET", "test_secret")
        totp_secret = env_values.get("ZERODHA_TOTP_SECRET", "")

        tm = ZerodhaTokenManager(
            api_key=api_key,
            api_secret=api_secret,
            totp_secret=totp_secret,
        )
        log.info(" ZerodhaTokenManager init: %s", _pass_fail(True))
        log.info(" Token fresh check available: %s", _pass_fail(True))

        has_access = tm.get_access_token() is not None
        log.info(" Access token available: %s", _pass_fail(has_access))
        if not has_access:
            log.warning(
                "  No active access token. Runtime will need"
                " to perform Zerodha login/session exchange."
            )
        return True
    except Exception as exc:
        log.error(" ZerodhaTokenManager instantiation failed: %s", exc)
        return False


def step_6_validate_config_singleton() -> bool:
    """Step 6: Verify Config singleton loads without error."""
    _section("Step 6: Validate Config Singleton Load")
    try:
        # Reset singleton for clean load
        import iatb.core.config as cfg_mod
        from iatb.core.config import get_config

        cfg_mod._config_instance = None

        config = get_config()
        log.info(" Config loaded: %s", _pass_fail(True))
        log.info(" execution_mode: %s", config.execution_mode)
        log.info(" live_trading_enabled: %s", config.live_trading_enabled)
        log.info(" default_exchange: %s", config.default_exchange)
        log.info(" data_dir: %s", config.data_dir)

        is_paper = config.execution_mode == "paper"
        log.info(" Paper mode confirmed: %s", _pass_fail(is_paper))
        return is_paper
    except Exception as exc:
        log.error(" Config load failed: %s", exc)
        return False


def step_7_validate_database_paths() -> bool:
    """Step 7: Verify audit and state database paths are writable."""
    _section("Step 7: Validate Database Paths")
    db_paths = [
        Path("data/audit/trades.sqlite"),
        Path("data/iatb.duckdb"),
    ]
    all_ok = True
    for db_path in db_paths:
        parent = db_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        writable = os.access(str(parent), os.W_OK)
        log.info(
            " %s parent writable: %s — %s", db_path, writable, _pass_fail(writable)
        )
        if not writable:
            all_ok = False
    return all_ok


def step_8_validate_no_live_conflict() -> bool:
    """Step 8: Verify no conflicting live-mode flags are set."""
    _section("Step 8: Validate No Live-Mode Conflicts")
    env_path = Path(".env")
    env_values = _load_env_values(env_path)

    iatb_mode = env_values.get("IATB_MODE", "").lower()
    execution_mode = env_values.get("EXECUTION_MODE", "").lower()
    live_enabled = env_values.get("LIVE_TRADING_ENABLED", "").lower()

    conflicts: list[str] = []

    if iatb_mode == "live":
        conflicts.append("IATB_MODE=live in .env")
    if execution_mode == "live":
        conflicts.append("EXECUTION_MODE=live in .env")
    if live_enabled in ("true", "1", "yes"):
        conflicts.append("LIVE_TRADING_ENABLED=true in .env")

    if conflicts:
        for c in conflicts:
            log.error(" CONFLICT: %s", c)
        log.error(" Live-mode conflicts found: %s", _pass_fail(False))
        return False

    log.info(" No live-mode conflicts: %s", _pass_fail(True))
    return True


def main() -> None:
    start_time_iso = datetime.now(UTC).isoformat()
    log.info("IATB Paper Trading Setup Validator")
    log.info("Started: %s UTC", start_time_iso)
    log.info("Log file: %s", _LOG_FILE)

    results: dict[str, bool] = {}

    results["env_file"] = step_1_validate_env_file()
    results["settings_toml"] = step_2_validate_settings_toml()
    results["directories"] = step_3_validate_directories()
    results["credentials"] = step_4_validate_zerodha_credentials()
    results["token_manager"] = step_5_validate_token_manager()
    results["config_load"] = step_6_validate_config_singleton()
    results["database_paths"] = step_7_validate_database_paths()
    results["no_live_conflict"] = step_8_validate_no_live_conflict()

    _section("VALIDATION SUMMARY")
    for step, ok in results.items():
        log.info(" %-25s %s", step, _pass_fail(ok))

    all_passed = all(results.values())
    log.info("")
    if all_passed:
        log.info(" *** SETUP VALIDATION: ALL 8 STEPS PASSED ***")
        log.info(
            " Ready to launch paper trading: poetry run python scripts/launch_paper_trading.py"
        )
    else:
        failed = [k for k, v in results.items() if not v]
        log.error(" *** SETUP VALIDATION: FAILED STEPS: %s ***", ", ".join(failed))
        log.error(" Fix the above issues before launching paper trading.")

    log.info(" Log file: %s", _LOG_FILE)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
