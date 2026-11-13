"""Poll local reminders while LifeOS is running."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lifeos.tasks import TaskStorageError
from lifeos.tasks.reminders import ADVANCE_MINUTES

if TYPE_CHECKING:
    from lifeos.tasks.reminders import ReminderService, Task


_ADVANCE_LABELS = {15: "提前 15 分钟", 60: "提前 1 小时", 1440: "提前 1 天"}


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
        self.checkbox.setToolTip("LifeOS 运行时提醒。只填写日期的任务以当天 23:59 为截止时间。")
        self.advance_button = QToolButton(self)
        self.advance_button.setObjectName("advanceReminderButton")
        self.advance_button.setText("提前提醒")
        self.advance_button.setToolTip("可同时选择多个提前时间")
        self.advance_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.advance_button)
        self.advance_button.setMenu(menu)
        self._advance_actions = {}
        for minutes in ADVANCE_MINUTES:
            action = menu.addAction(_ADVANCE_LABELS[minutes])
            action.setObjectName(f"advanceReminder{minutes}")
            action.setCheckable(True)
            action.toggled.connect(self._set_advance_minutes)
            self._advance_actions[minutes] = action
        self._advance_minutes: tuple[int, ...] = ()
        self.status = QLabel(self)
        self.status.setObjectName("deadlineReminderStatus")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        controls.addWidget(self.checkbox)
        controls.addWidget(self.advance_button)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(self.status)

        self._timer = QTimer(self)
        self._timer.setObjectName("deadlineReminderTimer")
        self._timer.setInterval(15_000)
        self._timer.timeout.connect(self._scan)
        try:
            self.checkbox.setChecked(service.enabled())
            self._set_advance_checks(service.advance_minutes())
        except TaskStorageError:
            self._show_status("暂时无法读取到期提醒设置。")
        self.advance_button.setEnabled(self.checkbox.isChecked())
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

        self.advance_button.setEnabled(enabled)
        if enabled:
            self._timer.start()
            self._scan()
        else:
            self._timer.stop()
            self._last_reminder = ""
            self._show_status("")

    def _set_advance_checks(self, minutes: tuple[int, ...]) -> None:
        self._advance_minutes = minutes
        for value, action in self._advance_actions.items():
            with QSignalBlocker(action):
                action.setChecked(value in minutes)

    def _set_advance_minutes(self, _checked: bool) -> None:
        selected = tuple(
            minutes for minutes, action in self._advance_actions.items() if action.isChecked()
        )
        try:
            self._service.set_advance_minutes(selected)
        except TaskStorageError:
            self._set_advance_checks(self._advance_minutes)
            self._show_status("暂时无法保存提前提醒设置。")
            return
        self._advance_minutes = selected
        self._scan()

    def _scan(self) -> None:
        if not self.checkbox.isChecked():
            return
        try:
            due, advance = self._service.claim_reminders(datetime.now())
        except TaskStorageError:
            self._show_status("暂时无法检查到期任务，LifeOS 会自动重试。")
            return

        if due or advance:
            lines = []
            if due:
                lines.append(self._format_tasks(due, "已到期"))
            if advance:
                lines.append(self._format_tasks(advance, "即将到期"))
            self._last_reminder = "\n".join(lines)
            if QSystemTrayIcon.isSystemTrayAvailable() and QSystemTrayIcon.supportsMessages():
                self._tray.show()
                self._tray.showMessage("LifeOS 到期提醒", self._last_reminder)
        self._show_status(self._last_reminder)

    @staticmethod
    def _format_tasks(tasks: list[Task], status: str) -> str:
        titles = [
            task.title if len(task.title) <= 48 else f"{task.title[:47]}…" for task in tasks[:2]
        ]
        return f"{len(tasks)} 项任务{status} · {'、'.join(titles)}"

    def _show_status(self, message: str) -> None:
        self.status.setText(message)
        self.status.setVisible(bool(message))
