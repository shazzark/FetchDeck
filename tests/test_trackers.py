import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fetchdeck.trackers import TrackerError, TrackerListStore, parse_tracker_list


class TrackerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(self.server.status_code)
        self.send_header("Content-Length", str(len(self.server.body)))
        self.end_headers()
        self.wfile.write(self.server.body)

    def log_message(self, _format, *_args):
        pass


class TrackerListTests(unittest.TestCase):
    def test_list_validation_deduplicates_and_rejects_unsupported_urls(self):
        trackers = parse_tracker_list(
            "# comment\n"
            "udp://tracker.example:6969/announce\n"
            "udp://tracker.example:6969/announce\n"
            "https://tracker.example/announce\n"
            "ws://tracker.example/announce\n"
            "https://user:pass@tracker.example/announce\n"
        )
        self.assertEqual(trackers, [
            "udp://tracker.example:6969/announce",
            "https://tracker.example/announce",
        ])

    def test_real_local_sync_saves_good_list_and_retains_it_after_failures(self):
        with tempfile.TemporaryDirectory(prefix="fetchdeck-trackers-") as directory:
            server = ThreadingHTTPServer(("127.0.0.1", 0), TrackerHandler)
            server.daemon_threads = True
            server.status_code = 200
            server.body = b"udp://tracker.local:6969/announce\nhttps://tracker.local/announce\n"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                cache = Path(directory) / "trackers.txt"
                store = TrackerListStore(cache, timeout=2)
                url = f"http://127.0.0.1:{server.server_port}/trackers.txt"
                saved = store.sync_url(url)
                original = cache.read_bytes()
                self.assertEqual(len(saved), 2)

                server.status_code = 503
                with self.assertRaises(TrackerError):
                    store.sync_url(url)
                self.assertEqual(cache.read_bytes(), original)

                server.status_code = 200
                server.body = b"# no usable trackers\nws://tracker.local/announce\n"
                with self.assertRaises(TrackerError):
                    store.sync_url(url)
                self.assertEqual(cache.read_bytes(), original)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
