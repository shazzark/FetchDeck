from __future__ import annotations

import itertools
import base64
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
from dataclasses import replace
from pathlib import Path
from queue import Empty, Queue
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from PySide6.QtCore import QThread, Signal

from .filesystem import move_to_recycle_bin
from .paths import AppPaths
from .preferences import Preferences
from .statistics import StatisticsStore
from .trackers import TrackerError, TrackerListStore


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
        download_limit_kib: int = 0,
        upload_limit_kib: int = 0,
        user_agent: str = "FetchDeck/0.1",
        resume_on_launch: bool = True,
    ) -> Aria2Daemon:
        if not 1 <= max_concurrent_downloads <= 64:
            raise EngineError("Concurrent download limit must be between 1 and 64.")
        if not 1 <= connections_per_task <= 16:
            raise EngineError("Connections per task must be between 1 and 16.")
        paths.prepare()
        lock = InstanceLock(paths.aria2_lock)
        lock.acquire()
        process: subprocess.Popen[bytes] | None = None
        launch_session: Path | None = None
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
                "--dir=" + str(paths.torrent_metadata),
                f"--input-file={paths.aria2_session}",
                f"--save-session={paths.aria2_session}",
                "--save-session-interval=1",
                "--auto-save-interval=3",
                "--continue=true",
                "--always-resume=true",
                "--enable-dht=true",
                "--enable-peer-exchange=true",
                "--bt-save-metadata=true",
                "--rpc-save-upload-metadata=true",
                "--seed-time=1440",
                "--seed-ratio=1.0",
                "--allow-overwrite=false",
                "--auto-file-renaming=true",
                f"--max-concurrent-downloads={max_concurrent_downloads}",
                f"--split={connections_per_task}",
                f"--max-connection-per-server={connections_per_task}",
                f"--max-overall-download-limit={download_limit_kib}K",
                f"--max-overall-upload-limit={upload_limit_kib}K",
                f"--user-agent={user_agent}",
                "--quiet=true",
            ]
            input_file = paths.aria2_session
            if not resume_on_launch and paths.aria2_session.stat().st_size:
                launch_session = paths.root / "launch-session.txt"
                launch_session.write_text(
                    mark_session_entries_paused(paths.aria2_session.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )
                input_file = launch_session
            args[args.index(f"--input-file={paths.aria2_session}")] = f"--input-file={input_file}"
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
                    if launch_session:
                        launch_session.unlink(missing_ok=True)
                    return cls(process, rpc, lock, version.get("version", "unknown"))
                except EngineError as exc:
                    last_rpc = exc
                    time.sleep(0.1)
            if launch_session:
                launch_session.unlink(missing_ok=True)
            raise EngineError(
                f"aria2 did not become ready on loopback port {port} within {startup_timeout:g}s. "
                "The port may be occupied or aria2 may have failed to start."
            ) from last_rpc
        except Exception:
            if launch_session:
                launch_session.unlink(missing_ok=True)
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
    notice = Signal(str)
    snapshot = Signal(list)
    action_finished = Signal(str, bool, str)

    def __init__(
        self,
        paths: AppPaths,
        preferences: Preferences | None = None,
        max_concurrent_downloads: int | None = None,
        connections_per_task: int | None = None,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.preferences = preferences or Preferences.defaults(paths.default_download_dir)
        if max_concurrent_downloads is not None:
            self.preferences = replace(self.preferences, max_concurrent_downloads=max_concurrent_downloads)
        if connections_per_task is not None:
            self.preferences = replace(self.preferences, connections_per_task=connections_per_task)
        self._actions: Queue[tuple[str, str, tuple[Any, ...]]] = Queue()
        self._ftp_resume_attempts: set[str] = set()
        self._task_destinations: dict[str, tuple[Path, str]] = {}
        self._task_sources: dict[str, str] = {}
        self._daemon: Aria2Daemon | None = None
        self.statistics = StatisticsStore(paths.activity)
        self._fresh_gids: set[str] = set()

    def submit(self, name: str, *args: Any) -> str:
        action_id = uuid.uuid4().hex
        self._actions.put((action_id, name, args))
        return action_id

    def run(self) -> None:
        try:
            session = self.paths.aria2_session.read_text(encoding="utf-8")
        except OSError:
            session = ""
        for gid, (uri, folder, out) in parse_session_entries(session).items():
            self._task_sources[gid] = uri
            self._task_destinations[gid] = (folder, out)
        try:
            self._daemon = Aria2Daemon.start(
                self.paths,
                max_concurrent_downloads=self.preferences.max_concurrent_downloads,
                connections_per_task=self.preferences.connections_per_task,
                download_limit_kib=self.preferences.download_limit_kib,
                upload_limit_kib=self.preferences.upload_limit_kib,
                user_agent=self.preferences.user_agent,
                resume_on_launch=self.preferences.resume_on_launch,
            )
        except EngineError as exc:
            self.error.emit(str(exc))
            return
        except OSError:
            self.error.emit("FetchDeck could not start aria2. Check the aria2 installation and permissions.")
            return

        self.ready.emit(self._daemon.version)
        try:
            trackers = TrackerListStore(self.paths.trackers).read()
            if trackers:
                self._daemon.rpc.call("changeGlobalOption", [{"bt-tracker": ",".join(trackers)}])
        except (EngineError, TrackerError) as exc:
            self.notice.emit(f"The saved tracker list could not be applied: {exc}")
        next_poll = 0.0
        last_error = ""
        try:
            while not self.isInterruptionRequested():
                try:
                    action_id, name, args = self._actions.get(timeout=0.1)
                    try:
                        result = self._run_action(name, args)
                        self.action_finished.emit(action_id, True, result or "")
                    except EngineError as exc:
                        self.action_finished.emit(action_id, False, str(exc))
                    except OSError:
                        self.action_finished.emit(action_id, False, "Windows could not complete the requested file operation.")
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

    def _run_action(self, name: str, args: tuple[Any, ...]) -> str | None:
        assert self._daemon is not None
        rpc = self._daemon.rpc
        if name == "add":
            url, folder = args
            gid = str(rpc.call("addUri", [[url], {"dir": str(folder)}]))
            self._task_destinations[gid] = (Path(folder), output_name_for_uri(url))
            self._task_sources[gid] = url
            self._fresh_gids.add(gid)
            return gid
        elif name == "add_magnet":
            magnet, folder = args
            if not is_magnet_uri(magnet):
                raise EngineError("Enter a valid BitTorrent magnet link with an info hash.")
            gid = str(rpc.call("addUri", [[magnet], {"dir": str(folder)}]))
            self._task_destinations[gid] = (Path(folder), output_name_for_uri(magnet))
            self._task_sources[gid] = magnet
            self._fresh_gids.add(gid)
            return gid
        elif name == "add_torrent":
            torrent_path, folder = args
            try:
                torrent_bytes = Path(torrent_path).read_bytes()
            except OSError as exc:
                raise EngineError("FetchDeck could not read the selected .torrent file.") from exc
            if not torrent_bytes or len(torrent_bytes) > 16 * 1024 * 1024:
                raise EngineError("Choose a non-empty .torrent file smaller than 16 MiB.")
            gid = str(rpc.call("addTorrent", [base64.b64encode(torrent_bytes).decode("ascii"), [], {"dir": str(folder)}]))
            self._task_destinations[gid] = (Path(folder), "")
            self._fresh_gids.add(gid)
            return gid
        elif name == "pause":
            try:
                rpc.call("pause", [args[0]])
            except EngineError:
                rpc.call("forcePause", [args[0]])
        elif name == "resume":
            task = rpc.call("tellStatus", [args[0], ["files"]])
            files = task.get("files") or []
            uris = files[0].get("uris") or [] if files else []
            if any(entry.get("uri", "").lower().startswith("ftp:") for entry in uris):
                self._ftp_resume_attempts.add(args[0])
            rpc.call("unpause", [args[0]])
        elif name == "remove":
            gid, status = args
            if status in {"active", "waiting", "paused"}:
                try:
                    rpc.call("remove", [gid])
                except EngineError:
                    rpc.call("forceRemove", [gid])
            rpc.call("removeDownloadResult", [gid])
            self._task_destinations.pop(gid, None)
            self._task_sources.pop(gid, None)
        elif name == "pause_all":
            rpc.call("pauseAll")
        elif name == "resume_all":
            rpc.call("unpauseAll")
        elif name == "set_trackers":
            trackers = args[0]
            if not isinstance(trackers, list) or not trackers:
                raise EngineError("Sync a usable tracker list before applying it.")
            rpc.call("changeGlobalOption", [{"bt-tracker": ",".join(trackers)}])
        elif name == "update_runtime_settings":
            preferences = args[0]
            if not isinstance(preferences, Preferences):
                raise EngineError("Invalid FetchDeck settings.")
            rpc.call("changeGlobalOption", [{
                "max-overall-download-limit": f"{preferences.download_limit_kib}K",
                "max-overall-upload-limit": f"{preferences.upload_limit_kib}K",
                "user-agent": preferences.user_agent,
            }])
        elif name == "restart":
            gid, overwrite = args
            task = rpc.call("tellStatus", [gid, ["files"]])
            files = task.get("files") or []
            if not files:
                raise EngineError("aria2 did not provide a file path for this task.")
            file_info = files[0]
            uris = file_info.get("uris") or []
            uri = next((entry.get("uri") for entry in uris if entry.get("uri")), None)
            uri = uri or self._task_sources.get(gid)
            if not uri:
                raise EngineError("This task does not have a restartable source URL.")
            parsed = urlsplit(uri)
            if parsed.scheme.lower() not in {"http", "https", "ftp"} or not parsed.hostname:
                raise EngineError("This task type cannot be restarted from the Downloads screen.")
            saved_path = Path(file_info.get("path") or "")
            saved_folder, saved_out = self._task_destinations.get(gid, (self.paths.default_download_dir, ""))
            out = saved_path.name or saved_out or unquote(Path(parsed.path).name)
            if not out:
                raise EngineError("aria2 could not determine the output filename for this task.")
            folder = saved_path.parent if saved_path.name else saved_folder
            if not overwrite:
                out = available_output_name(folder, out)
            rpc.call("removeDownloadResult", [gid])
            new_gid = rpc.call(
                "addUri",
                [[uri], {
                    "dir": str(folder),
                    "out": out,
                    "allow-overwrite": "true" if overwrite else "false",
                    "auto-file-renaming": "true",
                    "remove-control-file": "true" if overwrite else "false",
                    "always-resume": "true",
                }],
            )
            self._task_destinations[str(new_gid)] = (folder, out)
            self._task_sources[str(new_gid)] = uri
            self._fresh_gids.add(str(new_gid))
            self._task_destinations.pop(gid, None)
            self._task_sources.pop(gid, None)
            return str(new_gid)
        elif name == "recycle":
            gid, status = args
            task = rpc.call("tellStatus", [gid, ["files"]])
            files = task.get("files") or []
            path = Path(files[0].get("path", "")) if files else None
            if status in {"active", "waiting", "paused"}:
                try:
                    rpc.call("remove", [gid])
                except EngineError:
                    rpc.call("forceRemove", [gid])
            rpc.call("removeDownloadResult", [gid])
            self._task_destinations.pop(gid, None)
            self._task_sources.pop(gid, None)
            if path is None or not path.is_file():
                raise EngineError("The task was removed, but its downloaded file was not found.")
            related = [path, Path(f"{path}.aria2")]
            move_to_recycle_bin([candidate for candidate in related if candidate.exists()])
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
            "uploadLength",
            "downloadSpeed",
            "uploadSpeed",
            "seeder",
            "numSeeders",
            "numPeers",
            "infoHash",
            "followedBy",
            "errorCode",
            "errorMessage",
            "files",
        ]
        tasks: list[dict[str, Any]] = []
        tasks.extend(rpc.call("tellActive", [keys]))
        tasks.extend(rpc.call("tellWaiting", [0, 1000, keys]))
        tasks.extend(rpc.call("tellStopped", [0, 1000, keys]))
        self.statistics.observe(tasks, fresh_gids=self._fresh_gids)
        self._fresh_gids.difference_update(str(task.get("gid", "")) for task in tasks)
        for task in tasks:
            files = task.get("files") or []
            path = files[0].get("path", "") if files else ""
            if path:
                target = Path(path)
                self._task_destinations[task.get("gid", "")] = (target.parent, target.name)
                task["_fetchdeckPath"] = str(target)
                task["_fetchdeckName"] = target.name
            else:
                gid = task.get("gid", "")
                folder, output = self._task_destinations.get(gid, (Path(), ""))
                if not output and gid in self._task_sources:
                    output = output_name_for_uri(self._task_sources[gid])
                if output:
                    task["_fetchdeckPath"] = str(folder / output)
                    task["_fetchdeckName"] = output
            uris = files[0].get("uris") or [] if files else []
            source = next((entry.get("uri") for entry in uris if entry.get("uri")), None)
            if source:
                self._task_sources[task.get("gid", "")] = source
            source = source or self._task_sources.get(task.get("gid", ""), "")
            if source.lower().startswith("magnet:"):
                task["_fetchdeckType"] = "magnet"
                if task.get("status") == "active" and int(task.get("totalLength", 0) or 0) == 0:
                    task["_fetchdeckStatus"] = "Fetching metadata"
            if task.get("seeder") == "true" and task.get("status") == "active":
                task["_fetchdeckStatus"] = "Seeding"
            if task.get("gid") in self._ftp_resume_attempts and task.get("status") == "error":
                task["errorMessage"] = (
                    "The FTP server could not resume this partial download. "
                    "It may not support the REST command required for resume."
                )
            if task.get("status") in {"complete", "removed"}:
                self._ftp_resume_attempts.discard(task.get("gid", ""))
        return tasks


def available_output_name(folder: Path, filename: str) -> str:
    """Choose a destination not already present when restart keeps both files."""
    candidate = Path(filename)
    if not (folder / candidate.name).exists():
        return candidate.name
    for index in range(1, 10_000):
        name = f"{candidate.stem}.{index}{candidate.suffix}"
        if not (folder / name).exists():
            return name
    raise EngineError("No unused filename is available for the restarted download.")


def output_name_for_uri(uri: str) -> str:
    parsed = urlsplit(uri)
    if parsed.scheme.lower() == "magnet":
        name = next((value for key, value in parse_qsl(parsed.query) if key == "dn"), "")
        return unquote(name) or "BitTorrent download"
    return unquote(Path(parsed.path).name) or parsed.hostname or "Download"


def is_magnet_uri(uri: str) -> bool:
    try:
        parsed = urlsplit(uri.strip())
        return parsed.scheme.lower() == "magnet" and any(
            key == "xt" and value.lower().startswith(("urn:btih:", "urn:btmh:"))
            for key, value in parse_qsl(parsed.query)
        )
    except ValueError:
        return False


def parse_session_entries(session_text: str) -> dict[str, tuple[str, Path, str]]:
    """Read source and destination metadata from aria2's own session format."""
    entries: dict[str, tuple[str, Path, str]] = {}
    options: dict[str, str] = {}
    uri = ""

    def save_entry() -> None:
        gid = options.get("gid")
        folder = options.get("dir")
        if gid and folder:
            entries[gid] = (uri, Path(folder), options.get("out") or output_name_for_uri(uri))

    for line in session_text.splitlines():
        if not line:
            save_entry()
            options = {}
            uri = ""
        elif line[0].isspace():
            key, separator, value = line.strip().partition("=")
            if separator and key in {"gid", "dir", "out"}:
                options[key] = value
        elif not line.startswith("#"):
            save_entry()
            options = {}
            uri = line.split("\t", 1)[0]
    save_entry()
    return entries


def mark_session_entries_paused(session_text: str) -> str:
    """Pause restored jobs in a temporary aria2 input file without changing saved session state."""
    output = []
    for entry in session_text.split("\n\n"):
        lines = entry.splitlines()
        if lines and not lines[0].startswith("#") and not any(
            line.strip().startswith("pause=") for line in lines[1:]
        ):
            lines.append(" pause=true")
        output.append("\n".join(lines))
    return "\n\n".join(output)
