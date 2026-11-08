import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QItemSelectionModel, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox

from fetchdeck.app import FetchDeckWindow
from fetchdeck.engine import EngineError
from fetchdeck.preferences import Preferences


class EngineUnavailableUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def test_startup_error_is_visible_and_add_is_disabled(self):
        previous_app_data = os.environ.get("LOCALAPPDATA")
        with tempfile.TemporaryDirectory(prefix="fetchdeck-ui-") as app_data:
            os.environ["LOCALAPPDATA"] = app_data
            try:
                with patch(
                    "fetchdeck.engine.Aria2Daemon.start",
                    side_effect=EngineError("aria2c was not found"),
                ):
                    window = FetchDeckWindow()
                loop = QEventLoop()
                timer = QTimer()
                timer.setInterval(10)
                timer.timeout.connect(
                    lambda: loop.quit()
                    if window.engine_status.text().startswith("Engine unavailable:")
                    else None
                )
                timer.start()
                QTimer.singleShot(1000, loop.quit)
                loop.exec()
                timer.stop()
                self.assertIn("aria2c was not found", window.engine_status.text())
                self.assertFalse(window.add_button.isEnabled())
                window.close()
                self.app.processEvents()
            finally:
                if previous_app_data is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = previous_app_data

    def test_multiselection_survives_a_polling_snapshot_and_filters_apply(self):
        previous_app_data = os.environ.get("LOCALAPPDATA")
        with tempfile.TemporaryDirectory(prefix="fetchdeck-ui-selection-") as app_data:
            os.environ["LOCALAPPDATA"] = app_data
            try:
                with patch("fetchdeck.engine.Aria2Daemon.start", side_effect=EngineError("test engine unavailable")):
                    window = FetchDeckWindow()
                window.worker.wait(1000)
                tasks = [
                    {"gid": "a", "status": "waiting", "files": [{"path": "C:/downloads/alpha.zip"}]},
                    {"gid": "b", "status": "paused", "files": [{"path": "C:/downloads/beta.zip"}]},
                ]
                window._show_snapshot(tasks)
                selection = window.table.selectionModel()
                for row in (0, 1):
                    selection.select(
                        window.table.model().index(row, 0),
                        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
                    )
                window._show_snapshot(tasks)
                self.assertEqual({gid for gid, _status, _path in window._selected_tasks()}, {"a", "b"})
                window.status_filter.setCurrentText("Paused")
                self.assertTrue(window.table.isRowHidden(0))
                self.assertFalse(window.table.isRowHidden(1))
                window.preferences = replace(window.preferences, warn_on_quit=False)
                window.close()
                self.app.processEvents()
            finally:
                if previous_app_data is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = previous_app_data

    def test_completed_status_transition_is_added_to_feed_once(self):
        previous_app_data = os.environ.get("LOCALAPPDATA")
        with tempfile.TemporaryDirectory(prefix="fetchdeck-ui-events-") as app_data:
            os.environ["LOCALAPPDATA"] = app_data
            try:
                with patch("fetchdeck.engine.Aria2Daemon.start", side_effect=EngineError("test engine unavailable")):
                    window = FetchDeckWindow()
                window.worker.wait(1000)
                active = {"gid": "task-1", "status": "active", "files": [{"path": "C:/downloads/sample.zip"}]}
                complete = {**active, "status": "complete", "completedLength": "42", "totalLength": "42"}
                window._show_snapshot([active])
                window._show_snapshot([complete])
                window._show_snapshot([complete])
                self.assertEqual(window.notification_feed.count(), 1)
                self.assertEqual(len(window.notification_store.load()), 1)
                window.close()
                self.app.processEvents()
            finally:
                if previous_app_data is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = previous_app_data

    def test_settings_screen_saves_preferences_and_marks_restart_fields(self):
        previous_app_data = os.environ.get("LOCALAPPDATA")
        with tempfile.TemporaryDirectory(prefix="fetchdeck-ui-settings-") as app_data:
            os.environ["LOCALAPPDATA"] = app_data
            try:
                target = Path(app_data) / "downloads"
                target.mkdir()
                with patch("fetchdeck.engine.Aria2Daemon.start", side_effect=EngineError("test engine unavailable")):
                    window = FetchDeckWindow()
                window.worker.wait(1000)
                window.folder_setting.setText(str(target))
                window.concurrent_setting.setValue(7)
                window.download_limit_setting.setValue(512)
                window.theme_setting.setCurrentText("Dark")
                window._save_settings()
                saved = window.preferences_store.load()
                self.assertEqual(saved.default_folder, str(target))
                self.assertEqual(saved.max_concurrent_downloads, 7)
                self.assertEqual(saved.download_limit_kib, 512)
                self.assertEqual(saved.theme, "Dark")
                self.assertIn("Restart FetchDeck", window.settings_status.text())
                window.preferences = replace(window.preferences, warn_on_quit=False)
                window.close()
                self.app.processEvents()
                with patch("fetchdeck.engine.Aria2Daemon.start", side_effect=EngineError("test engine unavailable")):
                    reopened = FetchDeckWindow()
                reopened.worker.wait(1000)
                self.assertEqual(reopened.folder_setting.text(), str(target))
                self.assertEqual(reopened.concurrent_setting.value(), 7)
                self.assertEqual(reopened.download_limit_setting.value(), 512)
                self.assertEqual(reopened.theme_setting.currentText(), "Dark")
                reopened.preferences = replace(reopened.preferences, warn_on_quit=False)
                reopened.close()
                self.app.processEvents()
            finally:
                if previous_app_data is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = previous_app_data

    def test_active_work_quit_warning_can_be_cancelled(self):
        previous_app_data = os.environ.get("LOCALAPPDATA")
        with tempfile.TemporaryDirectory(prefix="fetchdeck-ui-quit-") as app_data:
            os.environ["LOCALAPPDATA"] = app_data
            try:
                with patch("fetchdeck.engine.Aria2Daemon.start", side_effect=EngineError("test engine unavailable")):
                    window = FetchDeckWindow()
                window.worker.wait(1000)
                window.show()
                window._latest_tasks = [{"gid": "active", "status": "active"}]
                with patch("fetchdeck.app.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
                    self.assertFalse(window.close())
                self.assertTrue(window.isVisible())
                window.preferences = replace(window.preferences, warn_on_quit=False)
                window.close()
                self.app.processEvents()
            finally:
                if previous_app_data is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = previous_app_data


if __name__ == "__main__":
    unittest.main()
