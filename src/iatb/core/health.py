"""
HTTP health endpoint support for runtime/container probes.
"""

import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import ClassVar

logger = logging.getLogger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    """Serve readiness/liveness checks for the runtime."""

    response_body: ClassVar[bytes] = b'{"status":"ok"}'

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET requests for /health."""
        if self.path != "/health":
            self.send_error(404, "Not Found")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.response_body)))
        self.end_headers()
        self.wfile.write(self.response_body)

    def log_message(self, format_str: str, *args: object) -> None:
        """Redirect HTTP server logs into project logger."""
        logger.debug("health-server %s", format_str % args)


class HealthServer:
    """Manage lifecycle for a lightweight HTTP health server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8000) -> None:
        self._server = ThreadingHTTPServer((host, port), _HealthHandler)
        self._thread: Thread | None = None

    @property
    def port(self) -> int:
        """Get active server port."""
        return int(self._server.server_port)

    def start(self) -> None:
        """Start health server in background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="iatb-health-server",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop health server and wait for shutdown."""
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)
