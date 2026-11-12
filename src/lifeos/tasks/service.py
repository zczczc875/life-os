"""Transaction-owning task service and detached public data objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Literal

from sqlalchemy.exc import OperationalError, SQLAlchemyError

from lifeos.infrastructure.database.task_repository import TaskRepository, TaskTitleError

if TYPE_CHECKING:
    from lifeos.infrastructure.database.engine import Database
    from lifeos.infrastructure.database.models import TaskRecord


@dataclass(frozen=True, slots=True)
class Task:
    """A detached task with UTC event timestamps and an optional local deadline."""

    id: str
    title: str
    status: Literal["pending", "completed"]
    created_at: datetime
    completed_at: datetime | None
    due_on: date | None = None
    due_time: time | None = None


class TaskValidationError(ValueError):
    """Raised when task input is invalid."""


class TaskNotFoundError(LookupError):
    """Raised when the requested task does not exist."""


class TaskStorageError(RuntimeError):
    """Raised when a database operation or transaction fails."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_task(record: TaskRecord) -> Task:
    return Task(
        id=record.id,
        title=record.title,
        status=record.status,
        created_at=_utc(record.created_at),
        completed_at=_utc(record.completed_at) if record.completed_at is not None else None,
        due_on=record.due_on,
        due_time=record.due_time,
    )


def _storage_error(error: Exception) -> TaskStorageError:
    if isinstance(error, OperationalError):
        detail = str(error.orig).lower()
        if detail in (
            "no such table: tasks",
            "no such column: tasks.due_on",
            "no such column: tasks.due_time",
            "no such column: tasks.reminder_claimed_at",
            "no such column: reminder_claimed_at",
            "table tasks has no column named due_on",
            "table tasks has no column named due_time",
        ):
            return TaskStorageError(
                "任务数据表需要更新，请先执行数据库迁移：python -m alembic upgrade head"
            )
    return TaskStorageError("任务存储操作失败")


def _validate_task_details(title: str, due_on: date | None, due_time: time | None) -> None:
    if not isinstance(title, str) or not title.strip():
        raise TaskValidationError("任务标题不能为空")
    if due_on is not None and (not isinstance(due_on, date) or isinstance(due_on, datetime)):
        raise TaskValidationError("截止日期必须是有效的日历日期")
    if due_time is None:
        return
    if due_on is None:
        raise TaskValidationError("填写截止时间时也需要截止日期")
    if (
        not isinstance(due_time, time)
        or due_time.tzinfo is not None
        or due_time.second
        or due_time.microsecond
    ):
        raise TaskValidationError("截止时间必须是精确到分钟的本地时间")


class TaskService:
    """Operate on tasks using short-lived database transactions."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create_task(
        self, title: str, *, due_on: date | None = None, due_time: time | None = None
    ) -> Task:
        _validate_task_details(title, due_on, due_time)
        try:
            with self._database.session_scope() as session:
                result = _to_task(
                    TaskRepository(session).add(title, due_on=due_on, due_time=due_time)
                )
            return result
        except TaskTitleError as error:
            raise TaskValidationError("任务标题不能为空") from error
        except (SQLAlchemyError, OSError) as error:
            raise _storage_error(error) from error

    def update_task(
        self,
        task_id: str,
        title: str,
        *,
        due_on: date | None = None,
        due_time: time | None = None,
    ) -> Task:
        """Replace a saved task's title and optional deadline."""
        _validate_task_details(title, due_on, due_time)
        try:
            with self._database.session_scope() as session:
                record = TaskRepository(session).update_details(
                    task_id, title, due_on=due_on, due_time=due_time
                )
                if record is None:
                    raise TaskNotFoundError("任务不存在")
                result = _to_task(record)
            return result
        except TaskTitleError as error:
            raise TaskValidationError("任务标题不能为空") from error
        except (SQLAlchemyError, OSError) as error:
            raise _storage_error(error) from error

    def list_tasks(self) -> list[Task]:
        try:
            with self._database.session_scope() as session:
                result = [_to_task(record) for record in TaskRepository(session).list_all()]
            return result
        except (SQLAlchemyError, OSError) as error:
            raise _storage_error(error) from error

    def complete_task(self, task_id: str) -> Task:
        try:
            with self._database.session_scope() as session:
                record = TaskRepository(session).mark_completed(task_id)
                if record is None:
                    raise TaskNotFoundError("任务不存在")
                result = _to_task(record)
            return result
        except (SQLAlchemyError, OSError) as error:
            raise _storage_error(error) from error
