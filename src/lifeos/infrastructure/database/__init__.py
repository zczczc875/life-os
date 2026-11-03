"""Database package for LifeOS; importing it has no side effects."""

from lifeos.infrastructure.database.engine import Database, DatabaseError, create_database
from lifeos.infrastructure.database.migrate import MigrationError, upgrade_to_head
from lifeos.infrastructure.database.models import AppSetting, Base
from lifeos.infrastructure.database.repository import SettingsRepository
from lifeos.infrastructure.database.url import (
    DEFAULT_DATABASE_FILENAME,
    DatabaseTarget,
    UnresolvedDatabaseError,
    resolve_target,
)

__all__ = [
    "DEFAULT_DATABASE_FILENAME",
    "AppSetting",
    "Base",
    "Database",
    "DatabaseError",
    "DatabaseTarget",
    "MigrationError",
    "SettingsRepository",
    "UnresolvedDatabaseError",
    "create_database",
    "resolve_target",
    "upgrade_to_head",
]
