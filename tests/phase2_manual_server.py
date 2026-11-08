"""Run the Phase 2 controlled HTTP handler for a visible Windows recovery check."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
spec = importlib.util.spec_from_file_location("phase2_integration", ROOT / "tests" / "test_aria2_integration.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load the Phase 2 controlled HTTP handler.")
phase2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phase2)


class RequestLoggingHandler(phase2.ControlledHandler):
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        range_header = self.headers.get("Range") or "none"
        line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} GET {path} Range={range_header}\n"
        with self.server.request_log_lock:
            with self.server.request_log.open("a", encoding="utf-8", newline="\n") as log:
                log.write(line)
                log.flush()
        super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--chunk-delay", type=float, default=0.25)
    parser.add_argument(
        "--request-log",
        type=Path,
        default=Path(tempfile.gettempdir()) / "fetchdeck-phase2-http-requests.log",
    )
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), RequestLoggingHandler)
    server.daemon_threads = True
    server.requests = []
    server.chunk_delay = args.chunk_delay
    server.request_log = args.request_log
    server.request_log_lock = threading.Lock()
    print(f"Serving {len(phase2.PAYLOAD)} bytes at http://{args.host}:{args.port}/phase2-resume-test.bin", flush=True)
    print(f"Chunk delay: {args.chunk_delay}s per 64 KiB; request log: {args.request_log}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
