"""Contract tests for the application task service using isolated SQLite."""

from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lifeos.config.settings import Settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.infrastructure.database.models import TaskRecord
from lifeos.tasks import (
    TaskNotFoundError,
    TaskService,
    TaskStorageError,
    TaskValidationError,
)


@pytest.fixture
def database(tmp_path):
    db = create_database(Settings(data_dir=tmp_path))
    db.ensure_schema()
    yield db
    db.dispose()


def test_create_trims_and_persists_detached_task(database):
    service = TaskService(database)
    task = service.create_task("  Plan coursework  ")
    assert task.title == "Plan coursework"
    assert task.status == "pending"
    assert task.id
    assert task.created_at.tzinfo == UTC
    assert task.completed_at is None
    assert service.list_tasks() == [task]


def test_timed_deadline_is_preserved_when_task_is_completed(database):
    service = TaskService(database)
    due_on, due_time = date(2026, 12, 18), time(17, 30)
    task = service.create_task("提交报告", due_on=due_on, due_time=due_time)
    assert (task.due_on, task.due_time) == (due_on, due_time)

    completed = service.complete_task(task.id)
    assert (completed.due_on, completed.due_time) == (due_on, due_time)
    assert service.list_tasks() == [completed]


@pytest.mark.parametrize(
    ("due_on", "due_time"),
    [
        (None, time(17, 30)),
        (date(2026, 12, 18), "17:30"),
        (date(2026, 12, 18), time(17, 30, tzinfo=UTC)),
        (date(2026, 12, 18), time(17, 30, 59)),
        (date(2026, 12, 18), time(17, 30, microsecond=1)),
    ],
)
def test_invalid_deadline_time_never_creates_a_task(database, due_on, due_time):
    service = TaskService(database)
    with pytest.raises(TaskValidationError, match="截止"):
        service.create_task("无效任务", due_on=due_on, due_time=due_time)
    assert service.list_tasks() == []


@pytest.mark.parametrize("title", ["", " \t\n "])
def test_blank_title_does_not_create_task(database, title):
    service = TaskService(database)
    with pytest.raises(TaskValidationError):
        service.create_task(title)
    assert service.list_tasks() == []


def test_list_newest_first_with_deterministic_id_tiebreak(database):
    with database.session_scope() as session:
        for task_id, created in (
            ("z", datetime(2026, 1, 2)),
            ("a", datetime(2026, 1, 2)),
            ("old", datetime(2026, 1, 1)),
        ):
            session.add(TaskRecord(id=task_id, title=task_id, status="pending", created_at=created))
    tasks = TaskService(database).list_tasks()
    assert [task.id for task in tasks] == ["a", "z", "old"]
    assert all(task.created_at.tzinfo == UTC for task in tasks)


def test_complete_preserves_first_timestamp_on_repeat(database):
    service = TaskService(database)
    created = service.create_task("Task")
    first = service.complete_task(created.id)
    second = service.complete_task(created.id)
    assert first.status == second.status == "completed"
    assert first.completed_at is not None and first.completed_at.tzinfo == UTC
    assert second.completed_at == first.completed_at
    assert service.list_tasks() == [second]


def test_complete_missing_task_raises_and_leaves_store_unchanged(database):
    service = TaskService(database)
    with pytest.raises(TaskNotFoundError):
        service.complete_task("does-not-exist")
    assert service.list_tasks() == []


def test_update_replaces_details_and_preserves_completion(database):
    service = TaskService(database)
    task = service.create_task("初稿", due_on=date(2026, 12, 18))
    completed = service.complete_task(task.id)
    other = service.create_task("另一项任务")
    new_date, new_time = date(2026, 12, 20), time(17, 30)

    updated = service.update_task(task.id, "  提交终稿  ", due_on=new_date, due_time=new_time)

    assert (updated.title, updated.due_on, updated.due_time) == ("提交终稿", new_date, new_time)
    assert (updated.id, updated.status, updated.created_at, updated.completed_at) == (
        completed.id,
        completed.status,
        completed.created_at,
        completed.completed_at,
    )
    assert set(service.list_tasks()) == {updated, other}

    cleared = service.update_task(task.id, updated.title)
    assert cleared.due_on is cleared.due_time is None
    assert set(service.list_tasks()) == {cleared, other}


def test_invalid_or_missing_update_leaves_stored_tasks_unchanged(database):
    service = TaskService(database)
    task = service.create_task("初稿", due_on=date(2026, 12, 18))

    with pytest.raises(TaskValidationError, match="标题"):
        service.update_task(task.id, "  ")
    with pytest.raises(TaskValidationError, match="截止"):
        service.update_task(task.id, "改标题", due_time=time(17, 30))
    with pytest.raises(TaskNotFoundError):
        service.update_task("missing", "改标题")

    assert service.list_tasks() == [task]


def test_commit_failure_is_translated_and_rolls_back(database, monkeypatch):
    service = TaskService(database)

    def fail_commit(_session):
        raise SQLAlchemyError("simulated commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        with pytest.raises(TaskStorageError) as caught:
            service.create_task("Must not persist")
    assert isinstance(caught.value.__cause__, SQLAlchemyError)
    assert service.list_tasks() == []


def test_missing_task_schema_reports_migration_and_creates_no_schema(tmp_path):
    db = create_database(Settings(data_dir=tmp_path))
    try:
        with pytest.raises(TaskStorageError, match="迁移"):
            TaskService(db).list_tasks()
        assert not db.is_migrated()
    finally:
        db.dispose()
