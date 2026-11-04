"""Contract tests against D's real Settings implementation.

Earlier database tests use a ``SimpleNamespace`` stand-in, which cannot prove
the real ``lifeos.config.settings.Settings`` satisfies what ``create_database``
expects. These tests import D's actual module, so a future change to the
Settings fields breaks here instead of at integration time.

All tests use temporary directories and never touch the real data directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lifeos.config.settings import Settings, get_settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.infrastructure.database.repository import SettingsRepository
from lifeos.infrastructure.database.url import DEFAULT_DATABASE_FILENAME, resolve_target
from tests._helpers import head_revision


def test_real_settings_exposes_the_fields_the_database_needs():
    """The frozen contract requires app_version: str and data_dir: Path."""
    settings = Settings(data_dir=Path("C:/tmp/lifeos-contract"))

    assert isinstance(settings.app_version, str)
    assert settings.app_version
    assert isinstance(settings.data_dir, Path)


def test_create_database_accepts_the_real_settings_object(tmp_path: Path):
    """End-to-end: D's Settings drives C's engine, migration and repository."""
    settings = Settings(data_dir=tmp_path / "data")

    database = create_database(settings)
    try:
        assert database.path == settings.data_dir / DEFAULT_DATABASE_FILENAME
        assert database.ensure_schema() == head_revision()
        assert database.check_connection() is True

        with database.session_scope() as session:
            SettingsRepository(session).set("app.locale", "zh-CN")
        with database.session_scope() as session:
            assert SettingsRepository(session).get("app.locale") == "zh-CN"
    finally:
        database.dispose()


def test_env_override_reaches_the_database_location(tmp_path: Path, monkeypatch):
    """LIFEOS_DATA_DIR must move the database, so tests never hit real data."""
    override = tmp_path / "overridden"
    monkeypatch.setenv("LIFEOS_DATA_DIR", str(override))
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.data_dir == override
        assert resolve_target(settings).path == override / DEFAULT_DATABASE_FILENAME
    finally:
        get_settings.cache_clear()


def test_startup_sequence_matches_the_composition_root(tmp_path: Path):
    """Mirror app.py's order: settings -> logging -> database -> status.

    The window itself is out of scope here; this guards the parts C depends on.
    """
    from lifeos.infrastructure.logging.setup import setup_logging

    settings = Settings(data_dir=tmp_path / "data")
    setup_logging(settings)

    database = create_database(settings)
    try:
        # app.py does not call ensure_schema yet; see DELIVERY_C_DATABASE.md.
        if not database.is_migrated():
            database.ensure_schema()
        assert database.check_connection() is True
    finally:
        database.dispose()

    assert (settings.data_dir / DEFAULT_DATABASE_FILENAME).is_file()


def test_settings_cache_is_not_shared_across_overrides(monkeypatch, tmp_path: Path):
    """get_settings is lru_cached; callers must clear it when overriding."""
    get_settings.cache_clear()
    monkeypatch.setenv("LIFEOS_DATA_DIR", str(tmp_path / "first"))
    first = get_settings()

    monkeypatch.setenv("LIFEOS_DATA_DIR", str(tmp_path / "second"))
    cached = get_settings()
    assert cached.data_dir == first.data_dir, "cache should return the first value"

    get_settings.cache_clear()
    refreshed = get_settings()
    assert refreshed.data_dir == tmp_path / "second"
    get_settings.cache_clear()


@pytest.mark.parametrize("missing", ["database_path", "database_filename"])
def test_optional_overrides_are_absent_but_tolerated(missing: str, tmp_path: Path):
    """C supports optional overrides; D's Settings omits them, which is fine."""
    settings = Settings(data_dir=tmp_path / "data")
    assert not hasattr(settings, missing)

    database = create_database(settings)
    try:
        assert database.path.name == DEFAULT_DATABASE_FILENAME
    finally:
        database.dispose()
