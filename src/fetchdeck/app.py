import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .engine import EngineWorker
from .paths import AppPaths


def validate_download_url(value: str) -> str:
    """Accept only direct HTTP(S) links without embedded credentials."""
    url = value.strip()
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("Enter a valid HTTP or HTTPS URL.") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        raise ValueError("Only direct HTTP and HTTPS links are supported in this phase.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Links with a username or password in the URL are not supported.")
    return url


def task_name(task: dict[str, Any]) -> str:
    files = task.get("files") or []
    if files and files[0].get("path"):
        return Path(files[0]["path"]).name or files[0]["path"]
    uris = files[0].get("uris", []) if files else []
    uri = uris[0].get("uri", "") if uris else ""
    parsed = urlsplit(uri)
    return unquote(Path(parsed.path).name) or parsed.hostname or "Download"


def format_bytes(value: str | int) -> str:
    size = int(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class AddDownloadDialog(QDialog):
    def __init__(self, default_folder: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add download")
        self.setMinimumWidth(520)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/file.zip")
        self.folder_input = QLineEdit(str(default_folder))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)

        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_input, 1)
        folder_row.addWidget(browse)

        form = QFormLayout()
        form.addRow("Download link", self.url_input)
        form.addRow("Save to", folder_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add to queue")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.url_input.setFocus()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a save folder", self.folder_input.text())
        if folder:
            self.folder_input.setText(folder)

    def _accept(self) -> None:
        try:
            validate_download_url(self.url_input.text())
            folder_text = self.folder_input.text().strip()
            if not folder_text:
                raise ValueError("Choose a save folder.")
            folder = Path(folder_text).expanduser()
            if not folder.is_dir():
                raise ValueError("Choose an existing save folder.")
        except ValueError as exc:
            QMessageBox.warning(self, "Check download details", str(exc))
            return
        self.accept()

    def values(self) -> tuple[str, Path]:
        return validate_download_url(self.url_input.text()), Path(self.folder_input.text().strip()).expanduser()


class FetchDeckWindow(QMainWindow):
    """Desktop shell and downloads screen; engine work stays on a QThread."""

    def __init__(self) -> None:
        super().__init__()
        self.paths = AppPaths.current_user()
        self.default_folder = self.paths.default_download_dir
        self.setWindowTitle("FetchDeck")
        self.resize(1100, 700)

        self.navigation = QListWidget()
        self.navigation.addItems(["Downloads", "Settings", "Trackers"])
        self.navigation.setFixedWidth(180)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._downloads_page())
        self.pages.addWidget(self._placeholder_page("Settings", "Settings will be available in Phase 4."))
        self.pages.addWidget(self._placeholder_page("Trackers", "Tracker management will be available in Phase 3."))
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.addWidget(self.navigation)
        shell_layout.addWidget(self.pages, 1)
        self.setCentralWidget(shell)

        self.worker = EngineWorker(self.paths)
        self.worker.ready.connect(self._engine_ready)
        self.worker.error.connect(self._engine_error)
        self.worker.snapshot.connect(self._show_snapshot)
        self.worker.action_finished.connect(self._action_finished)
        self.worker.start()

    @staticmethod
    def _placeholder_page(title: str, note: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(title))
        layout.addWidget(QLabel(note))
        layout.addStretch()
        return page

    def _downloads_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("FETCHDECK  /  DOWNLOADS"))

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("Add download")
        self.pause_button = QPushButton("Pause")
        self.resume_button = QPushButton("Resume")
        self.remove_button = QPushButton("Remove")
        self.add_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.add_button.clicked.connect(self._add_download)
        self.pause_button.clicked.connect(lambda: self._task_action("pause"))
        self.resume_button.clicked.connect(lambda: self._task_action("resume"))
        self.remove_button.clicked.connect(self._remove_download)
        for button in (self.add_button, self.pause_button, self.resume_button, self.remove_button):
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.engine_status = QLabel("Starting aria2…")
        self.engine_status.setWordWrap(True)
        layout.addWidget(self.engine_status)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["File", "Status", "Progress", "Transferred", "Total", "Speed", "Details"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)
        return page

    def _engine_ready(self, version: str) -> None:
        self.engine_status.setText(f"aria2 {version} is running.")
        self.add_button.setEnabled(True)

    def _engine_error(self, message: str) -> None:
        self.engine_status.setText(f"Engine unavailable: {message}")
        self.add_button.setEnabled(False)

    def _add_download(self) -> None:
        dialog = AddDownloadDialog(self.default_folder, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        url, folder = dialog.values()
        self.worker.submit("add", url, folder)

    def _selected_task(self) -> tuple[str, str] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole), item.data(Qt.ItemDataRole.UserRole + 1)

    def _task_action(self, action: str) -> None:
        selected = self._selected_task()
        if not selected:
            return
        gid, _status = selected
        self.worker.submit(action, gid)

    def _remove_download(self) -> None:
        selected = self._selected_task()
        if not selected:
            return
        gid, status = selected
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle("Remove download")
        confirmation.setText("Remove this task from the list?")
        confirmation.setInformativeText("Any downloaded files will be kept.")
        cancel = confirmation.addButton(QMessageBox.StandardButton.Cancel)
        remove = confirmation.addButton("Remove", QMessageBox.ButtonRole.AcceptRole)
        confirmation.setDefaultButton(cancel)
        confirmation.exec()
        if confirmation.clickedButton() == remove:
            self.worker.submit("remove", gid, status)

    def _selection_changed(self) -> None:
        selected = self._selected_task()
        enabled = selected is not None
        self.pause_button.setEnabled(enabled)
        self.resume_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)

    def _show_snapshot(self, tasks: list[dict[str, Any]]) -> None:
        current_gid = self._selected_task()
        selected_gid = current_gid[0] if current_gid else None
        self.table.setRowCount(len(tasks))
        selected_row = -1
        for row, task in enumerate(tasks):
            gid = task.get("gid", "")
            status = task.get("status", "unknown")
            completed = int(task.get("completedLength", 0) or 0)
            total = int(task.get("totalLength", 0) or 0)
            speed = int(task.get("downloadSpeed", 0) or 0)
            progress = f"{completed / total:.0%}" if total > 0 else "—"
            error = task.get("errorMessage", "") or ""
            values = (
                task_name(task),
                status.capitalize(),
                progress,
                format_bytes(completed),
                format_bytes(total) if total else "Unknown",
                f"{format_bytes(speed)}/s" if speed else "—",
                error,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, gid)
                    item.setData(Qt.ItemDataRole.UserRole + 1, status)
                self.table.setItem(row, column, item)
            if gid == selected_gid:
                selected_row = row
        self.table.resizeColumnsToContents()
        if selected_row >= 0:
            self.table.selectRow(selected_row)
        else:
            self._selection_changed()

    def _action_finished(self, _action_id: str, success: bool, message: str) -> None:
        if success:
            self.statusBar().showMessage("Download updated.", 3000)
        else:
            self.statusBar().showMessage(message or "The download action failed.", 8000)

    def closeEvent(self, event: Any) -> None:
        self.worker.requestInterruption()
        if self.worker.isRunning() and not self.worker.wait(6500):
            self.engine_status.setText("aria2 is still shutting down. Try closing FetchDeck again.")
            event.ignore()
            return
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FetchDeck")
    window = FetchDeckWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
