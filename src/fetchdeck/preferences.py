from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Preferences:
    default_folder: str
    max_concurrent_downloads: int = 5
    connections_per_task: int = 4
    download_limit_kib: int = 0
    upload_limit_kib: int = 0
    user_agent: str = "FetchDeck/0.1"
    theme: str = "System"
    notify_complete: bool = True
    notify_failure: bool = True
    resume_on_launch: bool = True
    warn_on_quit: bool = True

    @classmethod
    def defaults(cls, folder: Path) -> Preferences:
        return cls(default_folder=str(folder))


class PreferencesStore:
    def __init__(self, path: Path, default_folder: Path) -> None:
        self.path = path
        self.default_folder = default_folder

    def load(self) -> Preferences:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Preferences.defaults(self.default_folder)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("FetchDeck could not read its saved settings.") from exc
        if not isinstance(value, dict):
            raise ValueError("FetchDeck settings must be a JSON object.")
        defaults = asdict(Preferences.defaults(self.default_folder))
        defaults.update({key: value[key] for key in defaults.keys() & value.keys()})
        try:
            return validate_preferences(Preferences(**defaults))
        except (TypeError, ValueError) as exc:
            raise ValueError("FetchDeck settings contain an invalid value.") from exc

    def save(self, preferences: Preferences) -> None:
        checked = validate_preferences(preferences)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", dir=self.path.parent,
                prefix="preferences-", suffix=".tmp", delete=False,
            ) as temp:
                temp_path = Path(temp.name)
                json.dump(asdict(checked), temp, indent=2)
                temp.write("\n")
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_path, self.path)
        except OSError as exc:
            raise ValueError("FetchDeck could not save its settings.") from exc
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def validate_preferences(value: Preferences) -> Preferences:
    if not value.default_folder.strip():
        raise ValueError("Choose a default download folder.")
    if any(type(number) is not int for number in (
        value.max_concurrent_downloads, value.connections_per_task,
        value.download_limit_kib, value.upload_limit_kib,
    )):
        raise ValueError("Download limits and connection counts must be whole numbers.")
    if not 1 <= value.max_concurrent_downloads <= 64:
        raise ValueError("Concurrent downloads must be between 1 and 64.")
    if not 1 <= value.connections_per_task <= 16:
        raise ValueError("Connections per task must be between 1 and 16.")
    if not 0 <= value.download_limit_kib <= 10_000_000:
        raise ValueError("Download limit must be 0 or more.")
    if not 0 <= value.upload_limit_kib <= 10_000_000:
        raise ValueError("Upload limit must be 0 or more.")
    if (
        not value.user_agent.strip()
        or len(value.user_agent) > 256
        or any(ord(character) < 32 or ord(character) == 127 for character in value.user_agent)
    ):
        raise ValueError("User-Agent must contain 1 to 256 characters.")
    if value.theme not in {"System", "Light", "Dark"}:
        raise ValueError("Choose System, Light, or Dark theme.")
    if any(type(flag) is not bool for flag in (
        value.notify_complete, value.notify_failure, value.resume_on_launch, value.warn_on_quit
    )):
        raise ValueError("Notification and launch preferences must be true or false.")
    return value
