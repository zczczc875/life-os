"""Engine and session management for the local SQLite database.

The contract in ``docs/ARCHITECTURE.md`` is honoured here:

* ``create_database(settings) -> Database`` builds the engine and ensures the
  data directory exists.
* ``Database.check_connection() -> bool`` returns ``True`` when the database is
  readable and ``False`` when the connection is unavailable.
* ``Database.dispose() -> None`` releases the connection pool.

``is_migrated()`` is offered in addition to the agreed contract: a connectable
database is not necessarily a migrated one.

Importing this module never creates directories or opens connections; all
side effects happen inside ``create_database``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from lifeos.infrastructure.database.models import AppSetting
from lifeos.infrastructure.database.url import (
    DEFAULT_DATABASE_FILENAME,
    UnresolvedDatabaseError,
    resolve_target,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterator

    from sqlalchemy.engine import Engine

    from lifeos.infrastructure.database.url import DatabaseTarget

__all__ = ["DEFAULT_DATABASE_FILENAME", "Database", "DatabaseError", "create_database"]

_logger = logging.getLogger(__name__)


class DatabaseError(RuntimeError):
    """Raised when the database cannot be initialized or released."""


class Database:
    """Owns the SQLAlchemy engine and session factory for one SQLite file."""

    def __init__(self, engine: Engine, target: DatabaseTarget) -> None:
        self._engine = engine
        self._target = target
        self._path = target.path
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    @property
    def engine(self) -> Engine:
        """Return the underlying SQLAlchemy engine."""
        return self._engine

    @property
    def path(self) -> Path:
        """Return the SQLite file backing this database."""
        return self._path

    @property
    def url(self) -> str:
        """Return the SQLAlchemy URL, safe to log for local SQLite files."""
        return self._engine.url.render_as_string(hide_password=True)

    def session(self) -> Session:
        """Create a new session; the caller owns its lifecycle."""
        return self._session_factory()

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Yield a session that commits on success and rolls back on error."""
        session = self.session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def check_connection(self) -> bool:
        """Return ``True`` when the database is readable, ``False`` otherwise.

        The probe lists table names instead of issuing ``SELECT 1``: SQLite
        validates the file header lazily, so a trivial constant query succeeds
        even on a corrupt file. Connection problems are reported as ``False``
        so the UI can display a degraded state instead of crashing.
        """
        try:
            inspect(self._engine).get_table_names()
        except SQLAlchemyError:
            _logger.warning("database connection check failed for %s", self._path, exc_info=True)
            return False
        except OSError:
            _logger.warning("database file is not accessible: %s", self._path, exc_info=True)
            return False
        return True

    def is_migrated(self) -> bool:
        """Return whether the expected Phase 1 tables exist.

        ``check_connection`` only proves the file is readable: a freshly created
        SQLite file connects successfully while holding no tables, so settings
        access would still fail with "no such table". Use :meth:`ensure_schema`
        to bring an empty or outdated database up to date.
        """
        try:
            return inspect(self._engine).has_table(AppSetting.__tablename__)
        except SQLAlchemyError:
            _logger.warning("migration check failed for %s", self._path, exc_info=True)
            return False
        except OSError:
            _logger.warning("database file is not accessible: %s", self._path, exc_info=True)
            return False

    def ensure_schema(self) -> str:
        """Apply any pending migrations and return the resulting revision.

        This is what an installed, double-clicked application should call: the
        end user has no shell to run ``alembic upgrade head`` in. Alembic skips
        revisions that are already applied, so calling this on every startup is
        safe and cheap once the database is current.

        Raises :class:`MigrationError` when migrations are missing or fail, so
        startup can report a real problem instead of failing later with
        "no such table".
        """
        from lifeos.infrastructure.database.migrate import upgrade_to_head

        revision = upgrade_to_head(self._target)
        # The pool may hold connections opened before the schema changed.
        self._engine.dispose()
        return revision

    def dispose(self) -> None:
        """Release pooled connections; raises :class:`DatabaseError` on failure."""
        try:
            self._engine.dispose()
        except SQLAlchemyError as error:
            raise DatabaseError(f"failed to dispose database engine: {error}") from error

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"Database(path={str(self._path)!r})"


def create_database(settings: Any) -> Database:
    """Create a :class:`Database` for the SQLite file described by ``settings``.

    The parent directory is created when missing. Schema changes are owned by
    Alembic, so this function never creates or alters tables; call
    :meth:`Database.ensure_schema` to apply migrations.
    """
    try:
        target = resolve_target(settings)
    except UnresolvedDatabaseError as error:
        raise DatabaseError(str(error)) from error

    try:
        target.ensure_parent()
    except OSError as error:
        raise DatabaseError(
            f"failed to create data directory {target.path.parent}: {error}"
        ) from error

    try:
        engine = create_engine(
            target.url,
            future=True,
            connect_args=target.connect_args(),
        )
    except SQLAlchemyError as error:
        raise DatabaseError(
            f"failed to create database engine for {target.describe()}: {error}"
        ) from error

    _logger.info("database engine created for %s", target.describe())
    return Database(engine, target)
