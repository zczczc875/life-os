"""Exercise the composition root with isolated component doubles."""

import sys
from datetime import time
from types import ModuleType, SimpleNamespace

import pytest
import sqlalchemy

from lifeos.app import main


def _install(monkeypatch, name, **members):
    module = ModuleType(name)
    module.__dict__.update(members)
    monkeypatch.setitem(sys.modules, name, module)


@pytest.mark.parametrize("connected", [True, False])
def test_startup_order_and_status(monkeypatch, connected):
    calls = []
    settings = SimpleNamespace(app_version="test-version")

    class Database:
        engine = object()

        def check_connection(self):
            calls.append("check")
            return connected

        def dispose(self):
            calls.append("dispose")

    class Application:
        @staticmethod
        def instance():
            return None

        def __init__(self, argv):
            calls.append("application")

        def exec(self):
            calls.append("exec")
            return 0

    class Window:
        def __init__(self, version, status, *, task_service, draft_preview, quick_parse):
            assert (version, status) == ("test-version", connected)
            assert (task_service is not None) is connected
            assert (draft_preview is not None) is connected
            assert (quick_parse is not None) is connected
            if draft_preview is not None:
                [draft] = draft_preview("交表 DDL: 2026-12-18").tasks
                assert draft.title == "交表"
                assert draft.due_on.isoformat() == "2026-12-18"
                quick_task = quick_parse("2026年12月18日17:30前提交实验报告")
                assert quick_task.title == "提交实验报告"
                assert quick_task.due_on.isoformat() == "2026-12-18"
                assert quick_task.due_time == time(17, 30)
            calls.append("window")

        def show(self):
            calls.append("show")

    def get_settings():
        calls.append("settings")
        return settings

    def setup_logging(actual):
        assert actual is settings
        calls.append("logging")

    def create_database(actual):
        assert actual is settings
        calls.append("database")
        return Database()

    class Inspector:
        def has_table(self, name):
            assert name == "tasks"
            return True

        def get_columns(self, name):
            assert name == "tasks"
            return [{"name": "due_on"}, {"name": "due_time"}]

    monkeypatch.setattr(sqlalchemy, "inspect", lambda engine: Inspector())
    _install(monkeypatch, "PySide6.QtWidgets", QApplication=Application, QMessageBox=object)
    _install(monkeypatch, "lifeos.config.settings", get_settings=get_settings)
    _install(monkeypatch, "lifeos.infrastructure.database.engine", create_database=create_database)
    _install(monkeypatch, "lifeos.infrastructure.logging.setup", setup_logging=setup_logging)
    _install(monkeypatch, "lifeos.tasks", TaskService=lambda database: object())
    _install(monkeypatch, "lifeos.ui.main_window", MainWindow=Window)

    assert main() == 0
    assert calls == [
        "settings",
        "logging",
        "database",
        "check",
        "application",
        "window",
        "show",
        "exec",
        "dispose",
    ]


def test_disposes_database_on_connection_error(monkeypatch):
    calls = []

    class Database:
        def check_connection(self):
            raise RuntimeError("unexpected error")

        def dispose(self):
            calls.append("dispose")

    _install(monkeypatch, "PySide6.QtWidgets", QApplication=object, QMessageBox=object)
    _install(monkeypatch, "lifeos.config.settings", get_settings=lambda: object())
    _install(
        monkeypatch, "lifeos.infrastructure.database.engine", create_database=lambda _: Database()
    )
    _install(monkeypatch, "lifeos.infrastructure.logging.setup", setup_logging=lambda _: None)
    _install(monkeypatch, "lifeos.tasks", TaskService=object)
    _install(monkeypatch, "lifeos.ui.main_window", MainWindow=object)

    with pytest.raises(RuntimeError, match="unexpected error"):
        main()
    assert calls == ["dispose"]


@pytest.mark.parametrize("revision", [None, "0002_tasks", "0003_task_due_on"])
def test_unmigrated_database_prompts_and_disables_tasks(qapp, monkeypatch, tmp_path, revision):
    from alembic import command
    from PySide6.QtWidgets import QApplication, QMessageBox

    from lifeos.config import settings as settings_module
    from lifeos.infrastructure.logging import setup as logging_module
    from lifeos.ui import main_window
    from tests._helpers import alembic_config

    if revision is not None:
        command.upgrade(alembic_config(tmp_path / "lifeos.sqlite3"), revision)

    notices = []
    windows = []
    original_window = main_window.MainWindow

    def capture_window(*args, **kwargs):
        window = original_window(*args, **kwargs)
        windows.append(window)
        return window

    monkeypatch.setattr(
        settings_module, "get_settings", lambda: settings_module.Settings(data_dir=tmp_path)
    )
    monkeypatch.setattr(logging_module, "setup_logging", lambda settings: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: notices.append(args))
    monkeypatch.setattr(QApplication, "exec", lambda *args: 0)
    monkeypatch.setattr(main_window, "MainWindow", capture_window)

    assert main() == 0
    assert len(notices) == 1
    assert "alembic upgrade head" in notices[0][2]
    assert windows[0].database_status()
    assert not windows[0].task_panel.add_button.isEnabled()
    windows[0].close()
