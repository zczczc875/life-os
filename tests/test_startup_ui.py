from PySide6.QtGui import QAction

from lifeos.ui.main_window import MainWindow


class Startup:
    def __init__(self):
        self.registered = False

    def enabled(self):
        return self.registered

    def set_enabled(self, enabled):
        self.registered = enabled


def test_startup_toggle_tracks_registration_across_windows(qtbot):
    registration = Startup()
    first = MainWindow("test", True, windows_startup=registration)
    qtbot.addWidget(first)
    action = first.findChild(QAction, "windowsStartupAction")
    assert action.isCheckable() and not action.isChecked()
    action.trigger()
    assert registration.enabled()

    reopened = MainWindow("test", True, windows_startup=registration)
    qtbot.addWidget(reopened)
    action = reopened.findChild(QAction, "windowsStartupAction")
    assert action.isChecked()
    action.trigger()
    assert not registration.enabled()
