"""
Periodic non-interactive Zerodha connectivity monitoring.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from iatb.core.exceptions import ConfigError
from iatb.execution.zerodha_connection import ZerodhaConnection, ZerodhaSession
from iatb.execution.zerodha_token_manager import (
    ZerodhaTokenManager,
    apply_env_defaults,
    load_env_file,
)

_LOGGER_NAME = "iatb.scripts.monitor_zerodha_connection"
_STATUS_CONNECTED = "CONNECTED"
_STATUS_LOGIN_REQUIRED = "LOGIN_REQUIRED"
_STATUS_API_ERROR = "API_ERROR"
_EXIT_CONNECTED = 0
_EXIT_API_ERROR = 1
_EXIT_LOGIN_REQUIRED = 2
_DEFAULT_INTERVAL_SECONDS = 300.0
_DEFAULT_LOG_FILE = "logs/zerodha_connection_monitor.log"


@dataclass(frozen=True)
class MonitorCheckResult:
    status: str
    exit_code: int
    checked_at_utc: str
    message: str
    session: ZerodhaSession | None = None
    login_url: str | None = None


class _UtcFormatter(logging.Formatter):
    converter = time.gmtime


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Periodically verify Zerodha session health and log API errors.",
    )
    parser.add_argument("--env-file", default=".env", help="Path to env file with Zerodha keys.")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=_DEFAULT_INTERVAL_SECONDS,
        help="Delay between health checks in seconds.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one health check and exit.",
    )
    parser.add_argument(
        "--max-checks",
        type=int,
        default=0,
        help="Maximum checks to run (0 runs forever until interrupted).",
    )
    parser.add_argument(
        "--log-file",
        default=_DEFAULT_LOG_FILE,
        help="Path to monitor log file.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Logging verbosity for monitor output.",
    )
    parser.add_argument(
        "--persist-tokens",
        dest="persist_tokens",
        action="store_true",
        default=True,
        help="Persist refreshed session token metadata after successful checks.",
    )
    parser.add_argument(
        "--no-persist-tokens",
        dest="persist_tokens",
        action="store_false",
        help="Disable session token persistence during checks.",
    )
    return parser


def _emit(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _looks_like_login_required(message: str) -> bool:
    normalized = message.lower()
    markers = (
        "request token is required",
        "invalid token",
        "token is invalid",
        "http error 401",
        "http error 403",
        "tokenexception",
        "token expired",
    )
    return any(marker in normalized for marker in markers)


def _configure_logger(log_file: Path, level_name: str) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(_LOGGER_NAME)
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(getattr(logging, level_name))
    logger.propagate = False
    formatter = _UtcFormatter(
        fmt="%(asctime)sZ | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger


def _connected_result(
    *,
    session: ZerodhaSession,
    checked_at_utc: str,
) -> MonitorCheckResult:
    return MonitorCheckResult(
        status=_STATUS_CONNECTED,
        exit_code=_EXIT_CONNECTED,
        checked_at_utc=checked_at_utc,
        message="Session validation succeeded.",
        session=session,
    )


def _login_required_result(
    *,
    checked_at_utc: str,
    reason: str,
    login_url: str,
) -> MonitorCheckResult:
    return MonitorCheckResult(
        status=_STATUS_LOGIN_REQUIRED,
        exit_code=_EXIT_LOGIN_REQUIRED,
        checked_at_utc=checked_at_utc,
        message=reason,
        login_url=login_url,
    )


def _api_error_result(*, checked_at_utc: str, reason: str) -> MonitorCheckResult:
    return MonitorCheckResult(
        status=_STATUS_API_ERROR,
        exit_code=_EXIT_API_ERROR,
        checked_at_utc=checked_at_utc,
        message=reason,
    )


def _run_check(
    *,
    connection: ZerodhaConnection,
    token_manager: ZerodhaTokenManager,
    persist_tokens: bool,
) -> MonitorCheckResult:
    checked_at_utc = _utc_now_iso()
    saved_access_token = token_manager.resolve_saved_access_token()
    if saved_access_token:
        try:
            session = connection.establish_session(access_token=saved_access_token)
        except ConfigError as exc:
            if not _looks_like_login_required(str(exc)):
                return _api_error_result(checked_at_utc=checked_at_utc, reason=str(exc))
        else:
            if persist_tokens:
                token_manager.persist_session_tokens(
                    access_token=session.access_token,
                    request_token=None,
                )
            return _connected_result(session=session, checked_at_utc=checked_at_utc)
    saved_request_token = token_manager.resolve_saved_request_token()
    if saved_request_token:
        try:
            session = connection.establish_session(request_token=saved_request_token)
        except ConfigError as exc:
            if _looks_like_login_required(str(exc)):
                return _login_required_result(
                    checked_at_utc=checked_at_utc,
                    reason=str(exc),
                    login_url=connection.login_url(),
                )
            return _api_error_result(checked_at_utc=checked_at_utc, reason=str(exc))
        if persist_tokens:
            token_manager.persist_session_tokens(
                access_token=session.access_token,
                request_token=saved_request_token,
            )
        return _connected_result(session=session, checked_at_utc=checked_at_utc)
    return _login_required_result(
        checked_at_utc=checked_at_utc,
        reason="No same-day access token or request token available.",
        login_url=connection.login_url(),
    )


def _log_check_result(logger: logging.Logger, result: MonitorCheckResult) -> None:
    if result.status == _STATUS_CONNECTED:
        if result.session is None:
            msg = "Connected monitor result must include session details."
            raise RuntimeError(msg)
        logger.info(
            "status=%s check_time_utc=%s user_id=%s available_balance=%s",
            result.status,
            result.checked_at_utc,
            result.session.user_id,
            result.session.available_balance,
        )
        return
    if result.status == _STATUS_LOGIN_REQUIRED:
        logger.warning(
            "status=%s check_time_utc=%s reason=%s login_url=%s",
            result.status,
            result.checked_at_utc,
            result.message,
            result.login_url or "",
        )
        return
    logger.error(
        "status=%s check_time_utc=%s reason=%s",
        result.status,
        result.checked_at_utc,
        result.message,
    )


def _emit_check_result(*, check_number: int, result: MonitorCheckResult) -> None:
    _emit(f"ZERODHA_MONITOR_CHECK={check_number}")
    _emit(f"ZERODHA_MONITOR_STATUS={result.status}")
    _emit(f"ZERODHA_MONITOR_TIME_UTC={result.checked_at_utc}")
    _emit(f"ZERODHA_MONITOR_MESSAGE={result.message}")
    if result.session is not None:
        _emit(f"ZERODHA_USER_ID={result.session.user_id}")
        _emit(f"ZERODHA_USER_NAME={result.session.user_name}")
        _emit(f"ZERODHA_AVAILABLE_BALANCE={result.session.available_balance}")
    if result.login_url:
        _emit(f"ZERODHA_LOGIN_URL={result.login_url}")


def _aggregate_exit_code(current_code: int, next_code: int) -> int:
    if current_code == _EXIT_API_ERROR or next_code == _EXIT_API_ERROR:
        return _EXIT_API_ERROR
    if current_code == _EXIT_LOGIN_REQUIRED or next_code == _EXIT_LOGIN_REQUIRED:
        return _EXIT_LOGIN_REQUIRED
    return _EXIT_CONNECTED


def _validate_args(*, interval_seconds: float, max_checks: int) -> None:
    if interval_seconds <= 0:
        msg = "interval-seconds must be positive"
        raise ConfigError(msg)
    if max_checks < 0:
        msg = "max-checks cannot be negative"
        raise ConfigError(msg)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        _validate_args(
            interval_seconds=args.interval_seconds,
            max_checks=args.max_checks,
        )
        logger = _configure_logger(Path(args.log_file), args.log_level)
        env_path = Path(args.env_file)
        env_values = load_env_file(env_path)
        apply_env_defaults(env_values)
        token_manager = ZerodhaTokenManager(env_path=env_path, env_values=env_values)
        connection = ZerodhaConnection.from_env()
    except (ConfigError, OSError) as exc:
        _emit("ZERODHA_MONITOR_STATUS=API_ERROR")
        _emit(f"ZERODHA_MONITOR_MESSAGE={exc}")
        return _EXIT_API_ERROR
    checks_run = 0
    aggregate_code = _EXIT_CONNECTED
    try:
        while True:
            checks_run += 1
            result = _run_check(
                connection=connection,
                token_manager=token_manager,
                persist_tokens=args.persist_tokens,
            )
            _log_check_result(logger, result)
            _emit_check_result(check_number=checks_run, result=result)
            aggregate_code = _aggregate_exit_code(aggregate_code, result.exit_code)
            if args.once:
                return result.exit_code
            if args.max_checks and checks_run >= args.max_checks:
                return aggregate_code
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        logger.info("monitor interrupted after checks=%s", checks_run)
        return aggregate_code


if __name__ == "__main__":
    raise SystemExit(main())
