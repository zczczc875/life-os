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
from tests._helpers import alembic_config, head_revision

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = PROJECT_ROOT / "migrations" / "versions"

_FOLLOW_UP_REVISION = textwrap.dedent(
    '''
    """probe revision used only by the test suite

    Revision ID: {revision}
    Revises: {parent}
    """
    from __future__ import annotations

    import sqlalchemy as sa
    from alembic import op

    revision = "{revision}"
    down_revision = "{parent}"
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

#: Latest published revision; the probe stacks on top of it.
HEAD_REVISION = head_revision()


def _settings(data_dir: Path, **extra: object) -> SimpleNamespace:
    return SimpleNamespace(app_version="test-version", data_dir=data_dir, **extra)


@pytest.fixture
def add_follow_up_revision(tmp_path: Path):
    """Yield a callable that adds a probe revision inside a temporary copy.

    The migrations directory is copied into ``tmp_path`` so the test never
    writes into the source tree: a crashed run cannot leave a stray revision
    behind, and parallel runs cannot collide on a fixed filename
    (``docs/DELIVERY_PHASE1.md`` leftover item 1).
    """
    import shutil

    scripts = tmp_path / "migrations"
    shutil.copytree(PROJECT_ROOT / "migrations", scripts)
    revision = "9999_probe_revision"

    def _add() -> str:
        (scripts / "versions" / f"{revision}.py").write_text(
            _FOLLOW_UP_REVISION.format(revision=revision, parent=HEAD_REVISION),
            encoding="utf-8",
        )
        return revision

    _add.script_location = str(scripts)  # type: ignore[attr-defined]
    yield _add


def _config_for(scripts: str, database_path: Path):
    """Build an Alembic config bound to a temporary scripts directory."""
    return alembic_config(database_path, script_location=scripts)


def _columns(database) -> list[str]:
    return [column["name"] for column in inspect(database.engine).get_columns("app_settings")]


def test_a_later_migration_stacks_without_losing_data(tmp_path: Path, add_follow_up_revision):
    """Upgrading an installed app must keep the user's existing settings."""
    from alembic import command

    data_dir = tmp_path / "data"
    database_file = data_dir / "lifeos.sqlite3"
    scripts = add_follow_up_revision.script_location

    # A user already running the shipped version, with real data.
    command.upgrade(_config_for(scripts, database_file), "head")
    first = create_database(_settings(data_dir))
    with first.session_scope() as session:
        SettingsRepository(session).set("app.locale", "zh-CN")
    assert "probe_note" not in _columns(first)
    first.dispose()

    # A newer build ships one more migration.
    revision = add_follow_up_revision()
    command.upgrade(_config_for(scripts, database_file), "head")

    upgraded = create_database(_settings(data_dir))
    try:
        assert "probe_note" in _columns(upgraded)
        with upgraded.session_scope() as session:
            assert SettingsRepository(session).get("app.locale") == "zh-CN"

        from alembic.migration import MigrationContext

        with upgraded.engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() == revision
    finally:
        upgraded.dispose()


def test_the_added_column_can_be_rolled_back(tmp_path: Path, add_follow_up_revision):
    """A bad release must be reversible without destroying stored settings."""
    from alembic import command

    add_follow_up_revision()
    scripts = add_follow_up_revision.script_location

    data_dir = tmp_path / "data"
    database_file = data_dir / "lifeos.sqlite3"
    command.upgrade(_config_for(scripts, database_file), "head")

    database = create_database(_settings(data_dir))
    with database.session_scope() as session:
        SettingsRepository(session).set("keep", "me")
    assert "probe_note" in _columns(database)
    database.dispose()

    command.downgrade(_config_for(scripts, database_file), HEAD_REVISION)

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
    assert committed == ["0001_app_settings.py", "0002_tasks.py", "0003_task_due_on.py"]


def test_probe_revisions_never_touch_the_source_tree(tmp_path: Path, add_follow_up_revision):
    """The probe must live in a temporary copy, not in migrations/versions.

    Covers leftover item 1 in docs/DELIVERY_PHASE1.md: a crashed test run must
    not be able to leave a stray revision in the repository.
    """
    revision = add_follow_up_revision()

    assert not (VERSIONS_DIR / f"{revision}.py").exists()
    probe = Path(add_follow_up_revision.script_location) / "versions" / f"{revision}.py"
    assert probe.is_file()
    assert VERSIONS_DIR not in probe.parents
