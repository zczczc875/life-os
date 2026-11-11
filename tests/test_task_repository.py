"""Tests for the Phase 2 ``tasks`` table and :class:`TaskRepository`.

Every test runs against an isolated temporary database created by the real
Alembic migration, so the shipped schema - not just the declarative model - is
what gets exercised. The real data directory is never touched.

The repository never commits: the task service owns transactions through
``Database.session_scope()``. These tests therefore manage scopes explicitly.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from lifeos.infrastructure.database.engine import create_database
from lifeos.infrastructure.database.models import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_PENDING,
    TaskRecord,
    as_utc,
    to_naive_utc,
)
from lifeos.infrastructure.database.task_repository import TaskRepository, TaskTitleError


def _settings(data_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(app_version="test-version", data_dir=data_dir)


@pytest.fixture
def database(tmp_path: Path):
    """Yield a migrated database backed by a temporary directory."""
    instance = create_database(_settings(tmp_path / "data"))
    instance.ensure_schema()
    try:
        yield instance
    finally:
        instance.dispose()


# --- schema ----------------------------------------------------------------


def test_migration_creates_the_documented_columns(database):
    """The tasks table preserves the Phase 2 fields and adds an optional date."""
    columns = {column["name"]: column for column in inspect(database.engine).get_columns("tasks")}

    assert set(columns) == {
        "id",
        "title",
        "status",
        "created_at",
        "completed_at",
        "due_on",
        "due_time",
    }
    assert columns["id"]["nullable"] is False
    assert columns["title"]["nullable"] is False
    assert columns["status"]["nullable"] is False
    assert columns["created_at"]["nullable"] is False
    assert columns["completed_at"]["nullable"] is True
    assert columns["due_on"]["nullable"] is True
    assert columns["due_time"]["nullable"] is True

    assert inspect(database.engine).get_pk_constraint("tasks")["constrained_columns"] == ["id"]


def test_listing_order_is_supported_by_an_index(database):
    """Newest-first listing should not degrade into a full sort as data grows."""
    indexes = {index["name"] for index in inspect(database.engine).get_indexes("tasks")}
    assert "ix_tasks_created_at_id" in indexes


def test_unknown_status_is_rejected_by_the_database(database):
    """A service bug must not be able to persist an unrenderable status."""
    with pytest.raises(IntegrityError), database.session_scope() as session:
        session.add(
            TaskRecord(
                id="bad-status",
                title="x",
                status="archived",
                created_at=dt.datetime(2026, 1, 1),
            )
        )
        session.flush()


def test_completed_task_must_carry_a_completion_time(database):
    """status and completed_at must stay consistent at the storage layer."""
    with pytest.raises(IntegrityError), database.session_scope() as session:
        session.add(
            TaskRecord(
                id="no-time",
                title="x",
                status=TASK_STATUS_COMPLETED,
                created_at=dt.datetime(2026, 1, 1),
                completed_at=None,
            )
        )
        session.flush()


def test_pending_task_must_not_carry_a_completion_time(database):
    with pytest.raises(IntegrityError), database.session_scope() as session:
        session.add(
            TaskRecord(
                id="early-time",
                title="x",
                status=TASK_STATUS_PENDING,
                created_at=dt.datetime(2026, 1, 1),
                completed_at=dt.datetime(2026, 1, 2),
            )
        )
        session.flush()


def test_duplicate_ids_are_rejected(database):
    with pytest.raises(IntegrityError), database.session_scope() as session:
        repository = TaskRepository(session)
        repository.add("first", task_id="fixed-id")
        repository.add("second", task_id="fixed-id")


# --- creation --------------------------------------------------------------


def test_add_stores_a_pending_task(database):
    with database.session_scope() as session:
        task = TaskRepository(session).add("Write the report")

        assert task.id
        assert task.title == "Write the report"
        assert task.status == TASK_STATUS_PENDING
        assert task.completed_at is None
        assert task.created_at is not None


def test_add_trims_surrounding_whitespace(database):
    with database.session_scope() as session:
        task = TaskRepository(session).add("   padded title \n")
        assert task.title == "padded title"


@pytest.mark.parametrize("blank", ["", "   ", "\t\n", "\u3000"])
def test_add_rejects_a_blank_title(database, blank: str):
    """A title that is empty after trimming must not create a row."""
    with database.session_scope() as session:
        repository = TaskRepository(session)
        with pytest.raises(TaskTitleError):
            repository.add(blank)

    with database.session_scope() as session:
        assert TaskRepository(session).count() == 0


def test_add_generates_distinct_ids(database):
    with database.session_scope() as session:
        repository = TaskRepository(session)
        ids = {repository.add(f"task {index}").id for index in range(5)}
    assert len(ids) == 5


# --- listing ---------------------------------------------------------------


def test_list_all_returns_newest_first(database):
    """Documented order: created_at descending."""
    base = dt.datetime(2026, 3, 1, 12, 0, 0)
    with database.session_scope() as session:
        for offset, name in enumerate(["oldest", "middle", "newest"]):
            record = TaskRepository(session).add(name)
            record.created_at = base + dt.timedelta(hours=offset)
        session.flush()

    with database.session_scope() as session:
        titles = [task.title for task in TaskRepository(session).list_all()]
    assert titles == ["newest", "middle", "oldest"]


def test_list_all_breaks_ties_by_ascending_id(database):
    """Equal timestamps must fall back to ascending id, not arbitrary order."""
    same_moment = dt.datetime(2026, 3, 1, 12, 0, 0)
    with database.session_scope() as session:
        repository = TaskRepository(session)
        for task_id in ["id-c", "id-a", "id-b"]:
            record = repository.add(f"task {task_id}", task_id=task_id)
            record.created_at = same_moment
        session.flush()

    with database.session_scope() as session:
        ids = [task.id for task in TaskRepository(session).list_all()]
    assert ids == ["id-a", "id-b", "id-c"]


def test_list_all_is_empty_without_tasks(database):
    with database.session_scope() as session:
        assert TaskRepository(session).list_all() == []


# --- completion ------------------------------------------------------------


def test_mark_completed_sets_status_and_time(database):
    with database.session_scope() as session:
        task_id = TaskRepository(session).add("finish me").id

    with database.session_scope() as session:
        task = TaskRepository(session).mark_completed(task_id)
        assert task is not None
        assert task.status == TASK_STATUS_COMPLETED
        assert task.completed_at is not None


def test_repeated_completion_keeps_the_original_time(database):
    """Explicitly required: completing twice must not move completed_at."""
    with database.session_scope() as session:
        task_id = TaskRepository(session).add("finish me").id

    first_time = dt.datetime(2026, 5, 1, 8, 0, 0, tzinfo=dt.UTC)
    with database.session_scope() as session:
        TaskRepository(session).mark_completed(task_id, completed_at=first_time)

    later = dt.datetime(2026, 6, 1, 9, 30, 0, tzinfo=dt.UTC)
    with database.session_scope() as session:
        task = TaskRepository(session).mark_completed(task_id, completed_at=later)
        assert task is not None
        assert as_utc(task.completed_at) == first_time

    with database.session_scope() as session:
        stored = TaskRepository(session).get(task_id)
        assert as_utc(stored.completed_at) == first_time


def test_concurrent_repeated_completion_keeps_the_first_time(database):
    """Two sessions that both read a pending task must agree on the first time.

    This is the regression test for the lost-update bug: session B held a stale
    ``pending`` snapshot, so a read-then-write implementation let it overwrite
    the completion session A had already committed.

    Each session commits before the next one writes, because SQLite allows only
    one writer at a time; the race being covered is the stale *read*, which
    survives the commit ordering.
    """
    with database.session_scope() as session:
        task_id = TaskRepository(session).add("race").id

    first_time = dt.datetime(2026, 7, 1, 10, 0, 0, tzinfo=dt.UTC)
    later_time = dt.datetime(2026, 9, 9, 20, 0, 0, tzinfo=dt.UTC)

    session_a = database.session()
    session_b = database.session()
    try:
        repository_a = TaskRepository(session_a)
        repository_b = TaskRepository(session_b)

        # Both sessions observe the task while it is still pending, and B keeps
        # a reference so its snapshot stays loaded rather than being refreshed
        # by chance when another session commits.
        assert repository_a.get(task_id).status == TASK_STATUS_PENDING
        stale_copy = repository_b.get(task_id)
        assert stale_copy.status == TASK_STATUS_PENDING

        winner = repository_a.mark_completed(task_id, completed_at=first_time)
        session_a.commit()
        assert as_utc(winner.completed_at) == first_time

        # B still holds a pending snapshot, but must not move the time.
        assert stale_copy.status == TASK_STATUS_PENDING, "precondition: B's copy is stale"
        loser = repository_b.mark_completed(task_id, completed_at=later_time)
        session_b.commit()
        assert as_utc(loser.completed_at) == first_time, "B overwrote A's completion"
    finally:
        session_a.close()
        session_b.close()

    with database.session_scope() as session:
        assert as_utc(TaskRepository(session).get(task_id).completed_at) == first_time


def test_a_stale_pending_snapshot_cannot_overwrite_a_completion(database):
    """The guard must live in the UPDATE, not in a prior read.

    The object is loaded, then completed through another session, and only
    afterwards completed through the session holding the stale copy.
    """
    with database.session_scope() as session:
        task_id = TaskRepository(session).add("stale").id

    stale_session = database.session()
    try:
        stale_repository = TaskRepository(stale_session)
        stale_copy = stale_repository.get(task_id)
        assert stale_copy.status == TASK_STATUS_PENDING

        authoritative = dt.datetime(2026, 2, 2, 2, 0, 0, tzinfo=dt.UTC)
        with database.session_scope() as other:
            TaskRepository(other).mark_completed(task_id, completed_at=authoritative)

        result = stale_repository.mark_completed(
            task_id, completed_at=dt.datetime(2026, 12, 31, tzinfo=dt.UTC)
        )
        stale_session.commit()

        assert result.status == TASK_STATUS_COMPLETED
        assert as_utc(result.completed_at) == authoritative
    finally:
        stale_session.close()

    with database.session_scope() as session:
        stored = TaskRepository(session).get(task_id)
        assert as_utc(stored.completed_at) == dt.datetime(2026, 2, 2, 2, 0, 0, tzinfo=dt.UTC)


def test_mark_completed_returns_none_for_a_missing_task(database):
    """Absence is reported, not raised: the service maps it to its own error."""
    with database.session_scope() as session:
        assert TaskRepository(session).mark_completed("no-such-id") is None


def test_update_details_keeps_completion_written_after_session_loaded_task(database):
    with database.session_scope() as session:
        task_id = TaskRepository(session).add("初稿").id

    completion = dt.datetime(2026, 12, 20, 8, tzinfo=dt.UTC)
    due_on, due_time = dt.date(2026, 12, 22), dt.time(17, 30)
    with database.session_scope() as editing_session:
        repository = TaskRepository(editing_session)
        stale = repository.get(task_id)
        assert stale.status == TASK_STATUS_PENDING
        with database.session_scope() as completing_session:
            TaskRepository(completing_session).mark_completed(task_id, completion)
        assert stale.status == TASK_STATUS_PENDING

        updated = repository.update_details(task_id, "终稿", due_on=due_on, due_time=due_time)
        assert updated.status == TASK_STATUS_COMPLETED
        assert as_utc(updated.completed_at) == completion
        assert (updated.title, updated.due_on, updated.due_time) == ("终稿", due_on, due_time)

    with database.session_scope() as session:
        stored = TaskRepository(session).get(task_id)
        assert (stored.title, stored.due_on, stored.due_time) == ("终稿", due_on, due_time)
        assert stored.status == TASK_STATUS_COMPLETED
        assert as_utc(stored.completed_at) == completion


def test_get_returns_none_for_a_missing_task(database):
    with database.session_scope() as session:
        assert TaskRepository(session).get("no-such-id") is None


# --- timestamps ------------------------------------------------------------


def test_timestamps_are_stored_naive_and_restored_as_utc(database):
    """SQLite holds naive UTC; the service boundary needs aware UTC."""
    with database.session_scope() as session:
        task_id = TaskRepository(session).add("timezones").id

    with database.session_scope() as session:
        task = TaskRepository(session).get(task_id)
        assert task.created_at.tzinfo is None, "stored column must stay naive"

        restored = as_utc(task.created_at)
        assert restored.tzinfo == dt.UTC
        assert restored.replace(tzinfo=None) == task.created_at


def test_an_aware_completion_time_is_converted_not_truncated(database):
    """A non-UTC input must be converted, so local time is never stored as UTC."""
    with database.session_scope() as session:
        task_id = TaskRepository(session).add("offset").id

    # 18:30 at +08:00 is 10:30 UTC.
    aware = dt.datetime(2026, 4, 1, 18, 30, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    with database.session_scope() as session:
        TaskRepository(session).mark_completed(task_id, completed_at=aware)

    with database.session_scope() as session:
        stored = TaskRepository(session).get(task_id).completed_at
        assert stored == dt.datetime(2026, 4, 1, 10, 30)
        assert as_utc(stored) == aware


def test_to_naive_utc_and_as_utc_round_trip():
    aware = dt.datetime(2026, 2, 3, 4, 5, 6, tzinfo=dt.UTC)
    assert as_utc(to_naive_utc(aware)) == aware
    assert to_naive_utc(None) is None
    assert as_utc(None) is None


# --- persistence -----------------------------------------------------------


def test_tasks_survive_a_simulated_restart(tmp_path: Path):
    """Create, complete, reopen: status and timestamps must be preserved."""
    data_dir = tmp_path / "data"

    first = create_database(_settings(data_dir))
    first.ensure_schema()
    with first.session_scope() as session:
        repository = TaskRepository(session)
        kept = repository.add("survives restart").id
        done = repository.add("already done").id
    with first.session_scope() as session:
        TaskRepository(session).mark_completed(done)
        completion = as_utc(TaskRepository(session).get(done).completed_at)
    first.dispose()

    second = create_database(_settings(data_dir))
    try:
        with second.session_scope() as session:
            repository = TaskRepository(session)
            assert repository.count() == 2
            assert repository.get(kept).status == TASK_STATUS_PENDING
            reopened = repository.get(done)
            assert reopened.status == TASK_STATUS_COMPLETED
            assert as_utc(reopened.completed_at) == completion
    finally:
        second.dispose()


def test_rollback_discards_an_uncommitted_task(database):
    """A failed service operation must not leave a partial task behind."""
    with pytest.raises(RuntimeError, match="boom"), database.session_scope() as session:
        TaskRepository(session).add("never stored")
        raise RuntimeError("boom")

    with database.session_scope() as session:
        assert TaskRepository(session).count() == 0


def test_repository_does_not_commit_on_its_own(database):
    """The service owns transactions; the repository must not commit early."""
    session = database.session()
    try:
        TaskRepository(session).add("uncommitted")
        TaskRepository(session).mark_completed("missing-id")

        # Read through a separate connection: nothing may be visible yet.
        # ``sqlite3.connect`` is closed explicitly - its context manager only
        # manages a transaction, so a ``with`` block would leave the
        # connection open and hold a lock.
        probe = sqlite3.connect(str(database.path))
        try:
            assert probe.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
        finally:
            probe.close()

        session.rollback()
    finally:
        session.close()

    probe = sqlite3.connect(str(database.path))
    try:
        assert probe.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
    finally:
        probe.close()

    with database.session_scope() as session:
        assert TaskRepository(session).count() == 0


def test_existing_settings_are_untouched_by_the_task_migration(tmp_path: Path):
    """Phase 1 data must survive the upgrade that adds the tasks table."""
    from alembic import command

    from lifeos.infrastructure.database.repository import SettingsRepository
    from tests._helpers import alembic_config

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    database_file = data_dir / "lifeos.sqlite3"

    def _config():
        return alembic_config(database_file)

    # A user still on the Phase 1 schema, with real settings.
    command.upgrade(_config(), "0001_app_settings")
    legacy = create_database(_settings(data_dir))
    with legacy.session_scope() as session:
        SettingsRepository(session).set("app.locale", "zh-CN")
    assert "tasks" not in inspect(legacy.engine).get_table_names()
    legacy.dispose()

    # Upgrading to Phase 2 adds tasks and keeps the settings.
    command.upgrade(_config(), "head")
    upgraded = create_database(_settings(data_dir))
    try:
        assert "tasks" in inspect(upgraded.engine).get_table_names()
        with upgraded.session_scope() as session:
            assert SettingsRepository(session).get("app.locale") == "zh-CN"
            assert TaskRepository(session).count() == 0
            TaskRepository(session).add("works after upgrade")
    finally:
        upgraded.dispose()
