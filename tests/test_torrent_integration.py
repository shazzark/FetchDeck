import hashlib
import os
import socket
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from fetchdeck.engine import Aria2Daemon, EngineWorker
from fetchdeck.paths import AppPaths


PAYLOAD = b"FetchDeck lawful controlled torrent fixture\n" * 4096


class TrackerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.announces.append(self.path)
        query = self.path.partition("?")[2]
        port = int(next((part.split("=", 1)[1] for part in query.split("&") if part.startswith("port=")), "0"))
        peers = b"" if port == self.server.seed_port else b"\x7f\x00\x00\x01" + struct.pack("!H", self.server.seed_port)
        self.server.peer_responses.append((port, peers.hex()))
        body = bencode({b"complete": 1, b"incomplete": 0, b"interval": 30, b"peers": peers})
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        pass


def bencode(value):
    if isinstance(value, int):
        return b"i" + str(value).encode("ascii") + b"e"
    if isinstance(value, (bytes, bytearray)):
        return str(len(value)).encode("ascii") + b":" + bytes(value)
    if isinstance(value, str):
        return bencode(value.encode("utf-8"))
    if isinstance(value, list):
        return b"l" + b"".join(bencode(item) for item in value) + b"e"
    if isinstance(value, dict):
        return b"d" + b"".join(bencode(key) + bencode(value[key]) for key in sorted(value)) + b"e"
    raise TypeError(f"Cannot bencode {type(value)!r}")


def make_torrent(data, tracker_url, name):
    piece_length = 16 * 1024
    pieces = b"".join(
        hashlib.sha1(data[offset : offset + piece_length]).digest()
        for offset in range(0, len(data), piece_length)
    )
    info = {
        b"length": len(data),
        b"name": name.encode("utf-8"),
        b"piece length": piece_length,
        b"pieces": pieces,
        b"private": 1,
    }
    encoded_info = bencode(info)
    torrent = bencode({b"announce": tracker_url.encode("ascii"), b"info": info})
    info_hash = hashlib.sha1(encoded_info).hexdigest()
    return torrent, info_hash


def wait_until(predicate, timeout):
    if predicate():
        return True
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(25)
    timer.timeout.connect(lambda: loop.quit() if predicate() else None)
    timer.start()
    QTimer.singleShot(round(timeout * 1000), loop.quit)
    loop.exec()
    timer.stop()
    return predicate()


@unittest.skipUnless(Aria2Daemon._find_binary(), "aria2c.exe is not installed or not on PATH")
class ControlledTorrentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def test_torrent_and_magnet_download_from_known_local_seeder_and_seed(self):
        with tempfile.TemporaryDirectory(prefix="fetchdeck-torrent-") as directory:
            root = Path(directory)
            seed_dir = root / "seed"
            torrent_dir = root / "torrent"
            magnet_dir = root / "magnet"
            for folder in (seed_dir, torrent_dir, magnet_dir):
                folder.mkdir()
            name = "fetchdeck-controlled.bin"
            (seed_dir / name).write_bytes(PAYLOAD)

            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                seed_port = probe.getsockname()[1]
            server = ThreadingHTTPServer(("127.0.0.1", 0), TrackerHandler)
            server.daemon_threads = True
            server.seed_port = seed_port
            server.announces = []
            server.peer_responses = []
            tracker_thread = threading.Thread(target=server.serve_forever, daemon=True)
            tracker_thread.start()
            tracker_url = f"http://127.0.0.1:{server.server_port}/announce"
            torrent_bytes, info_hash = make_torrent(PAYLOAD, tracker_url, name)
            torrent_path = root / "controlled.torrent"
            torrent_path.write_bytes(torrent_bytes)

            seed_process = None
            worker = None
            magnet_worker = None
            try:
                seed_process = subprocess.Popen(
                    [
                        Aria2Daemon._find_binary(),
                        "--no-conf=true",
                        "--enable-rpc=false",
                        "--enable-dht=false",
                        "--enable-peer-exchange=false",
                        "--bt-enable-lpd=false",
                        "--bt-seed-unverified=true",
                        f"--listen-port={seed_port}",
                        "--seed-time=60",
                        "--seed-ratio=0.0",
                        f"--dir={seed_dir}",
                        "--show-console-readout=false",
                        "--summary-interval=0",
                        str(torrent_path),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                self.assertTrue(wait_until(lambda: bool(server.announces) or seed_process.poll() is not None, 8))
                if seed_process.poll() is not None:
                    detail = seed_process.communicate()[0].decode("utf-8", errors="replace")
                    self.fail(f"local aria2 seeder exited during startup: {detail}")
                self.assertTrue(
                    wait_until(lambda: can_connect(seed_port), 5),
                    f"aria2 seeder did not listen on its announced port {seed_port}",
                )

                worker, tasks, actions, errors, versions = start_worker(AppPaths(root / "app-data"))
                self.assertTrue(wait_until(lambda: versions or errors, 8), errors)
                self.assertTrue(versions, errors)
                self.action(worker, actions, errors, "set_trackers", [tracker_url])
                applied = worker._daemon.rpc.call("getGlobalOption").get("bt-tracker", "")
                self.assertIn(tracker_url, applied)

                torrent_action = worker.submit("add_torrent", torrent_path, torrent_dir)
                result = wait_for_action(actions, errors, torrent_action)
                self.assertTrue(result[0], result[1])
                torrent_gid = result[1]
                try:
                    torrent_task = wait_for_seeding(tasks, name, 15, torrent_gid)
                except AssertionError as exc:
                    raise AssertionError(f"{exc}; tracker announces: {server.announces}") from exc
                self.assertEqual(sha256(torrent_dir / name), hashlib.sha256(PAYLOAD).hexdigest())
                self.action(worker, actions, errors, "pause", torrent_gid)
                wait_for_gid_status(tasks, torrent_gid, {"paused"}, 8)
                self.action(worker, actions, errors, "resume", torrent_gid)
                wait_for_seeding(tasks, name, 20, torrent_gid)

                magnet = (
                    f"magnet:?xt=urn:btih:{info_hash}&dn={quote('fetchdeck-magnet.bin')}"
                    f"&tr={quote(tracker_url, safe='')}"
                )
                magnet_worker, magnet_tasks, magnet_actions, magnet_errors, magnet_versions = start_worker(
                    AppPaths(root / "magnet-app-data")
                )
                self.assertTrue(wait_until(lambda: magnet_versions or magnet_errors, 8), magnet_errors)
                self.assertTrue(magnet_versions, magnet_errors)
                self.action(magnet_worker, magnet_actions, magnet_errors, "set_trackers", [tracker_url])
                magnet_action = magnet_worker.submit("add_magnet", magnet, magnet_dir)
                result = wait_for_action(magnet_actions, magnet_errors, magnet_action)
                self.assertTrue(result[0], result[1])
                magnet_gid = result[1]
                try:
                    magnet_task = wait_for_seeding(magnet_tasks, name, 15, magnet_gid)
                except AssertionError as exc:
                    try:
                        peers = magnet_worker._daemon.rpc.call("getPeers", [magnet_gid])
                    except Exception as rpc_error:
                        peers = str(rpc_error)
                    raise AssertionError(
                        f"{exc}; seed port: {seed_port}; tracker announces: {server.announces}; "
                        f"peer responses: {server.peer_responses}; connected peers: {peers}"
                    ) from exc
                self.assertEqual(
                    sha256(magnet_dir / name), hashlib.sha256(PAYLOAD).hexdigest()
                )
                self.assertTrue(server.announces, "the controlled tracker received no announces")
                self.assertIsNone(seed_process.poll(), "the known aria2 seeder exited unexpectedly")
                self.assertTrue(magnet_task.get("seeder") == "true" or magnet_task.get("_fetchdeckStatus") == "Seeding")
            finally:
                if worker:
                    stop_worker(worker)
                if magnet_worker:
                    stop_worker(magnet_worker)
                if seed_process and seed_process.poll() is None:
                    seed_process.terminate()
                    try:
                        seed_process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        seed_process.kill()
                        seed_process.wait(timeout=3)
                if seed_process and seed_process.stdout:
                    seed_process.stdout.close()
                server.shutdown()
                server.server_close()
                tracker_thread.join(timeout=2)

    def action(self, worker, actions, errors, name, *args):
        action_id = worker.submit(name, *args)
        result = wait_for_action(actions, errors, action_id)
        self.assertTrue(result[0], result[1])


def start_worker(paths):
    worker = EngineWorker(paths, max_concurrent_downloads=2, connections_per_task=1)
    tasks = []
    actions = {}
    errors = []
    versions = []
    worker.snapshot.connect(lambda current: tasks.__setitem__(slice(None), current))
    worker.action_finished.connect(lambda action_id, success, message: actions.__setitem__(action_id, (success, message)))
    worker.error.connect(errors.append)
    worker.ready.connect(versions.append)
    worker.start()
    return worker, tasks, actions, errors, versions


def stop_worker(worker):
    if worker.isRunning():
        worker.requestInterruption()
        worker.wait(8000)


def wait_for_action(actions, errors, action_id):
    if not wait_until(lambda: action_id in actions or errors, 8):
        raise AssertionError(f"Action {action_id} did not finish; errors: {errors}")
    if action_id not in actions:
        raise AssertionError(f"Action failed before completion: {errors}")
    return actions[action_id]


def can_connect(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def wait_for_seeding(tasks, name, timeout, gid=None):
    found = {}
    followed_gids = set()

    def is_seeding():
        if gid:
            followed_gids.add(gid)
            parent = next((task for task in tasks if task.get("gid") == gid), None)
            if parent:
                followed_gids.update(parent.get("followedBy") or [])
        for task in tasks:
            if gid and task.get("gid") not in followed_gids:
                continue
            if task.get("_fetchdeckName") == name or any(
                Path(item.get("path", "")).name == name for item in task.get("files", [])
            ):
                if task.get("status") == "active" and task.get("completedLength") == task.get("totalLength"):
                    found.update(task)
                    return True
        return False

    if not wait_until(is_seeding, timeout):
        raise AssertionError(f"{name} did not complete and enter seeding; tasks: {tasks}")
    return found


def wait_for_gid_status(tasks, gid, statuses, timeout):
    found = {}

    def matches():
        for task in tasks:
            if task.get("gid") == gid and task.get("status") in statuses:
                found.update(task)
                return True
        return False

    if not wait_until(matches, timeout):
        raise AssertionError(f"{gid} did not reach {statuses}; tasks: {tasks}")
    return found


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
