"""Alembic environment for LifeOS.

The database URL is resolved in this order:

1. ``-x url=...`` passed on the Alembic command line.
2. ``LIFEOS_DATABASE_URL`` in the environment.
3. ``lifeos.config.settings.get_settings()`` when D's configuration module is
   available, using the same path rules as ``create_database``.
4. The default ``%LOCALAPPDATA%\\LifeOS\\data\\lifeos.sqlite3`` location.

This keeps ``alembic upgrade head`` working today and automatically follows the
configured data directory once Settings is merged.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from lifeos.infrastructure.database.models import Base
from lifeos.infrastructure.database.url import (
    UnresolvedDatabaseError,
    default_target,
    resolve_target,
    target_from_url,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url_from_settings() -> str | None:
    """Build a URL from D's Settings when the module is importable."""
    try:
        from lifeos.config.settings import get_settings
    except ImportError:
        return None

    try:
        settings = get_settings()
    except Exception:  # noqa: BLE001  # pragma: no cover - configuration errors surface at startup
        return None

    try:
        return resolve_target(settings).url_string
    except UnresolvedDatabaseError:
        return None


def resolve_url() -> str:
    """Return the database URL for this migration run."""
    # Set by lifeos.infrastructure.database.migrate for in-process upgrades.
    programmatic = config.attributes.get("lifeos_url")
    if programmatic:
        return str(programmatic)

    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return override

    env_url = os.environ.get("LIFEOS_DATABASE_URL")
    if env_url:
        return env_url

    from_settings = _url_from_settings()
    if from_settings:
        return from_settings

    return default_target().url_string


def _ensure_parent(url: str) -> None:
    """Create the SQLite parent directory so a fresh install can migrate."""
    try:
        target_from_url(url).ensure_parent()
    except UnresolvedDatabaseError:
        # Non-file targets have no local directory to prepare.
        return


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to the database."""
    context.configure(
        url=resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply migrations."""
    url = resolve_url()
    _ensure_parent(url)

    # create_engine is used directly instead of engine_from_config: the URL may
    # contain percent-encoded Windows path separators, which ConfigParser-backed
    # options would misread as interpolation syntax.
    connectable = create_engine(url, poolclass=pool.NullPool)

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
