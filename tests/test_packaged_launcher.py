"""Exercise the packaged launcher's migration safety with isolated databases."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from PySide6.QtWidgets import QMessageBox

import lifeos.app
from lifeos.config.settings import get_settings
from tests._helpers import head_revision

_PROJECT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "lifeos_packaged_launcher", _PROJECT / "packaging/launcher.py"
)
assert _spec is not None and _spec.loader is not None
launcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(launcher)


@pytest.fixture
def isolated_data(qapp, monkeypatch, tmp_path):
    for key in ("LIFEOS_DATABASE_URL", "LIFEOS_LOG_MAX_BYTES", "LIFEOS_LOG_BACKUP_COUNT"):
        monkeypatch.delenv(key, raising=False)
    data = tmp_path / "测试 数据"
    monkeypatch.setenv("LIFEOS_DATA_DIR", str(data))
    get_settings.cache_clear()
    launches = []
    errors = []
    monkeypatch.setattr(lifeos.app, "main", lambda: launches.append(True) or 0)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args))
    yield data, launches, errors
    get_settings.cache_clear()


def _answer(monkeypatch, value):
    prompts = []

    def question(*args):
        prompts.append(args)
        return value

    monkeypatch.setattr(QMessageBox, "question", question)
    return prompts


def _version(path):
    connection = sqlite3.connect(path)
    try:
        return connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        connection.close()


def _old_database(data):
    command.upgrade(Config(str(_PROJECT / "alembic.ini")), "0001_app_settings")
    database = data / "lifeos.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "INSERT INTO app_settings(key, value, updated_at) VALUES (?, ?, ?)",
            ("test_key", "test_value", "2026-01-01"),
        )
        connection.commit()
    finally:
        connection.close()
    return database


def test_cancel_fresh_initialization_creates_no_database(isolated_data, monkeypatch):
    data, launches, errors = isolated_data
    prompts = _answer(monkeypatch, QMessageBox.StandardButton.No)
    assert launcher.main() == 0
    assert len(prompts) == 1
    assert not data.exists()
    assert launches == [] and errors == []


def test_confirm_fresh_initialization_creates_latest_schema(isolated_data, monkeypatch):
    data, launches, errors = isolated_data
    prompts = _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    assert launcher.main() == 0
    assert len(prompts) == 1
    assert _version(data / "lifeos.sqlite3") == head_revision()
    assert launches == [True] and errors == []


def test_cancel_existing_upgrade_leaves_old_database_unchanged(isolated_data, monkeypatch):
    data, launches, errors = isolated_data
    database = _old_database(data)
    prompts = _answer(monkeypatch, QMessageBox.StandardButton.No)
    assert launcher.main() == 0
    assert len(prompts) == 1
    assert _version(database) == "0001_app_settings"
    assert not list(data.glob("*.bak"))
    assert launches == [] and errors == []


def test_confirm_existing_upgrade_preserves_settings_and_backup(isolated_data, monkeypatch):
    data, launches, errors = isolated_data
    database = _old_database(data)
    prompts = _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    assert launcher.main() == 0
    assert len(prompts) == 1 and _version(database) == head_revision()
    backups = list(data.glob("lifeos.sqlite3.before-upgrade-*.bak"))
    assert len(backups) == 1 and _version(backups[0]) == "0001_app_settings"
    for path in (database, backups[0]):
        connection = sqlite3.connect(path)
        try:
            assert connection.execute(
                "SELECT value FROM app_settings WHERE key='test_key'"
            ).fetchone() == ("test_value",)
        finally:
            connection.close()
    assert launches == [True] and errors == []


def test_unknown_existing_version_refuses_upgrade(isolated_data, monkeypatch):
    data, launches, errors = isolated_data
    database = _old_database(data)
    connection = sqlite3.connect(database)
    try:
        connection.execute("UPDATE alembic_version SET version_num='unknown_revision'")
        connection.commit()
    finally:
        connection.close()
    prompts = _answer(monkeypatch, QMessageBox.StandardButton.Yes)
    assert launcher.main() == 1
    assert not prompts and not launches and len(errors) == 1
    assert _version(database) == "unknown_revision"
    assert not list(data.glob("*.bak"))
