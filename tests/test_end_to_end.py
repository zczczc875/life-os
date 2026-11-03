"""Exercise real components together using a disposable database."""

import os
import subprocess
import sys


def test_migration_persistence_and_application(tmp_path):
    env = {key: value for key, value in os.environ.items() if not key.startswith("LIFEOS_")}
    env["LIFEOS_DATA_DIR"] = str(tmp_path / "data")
    env["QT_QPA_PLATFORM"] = "offscreen"

    def run(*args):
        return subprocess.run(
            [sys.executable, *args], env=env, check=True, capture_output=True, text=True, timeout=30
        )

    run("-m", "alembic", "upgrade", "head")
    setup = (
        "from lifeos.config.settings import get_settings\n"
        "from lifeos.infrastructure.database.engine import create_database\n"
        "from lifeos.infrastructure.database.repository import SettingsRepository\n"
        "db = create_database(get_settings())\n"
        "session = db.session()\n"
    )
    close = "session.close()\ndb.dispose()\n"
    run("-c", setup + "SettingsRepository(session).set('key', 'value')\nsession.commit()\n" + close)
    run("-c", setup + "assert SettingsRepository(session).get('key') == 'value'\n" + close)

    app_code = """\
import runpy
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
original_exec = QApplication.exec
def timed_exec(app):
    def check_window():
        windows = app.topLevelWidgets()
        good = any(w.isVisible() and w.windowTitle().startswith('LifeOS')
                   and w.database_status() for w in windows)
        app.exit(0 if good else 2)
    QTimer.singleShot(100, check_window)
    return original_exec()
QApplication.exec = timed_exec
runpy.run_module('lifeos', run_name='__main__')
"""
    run("-c", app_code)
