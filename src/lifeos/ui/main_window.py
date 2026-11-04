"""LifeOS main window: presentation only, no database or AI access.

The window renders what it is given. Task interactions are delegated to the
injected :class:`~lifeos.ui.task_panel.TaskService`, so this module never talks
to the database directly.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from lifeos.ui.task_panel import TaskPanel, TaskService

APP_NAME = "LifeOS"
WELCOME_TEXT = "欢迎使用 LifeOS，从今天开始整理你的生活。"
CONNECTED_TEXT = "数据库状态：已连接"
DISCONNECTED_TEXT = "数据库状态：未连接"
TASKS_HEADING = "我的任务"


class MainWindow(QMainWindow):
    """Show the application name, version, welcome text and connection status."""

    def __init__(
        self,
        app_version: str,
        database_status: bool,
        task_service: TaskService | None = None,
    ) -> None:
        super().__init__()
        self._app_version = app_version
        self._database_status = bool(database_status)

        self.setWindowTitle(f"{APP_NAME} {app_version}")
        self.resize(560, 640)
        self.setMinimumSize(460, 420)

        self.title_label = self._build_label("titleLabel", APP_NAME)
        title_font = QFont(self.title_label.font())
        title_font.setPointSize(title_font.pointSize() + 12)
        title_font.setBold(True)
        self.title_label.setFont(title_font)

        self.version_label = self._build_label("versionLabel", f"版本 {app_version}")
        self.welcome_label = self._build_label("welcomeLabel", WELCOME_TEXT)
        self.welcome_label.setWordWrap(True)
        self.status_label = self._build_label("statusLabel", "")
        self.tasks_heading_label = self._build_label("tasksHeadingLabel", TASKS_HEADING)
        heading_font = QFont(self.tasks_heading_label.font())
        heading_font.setBold(True)
        self.tasks_heading_label.setFont(heading_font)

        self.task_panel = TaskPanel(task_service, self)

        layout = QVBoxLayout()
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)
        for label in (
            self.title_label,
            self.version_label,
            self.welcome_label,
            self.tasks_heading_label,
        ):
            layout.addWidget(label)
        layout.addWidget(self.task_panel, 1)
        layout.addWidget(self.status_label)

        central_widget = QWidget(self)
        central_widget.setObjectName("centralWidget")
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self._render_database_status()

    @staticmethod
    def _build_label(object_name: str, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def database_status(self) -> bool:
        """Return the connection status this window was last given."""
        return self._database_status

    def set_database_status(self, database_status: bool) -> None:
        """Update the displayed status without touching the database."""
        self._database_status = bool(database_status)
        self._render_database_status()

    def _render_database_status(self) -> None:
        if self._database_status:
            self.status_label.setText(CONNECTED_TEXT)
            self.status_label.setStyleSheet("color: #1a7f37; font-weight: 600;")
        else:
            self.status_label.setText(DISCONNECTED_TEXT)
            self.status_label.setStyleSheet("color: #b42318; font-weight: 600;")
