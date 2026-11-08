import sys

from PySide6.QtWidgets import (\n    QApplication,\n    QHBoxLayout,\n    QLabel,\n    QListWidget,\n    QMainWindow,\n    QStackedWidget,\n    QVBoxLayout,\n    QWidget,\n)


class FetchDeckWindow(QMainWindow):
    """Foundation window with the three planned desktop destinations."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FetchDeck")
        self.resize(1040, 680)

        self.navigation = QListWidget()
        self.navigation.addItems(["Downloads", "Settings", "Trackers"])
        self.navigation.setFixedWidth(180)

        self.pages = QStackedWidget()
        for title, note in (
            ("Downloads", "Download queue will be available in Phase 1."),
            ("Settings", "Local preferences will be available in Phase 4."),
            ("Trackers", "Tracker management will be available in Phase 3."),
        ):
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.addWidget(QLabel(title))
            layout.addWidget(QLabel(note))
            layout.addStretch()
            self.pages.addWidget(page)

        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(QLabel("FETCHDECK  /  DOWNLOADS"))
        layout.addWidget(self.pages)

        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.addWidget(self.navigation)
        shell_layout.addWidget(body)
        self.setCentralWidget(shell)


def main() -> int:
    app = QApplication(sys.argv)
    window = FetchDeckWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
