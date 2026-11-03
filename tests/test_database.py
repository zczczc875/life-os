"""Tests for the SQLite data layer.

Every test uses a temporary data directory, so the real
``%LOCALAPPDATA%\\LifeOS\\data`` database is never touched.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, text

from lifeos.infrastructure.database.engine import (
    DEFAULT_DATABASE_FILENAME,
    Database,
    DatabaseError,
    create_database,
)
from lifeos.infrastructure.database.models import AppSetting, Base
from lifeos.infrastructure.database.repository import SettingsRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _settings(data_dir: Path, **extra: object) -> SimpleNamespace:
    """Build a Settings stand-in exposing only the fields C relies on."""
    return SimpleNamespace(app_version="test-version", data_dir=data_dir, **extra)


@pytest.fixture
def database(tmp_path: Path):
    """Yield a database whose schema is created from the declarative metadata."""
    instance = create_database(_settings(tmp_path / "data"))
    Base.metadata.create_all(instance.engine)
    try:
        yield instance
    finally:
        instance.dispose()


@pytest.fixture
def repository(database: Database):
    """Yield a repository bound to a session that is closed afterwards."""
    with database.session_scope() as session:
        yield SettingsRepository(session)


def test_create_database_uses_data_dir_and_creates_it(tmp_path: Path):
    data_dir = tmp_path / "nested" / "data"
    assert not data_dir.exists()

    instance = create_database(_settings(data_dir))
    try:
        assert data_dir.is_dir()
        assert instance.path == data_dir / DEFAULT_DATABASE_FILENAME
    finally:
        instance.dispose()


def test_create_database_honours_explicit_overrides(tmp_path: Path):
    custom = create_database(_settings(tmp_path / "data", database_filename="custom.sqlite3"))
    try:
        assert custom.path.name == "custom.sqlite3"
    finally:
        custom.dispose()

    explicit_path = tmp_path / "elsewhere" / "explicit.sqlite3"
    explicit = create_database(_settings(tmp_path / "data", database_path=explicit_path))
    try:
        assert explicit.path == explicit_path
        assert explicit_path.parent.is_dir()
    finally:
        explicit.dispose()


def test_create_database_requires_a_path():
    with pytest.raises(DatabaseError, match="data_dir"):
        create_database(SimpleNamespace(app_version="test-version"))


def test_importing_the_module_creates_nothing(tmp_path: Path):
    """Import must not create the data directory; only create_database may."""
    data_dir = tmp_path / "unused"
    assert "lifeos.infrastructure.database.engine" in sys.modules
    assert not data_dir.exists()


def test_check_connection_reports_true_for_a_usable_database(database: Database):
    assert database.check_connection() is True


def test_check_connection_reports_false_when_the_file_is_unusable(tmp_path: Path):
    broken = tmp_path / "data" / "broken.sqlite3"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"this is not a sqlite database")

    instance = create_database(_settings(tmp_path / "data", database_path=broken))
    try:
        assert instance.check_connection() is False
    finally:
        instance.dispose()


def test_dispose_is_idempotent(tmp_path: Path):
    instance = create_database(_settings(tmp_path / "data"))
    instance.dispose()
    instance.dispose()


def test_is_migrated_distinguishes_an_empty_file_from_a_migrated_one(tmp_path: Path):
    """A fresh SQLite file connects fine but has no tables yet."""
    instance = create_database(_settings(tmp_path / "data"))
    try:
        assert instance.check_connection() is True
        assert instance.is_migrated() is False

        Base.metadata.create_all(instance.engine)
        assert instance.is_migrated() is True
    finally:
        instance.dispose()


def test_settings_can_be_inserted_queried_and_updated(repository: SettingsRepository):
    assert repository.get("theme") is None
    assert repository.get("theme", "light") == "light"
    assert repository.exists("theme") is False

    repository.set("theme", "dark")
    assert repository.get("theme") == "dark"
    assert repository.exists("theme") is True

    repository.set("theme", "light")
    assert repository.get("theme") == "light"
    assert repository.all() == {"theme": "light"}


def test_set_rejects_an_empty_key(repository: SettingsRepository):
    with pytest.raises(ValueError, match="non-empty"):
        repository.set("", "value")


def test_delete_reports_whether_a_row_was_removed(repository: SettingsRepository):
    repository.set("obsolete", "1")
    repository._session.flush()

    assert repository.delete("obsolete") is True
    assert repository.delete("obsolete") is False
    assert repository.get("obsolete") is None


def test_all_returns_settings_ordered_by_key(repository: SettingsRepository):
    repository.set("b", "2")
    repository.set("a", "1")
    repository.set("c", "3")

    assert list(repository.all()) == ["a", "b", "c"]


def test_updated_at_advances_on_update(repository: SettingsRepository):
    row = repository.set("key", "first")
    repository._session.flush()
    created = row.updated_at

    repository.set("key", "second")
    repository._session.flush()

    assert row.updated_at >= created


def test_settings_survive_a_simulated_restart(tmp_path: Path):
    data_dir = tmp_path / "data"

    first = create_database(_settings(data_dir))
    Base.metadata.create_all(first.engine)
    with first.session_scope() as session:
        SettingsRepository(session).set("app.locale", "zh-CN")
    first.dispose()

    second = create_database(_settings(data_dir))
    try:
        assert second.check_connection() is True
        with second.session_scope() as session:
            assert SettingsRepository(session).get("app.locale") == "zh-CN"
    finally:
        second.dispose()


def test_session_scope_rolls_back_on_error(database: Database):
    with pytest.raises(RuntimeError, match="boom"), database.session_scope() as session:
        SettingsRepository(session).set("partial", "value")
        raise RuntimeError("boom")

    with database.session_scope() as session:
        assert SettingsRepository(session).get("partial") is None


def test_duplicate_keys_are_rejected_by_the_primary_key(database: Database):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), database.session_scope() as session:
        session.add(AppSetting(key="dup", value="a"))
        session.add(AppSetting(key="dup", value="b"))
        session.flush()


def test_migration_creates_the_expected_schema_on_an_empty_database(tmp_path: Path):
    """Run the real Alembic migration and inspect the resulting schema."""
    from alembic import command
    from alembic.config import Config

    target = tmp_path / "data" / "migrated.sqlite3"
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.cmd_opts = SimpleNamespace(x=[f"url=sqlite+pysqlite:///{target}"])

    command.upgrade(config, "head")

    instance = create_database(_settings(tmp_path / "data", database_path=target))
    try:
        inspector = inspect(instance.engine)
        assert "app_settings" in inspector.get_table_names()

        columns = {column["name"]: column for column in inspector.get_columns("app_settings")}
        assert set(columns) == {"key", "value", "updated_at"}
        assert columns["value"]["nullable"] is False
        assert columns["updated_at"]["nullable"] is False
        assert inspector.get_pk_constraint("app_settings")["constrained_columns"] == ["key"]
        assert instance.is_migrated() is True

        with instance.engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "0001_app_settings"

        with instance.session_scope() as session:
            SettingsRepository(session).set("migrated", "yes")
        with instance.session_scope() as session:
            assert SettingsRepository(session).get("migrated") == "yes"
    finally:
        instance.dispose()

    command.downgrade(config, "base")

    verify = create_database(_settings(tmp_path / "data", database_path=target))
    try:
        assert "app_settings" not in inspect(verify.engine).get_table_names()
        assert verify.is_migrated() is False
    finally:
        verify.dispose()
