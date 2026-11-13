from datetime import datetime
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QCheckBox, QLabel, QSystemTrayIcon, QToolButton

from lifeos.ui.reminders import ReminderPanel


class ReminderService:
    def __init__(self, enabled=False):
        self.is_enabled = enabled
        self.scans = []
        self.tasks = []
        self.upcoming = []
        self.minutes = ()

    def enabled(self):
        return self.is_enabled

    def set_enabled(self, enabled):
        self.is_enabled = enabled

    def advance_minutes(self):
        return self.minutes

    def set_advance_minutes(self, minutes):
        self.minutes = tuple(sorted(minutes))

    def claim_reminders(self, now):
        self.scans.append(now)
        tasks, self.tasks = self.tasks, []
        upcoming, self.upcoming = self.upcoming, []
        return tasks, upcoming


def test_toggling_reminders_starts_and_stops_scanning(qtbot, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    service = ReminderService()
    panel = ReminderPanel(service, QSystemTrayIcon())
    qtbot.addWidget(panel)
    panel.show()
    checkbox = panel.findChild(QCheckBox)
    assert not checkbox.isChecked()
    assert not service.scans

    qtbot.mouseClick(checkbox, Qt.MouseButton.LeftButton)

    assert service.is_enabled
    assert isinstance(service.scans[0], datetime)
    qtbot.mouseClick(checkbox, Qt.MouseButton.LeftButton)
    assert not service.is_enabled
    assert len(service.scans) == 1


def test_enabled_reminders_check_on_startup_and_display_in_window(qtbot, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    service = ReminderService(enabled=True)
    service.tasks = [SimpleNamespace(title="<b>补交报告</b>")]
    panel = ReminderPanel(service, QSystemTrayIcon())
    qtbot.addWidget(panel)
    panel.show()
    assert panel.findChild(QCheckBox).isChecked()
    qtbot.waitUntil(lambda: bool(service.scans))

    status = panel.findChild(QLabel)
    assert status.isVisible()
    assert "<b>补交报告</b>" in status.text()
    assert status.textFormat() == Qt.TextFormat.PlainText


def test_due_tasks_send_one_windows_notification_for_the_batch(qtbot, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(QSystemTrayIcon, "supportsMessages", lambda: True)
    notifications = []
    monkeypatch.setattr(
        QSystemTrayIcon, "showMessage", lambda self, title, message: notifications.append(message)
    )
    service = ReminderService()
    service.tasks = [SimpleNamespace(title=title) for title in ("报告", "交表", "交费")]
    panel = ReminderPanel(service, QSystemTrayIcon())
    qtbot.addWidget(panel)
    panel.show()

    qtbot.mouseClick(panel.findChild(QCheckBox), Qt.MouseButton.LeftButton)

    assert len(notifications) == 1
    assert "3 项" in notifications[0]
    assert "报告" in notifications[0]


def test_advance_controls_save_independent_choices_and_restore_them(qtbot, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    service = ReminderService()
    panel = ReminderPanel(service, QSystemTrayIcon())
    qtbot.addWidget(panel)
    panel.show()
    button = panel.findChild(QToolButton, "advanceReminderButton")
    assert not button.isEnabled()
    qtbot.mouseClick(panel.findChild(QCheckBox), Qt.MouseButton.LeftButton)
    assert button.isEnabled()
    for minutes in (15, 1440):
        button.menu().findChild(QAction, f"advanceReminder{minutes}").trigger()
    assert service.advance_minutes() == (15, 1440)

    reopened = ReminderPanel(service, QSystemTrayIcon())
    qtbot.addWidget(reopened)
    actions = reopened.findChild(QToolButton, "advanceReminderButton").menu().actions()
    assert [action.isChecked() for action in actions] == [True, False, True]


def test_due_and_advance_claims_are_distinguished_in_one_notification(qtbot, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(QSystemTrayIcon, "supportsMessages", lambda: True)
    notifications = []
    monkeypatch.setattr(
        QSystemTrayIcon, "showMessage", lambda self, title, message: notifications.append(message)
    )
    service = ReminderService()
    service.tasks = [SimpleNamespace(title="旧报告")]
    service.upcoming = [SimpleNamespace(title="新报告")]
    panel = ReminderPanel(service, QSystemTrayIcon())
    qtbot.addWidget(panel)
    panel.show()

    qtbot.mouseClick(panel.findChild(QCheckBox), Qt.MouseButton.LeftButton)

    message = "1 项任务已到期 · 旧报告\n1 项任务即将到期 · 新报告"
    assert notifications == [message]
    assert panel.findChild(QLabel).text() == message
