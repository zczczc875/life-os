"""Tests for migration state detection.

``docs/PHASE2_TASKS.md`` requires that a missing table is reported rather than
silently created or mistaken for a working database. Checking a single table's
existence was not enough: a Phase 1 database predating the ``tasks`` table
looked migrated and then failed with "no such table".
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lifeos.infrastructure.database.engine import create_database
from tests._helpers import alembic_config, head_revision


def _settings(data_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(app_version="test-version", data_dir=data_dir)


def test_is_migrated_is_false_on_an_empty_database(tmp_path: Path):
    instance = create_database(_settings(tmp_path / "data"))
    try:
        assert instance.check_connection() is True
        assert instance.current_revision() is None
        assert instance.is_migrated() is False
    finally:
        instance.dispose()


def test_is_migrated_is_false_on_an_outdated_database(tmp_path: Path):
    """A database left on an older revision must not look migrated."""
    from alembic import command

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    database_file = data_dir / "lifeos.sqlite3"
    command.upgrade(alembic_config(database_file), "0001_app_settings")

    instance = create_database(_settings(data_dir))
    try:
        assert instance.current_revision() == "0001_app_settings"
        assert instance.is_migrated() is False, "an outdated database must not look migrated"

        instance.ensure_schema()
        assert instance.current_revision() == head_revision()
        assert instance.is_migrated() is True
    finally:
        instance.dispose()


def test_task_operations_fail_loudly_on_an_outdated_database(tmp_path: Path):
    """Startup must detect this before task operations are attempted."""
    from alembic import command
    from sqlalchemy.exc import OperationalError

    from lifeos.infrastructure.database.task_repository import TaskRepository

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    command.upgrade(alembic_config(data_dir / "lifeos.sqlite3"), "0001_app_settings")

    instance = create_database(_settings(data_dir))
    try:
        assert instance.is_migrated() is False

        # Without the check above, this is the error the user would hit.
        try:
            with instance.session_scope() as session:
                TaskRepository(session).add("task")
        except OperationalError as error:
            assert "no such table" in str(error)
        else:  # pragma: no cover - would mean the table appeared on its own
            raise AssertionError("tasks table must not exist before migration")
    finally:
        instance.dispose()


def test_is_migrated_is_true_only_at_head(tmp_path: Path):
    instance = create_database(_settings(tmp_path / "data"))
    try:
        instance.ensure_schema()
        assert instance.current_revision() == head_revision()
        assert instance.is_migrated() is True
    finally:
        instance.dispose()
