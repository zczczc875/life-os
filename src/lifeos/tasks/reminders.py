"""Transaction-owning service for desktop deadline reminders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from lifeos.infrastructure.database.reminder_repository import ReminderRepository
from lifeos.tasks.service import TaskStorageError, _to_task

if TYPE_CHECKING:
    from datetime import datetime

    from lifeos.infrastructure.database.engine import Database
    from lifeos.tasks.service import Task


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
