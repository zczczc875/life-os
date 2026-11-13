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
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from lifeos.infrastructure.database.engine import create_database
from lifeos.infrastructure.database.models import Base
from lifeos.infrastructure.database.repository import SettingsRepository
from lifeos.tasks import TaskService, TaskStorageError
from lifeos.tasks.reminders import ReminderService
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
    assert committed == [
        "0001_app_settings.py",
        "0002_tasks.py",
        "0003_task_due_on.py",
        "0004_task_due_time.py",
        "0005_task_reminders.py",
        "0006_advance_reminders.py",
    ]


def test_deadline_time_migration_preserves_dated_and_undated_tasks(tmp_path: Path):
    from alembic import command

    database_file = tmp_path / "lifeos.sqlite3"
    config = alembic_config(database_file)
    command.upgrade(config, "0003_task_due_on")

    database = create_database(_settings(tmp_path))
    try:
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tasks (id, title, status, created_at, completed_at, due_on)"
                    " VALUES ('dated', '报告', 'completed', '2026-11-10 08:00:00',"
                    " '2026-11-11 08:00:00', '2026-11-12'),"
                    " ('undated', '整理桌面', 'pending', '2026-11-10 09:00:00', NULL, NULL)"
                )
            )

        service = TaskService(database)
        with pytest.raises(TaskStorageError, match="迁移"):
            service.list_tasks()

        assert database.ensure_schema() == HEAD_REVISION
        undated, dated = service.list_tasks()
        assert (undated.id, undated.title, undated.status) == ("undated", "整理桌面", "pending")
        assert undated.due_on is undated.due_time is None
        assert (dated.id, dated.title, dated.status) == ("dated", "报告", "completed")
        assert dated.completed_at is not None
        assert (dated.due_on, dated.due_time) == (date(2026, 11, 12), None)

        with (
            pytest.raises(IntegrityError, match="ck_tasks_due_time_date"),
            database.engine.begin() as connection,
        ):
            connection.execute(text("UPDATE tasks SET due_time = '09:00:00' WHERE id = 'undated'"))
        timed = service.create_task("签到", due_on=date(2026, 11, 13), due_time=time(17, 30))
        assert timed in service.list_tasks()
    finally:
        database.dispose()

    command.downgrade(config, "0003_task_due_on")
    downgraded = create_database(_settings(tmp_path))
    try:
        with downgraded.engine.connect() as connection:
            rows = connection.execute(text("SELECT id, due_on FROM tasks")).all()
        assert dict(rows) == {"dated": "2026-11-12", "undated": None, timed.id: "2026-11-13"}
        assert "due_time" not in {
            col["name"] for col in inspect(downgraded.engine).get_columns("tasks")
        }
    finally:
        downgraded.dispose()


def test_reminder_migration_preserves_existing_deadlines_and_defaults_off(tmp_path: Path):
    from alembic import command

    database_file = tmp_path / "lifeos.sqlite3"
    config = alembic_config(database_file)
    command.upgrade(config, "0004_task_due_time")
    database = create_database(_settings(tmp_path))
    try:
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tasks (id, title, status, created_at, due_on, due_time)"
                    " VALUES ('old', '已有任务', 'pending', '2026-11-11 08:00:00',"
                    " '2026-11-12', '09:00:00.000000')"
                )
            )
        assert database.ensure_schema() == HEAD_REVISION

        reminders = ReminderService(database)
        (task,) = TaskService(database).list_tasks()
        assert (task.id, task.title, task.due_on, task.due_time) == (
            "old",
            "已有任务",
            date(2026, 11, 12),
            time(9),
        )
        now = datetime(2026, 11, 12, 9)
        assert reminders.enabled() is False
        assert reminders.claim_due(now) == []
        reminders.set_enabled(True)
        assert reminders.claim_due(now) == [task]
        assert reminders.claim_due(now) == []
    finally:
        database.dispose()


def test_advance_migration_keeps_due_claims_and_disables_advance_by_default(tmp_path: Path):
    from alembic import command

    config = alembic_config(tmp_path / "lifeos.sqlite3")
    command.upgrade(config, "0005_task_reminders")
    database = create_database(_settings(tmp_path))
    try:
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tasks (id, title, status, created_at, due_on, due_time,"
                    " reminder_claimed_at) VALUES ('old', '已有任务', 'pending',"
                    " '2026-11-11 08:00:00', '2026-11-12', '09:00:00.000000',"
                    " '2026-11-12 01:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO app_settings (key, value, updated_at) VALUES"
                    " ('reminders.due_enabled', 'true', '2026-11-11 08:00:00')"
                )
            )
        assert database.ensure_schema() == "0006_advance_reminders"

        reminders = ReminderService(database)
        (task,) = TaskService(database).list_tasks()
        assert (task.id, task.due_on, task.due_time) == ("old", date(2026, 11, 12), time(9))
        assert reminders.enabled()
        assert reminders.advance_minutes() == ()
        with database.engine.connect() as connection:
            assert connection.execute(
                text("SELECT reminder_claimed_at, advance_reminder_mask FROM tasks")
            ).one() == ("2026-11-12 01:00:00", 0)
        assert reminders.claim_reminders(datetime(2026, 11, 12, 9)) == ([], [])
        reminders.set_advance_minutes([15])
        assert reminders.claim_reminders(datetime(2026, 11, 12, 8, 50)) == ([], [])
    finally:
        database.dispose()


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
