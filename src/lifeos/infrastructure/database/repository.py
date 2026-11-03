"""Repository for the ``app_settings`` table.

The repository keeps SQL inside the database module: callers pass a session and
work with plain Python values. Phase 1 only needs string settings, so values
are stored as text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from lifeos.infrastructure.database.models import AppSetting, utcnow

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

__all__ = ["SettingsRepository"]


class SettingsRepository:
    """Read and write key/value application settings."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the stored value for ``key``, or ``default`` when absent."""
        row = self._session.get(AppSetting, key)
        return default if row is None else row.value

    def set(self, key: str, value: str) -> AppSetting:
        """Insert or update ``key`` and return the stored row.

        The caller is responsible for committing the session; this keeps
        transaction boundaries with the unit of work that owns the session.
        """
        if not key:
            raise ValueError("setting key must be a non-empty string")

        row = self._session.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key, value=value)
            self._session.add(row)
        elif row.value != value:
            row.value = value
        else:
            # Touch the timestamp so repeated writes remain observable.
            row.updated_at = utcnow()
        return row

    def delete(self, key: str) -> bool:
        """Remove ``key`` and report whether a row was deleted."""
        result = self._session.execute(delete(AppSetting).where(AppSetting.key == key))
        return bool(result.rowcount)

    def all(self) -> dict[str, str]:
        """Return every setting as a ``key -> value`` mapping ordered by key."""
        rows = self._session.execute(select(AppSetting).order_by(AppSetting.key)).scalars()
        return {row.key: row.value for row in rows}

    def exists(self, key: str) -> bool:
        """Return whether ``key`` is stored."""
        return self._session.get(AppSetting, key) is not None
