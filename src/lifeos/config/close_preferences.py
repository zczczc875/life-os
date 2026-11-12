"""Persist the main window's close behavior in the local settings table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from sqlalchemy.exc import SQLAlchemyError

from lifeos.infrastructure.database.repository import SettingsRepository

if TYPE_CHECKING:
    from lifeos.infrastructure.database.engine import Database

type CloseAction = Literal["tray", "exit"]

_CLOSE_ACTION = "window.close_action"


class ClosePreferencesError(RuntimeError):
    """The window's close preference could not be read or saved."""


class ClosePreferences:
    def __init__(self, database: Database) -> None:
        self._database = database

    def get(self) -> CloseAction | None:
        """Return a remembered action, or None when the window should ask."""
        try:
            with self._database.session_scope() as session:
                action = SettingsRepository(session).get(_CLOSE_ACTION)
        except (SQLAlchemyError, OSError) as error:
            raise ClosePreferencesError("无法读取关闭窗口设置") from error
        if action == "tray" or action == "exit":
            return action
        return None

    def set(self, action: CloseAction | None) -> None:
        """Remember a choice, or clear it to show the prompt again."""
        try:
            with self._database.session_scope() as session:
                settings = SettingsRepository(session)
                if action is None:
                    settings.delete(_CLOSE_ACTION)
                else:
                    settings.upsert(_CLOSE_ACTION, action)
        except (SQLAlchemyError, OSError) as error:
            raise ClosePreferencesError("无法保存关闭窗口设置") from error
