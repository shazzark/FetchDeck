from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class NotificationStore:
    def __init__(self, path: Path, limit: int = 100) -> None:
        self.path = path
        self.limit = limit

    def load(self) -> list[dict[str, str]]:
        try:
            events = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("FetchDeck could not read its notification history.") from exc
        if not isinstance(events, list):
            raise ValueError("FetchDeck notification history must be a list.")
        return [event for event in events if valid_event(event)][-self.limit:]

    def append(self, kind: str, title: str, detail: str) -> dict[str, str]:
        event = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "title": title[:160],
            "detail": detail[:300],
        }
        events = self.load()
        events.append(event)
        self._write(events[-self.limit:])
        return event

    def _write(self, events: list[dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", dir=self.path.parent,
                prefix="notifications-", suffix=".tmp", delete=False,
            ) as temp:
                temp_path = Path(temp.name)
                json.dump(events, temp, indent=2)
                temp.write("\n")
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_path, self.path)
        except OSError as exc:
            raise ValueError("FetchDeck could not save its notification history.") from exc
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def valid_event(event: Any) -> bool:
    return isinstance(event, dict) and all(
        isinstance(event.get(key), str) for key in ("time", "kind", "title", "detail")
    )
