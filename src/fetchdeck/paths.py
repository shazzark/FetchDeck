from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @classmethod
    def current_user(cls) -> AppPaths:
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = Path(local_app_data) / "FetchDeck" if local_app_data else Path.home() / ".fetchdeck"
        return cls(root=root)

    @property
    def preferences(self) -> Path:
        return self.root / "preferences.json"

    @property
    def activity(self) -> Path:
        return self.root / "activity.json"

    @property
    def aria2_session(self) -> Path:
        return self.root / "aria2.session"

    @property
    def aria2_lock(self) -> Path:
        return self.root / "aria2.lock"

    @property
    def trackers(self) -> Path:
        return self.root / "trackers.txt"

    @property
    def torrent_metadata(self) -> Path:
        return self.root / "torrent-metadata"

    @property
    def default_download_dir(self) -> Path:
        downloads = Path.home() / "Downloads"
        return downloads if downloads.is_dir() else Path.home()

    def prepare(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.torrent_metadata.mkdir(parents=True, exist_ok=True)
