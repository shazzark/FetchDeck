import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote, urlsplit
from typing import Any

from PySide6.QtCore import QItemSelectionModel, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSpinBox,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .engine import EngineWorker, is_magnet_uri
from .dashboard_server import DashboardServer
from .notifications import NotificationStore
from .paths import AppPaths
from .preferences import Preferences, PreferencesStore, validate_preferences
from .trackers import TrackerError, TrackerListStore, TrackerSyncWorker


def validate_download_url(value: str) -> str:
    """Accept direct HTTP, HTTPS, or anonymous FTP links without URL credentials."""
    url = value.strip()
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("Enter a valid HTTP or HTTPS URL.") from exc
    if parsed.scheme.lower() not in {"http", "https", "ftp"} or not host:
        raise ValueError("Only direct HTTP, HTTPS, and FTP links are supported.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Links with a username or password in the URL are not supported.")
    return url


def task_name(task: dict[str, Any]) -> str:
    if task.get("_fetchdeckName"):
        return task["_fetchdeckName"]
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


def task_display_status(task: dict[str, Any]) -> str:
    if task.get("_fetchdeckStatus"):
        return task["_fetchdeckStatus"]
    return "Queued" if task.get("status") == "waiting" else str(task.get("status", "unknown")).capitalize()


def validate_download_source(value: str) -> str:
    source = value.strip()
    if source.lower().startswith("magnet:"):
        if not is_magnet_uri(source):
            raise ValueError("Enter a valid magnet link containing a BitTorrent info hash.")
        return source
    return validate_download_url(source)


class AddDownloadDialog(QDialog):
    def __init__(self, default_folder: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add download")
        self.setMinimumWidth(520)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/file.zip, ftp://… or magnet link")
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
            validate_download_source(self.url_input.text())
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
        return validate_download_source(self.url_input.text()), Path(self.folder_input.text().strip()).expanduser()


class FetchDeckWindow(QMainWindow):
    """Desktop shell and downloads screen; engine work stays on a QThread."""

    def __init__(self) -> None:
        super().__init__()
        self.paths = AppPaths.current_user()
        self.preferences_store = PreferencesStore(self.paths.preferences, self.paths.default_download_dir)
        try:
            self.preferences = self.preferences_store.load()
            self.preferences_error = ""
        except ValueError as exc:
            self.preferences = Preferences.defaults(self.paths.default_download_dir)
            self.preferences_error = str(exc)
        saved_folder = Path(self.preferences.default_folder).expanduser()
        self.default_folder = saved_folder if saved_folder.is_dir() else self.paths.default_download_dir
        self.preferences = replace(self.preferences, default_folder=str(self.default_folder))
        self.notification_store = NotificationStore(self.paths.notifications)
        try:
            self.notification_events = self.notification_store.load()
        except ValueError:
            self.notification_events = []
        self._known_task_status: dict[str, str] = {}
        self._has_snapshot = False
        self._latest_tasks: list[dict[str, Any]] = []
        self._engine_version = ""
        self._engine_health = "starting"
        self.dashboard_server: DashboardServer | None = None
        self._engine_preferences = self.preferences
        self.tracker_store = TrackerListStore(self.paths.trackers)
        self.tracker_sync_worker: TrackerSyncWorker | None = None
        self.setWindowTitle("FetchDeck")
        self.resize(1100, 700)

        self.navigation = QListWidget()
        self.navigation.addItems(["Downloads", "Settings", "Trackers"])
        self.navigation.setFixedWidth(180)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._downloads_page())
        self.pages.addWidget(self._settings_page())
        self.pages.addWidget(self._trackers_page())
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.addWidget(self.navigation)
        shell_layout.addWidget(self.pages, 1)
        self.setCentralWidget(shell)

        self.worker = EngineWorker(self.paths, preferences=self.preferences)
        self.worker.ready.connect(self._engine_ready)
        self.worker.error.connect(self._engine_error)
        self.worker.notice.connect(self._engine_notice)
        self.worker.snapshot.connect(self._show_snapshot)
        self.worker.action_finished.connect(self._action_finished)
        self.worker.start()
        self._apply_theme(self.preferences.theme)
        self.tray_icon = QSystemTrayIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), self)
        self.tray_icon.setToolTip("FetchDeck")
        tray_menu = QMenu(self)
        tray_menu.addAction("Show FetchDeck", self.showNormal)
        tray_menu.addAction("Quit", self.close)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(lambda _reason: self.showNormal())
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()
        self._install_shortcuts()

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("FETCHDECK  /  SETTINGS"))
        form = QFormLayout()
        self.folder_setting = QLineEdit(self.preferences.default_folder)
        choose_folder = QPushButton("Browse…")
        choose_folder.clicked.connect(self._choose_default_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_setting, 1)
        folder_row.addWidget(choose_folder)
        form.addRow("Default download folder", folder_row)

        self.concurrent_setting = QSpinBox()
        self.concurrent_setting.setRange(1, 64)
        self.concurrent_setting.setValue(self.preferences.max_concurrent_downloads)
        form.addRow("Concurrent downloads", self.concurrent_setting)
        self.connections_setting = QSpinBox()
        self.connections_setting.setRange(1, 16)
        self.connections_setting.setValue(self.preferences.connections_per_task)
        form.addRow("Connections per task", self.connections_setting)
        self.download_limit_setting = QSpinBox()
        self.download_limit_setting.setRange(0, 10_000_000)
        self.download_limit_setting.setSuffix(" KiB/s (0 = unlimited)")
        self.download_limit_setting.setValue(self.preferences.download_limit_kib)
        form.addRow("Download limit", self.download_limit_setting)
        self.upload_limit_setting = QSpinBox()
        self.upload_limit_setting.setRange(0, 10_000_000)
        self.upload_limit_setting.setSuffix(" KiB/s (0 = unlimited)")
        self.upload_limit_setting.setValue(self.preferences.upload_limit_kib)
        form.addRow("Upload limit", self.upload_limit_setting)
        self.user_agent_setting = QLineEdit(self.preferences.user_agent)
        form.addRow("User-Agent", self.user_agent_setting)
        self.theme_setting = QComboBox()
        self.theme_setting.addItems(["System", "Light", "Dark"])
        self.theme_setting.setCurrentText(self.preferences.theme)
        form.addRow("Theme", self.theme_setting)
        self.notify_complete_setting = QCheckBox("Notify when a download completes")
        self.notify_complete_setting.setChecked(self.preferences.notify_complete)
        form.addRow("Completion", self.notify_complete_setting)
        self.notify_failure_setting = QCheckBox("Notify when a download fails")
        self.notify_failure_setting.setChecked(self.preferences.notify_failure)
        form.addRow("Failure", self.notify_failure_setting)
        self.resume_launch_setting = QCheckBox("Resume unfinished downloads when FetchDeck starts")
        self.resume_launch_setting.setChecked(self.preferences.resume_on_launch)
        form.addRow("Launch behavior", self.resume_launch_setting)
        self.warn_quit_setting = QCheckBox("Warn before quitting with active downloads")
        self.warn_quit_setting.setChecked(self.preferences.warn_on_quit)
        form.addRow("Quit behavior", self.warn_quit_setting)
        layout.addLayout(form)

        self.settings_note = QLabel(
            "Concurrent downloads and connections per task take effect after restarting FetchDeck. "
            "Speed limits and User-Agent apply while it is running. Theme and folder apply immediately."
        )
        self.settings_note.setWordWrap(True)
        layout.addWidget(self.settings_note)
        self.settings_status = QLabel(self.preferences_error)
        self.settings_status.setWordWrap(True)
        layout.addWidget(self.settings_status)
        self.save_settings_button = QPushButton("Save settings")
        self.save_settings_button.clicked.connect(self._save_settings)
        layout.addWidget(self.save_settings_button)
        layout.addStretch()
        return page

    def _choose_default_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose the default download folder", self.folder_setting.text())
        if folder:
            self.folder_setting.setText(folder)

    def _settings_from_controls(self) -> Preferences:
        return validate_preferences(Preferences(
            default_folder=self.folder_setting.text().strip(),
            max_concurrent_downloads=self.concurrent_setting.value(),
            connections_per_task=self.connections_setting.value(),
            download_limit_kib=self.download_limit_setting.value(),
            upload_limit_kib=self.upload_limit_setting.value(),
            user_agent=self.user_agent_setting.text().strip(),
            theme=self.theme_setting.currentText(),
            notify_complete=self.notify_complete_setting.isChecked(),
            notify_failure=self.notify_failure_setting.isChecked(),
            resume_on_launch=self.resume_launch_setting.isChecked(),
            warn_on_quit=self.warn_quit_setting.isChecked(),
        ))

    def _save_settings(self) -> None:
        try:
            preferences = self._settings_from_controls()
            if not Path(preferences.default_folder).expanduser().is_dir():
                raise ValueError("Choose an existing default download folder.")
            self.preferences_store.save(preferences)
        except ValueError as exc:
            self.settings_status.setText(str(exc))
            return
        self.preferences = preferences
        self.default_folder = Path(preferences.default_folder).expanduser()
        self._apply_theme(preferences.theme)
        if self.worker.isRunning():
            self.worker.submit("update_runtime_settings", preferences)
        restart_needed = (
            preferences.max_concurrent_downloads != self._engine_preferences.max_concurrent_downloads
            or preferences.connections_per_task != self._engine_preferences.connections_per_task
        )
        self.settings_status.setText(
            "Settings saved. Restart FetchDeck to apply concurrent download and connection changes."
            if restart_needed else "Settings saved and applied."
        )

    def _apply_theme(self, theme: str) -> None:
        if theme == "Dark":
            QApplication.instance().setStyleSheet(
                "QWidget { background: #20252b; color: #e8edf2; } "
                "QLineEdit, QComboBox, QSpinBox, QTableWidget, QListWidget { background: #151a1f; }"
            )
        elif theme == "Light":
            QApplication.instance().setStyleSheet(
                "QWidget { background: #f5f7f9; color: #1b2733; } "
                "QLineEdit, QComboBox, QSpinBox, QTableWidget, QListWidget { background: white; }"
            )
        else:
            QApplication.instance().setStyleSheet("")

    def _install_shortcuts(self) -> None:
        shortcuts = (("Ctrl+N", self._add_download), ("Ctrl+O", self._add_torrent),
                     ("Ctrl+P", lambda: self._task_action("pause")),
                     ("Ctrl+R", lambda: self._task_action("resume")), ("Delete", self._remove_download))
        for sequence, callback in shortcuts:
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(callback)

    @staticmethod
    def _placeholder_page(title: str, note: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(title))
        layout.addWidget(QLabel(note))
        layout.addStretch()
        return page

    def _trackers_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("FETCHDECK  /  TRACKERS"))
        layout.addWidget(QLabel("Sync a community list. Changes apply to new BitTorrent tasks."))

        controls = QHBoxLayout()
        self.tracker_kind = QComboBox()
        self.tracker_kind.addItems(["best", "all"])
        self.sync_trackers_button = QPushButton("Sync list")
        self.apply_trackers_button = QPushButton("Apply saved list")
        self.sync_trackers_button.clicked.connect(self._sync_trackers)
        self.apply_trackers_button.clicked.connect(self._apply_trackers)
        controls.addWidget(self.tracker_kind)
        controls.addWidget(self.sync_trackers_button)
        controls.addWidget(self.apply_trackers_button)
        controls.addStretch()
        layout.addLayout(controls)

        self.tracker_status = QLabel()
        self.tracker_status.setWordWrap(True)
        layout.addWidget(self.tracker_status)
        self.tracker_list = QListWidget()
        layout.addWidget(self.tracker_list, 1)
        try:
            self._show_trackers(self.tracker_store.read())
        except TrackerError as exc:
            self.tracker_status.setText(str(exc))
        return page

    def _downloads_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("FETCHDECK  /  DOWNLOADS"))

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("Add download")
        self.dashboard_button = QPushButton("Dashboard")
        self.dashboard_button.clicked.connect(self._open_dashboard)
        self.add_torrent_button = QPushButton("Add .torrent")
        self.pause_button = QPushButton("Pause")
        self.resume_button = QPushButton("Resume")
        self.remove_button = QPushButton("Remove")
        self.restart_button = QPushButton("Restart")
        self.recycle_button = QPushButton("Move to Recycle Bin")
        self.pause_all_button = QPushButton("Pause all")
        self.resume_all_button = QPushButton("Resume all")
        self.add_button.setEnabled(False)
        self.add_torrent_button.setEnabled(False)
        for button in (
            self.pause_button,
            self.resume_button,
            self.remove_button,
            self.restart_button,
            self.recycle_button,
            self.pause_all_button,
            self.resume_all_button,
        ):
            button.setEnabled(False)
        self.add_button.clicked.connect(self._add_download)
        self.add_torrent_button.clicked.connect(self._add_torrent)
        self.pause_button.clicked.connect(lambda: self._task_action("pause"))
        self.resume_button.clicked.connect(lambda: self._task_action("resume"))
        self.remove_button.clicked.connect(self._remove_download)
        self.restart_button.clicked.connect(self._restart_download)
        self.recycle_button.clicked.connect(self._recycle_download)
        self.pause_all_button.clicked.connect(lambda: self.worker.submit("pause_all"))
        self.resume_all_button.clicked.connect(lambda: self.worker.submit("resume_all"))
        for button in (
            self.add_button,
            self.dashboard_button,
            self.add_torrent_button,
            self.pause_button,
            self.resume_button,
            self.remove_button,
            self.restart_button,
            self.recycle_button,
            self.pause_all_button,
            self.resume_all_button,
        ):
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search downloads")
        self.status_filter = QComboBox()
        self.status_filter.addItems([
            "All statuses", "Active", "Queued", "Paused", "Complete", "Failed", "Fetching metadata", "Seeding"
        ])
        self.search_input.textChanged.connect(self._apply_filters)
        self.status_filter.currentTextChanged.connect(self._apply_filters)
        filter_row.addWidget(self.search_input, 1)
        filter_row.addWidget(self.status_filter)
        layout.addLayout(filter_row)

        self.engine_status = QLabel("Starting aria2…")
        self.engine_status.setWordWrap(True)
        layout.addWidget(self.engine_status)
        self.downloads_state = QLabel("No downloads yet. Add a link or a .torrent file to get started.")
        self.downloads_state.setWordWrap(True)
        layout.addWidget(self.downloads_state)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["File", "Status", "Progress", "Transferred", "Total", "Speed", "Details"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel("Recent activity"))
        self.notification_feed = QListWidget()
        self.notification_feed.setMaximumHeight(130)
        layout.addWidget(self.notification_feed)
        self._refresh_notification_feed()
        return page

    def _engine_ready(self, version: str) -> None:
        self._engine_version = version
        self._engine_health = "running"
        self.engine_status.setText(f"aria2 {version} is running.")
        self.add_button.setEnabled(True)
        self.add_torrent_button.setEnabled(True)
        self.pause_all_button.setEnabled(True)
        self.resume_all_button.setEnabled(True)

    def _engine_error(self, message: str) -> None:
        self._engine_health = "unavailable"
        self.engine_status.setText(f"Engine unavailable: {message}")
        self.add_button.setEnabled(False)
        self.add_torrent_button.setEnabled(False)
        self.pause_all_button.setEnabled(False)
        self.resume_all_button.setEnabled(False)

    def _engine_notice(self, message: str) -> None:
        self.statusBar().showMessage(message, 10000)

    def _add_download(self) -> None:
        if not self.add_button.isEnabled():
            return
        dialog = AddDownloadDialog(self.default_folder, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        url, folder = dialog.values()
        action = "add_magnet" if url.lower().startswith("magnet:") else "add"
        self.worker.submit(action, url, folder)

    def _add_torrent(self) -> None:
        torrent_path, _selected_filter = QFileDialog.getOpenFileName(
            self, "Choose a torrent file", str(self.default_folder), "Torrent files (*.torrent)"
        )
        if not torrent_path:
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose a save folder", str(self.default_folder))
        if folder:
            self.worker.submit("add_torrent", Path(torrent_path), Path(folder))

    def _show_trackers(self, trackers: list[str]) -> None:
        self.tracker_list.clear()
        self.tracker_list.addItems(trackers)
        if trackers:
            self.tracker_status.setText(f"{len(trackers)} trackers saved locally.")
            self.apply_trackers_button.setEnabled(True)
        else:
            self.tracker_status.setText("No cached tracker list. Sync the best or all community list.")
            self.apply_trackers_button.setEnabled(False)

    def _sync_trackers(self) -> None:
        if self.tracker_sync_worker and self.tracker_sync_worker.isRunning():
            return
        kind = self.tracker_kind.currentText()
        worker = TrackerSyncWorker(self.tracker_store, kind)
        self.tracker_sync_worker = worker
        worker.completed.connect(self._trackers_synced)
        worker.failed.connect(self._trackers_failed)
        worker.finished.connect(self._tracker_sync_finished)
        self.sync_trackers_button.setEnabled(False)
        self.tracker_status.setText(f"Syncing the {kind} tracker list…")
        worker.start()

    def _trackers_synced(self, trackers: list[str]) -> None:
        self._show_trackers(trackers)
        self.tracker_status.setText(f"Synced and saved {len(trackers)} trackers. Applying to new BitTorrent tasks…")
        self.worker.submit("set_trackers", trackers)

    def _trackers_failed(self, message: str) -> None:
        try:
            self._show_trackers(self.tracker_store.read())
        except TrackerError:
            pass
        self.tracker_status.setText(message)

    def _tracker_sync_finished(self) -> None:
        self.sync_trackers_button.setEnabled(True)
        self.tracker_sync_worker = None

    def _apply_trackers(self) -> None:
        try:
            trackers = self.tracker_store.read()
        except TrackerError as exc:
            self.tracker_status.setText(str(exc))
            return
        if trackers:
            self.worker.submit("set_trackers", trackers)

    def _selected_tasks(self) -> list[tuple[str, str, str]]:
        selected = []
        for row in self.table.selectionModel().selectedRows():
            item = self.table.item(row.row(), 0)
            if item:
                selected.append((
                    item.data(Qt.ItemDataRole.UserRole),
                    item.data(Qt.ItemDataRole.UserRole + 1),
                    item.data(Qt.ItemDataRole.UserRole + 2) or "",
                ))
        return selected

    def _task_action(self, action: str) -> None:
        for gid, _status, _path in self._selected_tasks():
            self.worker.submit(action, gid)

    def _remove_download(self) -> None:
        selected = self._selected_tasks()
        if not selected:
            return
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle("Remove download")
        confirmation.setText(f"Remove {len(selected)} selected task(s) from the list?")
        confirmation.setInformativeText("Any downloaded files will be kept.")
        cancel = confirmation.addButton(QMessageBox.StandardButton.Cancel)
        remove = confirmation.addButton("Remove", QMessageBox.ButtonRole.AcceptRole)
        confirmation.setDefaultButton(cancel)
        confirmation.exec()
        if confirmation.clickedButton() == remove:
            for gid, status, _path in selected:
                self.worker.submit("remove", gid, status)

    def _restart_download(self) -> None:
        selected = self._selected_tasks()
        if len(selected) != 1:
            self.statusBar().showMessage("Select one stopped task to restart.", 5000)
            return
        gid, status, path_text = selected[0]
        if status in {"active", "waiting", "paused"}:
            self.statusBar().showMessage("Pause or stop this task before restarting it.", 5000)
            return
        path = Path(path_text) if path_text else None
        overwrite = False
        if path and path.exists():
            prompt = QMessageBox(self)
            prompt.setWindowTitle("Restart download")
            prompt.setText(f"{path.name} already exists.")
            prompt.setInformativeText("Replace the existing file, or keep it and save the restart with a new name?")
            cancel = prompt.addButton(QMessageBox.StandardButton.Cancel)
            keep = prompt.addButton("Keep both", QMessageBox.ButtonRole.ActionRole)
            replace = prompt.addButton("Replace existing", QMessageBox.ButtonRole.DestructiveRole)
            prompt.setDefaultButton(cancel)
            prompt.exec()
            if prompt.clickedButton() == cancel:
                return
            overwrite = prompt.clickedButton() == replace
            if prompt.clickedButton() not in (keep, replace):
                return
        self.worker.submit("restart", gid, overwrite)

    def _recycle_download(self) -> None:
        selected = self._selected_tasks()
        if not selected:
            return
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle("Move downloads to Recycle Bin")
        confirmation.setText(f"Move files for {len(selected)} selected task(s) to the Recycle Bin?")
        confirmation.setInformativeText("This removes the tasks and sends any downloaded files to the Windows Recycle Bin.")
        cancel = confirmation.addButton(QMessageBox.StandardButton.Cancel)
        move = confirmation.addButton("Move to Recycle Bin", QMessageBox.ButtonRole.DestructiveRole)
        confirmation.setDefaultButton(cancel)
        confirmation.exec()
        if confirmation.clickedButton() == move:
            for gid, status, _path in selected:
                self.worker.submit("recycle", gid, status)

    def _show_context_menu(self, position: Any) -> None:
        index = self.table.indexAt(position)
        if index.isValid() and not self.table.selectionModel().isRowSelected(index.row(), index.parent()):
            self.table.selectRow(index.row())
        menu = QMenu(self)
        menu.addAction("Pause selected", lambda: self._task_action("pause"))
        menu.addAction("Resume selected", lambda: self._task_action("resume"))
        menu.addAction("Restart selected", self._restart_download)
        menu.addSeparator()
        menu.addAction("Remove selected (keep files)", self._remove_download)
        menu.addAction("Move selected files to Recycle Bin", self._recycle_download)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _apply_filters(self, *_args: Any) -> None:
        query = self.search_input.text().strip().casefold()
        filter_value = self.status_filter.currentText()
        status_groups = {
            "Active": {"Active"},
            "Queued": {"Queued"},
            "Paused": {"Paused"},
            "Complete": {"Complete"},
            "Failed": {"Error"},
            "Fetching metadata": {"Fetching metadata"},
            "Seeding": {"Seeding"},
        }
        wanted = status_groups.get(filter_value)
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text().casefold()
            status = self.table.item(row, 1).text()
            self.table.setRowHidden(row, bool((query and query not in name) or (wanted and status not in wanted)))

    def _selection_changed(self) -> None:
        selected = self._selected_tasks()
        enabled = bool(selected)
        self.pause_button.setEnabled(enabled)
        self.resume_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        self.recycle_button.setEnabled(enabled)
        self.restart_button.setEnabled(len(selected) == 1)

    def _show_snapshot(self, tasks: list[dict[str, Any]]) -> None:
        current_status = {task.get("gid", ""): task.get("status", "unknown") for task in tasks}
        if self._has_snapshot:
            for task in tasks:
                gid = task.get("gid", "")
                status = task.get("status", "")
                if status in {"complete", "error"} and self._known_task_status.get(gid) != status:
                    self._record_task_event(task, status)
        self._known_task_status = current_status
        self._has_snapshot = True
        self._latest_tasks = tasks
        self._engine_health = "running"
        self.downloads_state.setText(
            "No downloads yet. Add a link or a .torrent file to get started."
            if not tasks else "No downloads match the current search and filter."
        )
        self.downloads_state.setVisible(not tasks)
        selected_gids = {gid for gid, _status, _path in self._selected_tasks()}
        self.table.setRowCount(len(tasks))
        selected_rows = []
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
                task_display_status(task),
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
                    files = task.get("files") or []
                    path = files[0].get("path", "") if files else ""
                    item.setData(Qt.ItemDataRole.UserRole + 2, path or task.get("_fetchdeckPath", ""))
                self.table.setItem(row, column, item)
            if gid in selected_gids:
                selected_rows.append(row)
        self.table.resizeColumnsToContents()
        self._apply_filters()
        if tasks and all(self.table.isRowHidden(row) for row in range(self.table.rowCount())):
            self.downloads_state.setVisible(True)
        selection = self.table.selectionModel()
        selection.clearSelection()
        for row in selected_rows:
            selection.select(
                self.table.model().index(row, 0),
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
        self._selection_changed()

    def _record_task_event(self, task: dict[str, Any], status: str) -> None:
        completed = status == "complete"
        if completed and not self.preferences.notify_complete:
            return
        if not completed and not self.preferences.notify_failure:
            return
        name = task_name(task)
        title = "Download complete" if completed else "Download failed"
        detail = name if completed else f"{name}: {task.get('errorMessage') or 'aria2 reported a failure.'}"
        try:
            event = self.notification_store.append("complete" if completed else "failure", title, detail)
        except ValueError as exc:
            self.statusBar().showMessage(str(exc), 8000)
            return
        self.notification_events.append(event)
        self.notification_events = self.notification_events[-100:]
        self._refresh_notification_feed()
        if QSystemTrayIcon.isSystemTrayAvailable():
            icon = QSystemTrayIcon.MessageIcon.Information if completed else QSystemTrayIcon.MessageIcon.Warning
            self.tray_icon.showMessage(title, detail, icon, 8000)

    def _refresh_notification_feed(self) -> None:
        if not hasattr(self, "notification_feed"):
            return
        self.notification_feed.clear()
        for event in reversed(self.notification_events[-100:]):
            self.notification_feed.addItem(f"{event['time']}  {event['title']} — {event['detail']}")

    def _open_dashboard(self) -> None:
        if self.dashboard_server is None:
            frozen_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
            candidates = [
                frozen_root / "dashboard",
                Path(sys.executable).resolve().parent / "dashboard",
                Path(__file__).resolve().parents[2] / "apps" / "dashboard" / "out",
            ]
            export_dir = next((path for path in candidates if (path / "index.html").is_file()), None)
            if export_dir is None:
                QMessageBox.information(self, "Dashboard unavailable", "Build the optional dashboard with npm run build --workspace @fetchdeck/dashboard, then restart FetchDeck.")
                return
            self.dashboard_server = DashboardServer(export_dir, self._dashboard_snapshot)
        try:
            address = getattr(self.dashboard_server, "address", None)
            if address is None:
                address = self.dashboard_server.start()
                self.dashboard_server.address = address
        except OSError as exc:
            QMessageBox.warning(self, "Dashboard unavailable", f"FetchDeck could not start the local dashboard server: {exc}")
            self.dashboard_server = None
            return
        QDesktopServices.openUrl(QUrl(address))

    def _dashboard_snapshot(self) -> dict[str, Any]:
        return self.worker.statistics.snapshot(
            engine_status=self._engine_health,
            engine_version=self._engine_version,
            tasks=self._latest_tasks,
        )

    def _action_finished(self, _action_id: str, success: bool, message: str) -> None:
        if success:
            self.statusBar().showMessage("Download updated.", 3000)
        else:
            self.statusBar().showMessage(message or "The download action failed.", 8000)

    def closeEvent(self, event: Any) -> None:
        active = [task for task in self._latest_tasks if task.get("status") in {"active", "waiting"}]
        if active and self.preferences.warn_on_quit:
            choice = QMessageBox.question(
                self,
                "Downloads are still active",
                f"{len(active)} download(s) are active or queued. Quit FetchDeck? They will stop and be saved for the next launch.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.tracker_sync_worker and self.tracker_sync_worker.isRunning():
            if not self.tracker_sync_worker.wait(10_500):
                self.tracker_status.setText("Tracker sync is still running. Try closing FetchDeck again.")
                event.ignore()
                return
        self.worker.requestInterruption()
        if self.worker.isRunning() and not self.worker.wait(6500):
            self.engine_status.setText("aria2 is still shutting down. Try closing FetchDeck again.")
            event.ignore()
            return
        if self.dashboard_server is not None:
            self.dashboard_server.close()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FetchDeck")
    window = FetchDeckWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
