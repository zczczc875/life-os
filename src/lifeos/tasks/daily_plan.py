"""Build a suggested task order from saved deadlines and the local clock."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable

PlanBucket = Literal["overdue", "today", "this_week", "later", "unscheduled"]
PlanPriority = Literal["high", "medium", "low"]

# The order of these buckets is also the order of the plan.
_BUCKET_PRIORITIES: dict[PlanBucket, PlanPriority] = {
    "overdue": "high",
    "today": "high",
    "this_week": "medium",
    "later": "medium",
    "unscheduled": "low",
}
_BUCKET_ORDER = {bucket: index for index, bucket in enumerate(_BUCKET_PRIORITIES)}


class _TaskWithDeadline(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def due_on(self) -> date | None: ...

    @property
    def due_time(self) -> time | None: ...


@dataclass(frozen=True, slots=True)
class PlannedTask:
    """One saved task with a suggested category and priority."""

    task_id: str
    title: str
    due_on: date | None
    due_time: time | None
    bucket: PlanBucket
    priority: PlanPriority


def _deadline_bucket(due_on: date | None, due_time: time | None, now: datetime) -> PlanBucket:
    if due_on is None:
        return "unscheduled"

    days_until_due = (due_on - now.date()).days
    if days_until_due < 0:
        return "overdue"
    if days_until_due == 0:
        if due_time is not None and now.time() > due_time:
            return "overdue"
        return "today"
    if days_until_due <= 6 - now.weekday():
        return "this_week"
    return "later"


def build_daily_plan(tasks: Iterable[_TaskWithDeadline], *, now: datetime) -> list[PlannedTask]:
    """Plan pending tasks using the local wall-clock minute in ``now``."""
    now = now.replace(second=0, microsecond=0)
    plan = []
    for task in tasks:
        if task.status != "pending":
            continue
        bucket = _deadline_bucket(task.due_on, task.due_time, now)
        plan.append(
            PlannedTask(
                task_id=task.id,
                title=task.title,
                due_on=task.due_on,
                due_time=task.due_time,
                bucket=bucket,
                priority=_BUCKET_PRIORITIES[bucket],
            )
        )

    # Sort date-only tasks at the end of their day and retain input order on ties.
    plan.sort(
        key=lambda task: (
            _BUCKET_ORDER[task.bucket],
            task.due_on or date.max,
            task.due_time or time.max,
        )
    )
    return plan
