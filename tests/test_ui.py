"""UI tests for the main window; the window is presentation-only."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QLabel, QMainWindow

from lifeos.ui.main_window import (
    CONNECTED_TEXT,
    DISCONNECTED_TEXT,
    WELCOME_TEXT,
    MainWindow,
)


@pytest.mark.parametrize(
    ("status", "expected_text"),
    [(True, CONNECTED_TEXT), (False, DISCONNECTED_TEXT)],
)
def test_shows_version_and_connection_status(qtbot, status, expected_text):
    window = MainWindow("0.1.0", status)
    qtbot.addWidget(window)

    assert isinstance(window, QMainWindow)
    assert "LifeOS" in window.windowTitle()
    assert "0.1.0" in window.windowTitle()
    assert window.findChild(QLabel, "versionLabel").text() == "版本 0.1.0"
    assert window.findChild(QLabel, "welcomeLabel").text() == WELCOME_TEXT
    assert window.findChild(QLabel, "statusLabel").text() == expected_text
    assert window.database_status() is status


def test_shows_welcome_and_selectable_labels(qtbot):
    window = MainWindow("0.1.0", True)
    qtbot.addWidget(window)

    assert window.findChild(QLabel, "titleLabel").text() == "LifeOS"
    welcome = window.findChild(QLabel, "welcomeLabel")
    assert welcome.wordWrap() is True
    assert not welcome.text().strip().startswith("<")


def test_status_can_be_updated_without_a_database(qtbot):
    window = MainWindow("0.1.0", False)
    qtbot.addWidget(window)

    window.set_database_status(True)
    assert window.findChild(QLabel, "statusLabel").text() == CONNECTED_TEXT
    assert window.database_status() is True

    window.set_database_status(False)
    assert window.findChild(QLabel, "statusLabel").text() == DISCONNECTED_TEXT
    assert window.database_status() is False


def test_window_can_be_shown_and_closed(qtbot):
    window = MainWindow("0.1.0", True)
    qtbot.addWidget(window)

    window.show()
    assert window.isVisible()

    window.close()
    assert not window.isVisible()
