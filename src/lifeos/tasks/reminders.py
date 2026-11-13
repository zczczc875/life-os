"""Transaction-owning service for desktop deadline reminders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from lifeos.infrastructure.database.reminder_repository import ADVANCE_MINUTES, ReminderRepository
from lifeos.tasks.service import TaskStorageError, TaskValidationError, _to_task

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from lifeos.infrastructure.database.engine import Database
    from lifeos.tasks.service import Task

__all__ = ["ADVANCE_MINUTES", "ReminderService"]


class ReminderService:
    def __init__(self, database: Database) -> None:
        self._database = database

    def enabled(self) -> bool:
        try:
            with self._database.session_scope() as session:
                return ReminderRepository(session).enabled()
        except (SQLAlchemyError, OSError) as error:
            raise TaskStorageError("无法读取到期提醒设置") from error

    def set_enabled(self, enabled: bool) -> None:
        try:
            with self._database.session_scope() as session:
                ReminderRepository(session).set_enabled(enabled)
        except (SQLAlchemyError, OSError) as error:
            raise TaskStorageError("无法保存到期提醒设置") from error

    def advance_minutes(self) -> tuple[int, ...]:
        try:
            with self._database.session_scope() as session:
                return ReminderRepository(session).advance_minutes()
        except (SQLAlchemyError, OSError) as error:
            raise TaskStorageError("无法读取提前提醒设置") from error

    def set_advance_minutes(self, minutes: Iterable[int]) -> None:
        selected = set(minutes)
        if not selected.issubset(ADVANCE_MINUTES):
            raise TaskValidationError("提前提醒可设置为 15 分钟、1 小时或 1 天")
        try:
            with self._database.session_scope() as session:
                ReminderRepository(session).set_advance_minutes(selected)
        except (SQLAlchemyError, OSError) as error:
            raise TaskStorageError("无法保存提前提醒设置") from error

    def claim_due(self, now: datetime) -> list[Task]:
        """Claim pending tasks at or before the given local wall-clock time.

        Return detached tasks after committing the claims. Claiming before
        notifying prevents duplicate submissions across scans and restarts.
        """
        try:
            with self._database.session_scope() as session:
                return [_to_task(record) for record in ReminderRepository(session).claim_due(now)]
        except (SQLAlchemyError, OSError) as error:
            raise TaskStorageError("无法检查到期提醒") from error

    def claim_advance(self, now: datetime) -> list[Task]:
        """Claim pending advance reminders without claiming due alerts."""
        try:
            with self._database.session_scope() as session:
                return [
                    _to_task(record) for record in ReminderRepository(session).claim_advance(now)
                ]
        except (SQLAlchemyError, OSError) as error:
            raise TaskStorageError("无法检查提前提醒") from error

    def claim_reminders(self, now: datetime) -> tuple[list[Task], list[Task]]:
        """Commit the due and advance batches together before showing either."""
        try:
            with self._database.session_scope() as session:
                repository = ReminderRepository(session)
                due = [_to_task(record) for record in repository.claim_due(now)]
                advance = [_to_task(record) for record in repository.claim_advance(now)]
            return due, advance
        except (SQLAlchemyError, OSError) as error:
            raise TaskStorageError("无法检查任务提醒") from error
