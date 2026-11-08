from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from typing import Any


class StatisticsStore:
    """Persist only public dashboard counters, with per-task transfer checkpoints."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {"version": 1, "days": {}, "tasks": {}}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("version") == 1:
                self._data = {"version": 1, "days": value.get("days", {}), "tasks": value.get("tasks", {})}
        except (OSError, ValueError, AttributeError):
            pass

    def observe(self, tasks: list[dict[str, Any]], *, fresh_gids: set[str] | None = None) -> None:
        today = date.today().isoformat()
        fresh_gids = fresh_gids or set()
        with self._lock:
            totals = self._data["days"].setdefault(today, {"download": 0, "upload": 0})
            checkpoints = self._data["tasks"]
            for task in tasks:
                gid = str(task.get("gid", ""))
                if not gid:
                    continue
                current = {
                    "download": max(0, int(task.get("completedLength", 0) or 0)),
                    "upload": max(0, int(task.get("uploadLength", 0) or 0)),
                }
                previous = checkpoints.get(gid)
                if previous is None:
                    previous = {"download": 0, "upload": 0} if gid in fresh_gids else current
                for direction in ("download", "upload"):
                    totals[direction] += max(0, current[direction] - int(previous.get(direction, 0)))
                checkpoints[gid] = current
            self._write_locked()

    def snapshot(self, *, engine_status: str, engine_version: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        active = [task for task in tasks if task.get("status") == "active"]
        queued = [task for task in tasks if task.get("status") == "waiting"]
        with self._lock:
            today = dict(self._data["days"].get(date.today().isoformat(), {"download": 0, "upload": 0}))
            days = [{"date": day, **dict(values)} for day, values in sorted(self._data["days"].items())]
        return {
            "version": 1,
            "engine": {"status": engine_status, "version": engine_version},
            "counts": {"active": len(active), "queued": len(queued)},
            "rates": {
                "download": sum(max(0, int(task.get("downloadSpeed", 0) or 0)) for task in active),
                "upload": sum(max(0, int(task.get("uploadSpeed", 0) or 0)) for task in active),
            },
            "today": today,
            "days": days,
        }

    def _write_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._data, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self.path)
