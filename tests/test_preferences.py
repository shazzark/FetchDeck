import tempfile
import unittest
from pathlib import Path

from fetchdeck.engine import mark_session_entries_paused
from fetchdeck.preferences import Preferences, PreferencesStore, validate_preferences


class PreferencesTests(unittest.TestCase):
    def test_preferences_round_trip_and_invalid_values_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="fetchdeck-preferences-") as directory:
            root = Path(directory)
            store = PreferencesStore(root / "preferences.json", root)
            defaults = store.load()
            self.assertEqual(defaults.max_concurrent_downloads, 5)
            changed = Preferences(
                default_folder=str(root),
                max_concurrent_downloads=8,
                connections_per_task=6,
                download_limit_kib=1200,
                upload_limit_kib=300,
                user_agent="FetchDeck test/1",
                theme="Dark",
                notify_complete=False,
                notify_failure=True,
                resume_on_launch=False,
                warn_on_quit=False,
            )
            store.save(changed)
            self.assertEqual(store.load(), changed)
            with self.assertRaises(ValueError):
                validate_preferences(Preferences(default_folder=str(root), theme="Neon"))

    def test_resume_disabled_marks_only_temporary_session_entries_paused(self):
        source = "https://example.test/file.bin\n  gid=abc\n  dir=C:/Downloads\n\nhttps://example.test/paused.bin\n  gid=def\n  pause=true\n"
        result = mark_session_entries_paused(source)
        self.assertIn("  gid=abc\n  dir=C:/Downloads\n pause=true", result)
        self.assertEqual(result.count("pause=true"), 2)


if __name__ == "__main__":
    unittest.main()
