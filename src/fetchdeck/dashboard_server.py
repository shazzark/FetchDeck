from __future__ import annotations

import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class DashboardServer:
    """Serve the static export and safe statistics from one loopback origin."""

    def __init__(self, export_dir: Path, snapshot_provider) -> None:
        self.export_dir = export_dir.resolve()
        self.snapshot_provider = snapshot_provider
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner._handle(self)

            def do_HEAD(self) -> None:
                owner._handle(self, head=True)

            def do_POST(self) -> None:
                owner._handle(self)

            def do_PUT(self) -> None:
                owner._handle(self)

            def do_DELETE(self) -> None:
                owner._handle(self)

            def do_OPTIONS(self) -> None:
                owner._handle(self)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, name="FetchDeckDashboard", daemon=True)
        self._thread.start()
        return f"http://127.0.0.1:{self._server.server_port}/"

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def _handle(self, request: BaseHTTPRequestHandler, head: bool = False) -> None:
        assert self._server is not None
        origin = f"http://127.0.0.1:{self._server.server_port}"
        if request.headers.get("Host", "").lower() != f"127.0.0.1:{self._server.server_port}":
            self._respond(request, 400, b"Invalid Host", "text/plain", head)
            return
        supplied_origin = request.headers.get("Origin")
        if supplied_origin and supplied_origin != origin:
            self._respond(request, 403, b"Origin denied", "text/plain", head)
            return
        if request.command not in {"GET", "HEAD"}:
            self._respond(request, 405, b"Method not allowed", "text/plain", head)
            return
        path = urlsplit(request.path).path
        if path == "/api/v1/stats":
            body = json.dumps(self.snapshot_provider(), separators=(",", ":")).encode("utf-8")
            self._respond(request, 200, body, "application/json; charset=utf-8", head)
            return
        relative = unquote(path.lstrip("/")) or "index.html"
        target = (self.export_dir / relative).resolve()
        if not target.is_relative_to(self.export_dir) or not target.is_file():
            self._respond(request, 404, b"Not found", "text/plain", head)
            return
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        try:
            body = target.read_bytes()
        except OSError:
            self._respond(request, 404, b"Not found", "text/plain", head)
            return
        self._respond(request, 200, body, mime, head)

    @staticmethod
    def _respond(request: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str, head: bool) -> None:
        request.send_response(status)
        request.send_header("Content-Type", content_type)
        request.send_header("Content-Length", str(len(body)))
        request.send_header("X-Content-Type-Options", "nosniff")
        request.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'")
        request.end_headers()
        if not head:
            request.wfile.write(body)
