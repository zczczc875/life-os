"""Declarative models for the local SQLite store.

Importing this module only declares metadata; it never touches the filesystem
or opens a connection.
"""

from __future__ import annotations

import datetime as _datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Index, String, Text, Time
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = [
    "AppSetting",
    "Base",
    "TaskRecord",
    "as_utc",
    "to_naive_utc",
    "utcnow",
]

#: Allowed values of :attr:`TaskRecord.status`.
TASK_STATUS_PENDING = "pending"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUSES = (TASK_STATUS_PENDING, TASK_STATUS_COMPLETED)


def utcnow() -> _datetime.datetime:
    """Return the current UTC time as a naive datetime.

    SQLite does not preserve timezone information, so timestamps are stored as
    naive UTC and must be interpreted as UTC by callers.
    """
    return _datetime.datetime.now(_datetime.UTC).replace(tzinfo=None)


def to_naive_utc(moment: _datetime.datetime | None) -> _datetime.datetime | None:
    """Convert an aware or naive datetime to the naive UTC form stored in SQLite.

    An aware value is converted to UTC before the tzinfo is dropped. A naive
    value is assumed to already be UTC, matching :func:`utcnow`. This keeps
    local time from being written as if it were UTC.
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(_datetime.UTC).replace(tzinfo=None)


def as_utc(moment: _datetime.datetime | None) -> _datetime.datetime | None:
    """Attach UTC to a datetime read back from SQLite.

    Phase 2 requires timezone-aware UTC at the service boundary, while the
    stored columns are naive. Values that already carry a timezone are
    normalised to UTC rather than being trusted as-is.
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=_datetime.UTC)
    return moment.astimezone(_datetime.UTC)


class Base(DeclarativeBase):
    """Shared declarative base for all LifeOS tables."""


class AppSetting(Base):
    """A single application setting stored as a key/value pair.

    ``key`` is the primary key, so settings are unique per key and can be
    inserted, queried and updated through :class:`SettingsRepository`.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[_datetime.datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"AppSetting(key={self.key!r})"


class TaskRecord(Base):
    """A single task row.

    Timestamps are naive UTC to match the SQLite convention. The optional
    deadline is a calendar date with an optional local wall-clock time.
    """

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=TASK_STATUS_PENDING,
    )
    created_at: Mapped[_datetime.datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
    )
    completed_at: Mapped[_datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    due_on: Mapped[_datetime.date | None] = mapped_column(Date, nullable=True)
    due_time: Mapped[_datetime.time | None] = mapped_column(
        Time,
        CheckConstraint(
            "due_time IS NULL OR due_on IS NOT NULL",
            name="ck_tasks_due_time_date",
        ),
        nullable=True,
    )

    __table_args__ = (
        # Reject unknown states at the storage layer, so a service bug cannot
        # persist a status the UI is unable to render.
        CheckConstraint(
            f"status IN ('{TASK_STATUS_PENDING}', '{TASK_STATUS_COMPLETED}')",
            name="ck_tasks_status",
        ),
        # A completed task must carry a completion time, and a pending one
        # must not; this keeps the two fields from drifting apart.
        CheckConstraint(
            f"(status = '{TASK_STATUS_COMPLETED}' AND completed_at IS NOT NULL)"
            f" OR (status = '{TASK_STATUS_PENDING}' AND completed_at IS NULL)",
            name="ck_tasks_completed_at",
        ),
        # Supports the documented listing order: newest first, then id.
        Index("ix_tasks_created_at_id", created_at.desc(), id),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"TaskRecord(id={self.id!r}, status={self.status!r})"
