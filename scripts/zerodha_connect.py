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
from iatb.execution.zerodha_token_manager import (
    ZerodhaTokenManager,
    apply_env_defaults,
    load_env_file,
)

_REDIRECT_URL_ENV = "ZERODHA_REDIRECT_URL"
_LOCAL_LOOPBACK = ".".join(("127", "0", "0", "1"))
_ANY_BIND = ".".join(("0", "0", "0", "0"))
_DEFAULT_REDIRECT_URL = f"http://{_LOCAL_LOOPBACK}:5000/callback"
_DEFAULT_LOGIN_TIMEOUT_SECONDS = 180
_DEFAULT_MAX_RECONNECT_ATTEMPTS = 3
_DEFAULT_RECONNECT_DELAY_SECONDS = 2.0


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
    parser.add_argument(
        "--max-reconnect-attempts",
        type=int,
        default=_DEFAULT_MAX_RECONNECT_ATTEMPTS,
        help="Max reconnect attempts for transient API/network failures.",
    )
    parser.add_argument(
        "--reconnect-delay-seconds",
        type=float,
        default=_DEFAULT_RECONNECT_DELAY_SECONDS,
        help="Base reconnect delay in seconds; multiplied by attempt index.",
    )
    auto_group = parser.add_mutually_exclusive_group()
    auto_group.add_argument("--auto-login", dest="auto_login", action="store_true", default=True)
    auto_group.add_argument("--no-auto-login", dest="auto_login", action="store_false")
    return parser


def _emit(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def _read_env_text(name: str) -> str:
    return os.getenv(name, "").strip()


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


def _looks_like_transient_api_error(message: str) -> bool:
    lowered = message.lower()
    markers = (
        "http error 429",
        "http error 500",
        "http error 502",
        "http error 503",
        "http error 504",
        "timed out",
        "temporary failure",
        "connection reset",
        "connection aborted",
        "connection refused",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "name resolution",
    )
    return any(marker in lowered for marker in markers)


def _validate_reconnect_settings(*, max_attempts: int, delay_seconds: float) -> None:
    if max_attempts <= 0:
        msg = "max-reconnect-attempts must be positive"
        raise ConfigError(msg)
    if delay_seconds < 0:
        msg = "reconnect-delay-seconds cannot be negative"
        raise ConfigError(msg)


def _establish_session_with_reconnect(
    connection: ZerodhaConnection,
    *,
    request_token: str | None,
    access_token: str | None,
    max_attempts: int,
    delay_seconds: float,
) -> ZerodhaSession:
    attempt = 1
    while attempt <= max_attempts:
        try:
            return connection.establish_session(
                request_token=request_token,
                access_token=access_token,
            )
        except ConfigError as exc:
            if not _looks_like_transient_api_error(str(exc)) or attempt >= max_attempts:
                raise
            retry_attempt = attempt + 1
            _emit(f"ZERODHA_RECONNECT_ATTEMPT={retry_attempt}")
            _emit(f"ZERODHA_RECONNECT_REASON={exc}")
            wait_seconds = delay_seconds * attempt
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            attempt = retry_attempt
    msg = "Session reconnect attempts exhausted"
    raise ConfigError(msg)


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


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        _validate_reconnect_settings(
            max_attempts=args.max_reconnect_attempts,
            delay_seconds=args.reconnect_delay_seconds,
        )
    except ConfigError as exc:
        _emit(f"ZERODHA_STATUS=BLOCKED reason={exc}")
        return 1
    env_path = Path(args.env_file)
    env_values = load_env_file(env_path)
    apply_env_defaults(env_values)
    token_manager = ZerodhaTokenManager(
        env_path=env_path,
        env_values=env_values,
    )
    connection = ZerodhaConnection.from_env()
    try:
        saved_access_token = token_manager.resolve_saved_access_token()
        if saved_access_token:
            session = _establish_session_with_reconnect(
                connection,
                request_token=None,
                access_token=saved_access_token,
                max_attempts=args.max_reconnect_attempts,
                delay_seconds=args.reconnect_delay_seconds,
            )
            _emit_connected(session)
            if args.save_access_token:
                persisted_path = token_manager.persist_session_tokens(
                    access_token=session.access_token,
                    request_token=None,
                )
                _emit(f"ZERODHA_TOKEN_SAVED={persisted_path}")
            return 0
    except ConfigError as exc:
        if not _looks_like_stale_token_error(str(exc)):
            _emit(f"ZERODHA_STATUS=BLOCKED reason={exc}")
            return 1
    try:
        redirect_url = _resolve_redirect_url(args.redirect_url)
        request_token = _resolve_request_token(args.request_token, args.redirect_url)
        if request_token is None:
            request_token = token_manager.resolve_saved_request_token()
        if request_token is None and args.auto_login:
            request_token = _auto_acquire_request_token(
                connection,
                redirect_url=redirect_url,
                timeout_seconds=args.login_timeout_seconds,
            )
        if request_token is None:
            _print_login_required(connection)
            return 2
        session = _establish_session_with_reconnect(
            connection,
            request_token=request_token,
            access_token=None,
            max_attempts=args.max_reconnect_attempts,
            delay_seconds=args.reconnect_delay_seconds,
        )
    except ConfigError as exc:
        _emit(f"ZERODHA_STATUS=BLOCKED reason={exc}")
        return 1
    _emit_connected(session)
    if args.save_access_token:
        persisted_path = token_manager.persist_session_tokens(
            access_token=session.access_token,
            request_token=request_token,
        )
        _emit(f"ZERODHA_TOKEN_SAVED={persisted_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
