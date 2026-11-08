from __future__ import annotations

import itertools
import json
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from PySide6.QtCore import QThread, Signal

from .paths import AppPaths


class EngineError(RuntimeError):
    """An aria2 startup or JSON-RPC failure safe to show in the UI."""


class InstanceLock:
    """Hold an OS lock for the full lifetime of the shared aria2 session."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: Any = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+b")
        self._file.seek(0)
        if self.path.stat().st_size == 0:
            self._file.write(b"\0")
            self._file.flush()
        self._file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._file.close()
            self._file = None
            raise EngineError("Another FetchDeck instance is using the download session.") from exc

    def release(self) -> None:
        if self._file is None:
            return
        try:
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None


class Aria2Rpc:
    def __init__(self, port: int, secret: str, timeout: float = 2.0) -> None:
        self.endpoint = f"http://127.0.0.1:{port}/jsonrpc"
        self.secret = secret
        self.timeout = timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._ids = itertools.count(1)
        self._id_lock = threading.Lock()

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        with self._id_lock:
            request_id = next(self._ids)
        body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": f"aria2.{method}",
            "params": [f"token:{self.secret}", *(params or [])],
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise EngineError(f"aria2 RPC returned HTTP {exc.code}.") from None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeDecodeError):
            raise EngineError("aria2 RPC is unavailable or did not answer in time.") from None

        if not isinstance(payload, dict) or payload.get("id") != request_id:
            raise EngineError("aria2 returned an invalid JSON-RPC response.")
        if payload.get("error"):
            error = payload["error"]
            message = (
                error.get("message", "aria2 returned an unknown error")
                if isinstance(error, dict)
                else "aria2 returned an unknown error"
            )
            raise EngineError(f"aria2: {message}")
        if "result" not in payload:
            raise EngineError("aria2 returned an invalid JSON-RPC response.")
        return payload["result"]


class Aria2Daemon:
    def __init__(
        self,
        process: subprocess.Popen[bytes],
        rpc: Aria2Rpc,
        lock: InstanceLock,
        version: str,
    ) -> None:
        self.process = process
        self.rpc = rpc
        self.lock = lock
        self.version = version

    @staticmethod
    def _find_binary() -> str:
        binary = "aria2c.exe" if os.name == "nt" else "aria2c"
        found = shutil.which(binary)
        if found:
            return found
        candidates = (
            [r"C:\Program Files\aria2\aria2c.exe", r"C:\ProgramData\chocolatey\bin\aria2c.exe"]
            if os.name == "nt"
            else ["/opt/homebrew/bin/aria2c", "/usr/local/bin/aria2c", "/usr/bin/aria2c"]
        )
        found = next((path for path in candidates if Path(path).is_file()), "")
        if found or os.name != "nt":
            return found

        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            return ""
        winget = Path(local_app_data) / "Microsoft" / "WinGet"
        for candidate in (winget / "Links" / binary,):
            if candidate.is_file():
                return str(candidate)
        packages = winget / "Packages"
        for package in packages.glob("aria2.aria2_*"):
            matches = package.glob("aria2-*-win-64bit-build*/aria2c.exe")
            binary_path = next(matches, None)
            if binary_path is not None and binary_path.is_file():
                return str(binary_path)
        return ""

    @staticmethod
    def _free_loopback_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])

    @classmethod
    def start(
        cls,
        paths: AppPaths,
        startup_timeout: float = 8.0,
        max_concurrent_downloads: int = 5,
        connections_per_task: int = 4,
    ) -> Aria2Daemon:
        if not 1 <= max_concurrent_downloads <= 64:
            raise EngineError("Concurrent download limit must be between 1 and 64.")
        if not 1 <= connections_per_task <= 16:
            raise EngineError("Connections per task must be between 1 and 16.")
        paths.prepare()
        lock = InstanceLock(paths.aria2_lock)
        lock.acquire()
        process: subprocess.Popen[bytes] | None = None
        try:
            paths.aria2_session.touch(exist_ok=True)
            binary = cls._find_binary()
            if not binary:
                raise EngineError("aria2c was not found. Install aria2 and add it to PATH.")
            port = cls._free_loopback_port()
            secret = secrets.token_urlsafe(32)
            args = [
                binary,
                "--no-conf=true",
                "--enable-rpc=true",
                f"--rpc-listen-port={port}",
                "--rpc-listen-all=false",
                f"--rpc-secret={secret}",
                "--dir=" + str(paths.default_download_dir),
                f"--input-file={paths.aria2_session}",
                f"--save-session={paths.aria2_session}",
                "--save-session-interval=15",
                "--continue=true",
                "--allow-overwrite=false",
                "--auto-file-renaming=true",
                f"--max-concurrent-downloads={max_concurrent_downloads}",
                f"--split={connections_per_task}",
                f"--max-connection-per-server={connections_per_task}",
                "--quiet=true",
            ]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            rpc = Aria2Rpc(port, secret, timeout=0.75)
            deadline = time.monotonic() + startup_timeout
            last_rpc: EngineError | None = None
            while time.monotonic() < deadline:
                exit_code = process.poll()
                if exit_code is not None:
                    raise EngineError(f"aria2 exited during startup (code {exit_code}).")
                try:
                    version = rpc.call("getVersion")
                    rpc.timeout = 2.0
                    return cls(process, rpc, lock, version.get("version", "unknown"))
                except EngineError as exc:
                    last_rpc = exc
                    time.sleep(0.1)
            raise EngineError(
                f"aria2 did not become ready on loopback port {port} within {startup_timeout:g}s. "
                "The port may be occupied or aria2 may have failed to start."
            ) from last_rpc
        except Exception:
            try:
                if process is not None and process.poll() is None:
                    try:
                        process.terminate()
                    except OSError:
                        pass
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            finally:
                lock.release()
            raise

    def stop(self) -> None:
        try:
            if self.process.poll() is None:
                try:
                    self.rpc.call("saveSession")
                    self.rpc.call("shutdown")
                except EngineError:
                    pass
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=2)
        finally:
            self.lock.release()


class EngineWorker(QThread):
    ready = Signal(str)
    error = Signal(str)
    snapshot = Signal(list)
    action_finished = Signal(str, bool, str)

    def __init__(
        self,
        paths: AppPaths,
        max_concurrent_downloads: int = 5,
        connections_per_task: int = 4,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.max_concurrent_downloads = max_concurrent_downloads
        self.connections_per_task = connections_per_task
        self._actions: Queue[tuple[str, str, tuple[Any, ...]]] = Queue()
        self._daemon: Aria2Daemon | None = None

    def submit(self, name: str, *args: Any) -> str:
        action_id = uuid.uuid4().hex
        self._actions.put((action_id, name, args))
        return action_id

    def run(self) -> None:
        try:
            self._daemon = Aria2Daemon.start(
                self.paths,
                max_concurrent_downloads=self.max_concurrent_downloads,
                connections_per_task=self.connections_per_task,
            )
        except EngineError as exc:
            self.error.emit(str(exc))
            return
        except OSError:
            self.error.emit("FetchDeck could not start aria2. Check the aria2 installation and permissions.")
            return

        self.ready.emit(self._daemon.version)
        next_poll = 0.0
        last_error = ""
        try:
            while not self.isInterruptionRequested():
                try:
                    action_id, name, args = self._actions.get(timeout=0.1)
                    try:
                        self._run_action(name, args)
                        self.action_finished.emit(action_id, True, "")
                    except EngineError as exc:
                        self.action_finished.emit(action_id, False, str(exc))
                except Empty:
                    pass

                if self._daemon.process.poll() is not None:
                    self.error.emit("aria2 exited unexpectedly. Restart FetchDeck after checking the installation.")
                    break
                if time.monotonic() >= next_poll:
                    try:
                        self.snapshot.emit(self._fetch_tasks())
                        if last_error:
                            self.ready.emit(self._daemon.version)
                            last_error = ""
                    except EngineError as exc:
                        if str(exc) != last_error:
                            self.error.emit(str(exc))
                            last_error = str(exc)
                    next_poll = time.monotonic() + 1.0
        finally:
            self._daemon.stop()
            self._daemon = None

    def _run_action(self, name: str, args: tuple[Any, ...]) -> None:
        assert self._daemon is not None
        rpc = self._daemon.rpc
        if name == "add":
            url, folder = args
            rpc.call("addUri", [[url], {"dir": str(folder)}])
        elif name == "pause":
            try:
                rpc.call("pause", [args[0]])
            except EngineError:
                rpc.call("forcePause", [args[0]])
        elif name == "resume":
            rpc.call("unpause", [args[0]])
        elif name == "remove":
            gid, status = args
            if status in {"active", "waiting", "paused"}:
                try:
                    rpc.call("remove", [gid])
                except EngineError:
                    rpc.call("forceRemove", [gid])
            rpc.call("removeDownloadResult", [gid])
        else:
            raise EngineError("Unknown download action.")

    def _fetch_tasks(self) -> list[dict[str, Any]]:
        assert self._daemon is not None
        rpc = self._daemon.rpc
        keys = [
            "gid",
            "status",
            "totalLength",
            "completedLength",
            "downloadSpeed",
            "errorCode",
            "errorMessage",
            "files",
        ]
        tasks: list[dict[str, Any]] = []
        tasks.extend(rpc.call("tellActive", [keys]))
        tasks.extend(rpc.call("tellWaiting", [0, 1000, keys]))
        tasks.extend(rpc.call("tellStopped", [0, 1000, keys]))
        return tasks
