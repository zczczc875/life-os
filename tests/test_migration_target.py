"""Tests for migration target resolution (review feedback from A).

Two failure modes are covered:

* A broken configuration must abort the migration instead of silently falling
  back to the default location.
* Migrations and the application must always agree on the database file, so a
  schema is never created in a database the app does not open.

All tests use temporary directories and never touch the real data directory.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from lifeos.config.settings import Settings, get_settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.infrastructure.database.repository import SettingsRepository
from lifeos.infrastructure.database.url import (
    DEFAULT_DATABASE_FILENAME,
    MigrationTargetError,
    default_target,
    resolve_target,
)
from tests._helpers import head_revision

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / "migrations" / "env.py"


def _settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir)


def _load_env_module(monkeypatch, x_arguments=None, attributes=None):
    """Execute migrations/env.py far enough to call its resolver.

    env.py runs migrations at import time, so the Alembic context is stubbed to
    report offline mode and then intercepted; this exercises the real
    resolution code without touching a database.
    """
    captured: dict[str, object] = {}

    class _Context:
        config = SimpleNamespace(
            config_file_name=None,
            attributes=dict(attributes or {}),
        )

        @staticmethod
        def get_x_argument(as_dictionary=False):
            return dict(x_arguments or {}) if as_dictionary else []

        @staticmethod
        def is_offline_mode():
            return True

        @staticmethod
        def configure(**kwargs):
            captured["url"] = kwargs.get("url")
            raise _StopEnv

        @staticmethod
        def begin_transaction():  # pragma: no cover - never reached
            raise AssertionError("migrations must not run in this test")

    class _StopEnv(Exception):
        """Stops env.py once the target has been resolved."""

    monkeypatch.setitem(sys.modules, "alembic", SimpleNamespace(context=_Context))
    monkeypatch.setattr("alembic.context", _Context, raising=False)

    try:
        runpy.run_path(str(ENV_PATH), run_name="lifeos_env_under_test")
    except _StopEnv:
        return captured
    return captured


def test_broken_configuration_aborts_instead_of_using_the_default(monkeypatch):
    """An invalid config must raise, not quietly migrate %LOCALAPPDATA%."""
    monkeypatch.setenv("LIFEOS_LOG_MAX_BYTES", "not-a-number")
    get_settings.cache_clear()
    try:
        with pytest.raises(MigrationTargetError, match="configuration is invalid"):
            _load_env_module(monkeypatch)
    finally:
        get_settings.cache_clear()


def test_the_abort_message_names_the_real_cause(monkeypatch):
    """The operator must learn what to fix, not just that something failed."""
    monkeypatch.setenv("LIFEOS_LOG_MAX_BYTES", "not-a-number")
    get_settings.cache_clear()
    try:
        with pytest.raises(MigrationTargetError) as info:
            _load_env_module(monkeypatch)
        assert "refusing to migrate" in str(info.value)
        assert "log_max_bytes" in str(info.value).lower()
    finally:
        get_settings.cache_clear()


def test_an_invalid_explicit_url_is_rejected(monkeypatch):
    """A malformed -x url= must abort rather than fall back to settings."""
    with pytest.raises(MigrationTargetError, match="-x url"):
        _load_env_module(monkeypatch, x_arguments={"url": "postgresql://host/db"})


def test_migration_follows_the_configured_data_dir(monkeypatch, tmp_path: Path):
    """env.py must resolve to the same file the application opens."""
    configured = tmp_path / "configured"
    monkeypatch.setenv("LIFEOS_DATA_DIR", str(configured))
    get_settings.cache_clear()
    try:
        captured = _load_env_module(monkeypatch)
        resolved = str(captured["url"])

        expected = resolve_target(get_settings()).url_string
        assert resolved == expected
        assert resolved != default_target().url_string
    finally:
        get_settings.cache_clear()


def test_migration_and_application_agree_on_the_database_file(tmp_path: Path):
    """The end-to-end guarantee behind A's feedback.

    Migrate through the application entry point, then open the configured
    database independently: the table created by the migration must be there.
    """
    import sqlite3

    settings = _settings(tmp_path / "data")
    expected_file = settings.data_dir / DEFAULT_DATABASE_FILENAME

    database = create_database(settings)
    try:
        assert database.path == expected_file
        database.ensure_schema()
        with database.session_scope() as session:
            SettingsRepository(session).set("agreed", "yes")
    finally:
        database.dispose()

    # Read the configured file directly: no stray database may hold the schema.
    connection = sqlite3.connect(expected_file)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"app_settings", "alembic_version"} <= tables
        stored = connection.execute("SELECT value FROM app_settings WHERE key='agreed'").fetchone()
        assert stored == ("yes",)
    finally:
        connection.close()

    siblings = sorted(path.name for path in tmp_path.rglob("*.sqlite3"))
    assert siblings == [DEFAULT_DATABASE_FILENAME], "a second database file was created"


def test_env_no_longer_honours_a_private_url_variable(monkeypatch, tmp_path: Path):
    """LIFEOS_DATABASE_URL used to bypass Settings and split the two paths."""
    configured = tmp_path / "configured"
    monkeypatch.setenv("LIFEOS_DATA_DIR", str(configured))
    monkeypatch.setenv(
        "LIFEOS_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'elsewhere.sqlite3'}"
    )
    get_settings.cache_clear()
    try:
        captured = _load_env_module(monkeypatch)
        assert "elsewhere" not in str(captured["url"])
        assert str(captured["url"]) == resolve_target(get_settings()).url_string
    finally:
        get_settings.cache_clear()


def test_programmatic_target_is_honoured(monkeypatch, tmp_path: Path):
    """ensure_schema passes the application's own target; it must win."""
    chosen = tmp_path / "chosen.sqlite3"
    captured = _load_env_module(
        monkeypatch, attributes={"lifeos_url": f"sqlite+pysqlite:///{chosen}"}
    )
    assert "chosen.sqlite3" in str(captured["url"])


def test_upgrade_reports_the_revision_it_applied(tmp_path: Path):
    """A silent no-op would hide a schema applied to the wrong database."""
    settings = _settings(tmp_path / "data")
    database = create_database(settings)
    try:
        assert database.ensure_schema() == head_revision()
    finally:
        database.dispose()
