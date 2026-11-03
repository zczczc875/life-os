"""Alembic environment for LifeOS.

The migration target is resolved by the same code the application uses, so a
migration can never create tables in a different file from the one the app
opens. Resolution order:

1. ``-x url=...`` passed on the Alembic command line (explicit operator intent).
2. ``lifeos.config.settings.get_settings()`` - the single source of truth,
   honouring ``LIFEOS_DATA_DIR`` exactly as the application does.

A broken configuration aborts the migration instead of silently falling back to
the default location: writing a schema into the wrong database is worse than
refusing to run.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from lifeos.infrastructure.database.models import Base
from lifeos.infrastructure.database.url import (
    MigrationTargetError,
    UnresolvedDatabaseError,
    resolve_target,
    target_from_url,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _target_from_explicit_url(url: str, source: str):
    """Validate an operator-supplied URL, reporting where it came from."""
    try:
        return target_from_url(url)
    except UnresolvedDatabaseError as error:
        raise MigrationTargetError(f"invalid database URL from {source}: {error}") from error


def _target_from_settings():
    """Resolve the migration target from the application configuration.

    Configuration failures propagate as :class:`MigrationTargetError`. Guessing
    a default here would migrate a database the application never opens, which
    surfaces much later as a confusing "no such table" error.
    """
    try:
        from lifeos.config.settings import get_settings
    except ImportError as error:  # pragma: no cover - config package always ships
        raise MigrationTargetError(
            "cannot import lifeos.config.settings; install the project before migrating"
        ) from error

    try:
        settings = get_settings()
    except Exception as error:
        raise MigrationTargetError(
            f"application configuration is invalid, refusing to migrate: {error}"
        ) from error

    return resolve_target(settings)


def resolve_migration_target():
    """Return the :class:`DatabaseTarget` this migration run must use."""
    # Set by lifeos.infrastructure.database.migrate for in-process upgrades.
    programmatic = config.attributes.get("lifeos_url")
    if programmatic:
        return _target_from_explicit_url(str(programmatic), "programmatic target")

    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return _target_from_explicit_url(override, "-x url")

    return _target_from_settings()


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to the database."""
    target = resolve_migration_target()
    context.configure(
        url=target.url_string,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply migrations."""
    target = resolve_migration_target()
    target.ensure_parent()

    # The URL object is passed directly rather than a string: percent-encoded
    # Windows path separators would otherwise be misread downstream.
    connectable = create_engine(target.url, poolclass=pool.NullPool)

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
