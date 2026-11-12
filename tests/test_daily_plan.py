from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Literal

from lifeos.tasks import Task
from lifeos.tasks.daily_plan import PlannedTask, build_daily_plan


def _task(
    task_id: str,
    due_on: date | None = None,
    due_time: time | None = None,
    *,
    status: Literal["pending", "completed"] = "pending",
) -> Task:
    created_at = datetime(2026, 11, 1, tzinfo=UTC)
    return Task(
        id=task_id,
        title=f"任务 {task_id}",
        status=status,
        created_at=created_at,
        completed_at=created_at if status == "completed" else None,
        due_on=due_on,
        due_time=due_time,
    )


def test_plan_orders_pending_tasks_by_bucket_and_deadline():
    today = date(2026, 11, 12)
    tasks = [
        _task("unscheduled-first"),
        _task("future-later", date(2026, 12, 1)),
        _task("today-no-time", today),
        _task("today-evening", today, time(18)),
        _task("overdue-this-morning", today, time(8)),
        _task("completed", date(2026, 11, 10), status="completed"),
        _task("this-week-sunday", date(2026, 11, 15)),
        _task("overdue-yesterday", date(2026, 11, 11)),
        _task("today-first-tie", today, time(12)),
        _task("this-week-friday", date(2026, 11, 13)),
        _task("today-second-tie", today, time(12)),
        _task("future-next-monday", date(2026, 11, 16)),
        _task("unscheduled-second"),
    ]

    plan = build_daily_plan(iter(tasks), now=datetime(2026, 11, 12, 10, 30))

    assert [(item.task_id, item.bucket, item.priority) for item in plan] == [
        ("overdue-yesterday", "overdue", "high"),
        ("overdue-this-morning", "overdue", "high"),
        ("today-first-tie", "today", "high"),
        ("today-second-tie", "today", "high"),
        ("today-evening", "today", "high"),
        ("today-no-time", "today", "high"),
        ("this-week-friday", "this_week", "medium"),
        ("this-week-sunday", "this_week", "medium"),
        ("future-next-monday", "later", "medium"),
        ("future-later", "later", "medium"),
        ("unscheduled-first", "unscheduled", "low"),
        ("unscheduled-second", "unscheduled", "low"),
    ]
    assert plan[1] == PlannedTask(
        task_id="overdue-this-morning",
        title="任务 overdue-this-morning",
        due_on=today,
        due_time=time(8),
        bucket="overdue",
        priority="high",
    )


def test_timed_deadline_changes_bucket_after_its_local_minute():
    local_tz = timezone(timedelta(hours=8))
    now = datetime(2026, 11, 12, 17, 30, 59, tzinfo=local_tz)
    task = _task("timed", now.date(), time(17, 30))

    assert build_daily_plan([task], now=now)[0].bucket == "today"
    assert build_daily_plan([task], now=now + timedelta(seconds=1))[0].bucket == "overdue"


def test_date_only_deadline_and_week_boundary_roll_over_at_midnight():
    sunday = datetime(2026, 11, 15, 23, 59, 59)
    monday = sunday + timedelta(seconds=1)
    tasks = [_task("monday", monday.date()), _task("sunday", sunday.date())]

    assert [item.bucket for item in build_daily_plan(tasks, now=sunday)] == ["today", "later"]
    assert [item.bucket for item in build_daily_plan(tasks, now=monday)] == ["overdue", "today"]


def test_plan_is_empty_without_pending_tasks():
    task = _task("completed", status="completed")
    assert build_daily_plan([task], now=datetime(2026, 11, 12)) == []
