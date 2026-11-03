"""Database location resolution for the local LifeOS application.

Phase 1 stores data in a local SQLite file. This module turns ``Settings`` into
a concrete file location and SQLAlchemy URL, and it understands the difference
between running from source and running from a packaged executable.

Importing this module has no side effects; it only computes paths and URLs.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

__all__ = [
    "DEFAULT_DATABASE_FILENAME",
    "SQLITE_DRIVER",
    "DatabaseTarget",
    "MigrationTargetError",
    "UnresolvedDatabaseError",
    "is_frozen",
    "resolve_target",
]

#: Default SQLite filename inside ``Settings.data_dir``.
DEFAULT_DATABASE_FILENAME = "lifeos.sqlite3"

#: SQLAlchemy driver used for the local SQLite database.
SQLITE_DRIVER = "sqlite+pysqlite"


class UnresolvedDatabaseError(ValueError):
    """Raised when settings do not describe any database location."""


class MigrationTargetError(RuntimeError):
    """Raised when a migration cannot determine a trustworthy target.

    Raised instead of guessing a location, so a broken configuration never
    results in a schema being written into a database the application will not
    open.
    """


def is_frozen() -> bool:
    """Return whether the app is running from a packaged executable.

    PyInstaller and similar tools set ``sys.frozen``; the bundled data root is
    then exposed as ``sys._MEIPASS``. Resource lookups must not assume the
    source tree exists next to the executable.
    """
    return bool(getattr(sys, "frozen", False))


@dataclass(frozen=True)
class DatabaseTarget:
    """A resolved SQLite database location."""

    path: Path

    @property
    def url(self) -> URL:
        """Return the SQLAlchemy URL for this database file."""
        return URL.create(SQLITE_DRIVER, database=str(self.path))

    @property
    def url_string(self) -> str:
        """Return the URL as a string for internal, programmatic use.

        SQLAlchemy percent-encodes the Windows path separators, so this value
        round-trips safely through ``make_url`` but is not meant for display or
        for pasting into a shell. Use :meth:`describe` when showing a location
        to a user.
        """
        return self.url.render_as_string(hide_password=True)

    def connect_args(self) -> dict[str, Any]:
        """Return ``create_engine(connect_args=...)`` values for SQLite.

        ``check_same_thread`` is relaxed so a background worker may reuse the
        engine; callers must still confine one session to one thread.
        """
        return {"check_same_thread": False}

    def ensure_parent(self) -> None:
        """Create the directory holding the database file when missing."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def describe(self) -> str:
        """Return a log-safe description of this target."""
        return str(self.path)


def _default_data_dir() -> Path:
    """Return ``%LOCALAPPDATA%\\LifeOS\\data`` with a cross-platform fallback.

    A packaged app must never write next to its own executable: that directory
    is often read-only (``C:\\Program Files``) and is replaced on upgrade.
    """
    import os

    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "LifeOS" / "data"


def resolve_target(settings: Any) -> DatabaseTarget:
    """Resolve the database file described by ``settings``.

    Resolution order, highest priority first:

    1. ``settings.database_path`` - an explicit database file.
    2. ``settings.data_dir`` plus ``settings.database_filename`` or the default
       filename.

    Only attributes that are present are read, so D's ``Settings`` needs to
    expose nothing beyond ``data_dir`` for Phase 1.
    """
    explicit_path = getattr(settings, "database_path", None)
    if explicit_path is not None:
        return DatabaseTarget(Path(explicit_path).expanduser())

    data_dir = getattr(settings, "data_dir", None)
    if data_dir is None:
        raise UnresolvedDatabaseError(
            "settings must provide 'data_dir' or 'database_path' to locate the database"
        )

    filename = getattr(settings, "database_filename", None) or DEFAULT_DATABASE_FILENAME
    return DatabaseTarget(Path(data_dir).expanduser() / str(filename))


def target_from_url(url: str) -> DatabaseTarget:
    """Build a target from a SQLite URL string, used by the migration CLI."""
    try:
        parsed = make_url(url)
    except ArgumentError as error:
        raise UnresolvedDatabaseError(f"invalid database URL: {error}") from error

    if parsed.get_backend_name() != "sqlite":
        raise UnresolvedDatabaseError(
            f"Phase 1 supports SQLite only, got backend {parsed.get_backend_name()!r}"
        )
    if not parsed.database or parsed.database == ":memory:":
        raise UnresolvedDatabaseError("a file-backed SQLite database is required")
    return DatabaseTarget(Path(parsed.database))


def default_target() -> DatabaseTarget:
    """Return the location used when no configuration is supplied.

    This documents the built-in default and is used to assert it. Production
    code paths resolve from ``Settings`` instead; migrations must never fall
    back here, because writing a schema to a guessed location hides a broken
    configuration until the application fails with "no such table".
    """
    return DatabaseTarget(_default_data_dir() / DEFAULT_DATABASE_FILENAME)
