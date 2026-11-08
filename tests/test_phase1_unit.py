import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fetchdeck.app import format_bytes, task_name, validate_download_source, validate_download_url
from fetchdeck.engine import Aria2Rpc, EngineError, InstanceLock


class RpcHandler(BaseHTTPRequestHandler):
    last_request = None

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        type(self).last_request = request
        body = json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": "ready"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        pass


class FetchDeckUnitTests(unittest.TestCase):
    def test_accepts_http_and_https_links(self):
        self.assertEqual(validate_download_url("  https://example.test/archive.zip  "), "https://example.test/archive.zip")
        self.assertEqual(validate_download_url("http://127.0.0.1:8080/file"), "http://127.0.0.1:8080/file")
        self.assertEqual(validate_download_url("ftp://example.test/file.zip"), "ftp://example.test/file.zip")

    def test_accepts_valid_magnets_and_rejects_magnets_without_hashes(self):
        magnet = "magnet:?xt=urn:btih:0123456789012345678901234567890123456789&dn=test.iso"
        self.assertEqual(validate_download_source(magnet), magnet)
        with self.assertRaises(ValueError):
            validate_download_source("magnet:?dn=missing-hash")

    def test_rejects_unsupported_and_credential_bearing_links(self):
        for url in ("magnet:?xt=urn:btih:abc", "https:///missing-host", "https://user:pass@example.test/file"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_download_url(url)

    def test_formats_unknown_size_and_filename(self):
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(task_name({"files": [{"path": "C:\\downloads\\report.zip"}]}), "report.zip")
        self.assertEqual(task_name({"files": [{"uris": [{"uri": "https://example.test/a%20b.zip"}]}]}), "a b.zip")

    def test_session_lock_rejects_a_second_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "aria2.lock"
            first = InstanceLock(path)
            first.acquire()
            try:
                probe = (
                    "import sys; from pathlib import Path; "
                    "from fetchdeck.engine import EngineError, InstanceLock; "
                    "lock=InstanceLock(Path(sys.argv[1])); "
                    "\ntry: lock.acquire()"
                    "\nexcept EngineError: sys.exit(19)"
                    "\nelse: lock.release(); sys.exit(0)"
                )
                result = subprocess.run(
                    [sys.executable, "-c", probe, str(path)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 19, result.stderr)
            finally:
                first.release()
            second = InstanceLock(path)
            second.acquire()
            second.release()

    def test_rpc_authenticates_with_token_and_uses_json_rpc(self):
        RpcHandler.last_request = None
        server = ThreadingHTTPServer(("127.0.0.1", 0), RpcHandler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            rpc = Aria2Rpc(server.server_port, "test-secret")
            self.assertEqual(rpc.call("getVersion"), "ready")
            self.assertEqual(RpcHandler.last_request["method"], "aria2.getVersion")
            self.assertEqual(RpcHandler.last_request["params"], ["token:test-secret"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_rpc_rejects_malformed_or_mismatched_responses(self):
        class BadHandler(RpcHandler):
            def do_POST(self):
                body = b'{"jsonrpc":"2.0","id":-1,"result":"ready"}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), BadHandler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(EngineError):
                Aria2Rpc(server.server_port, "test-secret").call("getVersion")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
