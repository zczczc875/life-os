"""Reminder eligibility and durable claim behavior against migrated SQLite."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
from threading import Barrier

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lifeos.config.settings import Settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.infrastructure.database.reminder_repository import ReminderRepository
from lifeos.tasks import TaskService, TaskStorageError, TaskValidationError
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


def test_advance_reminders_follow_each_enabled_threshold_and_keep_due_alert(database):
    reminders = ReminderService(database)
    task = TaskService(database).create_task("交表", due_on=DAY, due_time=time(17))
    assert reminders.advance_minutes() == ()
    assert reminders.claim_advance(datetime(2026, 11, 12, 16)) == []

    reminders.set_advance_minutes([1440, 15, 60, 15])
    assert reminders.advance_minutes() == (15, 60, 1440)
    assert reminders.claim_advance(datetime(2026, 11, 11, 17)) == []
    reminders.set_enabled(True)

    assert reminders.claim_advance(datetime(2026, 11, 11, 16, 59, 59)) == []
    assert reminders.claim_reminders(datetime(2026, 11, 11, 17)) == ([], [task])
    assert reminders.claim_reminders(datetime(2026, 11, 12, 15, 59, 59)) == ([], [])
    assert reminders.claim_reminders(datetime(2026, 11, 12, 16)) == ([], [task])
    assert reminders.claim_reminders(datetime(2026, 11, 12, 16, 45)) == ([], [task])
    assert reminders.claim_reminders(datetime(2026, 11, 12, 17)) == ([task], [])


def test_reopen_catches_latest_missed_lead_and_suppresses_later_enabled_farther_leads(database):
    reminders = ReminderService(database)
    reminders.set_advance_minutes([15, 1440])
    reminders.set_enabled(True)
    task = TaskService(database).create_task("仅日期", due_on=DAY)
    database.dispose()

    restarted = create_database(Settings(data_dir=database.path.parent))
    try:
        reopened = ReminderService(restarted)
        assert reopened.advance_minutes() == (15, 1440)
        assert reopened.claim_advance(datetime(2026, 11, 11, 23, 58, 59)) == []
        assert reopened.claim_advance(datetime(2026, 11, 12, 23, 50)) == [task]
        restarted.dispose()
        reopened.set_advance_minutes([15, 60, 1440])
        assert reopened.claim_advance(datetime(2026, 11, 12, 23, 51)) == []
        assert reopened.claim_reminders(datetime(2026, 11, 12, 23, 59)) == ([task], [])
    finally:
        restarted.dispose()


def test_advance_reminders_skip_completed_undated_and_already_due_tasks(database):
    tasks = TaskService(database)
    reminders = ReminderService(database)
    reminders.set_enabled(True)
    reminders.set_advance_minutes([15, 60, 1440])
    finished = tasks.create_task("完成", due_on=DAY, due_time=time(17))
    tasks.complete_task(finished.id)
    tasks.create_task("未排期")
    expired = tasks.create_task("已经到期", due_on=DAY, due_time=time(17))
    assert reminders.claim_reminders(datetime(2026, 11, 12, 17)) == ([expired], [])
    assert reminders.claim_advance(datetime(2026, 11, 12, 16, 55)) == []


def test_advance_reminders_rearm_only_when_deadline_changes(database):
    tasks = TaskService(database)
    reminders = ReminderService(database)
    reminders.set_advance_minutes([60])
    reminders.set_enabled(True)
    task = tasks.create_task("交表", due_on=DAY, due_time=time(17))
    now = datetime(2026, 11, 12, 16, 45)
    assert reminders.claim_advance(now) == [task]

    tasks.update_task(task.id, "提交表格", due_on=DAY, due_time=time(17))
    reminders.set_advance_minutes([])
    reminders.set_advance_minutes([60])
    assert reminders.claim_advance(now) == []

    updated = tasks.update_task(task.id, "提交表格", due_on=DAY, due_time=time(17, 30))
    assert reminders.claim_advance(now) == [updated]
    tasks.update_task(task.id, "提交表格")
    assert reminders.claim_advance(now) == []


def test_invalid_advance_preferences_preserve_the_saved_presets(database):
    reminders = ReminderService(database)
    reminders.set_advance_minutes([60])
    with pytest.raises(TaskValidationError):
        reminders.set_advance_minutes([15, 10])
    assert reminders.advance_minutes() == (60,)


def test_concurrent_scanners_split_due_and_advance_batches_without_duplicates(database):
    reminders = ReminderService(database)
    reminders.set_advance_minutes([15, 60, 1440])
    reminders.set_enabled(True)
    tasks = TaskService(database)
    due = tasks.create_task("已到期", due_on=DAY, due_time=time(17))
    advance = tasks.create_task("待到期", due_on=DAY, due_time=time(17, 10))
    start = Barrier(2)

    def scan():
        start.wait(timeout=5)
        return ReminderService(database).claim_reminders(datetime(2026, 11, 12, 17))

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(scan)
        second = executor.submit(scan)
        assert [first.result(), second.result()].count(([due], [advance])) == 1
        assert [first.result(), second.result()].count(([], [])) == 1


def test_combined_claim_rolls_back_due_batch_when_advance_scan_fails(database, monkeypatch):
    reminders = ReminderService(database)
    reminders.set_advance_minutes([15])
    reminders.set_enabled(True)
    tasks = TaskService(database)
    due = tasks.create_task("已到期", due_on=DAY, due_time=time(17))
    advance = tasks.create_task("待到期", due_on=DAY, due_time=time(17, 10))
    now = datetime(2026, 11, 12, 17)

    def fail_advance(_repository, _now):
        raise SQLAlchemyError("simulated advance scan failure")

    with monkeypatch.context() as patch:
        patch.setattr(ReminderRepository, "claim_advance", fail_advance)
        with pytest.raises(TaskStorageError):
            reminders.claim_reminders(now)
    assert reminders.claim_reminders(now) == ([due], [advance])
