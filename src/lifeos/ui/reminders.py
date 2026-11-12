"""Poll local reminders while LifeOS is running."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from lifeos.tasks import TaskStorageError

if TYPE_CHECKING:
    from lifeos.tasks.reminders import ReminderService


class ReminderPanel(QWidget):
    def __init__(
        self, service: ReminderService, tray: QSystemTrayIcon, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._tray = tray
        self._last_reminder = ""

        self.checkbox = QCheckBox("到期提醒", self)
        self.checkbox.setObjectName("deadlineReminderCheck")
        self.checkbox.setToolTip("LifeOS 运行时提醒。只填写日期的任务在当天 23:59 提醒。")
        self.status = QLabel(self)
        self.status.setObjectName("deadlineReminderStatus")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.checkbox)
        layout.addWidget(self.status)

        self._timer = QTimer(self)
        self._timer.setObjectName("deadlineReminderTimer")
        self._timer.setInterval(15_000)
        self._timer.timeout.connect(self._scan)
        try:
            self.checkbox.setChecked(service.enabled())
        except TaskStorageError:
            self._show_status("暂时无法读取到期提醒设置。")
        self.checkbox.toggled.connect(self._set_enabled)
        if self.checkbox.isChecked():
            self._timer.start()
            QTimer.singleShot(0, self, self._scan)

    def _set_enabled(self, enabled: bool) -> None:
        try:
            self._service.set_enabled(enabled)
        except TaskStorageError:
            with QSignalBlocker(self.checkbox):
                self.checkbox.setChecked(not enabled)
            self._show_status("暂时无法保存到期提醒设置。")
            return

        if enabled:
            self._timer.start()
            self._scan()
        else:
            self._timer.stop()
            self._last_reminder = ""
            self._show_status("")

    def _scan(self) -> None:
        if not self.checkbox.isChecked():
            return
        try:
            tasks = self._service.claim_due(datetime.now())
        except TaskStorageError:
            self._show_status("暂时无法检查到期任务，LifeOS 会自动重试。")
            return

        if tasks:
            titles = [
                task.title if len(task.title) <= 48 else f"{task.title[:47]}…" for task in tasks[:2]
            ]
            self._last_reminder = f"{len(tasks)} 项任务已到期 · {'、'.join(titles)}"
            if QSystemTrayIcon.isSystemTrayAvailable() and QSystemTrayIcon.supportsMessages():
                self._tray.show()
                self._tray.showMessage("LifeOS 到期提醒", self._last_reminder)
        self._show_status(self._last_reminder)

    def _show_status(self, message: str) -> None:
        self.status.setText(message)
        self.status.setVisible(bool(message))
