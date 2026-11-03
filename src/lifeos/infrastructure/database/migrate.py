"""Programmatic schema migration, usable from a packaged executable.

A user who double-clicks ``LifeOS.exe`` has no shell, so requiring
``alembic upgrade head`` on the command line would leave the app with no
tables. ``upgrade_to_head`` performs the same migration in-process.

Importing this module has no side effects; migrations run only when called.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from lifeos.infrastructure.database.url import is_frozen

if TYPE_CHECKING:  # pragma: no cover - typing only
    from alembic.config import Config

    from lifeos.infrastructure.database.url import DatabaseTarget

__all__ = ["MigrationError", "find_migrations_dir", "upgrade_to_head"]

_logger = logging.getLogger(__name__)

#: Directory name holding the Alembic environment and versions.
_MIGRATIONS_DIRNAME = "migrations"


class MigrationError(RuntimeError):
    """Raised when migrations cannot be located or applied."""


def _candidate_roots() -> list[Path]:
    """Return directories that may contain the migrations folder.

    When frozen, PyInstaller unpacks bundled data to ``sys._MEIPASS``; the
    source tree is not present. When running from source, the project root is
    four levels above this file.
    """
    roots: list[Path] = []

    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        roots.append(Path(bundle_dir))

    if is_frozen():
        roots.append(Path(sys.executable).parent)

    # src/lifeos/infrastructure/database/migrate.py -> project root
    roots.append(Path(__file__).resolve().parents[4])
    return roots


def find_migrations_dir() -> Path:
    """Locate the Alembic ``migrations`` directory.

    Raises :class:`MigrationError` with the inspected locations when missing,
    which is the common symptom of a packaging configuration that forgot to
    bundle the migrations as data files.
    """
    inspected: list[Path] = []
    for root in _candidate_roots():
        candidate = root / _MIGRATIONS_DIRNAME
        inspected.append(candidate)
        if (candidate / "env.py").is_file():
            return candidate

    locations = "\n  ".join(str(path) for path in inspected)
    raise MigrationError(
        "could not locate the 'migrations' directory. When packaging LifeOS, "
        "bundle it as data files so schema upgrades work in the installed app. "
        f"Inspected:\n  {locations}"
    )


def _build_config(target: DatabaseTarget, migrations_dir: Path) -> Config:
    """Build an Alembic config pointing at ``target`` without reading ini files.

    The URL is passed through ``config.attributes`` rather than
    ``set_main_option``: Alembic stores main options in a ConfigParser, which
    treats ``%`` as interpolation syntax. URL-encoded Windows paths such as
    ``C%3A%5CUsers`` would raise "invalid interpolation syntax".
    """
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(migrations_dir))
    # env.py reads the URL from this attribute, mirroring `alembic -x url=...`.
    config.attributes["lifeos_url"] = target.url_string
    return config


def upgrade_to_head(target: DatabaseTarget) -> str:
    """Upgrade ``target`` to the latest revision and return that revision.

    Safe to call on every startup: Alembic skips revisions that are already
    applied, so an up-to-date database is left untouched.
    """
    from alembic import command
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    migrations_dir = find_migrations_dir()
    target.ensure_parent()
    config = _build_config(target, migrations_dir)

    try:
        command.upgrade(config, "head")
    except Exception as error:  # re-raised as MigrationError below
        raise MigrationError(f"failed to upgrade {target.describe()}: {error}") from error

    engine = create_engine(target.url, connect_args=target.connect_args())
    try:
        with engine.connect() as connection:
            revision = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()

    _logger.info("database schema upgraded to %s", revision)
    return revision or ""
