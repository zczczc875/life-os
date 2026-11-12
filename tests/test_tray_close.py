from types import SimpleNamespace

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QSystemTrayIcon

from lifeos.ui.main_window import MainWindow


class Preferences:
    def __init__(self, action=None):
        self.action = action

    def get(self):
        return self.action

    def set(self, action):
        self.action = action


@pytest.fixture
def tray_window(qtbot, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)

    def create(preferences, **kwargs):
        window = MainWindow("test", True, close_preferences=preferences, **kwargs)
        qtbot.addWidget(
            window, before_close_func=lambda widget: setattr(widget, "_quit_requested", True)
        )
        window.show()
        return window

    return create


def answer_close(button_name, *, remember=False):
    observed = []

    def choose():
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            return
        try:
            observed.append(dialog.windowTitle())
            dialog.findChild(QCheckBox, "rememberCloseAction").setChecked(remember)
            if button_name is not None:
                button = dialog.findChild(QPushButton, button_name)
                observed.append(button.isEnabled())
                button.click()
        finally:
            if dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, choose)
    return observed


def test_close_to_tray_can_restore_and_then_exit(qtbot, tray_window, monkeypatch):
    preferences = Preferences()
    window = tray_window(preferences)
    observed = answer_close("minimizeToTrayButton")
    window.close()
    assert observed == ["关闭 LifeOS", True]
    assert not window.isVisible()
    assert preferences.get() is None

    tray = window.findChild(QSystemTrayIcon)
    assert tray.isVisible()
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    assert window.isVisible()

    answer_close("minimizeToTrayButton")
    window.close()
    quits = []
    monkeypatch.setattr(QApplication, "quit", lambda: quits.append(True))
    tray.contextMenu().findChild(QAction, "trayQuitAction").trigger()
    assert quits == [True]
    assert not tray.isVisible()
    assert window.close()


@pytest.mark.parametrize(
    ("button", "action"),
    [("minimizeToTrayButton", "tray"), ("exitLifeOSButton", "exit")],
)
def test_remembered_choice_skips_dialog_in_new_window(tray_window, button, action):
    preferences = Preferences()
    first = tray_window(preferences)
    observed = answer_close(button, remember=True)
    first.close()
    assert observed == ["关闭 LifeOS", True]
    assert preferences.get() == action
    assert not first.isVisible()

    reopened = tray_window(preferences)
    reopened.close()
    assert not reopened.isVisible()
    assert reopened.findChild(QSystemTrayIcon).isVisible() == (action == "tray")
    reopened.findChild(QAction, "resetCloseAction").trigger()
    assert preferences.get() is None


def test_dismissing_prompt_keeps_window_open_without_saving(tray_window):
    preferences = Preferences()
    window = tray_window(preferences)
    observed = answer_close(None, remember=True)
    window.close()
    assert observed == ["关闭 LifeOS"]
    assert window.isVisible()
    assert preferences.get() is None
    answer_close("exitLifeOSButton")
    assert window.close()


def test_unavailable_tray_does_not_hide_window(tray_window, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    preferences = Preferences("tray")
    window = tray_window(preferences)
    observed = answer_close("minimizeToTrayButton")
    window.close()
    assert observed == ["关闭 LifeOS", False]
    assert window.isVisible()
    assert preferences.get() == "tray"
    answer_close("exitLifeOSButton")
    assert window.close()


def test_reminders_keep_scanning_with_window_hidden(qtbot, tray_window):
    scans = []
    service = SimpleNamespace(enabled=lambda: True, claim_due=lambda now: scans.append(now) or [])
    window = tray_window(Preferences("tray"), reminder_service=service)
    assert len(window.findChildren(QSystemTrayIcon)) == 1
    window.close()
    assert not window.isVisible()
    timer = window.findChild(QTimer, "deadlineReminderTimer")
    timer.setInterval(20)
    qtbot.waitUntil(lambda: len(scans) >= 2)
