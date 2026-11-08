import hashlib
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from fetchdeck.engine import Aria2Daemon, EngineWorker
from fetchdeck.paths import AppPaths


PAYLOAD = bytes(index % 251 for index in range(8 * 1024 * 1024))


class ControlledHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        self.server.requests.append((path, self.headers.get("Range")))
        if path == "/missing.bin":
            self.send_error(404, "controlled missing file")
            return
        start = 0
        end = len(PAYLOAD) - 1
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            try:
                range_start, range_end = range_header[6:].split("-", 1)
                start = int(range_start)
                end = int(range_end) if range_end else end
            except ValueError:
                self.send_error(400)
                return
            if start >= len(PAYLOAD) or end < start or end >= len(PAYLOAD):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(PAYLOAD)}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(PAYLOAD)}")
        else:
            self.send_response(200)
        remaining = PAYLOAD[start : end + 1]
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(remaining)))
        self.end_headers()
        try:
            for offset in range(0, len(remaining), 64 * 1024):
                self.wfile.write(remaining[offset : offset + 64 * 1024])
                self.wfile.flush()
                time.sleep(0.025)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, _format, *_args):
        pass


@unittest.skipUnless(Aria2Daemon._find_binary(), "aria2c.exe is not installed or not on PATH")
class Aria2ControlledServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def test_queue_pause_resume_removal_failure_and_sha256(self):
        with tempfile.TemporaryDirectory(prefix="fetchdeck-engine-") as directory:
            root = Path(directory)
            save_dir = root / "downloads"
            save_dir.mkdir()
            paths = AppPaths(root / "app-data")
            server = ThreadingHTTPServer(("127.0.0.1", 0), ControlledHandler)
            server.daemon_threads = True
            server.requests = []
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            worker = EngineWorker(
                paths,
                max_concurrent_downloads=1,
                connections_per_task=1,
            )
            tasks = []
            actions = {}
            errors = []
            versions = []
            worker.snapshot.connect(lambda current: tasks.__setitem__(slice(None), current))
            worker.action_finished.connect(
                lambda action_id, success, message: actions.__setitem__(action_id, (success, message))
            )
            worker.error.connect(errors.append)
            worker.ready.connect(versions.append)
            worker.start()

            try:
                self.assertTrue(wait_until(lambda: versions or errors, 8), errors)
                self.assertTrue(versions, errors)
                self.assertIn("1.37.0", versions[0])
                base = f"http://127.0.0.1:{server.server_port}"

                self._action(worker, actions, errors, "add", base + "/first.bin", save_dir)
                self._action(worker, actions, errors, "add", base + "/second.bin", save_dir)
                first = wait_for_file_status(tasks, "first.bin", {"active"}, 8)
                second = wait_for_file_status(tasks, "second.bin", {"waiting"}, 8)

                self._action(worker, actions, errors, "pause", first["gid"])
                wait_for_status(tasks, first["gid"], {"paused"}, 5)
                wait_for_status(tasks, second["gid"], {"complete"}, 20)
                self._action(worker, actions, errors, "resume", first["gid"])
                wait_for_status(tasks, first["gid"], {"complete"}, 20)

                first_file = save_dir / "first.bin"
                second_file = save_dir / "second.bin"
                expected_hash = hashlib.sha256(PAYLOAD).hexdigest()
                self.assertEqual(sha256(first_file), expected_hash)
                self.assertEqual(sha256(second_file), expected_hash)

                self._action(worker, actions, errors, "remove", first["gid"], "complete")
                self.assertTrue(first_file.exists(), "removing a task result must preserve its file")
                self.assertTrue(wait_until(lambda: not has_gid(tasks, first["gid"]), 5))

                self._action(worker, actions, errors, "add", base + "/missing.bin", save_dir)
                failed = wait_for_file_status(tasks, "missing.bin", {"error"}, 10)
                self.assertTrue(failed.get("errorMessage"))
                self.assertTrue(any(path == "/missing.bin" for path, _range in server.requests))

            finally:
                worker.requestInterruption()
                if worker.isRunning():
                    worker.wait(8000)
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=2)

    def _action(self, worker, actions, errors, name, *args):
        action_id = worker.submit(name, *args)
        self.assertTrue(wait_until(lambda: action_id in actions or errors, 6), errors)
        self.assertIn(action_id, actions, errors)
        success, message = actions[action_id]
        self.assertTrue(success, message)


def wait_until(predicate, timeout):
    if predicate():
        return True
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda: loop.quit() if predicate() else None)
    timer.start()
    QTimer.singleShot(round(timeout * 1000), loop.quit)
    loop.exec()
    timer.stop()
    return predicate()


def wait_for_file_status(tasks, name, expected, timeout):
    found = {}

    def matches():
        for task in tasks:
            if task_filename(task) == name and task.get("status") in expected:
                found.update(task)
                return True
        return False

    if not wait_until(matches, timeout):
        raise AssertionError(f"{name} did not reach {expected}; current tasks: {tasks}")
    return found


def task_filename(task):
    files = task.get("files") or []
    if not files:
        return ""
    path = files[0].get("path", "")
    if path:
        return Path(path).name
    uris = files[0].get("uris") or []
    uri = uris[0].get("uri", "") if uris else ""
    return Path(urlsplit(uri).path).name


def wait_for_status(tasks, gid, expected, timeout):
    found = {}

    def matches():
        for task in tasks:
            if task.get("gid") == gid and task.get("status") in expected:
                found.update(task)
                return True
        return False

    if not wait_until(matches, timeout):
        raise AssertionError(f"Task {gid} did not reach {expected}; current tasks: {tasks}")
    return found


def has_gid(tasks, gid):
    return any(task.get("gid") == gid for task in tasks)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
