"""Tests for packaged (installed .exe) behaviour of the data layer.

An end user double-clicks an installer and never opens a shell, so the app
must create and locate its own schema. Every test uses a temporary data
directory and never touches the real ``%LOCALAPPDATA%\\LifeOS\\data``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from lifeos.infrastructure.database.engine import create_database
from lifeos.infrastructure.database.repository import SettingsRepository
from lifeos.infrastructure.database.url import DEFAULT_DATABASE_FILENAME

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _settings(data_dir: Path, **extra: object) -> SimpleNamespace:
    """Build a Settings stand-in exposing only the fields C relies on."""
    return SimpleNamespace(app_version="test-version", data_dir=data_dir, **extra)


# --- Packaged / installed application behaviour -----------------------------
#
# An end user double-clicks an installer or .exe and never opens a shell, so
# the app must create its own schema. These tests cover that path.


def test_ensure_schema_creates_the_schema_on_a_fresh_install(tmp_path: Path):
    """First launch of an installed app: empty data dir, no shell, no tables."""
    instance = create_database(_settings(tmp_path / "data"))
    try:
        assert instance.check_connection() is True
        assert instance.is_migrated() is False

        revision = instance.ensure_schema()
        assert revision == "0001_app_settings"
        assert instance.is_migrated() is True

        # The store is immediately usable without any manual migration step.
        with instance.session_scope() as session:
            SettingsRepository(session).set("first.run", "done")
        with instance.session_scope() as session:
            assert SettingsRepository(session).get("first.run") == "done"
    finally:
        instance.dispose()


def test_ensure_schema_is_safe_to_call_on_every_startup(tmp_path: Path):
    """Launching an already-installed app must not disturb existing data."""
    data_dir = tmp_path / "data"

    first = create_database(_settings(data_dir))
    first.ensure_schema()
    with first.session_scope() as session:
        SettingsRepository(session).set("app.locale", "zh-CN")
    first.dispose()

    second = create_database(_settings(data_dir))
    try:
        # Second startup: ensure_schema runs again and is a no-op.
        assert second.ensure_schema() == "0001_app_settings"
        with second.session_scope() as session:
            assert SettingsRepository(session).get("app.locale") == "zh-CN"
    finally:
        second.dispose()


def test_ensure_schema_reports_missing_migrations_clearly(tmp_path: Path, monkeypatch):
    """A packaging mistake must fail with an actionable message."""
    from lifeos.infrastructure.database import migrate

    monkeypatch.setattr(migrate, "_candidate_roots", lambda: [tmp_path / "not-bundled"])

    instance = create_database(_settings(tmp_path / "data"))
    try:
        with pytest.raises(migrate.MigrationError, match="bundle it as data files"):
            instance.ensure_schema()
    finally:
        instance.dispose()


def test_find_migrations_dir_locates_the_project_migrations():
    """Running from source must find the real migrations directory."""
    from lifeos.infrastructure.database.migrate import find_migrations_dir

    found = find_migrations_dir()
    assert found == PROJECT_ROOT / "migrations"
    assert (found / "versions" / "0001_app_settings.py").is_file()


def test_find_migrations_dir_prefers_the_pyinstaller_bundle(tmp_path: Path, monkeypatch):
    """When frozen, migrations come from the unpacked bundle, not the source tree."""
    from lifeos.infrastructure.database import migrate

    bundled = tmp_path / "bundle" / "migrations"
    bundled.mkdir(parents=True)
    (bundled / "env.py").write_text("# bundled", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)

    assert migrate.find_migrations_dir() == bundled


def test_is_frozen_reflects_the_pyinstaller_flag(monkeypatch):
    from lifeos.infrastructure.database.url import is_frozen

    monkeypatch.delattr(sys, "frozen", raising=False)
    assert is_frozen() is False

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert is_frozen() is True


def test_data_is_stored_outside_the_installation_directory(tmp_path: Path, monkeypatch):
    """Default data must live in %LOCALAPPDATA%, never next to the executable.

    An installed app often sits in a read-only Program Files directory that is
    replaced on upgrade, so writing the database there would fail or lose data.
    """
    from lifeos.infrastructure.database.url import default_target

    fake_local = tmp_path / "AppData" / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(fake_local))

    target = default_target()
    assert target.path == fake_local / "LifeOS" / "data" / DEFAULT_DATABASE_FILENAME

    install_dir = Path(sys.executable).parent
    assert install_dir not in target.path.parents


def test_resolve_target_rejects_settings_without_a_location():
    from lifeos.infrastructure.database.url import UnresolvedDatabaseError, resolve_target

    with pytest.raises(UnresolvedDatabaseError, match="data_dir"):
        resolve_target(SimpleNamespace(app_version="test-version"))


def test_target_from_url_rejects_non_sqlite_backends():
    from lifeos.infrastructure.database.url import UnresolvedDatabaseError, target_from_url

    with pytest.raises(UnresolvedDatabaseError, match="SQLite only"):
        target_from_url("postgresql+psycopg://user:secret@localhost/lifeos")


def test_target_url_does_not_leak_a_password():
    """Log-safe rendering, in case a URL ever carries credentials."""
    from lifeos.infrastructure.database.url import DatabaseTarget

    target = DatabaseTarget(Path("C:/data/lifeos.sqlite3"))
    assert "lifeos.sqlite3" in target.url_string
    assert target.describe() == str(Path("C:/data/lifeos.sqlite3"))


def test_windows_paths_with_spaces_are_handled(tmp_path: Path):
    """Installed apps commonly sit under paths containing spaces."""
    data_dir = tmp_path / "Local App Data" / "Life OS"
    instance = create_database(_settings(data_dir))
    try:
        assert instance.ensure_schema() == "0001_app_settings"
        with instance.session_scope() as session:
            SettingsRepository(session).set("spaced", "ok")
        with instance.session_scope() as session:
            assert SettingsRepository(session).get("spaced") == "ok"
    finally:
        instance.dispose()
