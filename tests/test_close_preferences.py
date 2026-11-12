"""Verify durable window-close settings against migrated SQLite."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lifeos.config.close_preferences import ClosePreferences, ClosePreferencesError
from lifeos.config.settings import Settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.infrastructure.database.repository import SettingsRepository


@pytest.fixture
def database(tmp_path):
    db = create_database(Settings(data_dir=tmp_path))
    db.ensure_schema()
    try:
        yield db
    finally:
        db.dispose()


def test_remembered_action_survives_restart_and_can_be_reset(database):
    preferences = ClosePreferences(database)
    assert preferences.get() is None

    with database.session_scope() as session:
        SettingsRepository(session).set("reminders.due_enabled", "true")
    preferences.set("tray")
    database.dispose()

    restarted = create_database(Settings(data_dir=database.path.parent))
    try:
        reopened = ClosePreferences(restarted)
        assert reopened.get() == "tray"
        reopened.set("exit")
        assert reopened.get() == "exit"
        reopened.set(None)
        assert reopened.get() is None
        with restarted.session_scope() as session:
            assert SettingsRepository(session).all() == {"reminders.due_enabled": "true"}
    finally:
        restarted.dispose()


def test_unknown_saved_action_defaults_to_asking(database):
    with database.session_scope() as session:
        SettingsRepository(session).set("window.close_action", "unknown")
    assert ClosePreferences(database).get() is None


def test_concurrent_first_writes_leave_one_saved_action(database):
    start = Barrier(2)

    def save(action):
        start.wait(timeout=5)
        ClosePreferences(database).set(action)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(save, "tray")
        second = executor.submit(save, "exit")
        first.result()
        second.result()
    assert ClosePreferences(database).get() in {"tray", "exit"}


def test_failed_write_leaves_previous_action_available(database, monkeypatch):
    preferences = ClosePreferences(database)
    preferences.set("tray")

    def fail_commit(_session):
        raise SQLAlchemyError("simulated commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        with pytest.raises(ClosePreferencesError):
            preferences.set("exit")
    assert preferences.get() == "tray"
