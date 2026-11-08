import hashlib
import os
import socket
import socketserver
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
                time.sleep(getattr(self.server, "chunk_delay", 0.025))
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, _format, *_args):
        pass


class FtpHandler(socketserver.BaseRequestHandler):
    def handle(self):
        control = self.request
        reader = control.makefile("rb")
        passive = None
        offset = 0
        control.sendall(b"220 FetchDeck test server ready\r\n")
        try:
            while line := reader.readline(4096):
                command, _, argument = line.decode("ascii", errors="replace").strip().partition(" ")
                command = command.upper()
                argument = argument.strip()
                self.server.commands.append((command, argument))
                if command == "USER":
                    self.reply(control, "331 Password required")
                elif command == "PASS":
                    self.reply(control, "230 Logged in")
                elif command == "SYST":
                    self.reply(control, "215 UNIX Type: L8")
                elif command in {"CWD", "CDUP"}:
                    self.reply(control, "250 Directory changed")
                elif command in {"TYPE", "OPTS", "NOOP", "CLNT"}:
                    self.reply(control, "200 OK")
                elif command == "PWD":
                    self.reply(control, '257 "/" is current directory')
                elif command == "FEAT":
                    features = " REST STREAM\r\n" if self.server.supports_rest else ""
                    control.sendall(f"211-Features{features} UTF8\r\n211 End\r\n".encode())
                elif command == "SIZE":
                    self.reply(control, f"213 {len(PAYLOAD)}")
                elif command in {"EPSV", "PASV"}:
                    if passive:
                        passive.close()
                    passive = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    passive.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    passive.bind(("127.0.0.1", 0))
                    passive.listen(1)
                    port = passive.getsockname()[1]
                    if command == "EPSV":
                        self.reply(control, f"229 Entering Extended Passive Mode (|||{port}|)")
                    else:
                        self.reply(control, f"227 Entering Passive Mode (127,0,0,1,{port // 256},{port % 256})")
                elif command == "REST":
                    if not self.server.supports_rest:
                        self.reply(control, "502 REST is not supported")
                    else:
                        offset = int(argument)
                        self.server.rest_offsets.append(offset)
                        self.reply(control, f"350 Restarting at {offset}")
                elif command == "RETR":
                    if passive is None:
                        self.reply(control, "425 Use EPSV or PASV first")
                        continue
                    self.reply(control, "150 Opening binary data connection")
                    try:
                        data, _address = passive.accept()
                        with data:
                            for position in range(offset, len(PAYLOAD), 64 * 1024):
                                data.sendall(PAYLOAD[position : position + 64 * 1024])
                                time.sleep(0.02)
                        offset = 0
                        self.reply(control, "226 Transfer complete")
                    except OSError:
                        break
                    finally:
                        passive.close()
                        passive = None
                elif command == "QUIT":
                    self.reply(control, "221 Goodbye")
                    return
                else:
                    self.reply(control, "502 Command not supported")
        except (ConnectionError, OSError):
            pass
        finally:
            if passive:
                passive.close()
            reader.close()

    @staticmethod
    def reply(control, message):
        control.sendall(f"{message}\r\n".encode())


class FtpTestServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, supports_rest=True):
        super().__init__(("127.0.0.1", 0), FtpHandler)
        self.supports_rest = supports_rest
        self.rest_offsets = []
        self.commands = []


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

    def test_graceful_restart_restores_pause_and_resumes_from_saved_offset(self):
        with tempfile.TemporaryDirectory(prefix="fetchdeck-recovery-") as directory:
            root = Path(directory)
            save_dir = root / "downloads"
            save_dir.mkdir()
            paths = AppPaths(root / "app-data")
            server = ThreadingHTTPServer(("127.0.0.1", 0), ControlledHandler)
            server.daemon_threads = True
            server.requests = []
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            worker, tasks, actions, errors, versions = self._start_worker(paths)
            try:
                self.assertTrue(wait_until(lambda: versions or errors, 8), errors)
                self._action(worker, actions, errors, "add", f"http://127.0.0.1:{server.server_port}/recovered.bin", save_dir)
                task = wait_for_file_status(tasks, "recovered.bin", {"active"}, 8)
                self.assertTrue(wait_until(lambda: int(find_task(tasks, task["gid"]).get("completedLength", 0)) > 0, 8))
                self._action(worker, actions, errors, "pause", task["gid"])
                wait_for_status(tasks, task["gid"], {"paused"}, 5)
                self._stop_worker(worker)

                session = paths.aria2_session.read_text(encoding="utf-8")
                self.assertIn("pause=true", session)
                self.assertTrue((save_dir / "recovered.bin.aria2").exists())

                worker, tasks, actions, errors, versions = self._start_worker(paths)
                self.assertTrue(wait_until(lambda: versions or errors, 8), errors)
                self.assertTrue(versions, errors)
                restored = wait_for_file_status(tasks, "recovered.bin", {"paused"}, 8)
                self._action(worker, actions, errors, "resume", restored["gid"])
                wait_for_status(tasks, restored["gid"], {"complete"}, 20)
                offsets = [
                    int(header[6:].split("-", 1)[0])
                    for path, header in server.requests
                    if path == "/recovered.bin" and header and header.startswith("bytes=")
                ]
                self.assertTrue(any(offset > 0 for offset in offsets), f"server saw no nonzero resume offset: {offsets}")
                self.assertEqual(sha256(save_dir / "recovered.bin"), hashlib.sha256(PAYLOAD).hexdigest())
            finally:
                self._stop_worker(worker)
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=2)

    def test_forced_engine_exit_recovers_saved_partial_download(self):
        with tempfile.TemporaryDirectory(prefix="fetchdeck-forced-exit-") as directory:
            root = Path(directory)
            save_dir = root / "downloads"
            save_dir.mkdir()
            paths = AppPaths(root / "app-data")
            server = ThreadingHTTPServer(("127.0.0.1", 0), ControlledHandler)
            server.daemon_threads = True
            server.requests = []
            server.chunk_delay = 0.1
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            worker, tasks, actions, errors, versions = self._start_worker(paths)
            url = f"http://127.0.0.1:{server.server_port}/forced.bin"
            try:
                self.assertTrue(wait_until(lambda: versions or errors, 8), errors)
                self._action(worker, actions, errors, "add", url, save_dir)
                task = wait_for_file_status(tasks, "forced.bin", {"active"}, 8)
                self.assertTrue(wait_until(lambda: (save_dir / "forced.bin.aria2").exists(), 8))
                self.assertTrue(
                    wait_until(lambda: int(find_task(tasks, task["gid"]).get("completedLength", 0)) > 0, 5)
                )
                time.sleep(3.5)
                worker._daemon.process.kill()
                self.assertTrue(worker.wait(8000), "worker did not notice the forced aria2 exit")
                self.assertIn(url, paths.aria2_session.read_text(encoding="utf-8"))
                self.assertTrue((save_dir / "forced.bin.aria2").exists())

                worker, tasks, actions, errors, versions = self._start_worker(paths)
                self.assertTrue(wait_until(lambda: versions or errors, 8), errors)
                restored = wait_for_file_status(tasks, "forced.bin", {"active", "complete"}, 12)
                if restored["status"] != "complete":
                    wait_for_status(tasks, restored["gid"], {"complete"}, 20)
                offsets = [
                    int(header[6:].split("-", 1)[0])
                    for path, header in server.requests
                    if path == "/forced.bin" and header and header.startswith("bytes=")
                ]
                self.assertTrue(any(offset > 0 for offset in offsets), f"server saw no nonzero resume offset: {offsets}")
                self.assertEqual(sha256(save_dir / "forced.bin"), hashlib.sha256(PAYLOAD).hexdigest())
            finally:
                self._stop_worker(worker)
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=2)

    def test_ftp_transfer_resumes_with_server_rest_support(self):
        with tempfile.TemporaryDirectory(prefix="fetchdeck-ftp-") as directory:
            root = Path(directory)
            save_dir = root / "downloads"
            save_dir.mkdir()
            paths = AppPaths(root / "app-data")
            server = FtpTestServer(supports_rest=True)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            worker, tasks, actions, errors, versions = self._start_worker(paths)
            try:
                self.assertTrue(wait_until(lambda: versions or errors, 8), errors)
                url = f"ftp://127.0.0.1:{server.server_address[1]}/payload.bin"
                self._action(worker, actions, errors, "add", url, save_dir)
                task = wait_for_file_status(tasks, "payload.bin", {"active"}, 8)
                self.assertTrue(
                    wait_until(lambda: int(find_task(tasks, task["gid"]).get("completedLength", 0)) > 0, 8),
                    f"FTP transfer did not start: {tasks}; commands: {server.commands}",
                )
                self._action(worker, actions, errors, "pause", task["gid"])
                wait_for_status(tasks, task["gid"], {"paused"}, 5)
                self._action(worker, actions, errors, "resume", task["gid"])
                wait_for_status(tasks, task["gid"], {"complete"}, 20)
                self.assertTrue(any(offset > 0 for offset in server.rest_offsets), server.rest_offsets)
                self.assertEqual(sha256(save_dir / "payload.bin"), hashlib.sha256(PAYLOAD).hexdigest())
            finally:
                self._stop_worker(worker)
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=2)

    def test_ftp_server_without_rest_reports_resume_failure(self):
        with tempfile.TemporaryDirectory(prefix="fetchdeck-ftp-no-rest-") as directory:
            root = Path(directory)
            save_dir = root / "downloads"
            save_dir.mkdir()
            server = FtpTestServer(supports_rest=False)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            worker, tasks, actions, errors, versions = self._start_worker(AppPaths(root / "app-data"))
            try:
                self.assertTrue(wait_until(lambda: versions or errors, 8), errors)
                url = f"ftp://127.0.0.1:{server.server_address[1]}/payload.bin"
                self._action(worker, actions, errors, "add", url, save_dir)
                task = wait_for_file_status(tasks, "payload.bin", {"active"}, 8)
                self.assertTrue(
                    wait_until(lambda: int(find_task(tasks, task["gid"]).get("completedLength", 0)) > 0, 8)
                )
                self._action(worker, actions, errors, "pause", task["gid"])
                wait_for_status(tasks, task["gid"], {"paused"}, 5)
                self._action(worker, actions, errors, "resume", task["gid"])
                failed = wait_for_status(tasks, task["gid"], {"error"}, 10)
                self.assertTrue(failed.get("errorMessage"), f"FTP commands: {server.commands}")
                self.assertIn("may not support the REST command", failed["errorMessage"])
                self.assertTrue(any(command == "REST" for command, _arg in server.commands))
            finally:
                self._stop_worker(worker)
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=2)

    def test_restart_keeps_existing_file_or_replaces_after_explicit_choice(self):
        with tempfile.TemporaryDirectory(prefix="fetchdeck-restart-") as directory:
            root = Path(directory)
            save_dir = root / "downloads"
            save_dir.mkdir()
            paths = AppPaths(root / "app-data")
            server = ThreadingHTTPServer(("127.0.0.1", 0), ControlledHandler)
            server.daemon_threads = True
            server.requests = []
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            worker, tasks, actions, errors, versions = self._start_worker(paths)
            try:
                self.assertTrue(wait_until(lambda: versions or errors, 8), errors)
                url = f"http://127.0.0.1:{server.server_port}/collision.bin"
                self._action(worker, actions, errors, "add", url, save_dir)
                completed = wait_for_file_status(tasks, "collision.bin", {"complete"}, 15)
                original = save_dir / "collision.bin"
                existing_contents = b"keep this existing file"
                original.write_bytes(existing_contents)

                restarted_gid = self._action(worker, actions, errors, "restart", completed["gid"], False)
                self.assertTrue(restarted_gid, "aria2 did not return a GID for the restarted task")
                kept = wait_for_status(tasks, restarted_gid, {"complete"}, 15)
                restarted_file = Path(kept["files"][0]["path"])
                self.assertTrue(wait_until(lambda: restarted_file.is_file() and sha256(restarted_file) == hashlib.sha256(PAYLOAD).hexdigest(), 15))
                self.assertEqual(original.read_bytes(), existing_contents)

                restarted_file.write_bytes(existing_contents)
                replaced_gid = self._action(worker, actions, errors, "restart", kept["gid"], True)
                self.assertTrue(replaced_gid, "aria2 did not return a GID for the overwritten task")
                wait_for_status(tasks, replaced_gid, {"complete"}, 15)
                self.assertTrue(wait_until(lambda: restarted_file.is_file() and sha256(restarted_file) == hashlib.sha256(PAYLOAD).hexdigest(), 15))
            finally:
                self._stop_worker(worker)
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=2)

    def test_pause_all_and_resume_all_control_the_entire_queue(self):
        with tempfile.TemporaryDirectory(prefix="fetchdeck-bulk-") as directory:
            root = Path(directory)
            save_dir = root / "downloads"
            save_dir.mkdir()
            server = ThreadingHTTPServer(("127.0.0.1", 0), ControlledHandler)
            server.daemon_threads = True
            server.requests = []
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            worker, tasks, actions, errors, versions = self._start_worker(AppPaths(root / "app-data"))
            try:
                self.assertTrue(wait_until(lambda: versions or errors, 8), errors)
                base = f"http://127.0.0.1:{server.server_port}"
                self._action(worker, actions, errors, "add", base + "/bulk-a.bin", save_dir)
                self._action(worker, actions, errors, "add", base + "/bulk-b.bin", save_dir)
                wait_for_file_status(tasks, "bulk-a.bin", {"active"}, 8)
                wait_for_file_status(tasks, "bulk-b.bin", {"active", "waiting"}, 8)
                self._action(worker, actions, errors, "pause_all")
                self.assertTrue(wait_until(lambda: all(task["status"] == "paused" for task in tasks), 8), tasks)
                self._action(worker, actions, errors, "resume_all")
                wait_for_file_status(tasks, "bulk-a.bin", {"complete"}, 20)
                wait_for_file_status(tasks, "bulk-b.bin", {"complete"}, 20)
                expected = hashlib.sha256(PAYLOAD).hexdigest()
                self.assertEqual(sha256(save_dir / "bulk-a.bin"), expected)
                self.assertEqual(sha256(save_dir / "bulk-b.bin"), expected)
            finally:
                self._stop_worker(worker)
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=2)

    def _start_worker(self, paths):
        worker = EngineWorker(paths, max_concurrent_downloads=1, connections_per_task=1)
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
        return worker, tasks, actions, errors, versions

    @staticmethod
    def _stop_worker(worker):
        if worker.isRunning():
            worker.requestInterruption()
            worker.wait(8000)

    def _action(self, worker, actions, errors, name, *args):
        action_id = worker.submit(name, *args)
        self.assertTrue(wait_until(lambda: action_id in actions or errors, 6), errors)
        self.assertIn(action_id, actions, errors)
        success, message = actions[action_id]
        self.assertTrue(success, message)
        return message


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


def find_task(tasks, gid):
    return next(task for task in tasks if task.get("gid") == gid)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
