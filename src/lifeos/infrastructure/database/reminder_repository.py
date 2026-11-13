"""Store reminder preferences and atomically claim the currently due tasks."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import Integer, Time, case, cast, func, literal, select, update

from lifeos.infrastructure.database.models import (
    TASK_STATUS_PENDING,
    AppSetting,
    TaskRecord,
    utcnow,
)
from lifeos.infrastructure.database.repository import SettingsRepository

if TYPE_CHECKING:
    from collections.abc import Collection

    from sqlalchemy.orm import Session
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.selectable import Exists

ADVANCE_MINUTES = (15, 60, 1440)
_ADVANCE_FLAGS = {minutes: 1 << index for index, minutes in enumerate(ADVANCE_MINUTES)}
_ALL_ADVANCE_FLAGS = sum(_ADVANCE_FLAGS.values())
_ADVANCE_MASK_VALUES = tuple(str(mask) for mask in range(_ALL_ADVANCE_FLAGS + 1))
_ADVANCE_KEY = "reminders.advance_mask"
_ENABLED_KEY = "reminders.due_enabled"
_DATE_ONLY_TIME = time(23, 59)


def _deadline_at_or_before(moment: datetime) -> ColumnElement[bool]:
    local_due_time = func.coalesce(TaskRecord.due_time, literal(_DATE_ONLY_TIME, Time()))
    return (TaskRecord.due_on < moment.date()) | (
        (TaskRecord.due_on == moment.date()) & (local_due_time <= moment.time())
    )


def _reminders_enabled() -> Exists:
    return (
        select(AppSetting.key)
        .where(AppSetting.key == _ENABLED_KEY, AppSetting.value == "true")
        .exists()
    )


class ReminderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enabled(self) -> bool:
        return SettingsRepository(self._session).get(_ENABLED_KEY) == "true"

    def set_enabled(self, enabled: bool) -> None:
        value = "true" if enabled else "false"
        SettingsRepository(self._session).upsert(_ENABLED_KEY, value)

    def advance_minutes(self) -> tuple[int, ...]:
        value = SettingsRepository(self._session).get(_ADVANCE_KEY)
        mask = int(value) if value in _ADVANCE_MASK_VALUES else 0
        return tuple(minutes for minutes, flag in _ADVANCE_FLAGS.items() if mask & flag)

    def set_advance_minutes(self, minutes: Collection[int]) -> None:
        mask = sum(_ADVANCE_FLAGS[lead] for lead in minutes)
        SettingsRepository(self._session).upsert(_ADVANCE_KEY, str(mask))

    def claim_due(self, now: datetime) -> list[TaskRecord]:
        """Check opt-in, eligibility and deduplication in a single write."""
        statement = (
            update(TaskRecord)
            .where(
                _reminders_enabled(),
                TaskRecord.status == TASK_STATUS_PENDING,
                TaskRecord.reminder_claimed_at.is_(None),
                _deadline_at_or_before(now),
            )
            .values(reminder_claimed_at=utcnow())
            .returning(TaskRecord)
        )
        records = self._session.scalars(statement, execution_options={"synchronize_session": False})
        return list(records)

    def claim_advance(self, now: datetime) -> list[TaskRecord]:
        """Claim the closest elapsed enabled lead and skip any older leads."""
        enabled_mask = (
            select(cast(AppSetting.value, Integer))
            .where(AppSetting.key == _ADVANCE_KEY, AppSetting.value.in_(_ADVANCE_MASK_VALUES))
            .scalar_subquery()
        )
        elapsed_leads = []
        for minutes, flag in _ADVANCE_FLAGS.items():
            try:
                latest_deadline = now + timedelta(minutes=minutes)
            except OverflowError:
                latest_deadline = datetime.max
            elapsed_leads.append(
                (
                    (enabled_mask.bitwise_and(flag) != 0) & _deadline_at_or_before(latest_deadline),
                    flag,
                )
            )
        closest_flag = case(*elapsed_leads, else_=0)
        current_mask = TaskRecord.advance_reminder_mask
        # Lower bits are closer to the deadline. Consume the chosen bit and
        # every higher one, including leads that might be enabled later.
        consumed_flags = _ALL_ADVANCE_FLAGS - (closest_flag - 1)
        statement = (
            update(TaskRecord)
            .where(
                _reminders_enabled(),
                TaskRecord.status == TASK_STATUS_PENDING,
                TaskRecord.reminder_claimed_at.is_(None),
                ~_deadline_at_or_before(now),
                closest_flag != 0,
                current_mask.bitwise_and(closest_flag) == 0,
            )
            .values(advance_reminder_mask=current_mask.bitwise_or(consumed_flags))
            .returning(TaskRecord)
        )
        records = self._session.scalars(statement, execution_options={"synchronize_session": False})
        return list(records)
