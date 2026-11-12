"""Store reminder preferences and atomically claim the currently due tasks."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import Time, func, literal, select, update
from sqlalchemy.dialects.sqlite import insert

from lifeos.infrastructure.database.models import (
    TASK_STATUS_PENDING,
    AppSetting,
    TaskRecord,
    utcnow,
)
from lifeos.infrastructure.database.repository import SettingsRepository

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

_ENABLED_KEY = "reminders.due_enabled"
_DATE_ONLY_TIME = time(23, 59)


class ReminderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enabled(self) -> bool:
        return SettingsRepository(self._session).get(_ENABLED_KEY) == "true"

    def set_enabled(self, enabled: bool) -> None:
        value = "true" if enabled else "false"
        statement = insert(AppSetting).values(key=_ENABLED_KEY, value=value)
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[AppSetting.key],
                set_={"value": value, "updated_at": utcnow()},
            )
        )

    def claim_due(self, now: datetime) -> list[TaskRecord]:
        """Check opt-in, eligibility and deduplication in a single write."""
        reminders_enabled = (
            select(AppSetting.key)
            .where(AppSetting.key == _ENABLED_KEY, AppSetting.value == "true")
            .exists()
        )
        local_due_time = func.coalesce(TaskRecord.due_time, literal(_DATE_ONLY_TIME, Time()))
        statement = (
            update(TaskRecord)
            .where(
                reminders_enabled,
                TaskRecord.status == TASK_STATUS_PENDING,
                TaskRecord.reminder_claimed_at.is_(None),
                (TaskRecord.due_on < now.date())
                | ((TaskRecord.due_on == now.date()) & (local_due_time <= now.time())),
            )
            .values(reminder_claimed_at=utcnow())
            .returning(TaskRecord)
        )
        records = self._session.scalars(statement, execution_options={"synchronize_session": False})
        return list(records)
