from __future__ import annotations

import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QThread, Signal


TRACKER_LISTS = {
    "best": "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt",
    "all": "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_all.txt",
}
MAX_TRACKER_RESPONSE = 2 * 1024 * 1024
MAX_TRACKERS = 2000


class TrackerError(RuntimeError):
    """A tracker list could not be downloaded, validated, or stored."""


class TrackerListStore:
    def __init__(self, path: Path, timeout: float = 10.0) -> None:
        self.path = path
        self.timeout = timeout

    def read(self) -> list[str]:
        try:
            return parse_tracker_list(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise TrackerError("FetchDeck could not read its saved tracker list.") from exc

    def sync(self, kind: str) -> list[str]:
        try:
            url = TRACKER_LISTS[kind]
        except KeyError as exc:
            raise TrackerError("Choose the best or all community tracker list.") from exc
        return self.sync_url(url)

    def sync_url(self, url: str) -> list[str]:
        request = urllib.request.Request(url, headers={"User-Agent": "FetchDeck/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise TrackerError(f"Tracker source returned HTTP {response.status}.")
                body = response.read(MAX_TRACKER_RESPONSE + 1)
        except TrackerError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TrackerError("Could not sync trackers. The last saved list is still available.") from exc
        if len(body) > MAX_TRACKER_RESPONSE:
            raise TrackerError("Tracker source exceeded the 2 MiB size limit.")
        try:
            trackers = parse_tracker_list(body.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise TrackerError("Tracker source is not valid UTF-8 text.") from exc
        if not trackers:
            raise TrackerError("Tracker source contained no usable tracker URLs.")
        self._write_atomic(trackers)
        return trackers

    def _write_atomic(self, trackers: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", dir=self.path.parent, prefix="trackers-", suffix=".tmp", delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write("\n".join(trackers) + "\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        except OSError as exc:
            raise TrackerError("FetchDeck could not save the updated tracker list.") from exc
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)


def parse_tracker_list(text: str) -> list[str]:
    trackers = []
    seen = set()
    for raw_line in text.splitlines():
        candidate = raw_line.strip()
        if not candidate or candidate.startswith("#") or len(candidate) > 2048 or candidate in seen:
            continue
        try:
            parsed = urlsplit(candidate)
            host = parsed.hostname
            _ = parsed.port
        except ValueError:
            continue
        if (
            parsed.scheme.lower() not in {"udp", "http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
        ):
            continue
        seen.add(candidate)
        trackers.append(candidate)
        if len(trackers) >= MAX_TRACKERS:
            break
    return trackers


class TrackerSyncWorker(QThread):
    completed = Signal(list)
    failed = Signal(str)

    def __init__(self, store: TrackerListStore, kind: str) -> None:
        super().__init__()
        self.store = store
        self.kind = kind

    def run(self) -> None:
        try:
            self.completed.emit(self.store.sync(self.kind))
        except TrackerError as exc:
            self.failed.emit(str(exc))
