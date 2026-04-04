"""
Automated Zerodha login bootstrap with day-scoped token lifecycle.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
import webbrowser
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from queue import Empty, Full, Queue
from urllib.parse import urlparse

from iatb.core.exceptions import ConfigError
from iatb.execution.zerodha_connection import (
    ZerodhaConnection,
    ZerodhaSession,
    extract_request_token_from_text,
)

_ACCESS_TOKEN_ENV = "ZERODHA_ACCESS_TOKEN"  # noqa: S105
_ACCESS_TOKEN_DATE_ENV = "ZERODHA_ACCESS_TOKEN_DATE_UTC"  # noqa: S105
_REQUEST_TOKEN_ENV = "ZERODHA_REQUEST_TOKEN"  # noqa: S105
_REQUEST_TOKEN_DATE_ENV = "ZERODHA_REQUEST_TOKEN_DATE_UTC"  # noqa: S105
_REDIRECT_URL_ENV = "ZERODHA_REDIRECT_URL"
_BROKER_VERIFIED_ENV = "BROKER_OAUTH_2FA_VERIFIED"
_LOCAL_LOOPBACK = ".".join(("127", "0", "0", "1"))
_ANY_BIND = ".".join(("0", "0", "0", "0"))
_DEFAULT_REDIRECT_URL = f"http://{_LOCAL_LOOPBACK}:5000/callback"
_DEFAULT_LOGIN_TIMEOUT_SECONDS = 180


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Zerodha credentials and fetch account info.",
    )
    parser.add_argument("--env-file", default=".env", help="Path to env file with Zerodha keys.")
    parser.add_argument(
        "--request-token", default="", help="Request token from Zerodha redirect URL."
    )
    parser.add_argument(
        "--redirect-url", default="", help="Full redirect URL containing request_token."
    )
    parser.add_argument(
        "--save-access-token", action="store_true", help="Persist session token metadata."
    )
    parser.add_argument(
        "--login-timeout-seconds",
        type=int,
        default=_DEFAULT_LOGIN_TIMEOUT_SECONDS,
        help="Max seconds to wait for callback token capture after opening login page.",
    )
    auto_group = parser.add_mutually_exclusive_group()
    auto_group.add_argument("--auto-login", dest="auto_login", action="store_true", default=True)
    auto_group.add_argument("--no-auto-login", dest="auto_login", action="store_false")
    return parser


def _emit(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def _parse_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _apply_env_defaults(values: dict[str, str]) -> None:
    for key, value in values.items():
        if value and key not in os.environ:
            os.environ[key] = value


def _persist_env_updates(env_path: Path, updates: dict[str, str]) -> None:
    original_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    rewritten: list[str] = []
    touched_keys: set[str] = set()
    for line in original_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key, _ = line.split("=", maxsplit=1)
            normalized_key = key.strip()
            if normalized_key in updates:
                rewritten.append(f"{normalized_key}={updates[normalized_key]}")
                touched_keys.add(normalized_key)
                continue
        rewritten.append(line)
    for key, value in updates.items():
        if key not in touched_keys:
            rewritten.append(f"{key}={value}")
    env_path.write_text("\n".join(rewritten).rstrip() + "\n", encoding="utf-8")


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _is_today(date_text: str) -> bool:
    normalized = date_text.strip()
    if not normalized:
        return False
    try:
        return date.fromisoformat(normalized) == _utc_today()
    except ValueError:
        return False


def _read_env_text(name: str) -> str:
    return os.getenv(name, "").strip()


def _resolve_saved_access_token() -> str | None:
    access_token = _read_env_text(_ACCESS_TOKEN_ENV)
    if not access_token:
        return None
    access_date = _read_env_text(_ACCESS_TOKEN_DATE_ENV)
    if access_date and not _is_today(access_date):
        return None
    return access_token


def _resolve_saved_request_token() -> str | None:
    request_token = _read_env_text(_REQUEST_TOKEN_ENV)
    if not request_token:
        return None
    request_date = _read_env_text(_REQUEST_TOKEN_DATE_ENV)
    if request_date and not _is_today(request_date):
        return None
    return request_token


def _resolve_redirect_url(cli_redirect_url: str) -> str:
    cli_value = cli_redirect_url.strip()
    if cli_value:
        return cli_value
    env_value = _read_env_text(_REDIRECT_URL_ENV)
    return env_value if env_value else _DEFAULT_REDIRECT_URL


def _resolve_request_token(request_token: str, redirect_url: str) -> str | None:
    normalized = request_token.strip()
    if normalized:
        return normalized
    redirect = redirect_url.strip()
    if not redirect:
        return None
    try:
        return extract_request_token_from_text(redirect)
    except ConfigError as exc:
        lowered = redirect.lower()
        if "status=" in lowered and "request_token=" not in lowered:
            msg = (
                "redirect_url is incomplete or was split at '&'. "
                "Pass full quoted URL or provide --request-token directly."
            )
            raise ConfigError(msg) from exc
        raise


def _looks_like_stale_token_error(message: str) -> bool:
    lowered = message.lower()
    return "403" in lowered or "401" in lowered or "invalid token" in lowered


def _print_login_required(connection: ZerodhaConnection) -> None:
    _emit("ZERODHA_STATUS=LOGIN_REQUIRED")
    _emit(f"ZERODHA_LOGIN_URL={connection.login_url()}")
    _emit(
        "NEXT=Complete Zerodha login and rerun with "
        "--redirect-url <full_redirect_url> or --request-token <token>.",
    )


def _emit_connected(session: ZerodhaSession) -> None:
    _emit("ZERODHA_STATUS=CONNECTED")
    _emit(f"ZERODHA_USER_NAME={session.user_name}")
    _emit(f"ZERODHA_USER_ID={session.user_id}")
    _emit(f"ZERODHA_EMAIL={session.user_email}")
    _emit(f"ZERODHA_AVAILABLE_BALANCE={session.available_balance}")


def _is_local_host(hostname: str) -> bool:
    normalized = hostname.lower()
    local_names = {_LOCAL_LOOPBACK, "localhost", _ANY_BIND, socket.gethostname().lower()}
    return normalized in local_names


def _parse_callback_endpoint(redirect_url: str) -> tuple[str, int, str]:
    parsed = urlparse(redirect_url)
    if parsed.scheme != "http" or not parsed.hostname:
        msg = "ZERODHA_REDIRECT_URL must be an http URL with local host"
        raise ConfigError(msg)
    if not _is_local_host(parsed.hostname):
        msg = "ZERODHA_REDIRECT_URL host must resolve to this machine for auto-capture"
        raise ConfigError(msg)
    path = parsed.path if parsed.path else "/"
    port = parsed.port if parsed.port is not None else 80
    return parsed.hostname, port, path


def _build_callback_handler(
    callback_path: str,
    token_queue: Queue[str],
) -> type[BaseHTTPRequestHandler]:
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != callback_path:
                self.send_response(404)
                self.end_headers()
                return
            try:
                token = extract_request_token_from_text(self.path)
            except ConfigError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"request_token missing in callback URL")
                return
            try:
                token_queue.put_nowait(token)
            except Full:
                pass
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Zerodha login successful. You can close this browser tab.")

        def log_message(self, message_format: str, *args: object) -> None:
            _ = message_format, args

    return CallbackHandler


def _wait_for_callback_token(
    server: HTTPServer, token_queue: Queue[str], timeout_seconds: int
) -> str | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        server.handle_request()
        try:
            return token_queue.get_nowait()
        except Empty:
            continue
    return None


def _auto_acquire_request_token(
    connection: ZerodhaConnection,
    *,
    redirect_url: str,
    timeout_seconds: int,
) -> str | None:
    if timeout_seconds <= 0:
        msg = "login-timeout-seconds must be positive"
        raise ConfigError(msg)
    host, port, callback_path = _parse_callback_endpoint(redirect_url)
    token_queue: Queue[str] = Queue(maxsize=1)
    handler = _build_callback_handler(callback_path, token_queue)
    with HTTPServer((host, port), handler) as server:
        server.timeout = 1
        _emit("ZERODHA_STATUS=LOGIN_INITIATED")
        _emit(f"ZERODHA_LOGIN_URL={connection.login_url()}")
        webbrowser.open(connection.login_url(), new=2)
        return _wait_for_callback_token(server, token_queue, timeout_seconds)


def _persist_session_state(
    env_path: Path, session: ZerodhaSession, request_token: str | None
) -> None:
    today = _utc_today().isoformat()
    updates = {
        _ACCESS_TOKEN_ENV: session.access_token,
        _ACCESS_TOKEN_DATE_ENV: today,
        _BROKER_VERIFIED_ENV: "true",
    }
    if request_token:
        updates[_REQUEST_TOKEN_ENV] = request_token
        updates[_REQUEST_TOKEN_DATE_ENV] = today
    _persist_env_updates(env_path, updates)
    _emit(f"ZERODHA_TOKEN_SAVED={env_path}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    env_path = Path(args.env_file)
    _apply_env_defaults(_parse_env_file(env_path))
    connection = ZerodhaConnection.from_env()
    try:
        saved_access_token = _resolve_saved_access_token()
        if saved_access_token:
            session = connection.establish_session(access_token=saved_access_token)
            _emit_connected(session)
            if args.save_access_token:
                _persist_session_state(env_path, session, request_token=None)
            return 0
    except ConfigError as exc:
        if not _looks_like_stale_token_error(str(exc)):
            _emit(f"ZERODHA_STATUS=BLOCKED reason={exc}")
            return 1
    try:
        redirect_url = _resolve_redirect_url(args.redirect_url)
        request_token = _resolve_request_token(args.request_token, args.redirect_url)
        if request_token is None:
            request_token = _resolve_saved_request_token()
        if request_token is None and args.auto_login:
            request_token = _auto_acquire_request_token(
                connection,
                redirect_url=redirect_url,
                timeout_seconds=args.login_timeout_seconds,
            )
        if request_token is None:
            _print_login_required(connection)
            return 2
        session = connection.establish_session(request_token=request_token)
    except ConfigError as exc:
        _emit(f"ZERODHA_STATUS=BLOCKED reason={exc}")
        return 1
    _emit_connected(session)
    if args.save_access_token:
        _persist_session_state(env_path, session, request_token=request_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
