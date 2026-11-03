"""Declarative models for the local SQLite store.

Importing this module only declares metadata; it never touches the filesystem
or opens a connection.
"""

from __future__ import annotations

import datetime as _datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["AppSetting", "Base", "utcnow"]


def utcnow() -> _datetime.datetime:
    """Return the current UTC time as a naive datetime.

    SQLite does not preserve timezone information, so timestamps are stored as
    naive UTC and must be interpreted as UTC by callers.
    """
    return _datetime.datetime.now(_datetime.UTC).replace(tzinfo=None)


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
