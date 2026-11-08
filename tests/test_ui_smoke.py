import os
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from fetchdeck.app import FetchDeckWindow
from fetchdeck.engine import EngineError


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


if __name__ == "__main__":
    unittest.main()
