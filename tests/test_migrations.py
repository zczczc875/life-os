"""Tests proving that schema evolution is genuinely managed by Alembic.

``docs/DATA_MODEL.md`` requires that "结构演进通过 Alembic 迁移管理". Creating the
first table is not enough evidence: the real requirement is that a *later*
migration stacks onto an existing database and preserves the rows already
stored there, which is exactly what happens when an installed app is upgraded.

These tests generate a throwaway revision at runtime, so no probe migration is
ever committed to ``migrations/versions/``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect

from lifeos.infrastructure.database.engine import create_database
from lifeos.infrastructure.database.models import Base
from lifeos.infrastructure.database.repository import SettingsRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = PROJECT_ROOT / "migrations" / "versions"

_FOLLOW_UP_REVISION = textwrap.dedent(
    '''
    """probe revision used only by the test suite

    Revision ID: {revision}
    Revises: 0001_app_settings
    """
    from __future__ import annotations

    import sqlalchemy as sa
    from alembic import op

    revision = "{revision}"
    down_revision = "0001_app_settings"
    branch_labels = None
    depends_on = None


    def upgrade() -> None:
        with op.batch_alter_table("app_settings") as batch:
            batch.add_column(sa.Column("probe_note", sa.Text(), nullable=True))


    def downgrade() -> None:
        with op.batch_alter_table("app_settings") as batch:
            batch.drop_column("probe_note")
    '''
)


def _settings(data_dir: Path, **extra: object) -> SimpleNamespace:
    return SimpleNamespace(app_version="test-version", data_dir=data_dir, **extra)


@pytest.fixture
def add_follow_up_revision():
    """Return a callable that adds a second revision, removed after the test.

    The revision is written on demand rather than up front: a test must first
    build a database at ``0001`` to represent an already-installed app, and
    only then introduce the newer migration.
    """
    revision = "9999_probe_revision"
    path = VERSIONS_DIR / f"{revision}.py"

    def _add() -> str:
        path.write_text(_FOLLOW_UP_REVISION.format(revision=revision), encoding="utf-8")
        return revision

    try:
        yield _add
    finally:
        path.unlink(missing_ok=True)


def _columns(database) -> list[str]:
    return [column["name"] for column in inspect(database.engine).get_columns("app_settings")]


def test_a_later_migration_stacks_without_losing_data(tmp_path: Path, add_follow_up_revision):
    """Upgrading an installed app must keep the user's existing settings."""
    data_dir = tmp_path / "data"

    # A user already running the shipped version, with real data.
    first = create_database(_settings(data_dir))
    assert first.ensure_schema() == "0001_app_settings"
    with first.session_scope() as session:
        SettingsRepository(session).set("app.locale", "zh-CN")
    assert "probe_note" not in _columns(first)
    first.dispose()

    # A newer build ships one more migration.
    revision = add_follow_up_revision()

    upgraded = create_database(_settings(data_dir))
    try:
        assert upgraded.ensure_schema() == revision
        assert "probe_note" in _columns(upgraded)
        with upgraded.session_scope() as session:
            assert SettingsRepository(session).get("app.locale") == "zh-CN"
    finally:
        upgraded.dispose()


def test_the_added_column_can_be_rolled_back(tmp_path: Path, add_follow_up_revision):
    """A bad release must be reversible without destroying stored settings."""
    from alembic import command
    from alembic.config import Config

    add_follow_up_revision()

    data_dir = tmp_path / "data"
    database = create_database(_settings(data_dir))
    database.ensure_schema()
    with database.session_scope() as session:
        SettingsRepository(session).set("keep", "me")
    assert "probe_note" in _columns(database)
    database.dispose()

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.attributes["lifeos_url"] = f"sqlite+pysqlite:///{data_dir / 'lifeos.sqlite3'}"
    command.downgrade(config, "0001_app_settings")

    verify = create_database(_settings(data_dir))
    try:
        assert "probe_note" not in _columns(verify)
        with verify.session_scope() as session:
            assert SettingsRepository(session).get("keep") == "me"
    finally:
        verify.dispose()


def test_models_and_migrations_do_not_drift(tmp_path: Path):
    """The initial migration must match models.py exactly.

    Autogenerate comparison catches the common mistake of editing a model
    without writing the matching migration, which would make a developer's
    database differ from every installed user's database.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    database = create_database(_settings(tmp_path / "data"))
    try:
        database.ensure_schema()
        with database.engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        assert differences == [], f"models.py and migrations disagree: {differences}"
    finally:
        database.dispose()


def test_only_reviewed_revisions_are_committed():
    """Guard against a stray probe revision being committed by accident."""
    committed = sorted(path.name for path in VERSIONS_DIR.glob("*.py"))
    assert committed == ["0001_app_settings.py"]
