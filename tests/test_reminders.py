"""Reminder eligibility and durable claim behavior against migrated SQLite."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from threading import Barrier

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lifeos.config.settings import Settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.tasks import TaskService, TaskStorageError
from lifeos.tasks.reminders import ReminderService

DAY = date(2026, 11, 12)


@pytest.fixture
def database(tmp_path):
    db = create_database(Settings(data_dir=tmp_path))
    db.ensure_schema()
    try:
        yield db
    finally:
        db.dispose()


def test_claims_only_pending_tasks_at_their_local_deadline(database):
    tasks = TaskService(database)
    reminders = ReminderService(database)
    timed = tasks.create_task("定时", due_on=DAY, due_time=time(17, 30))
    date_only = tasks.create_task("仅日期", due_on=DAY)
    completed = tasks.create_task("已完成", due_on=DAY, due_time=time(12))
    tasks.complete_task(completed.id)
    tasks.create_task("未排期")
    tasks.create_task("明天", due_on=date(2026, 11, 13), due_time=time(0))

    assert reminders.enabled() is False
    assert reminders.claim_due(datetime(2026, 11, 12, 17, 30)) == []
    reminders.set_enabled(True)
    assert reminders.claim_due(datetime(2026, 11, 12, 17, 29, 59)) == []
    assert reminders.claim_due(datetime(2026, 11, 12, 17, 30)) == [timed]
    assert reminders.claim_due(datetime(2026, 11, 12, 23, 58, 59)) == []
    assert reminders.claim_due(datetime(2026, 11, 12, 23, 59)) == [date_only]
    assert reminders.claim_due(datetime(2026, 11, 12, 23, 59, 59)) == []


def test_reopen_recovers_missed_reminders_once_and_preserves_preference(database):
    tasks = TaskService(database)
    reminders = ReminderService(database)
    overdue = tasks.create_task("错过", due_on=DAY)
    reminders.set_enabled(True)
    database.dispose()

    restarted = create_database(Settings(data_dir=database.path.parent))
    try:
        reopened = ReminderService(restarted)
        now = datetime(2026, 11, 13, 9)
        assert reopened.enabled() is True
        assert reopened.claim_due(now) == [overdue]
        restarted.dispose()
        assert ReminderService(restarted).claim_due(now) == []
        reopened.set_enabled(False)
        assert reminders.enabled() is False
    finally:
        restarted.dispose()


def test_deadline_edits_rearm_and_title_edits_keep_the_claim(database):
    tasks = TaskService(database)
    reminders = ReminderService(database)
    reminders.set_enabled(True)
    task = tasks.create_task("报告", due_on=DAY, due_time=time(17))
    now = datetime(2026, 11, 12, 17)
    assert reminders.claim_due(now) == [task]

    tasks.update_task(task.id, "写报告", due_on=DAY, due_time=time(17))
    assert reminders.claim_due(now) == []
    updated = tasks.update_task(task.id, "写报告", due_on=DAY, due_time=time(18))
    assert reminders.claim_due(now) == []
    assert reminders.claim_due(datetime(2026, 11, 12, 18)) == [updated]
    tasks.update_task(task.id, updated.title)
    assert reminders.claim_due(datetime(2026, 11, 12, 19)) == []
    restored = tasks.update_task(task.id, updated.title, due_on=DAY, due_time=time(17))
    assert reminders.claim_due(datetime(2026, 11, 12, 19)) == [restored]


def test_concurrent_scanners_claim_each_task_once(database):
    reminders = ReminderService(database)
    reminders.set_enabled(True)
    task = TaskService(database).create_task("报告", due_on=DAY, due_time=time(17))
    start = Barrier(2)

    def scan():
        start.wait(timeout=5)
        return ReminderService(database).claim_due(datetime(2026, 11, 12, 18))

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(scan)
        second = executor.submit(scan)
        assert first.result() + second.result() == [task]


def test_failed_claim_commit_leaves_the_reminder_available_for_retry(database, monkeypatch):
    reminders = ReminderService(database)
    reminders.set_enabled(True)
    task = TaskService(database).create_task("报告", due_on=DAY, due_time=time(17))
    now = datetime(2026, 11, 12, 17)

    def fail_commit(_session):
        raise SQLAlchemyError("simulated commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        with pytest.raises(TaskStorageError):
            reminders.claim_due(now)
    assert reminders.claim_due(now) == [task]
