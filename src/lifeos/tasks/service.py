"""Transaction-owning task service and detached public data objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy.exc import OperationalError, SQLAlchemyError

from lifeos.infrastructure.database.task_repository import TaskRepository, TaskTitleError

if TYPE_CHECKING:
    from lifeos.infrastructure.database.engine import Database
    from lifeos.infrastructure.database.models import TaskRecord


@dataclass(frozen=True, slots=True)
class Task:
    """A detached task value with timestamps normalized to UTC."""

    id: str
    title: str
    status: Literal["pending", "completed"]
    created_at: datetime
    completed_at: datetime | None
    due_on: date | None = None


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
    )


def _storage_error(error: Exception) -> TaskStorageError:
    if isinstance(error, OperationalError):
        detail = str(error.orig).lower()
        if detail == "no such table: tasks" or detail in (
            "no such column: tasks.due_on",
            "table tasks has no column named due_on",
        ):
            return TaskStorageError(
                "任务数据表需要更新，请先执行数据库迁移：python -m alembic upgrade head"
            )
    return TaskStorageError("任务存储操作失败")


class TaskService:
    """Operate on tasks using short-lived database transactions."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create_task(self, title: str, *, due_on: date | None = None) -> Task:
        if not isinstance(title, str) or not title.strip():
            raise TaskValidationError("任务标题不能为空")
        if due_on is not None and (not isinstance(due_on, date) or isinstance(due_on, datetime)):
            raise TaskValidationError("截止日期必须是有效的日历日期")
        try:
            with self._database.session_scope() as session:
                result = _to_task(TaskRepository(session).add(title.strip(), due_on=due_on))
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
