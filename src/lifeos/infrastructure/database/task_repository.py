"""Repository for the ``tasks`` table.

Phase 2 keeps SQL inside the database layer. Following the Phase 1 convention,
the repository receives a ``Session`` and never commits: the task service owns
transaction boundaries through ``Database.session_scope()``.

Timestamps are stored as naive UTC to match the existing SQLite columns, and
are returned as timezone-aware UTC so the service layer never has to guess.

The public method names are a proposal for A to confirm; see
``docs/DELIVERY_C_PHASE2.md``.
"""

from __future__ import annotations

import datetime as _datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update

from lifeos.infrastructure.database.models import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_PENDING,
    TaskRecord,
    to_naive_utc,
    utcnow,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

__all__ = ["TaskRepository", "TaskTitleError"]


class TaskTitleError(ValueError):
    """Raised when a task title is empty after trimming.

    The service layer is expected to surface this as its own
    ``TaskValidationError``; the repository refuses the write regardless, so an
    invalid row cannot reach the database through another caller.
    """


def normalize_title(title: str) -> str:
    """Trim surrounding whitespace and reject an empty result."""
    if title is None:
        raise TaskTitleError("task title must be a string, got None")
    trimmed = title.strip()
    if not trimmed:
        raise TaskTitleError("task title must not be empty after trimming")
    return trimmed


class TaskRepository:
    """Create, read and complete task rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, title: str, task_id: str | None = None) -> TaskRecord:
        """Insert a ``pending`` task and return the stored row.

        The title is trimmed; an empty result raises :class:`TaskTitleError`.
        ``task_id`` is generated when omitted so the caller does not have to,
        and stays fixed afterwards.
        """
        normalized = normalize_title(title)
        record = TaskRecord(
            id=task_id or uuid.uuid4().hex,
            title=normalized,
            status=TASK_STATUS_PENDING,
            created_at=utcnow(),
            completed_at=None,
        )
        self._session.add(record)
        # Flush so a duplicate id or constraint violation surfaces here rather
        # than at commit time, where the cause is harder to attribute.
        self._session.flush()
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        """Return the task with ``task_id``, or ``None`` when absent."""
        return self._session.get(TaskRecord, task_id)

    def list_all(self) -> list[TaskRecord]:
        """Return every task, newest first, ties broken by ascending id."""
        statement = select(TaskRecord).order_by(
            TaskRecord.created_at.desc(),
            TaskRecord.id.asc(),
        )
        return list(self._session.execute(statement).scalars())

    def mark_completed(
        self,
        task_id: str,
        completed_at: _datetime.datetime | None = None,
    ) -> TaskRecord | None:
        """Mark a task completed and return it, or ``None`` when absent.

        Completion is performed by a single conditional ``UPDATE`` guarded by
        ``status = 'pending'``, so the database itself decides the winner when
        two sessions complete the same task. Reading the row first and then
        writing would let a session holding a stale ``pending`` snapshot
        overwrite a completion another session already committed.

        Repeated completion is a no-op that preserves the original
        ``completed_at``. The caller still owns the transaction: this method
        issues the statement but never commits.
        """
        explicit = to_naive_utc(completed_at)
        moment = utcnow() if explicit is None else explicit

        statement = (
            update(TaskRecord)
            .where(
                TaskRecord.id == task_id,
                TaskRecord.status == TASK_STATUS_PENDING,
            )
            .values(status=TASK_STATUS_COMPLETED, completed_at=moment)
        )
        self._session.execute(statement)

        # This session may hold a stale ``pending`` copy of a row another
        # session has already completed, so re-read it from the database.
        # Only the affected row is expired: the caller's other objects in this
        # session must not be invalidated as a side effect.
        cached = self._session.identity_map.get(self._session.identity_key(TaskRecord, task_id))
        if cached is not None:
            self._session.expire(cached)

        # A missing task and an already-completed one are distinguished here;
        # the re-read also yields the stored completion time rather than ours.
        return self._session.get(TaskRecord, task_id)

    def count(self) -> int:
        """Return the number of stored tasks."""
        statement = select(func.count()).select_from(TaskRecord)
        return int(self._session.execute(statement).scalar_one())
