"""Shared helpers for the test suite.

Keeps tests from hardcoding the latest Alembic revision: a new migration would
otherwise break unrelated assertions, as happened when the tasks table was
added on top of ``0001_app_settings``.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
VERSIONS_DIR = MIGRATIONS_DIR / "versions"


def head_revision() -> str:
    """Return the current head revision read from the migration scripts."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config).get_current_head()


def alembic_config(database_path: Path, script_location: Path | str | None = None):
    """Build an Alembic config targeting ``database_path``.

    The URL travels through ``config.attributes`` because percent-encoded
    Windows paths break ConfigParser interpolation.
    """
    from alembic.config import Config

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(script_location or MIGRATIONS_DIR))
    config.attributes["lifeos_url"] = f"sqlite+pysqlite:///{database_path}"
    return config
