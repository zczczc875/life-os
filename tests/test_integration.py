"""Exercise the composition root with isolated component doubles."""

import sys
from types import ModuleType, SimpleNamespace

import pytest

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
        def __init__(self, version, status):
            assert (version, status) == ("test-version", connected)
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

    _install(monkeypatch, "PySide6.QtWidgets", QApplication=Application)
    _install(monkeypatch, "lifeos.config.settings", get_settings=get_settings)
    _install(monkeypatch, "lifeos.infrastructure.database.engine", create_database=create_database)
    _install(monkeypatch, "lifeos.infrastructure.logging.setup", setup_logging=setup_logging)
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

    _install(monkeypatch, "PySide6.QtWidgets", QApplication=object)
    _install(monkeypatch, "lifeos.config.settings", get_settings=lambda: object())
    _install(
        monkeypatch, "lifeos.infrastructure.database.engine", create_database=lambda _: Database()
    )
    _install(monkeypatch, "lifeos.infrastructure.logging.setup", setup_logging=lambda _: None)
    _install(monkeypatch, "lifeos.ui.main_window", MainWindow=object)

    with pytest.raises(RuntimeError, match="unexpected error"):
        main()
    assert calls == ["dispose"]
