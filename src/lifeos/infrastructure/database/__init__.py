"""Database package for LifeOS; importing it has no side effects."""

from lifeos.infrastructure.database.engine import Database, DatabaseError, create_database
from lifeos.infrastructure.database.migrate import MigrationError, upgrade_to_head
from lifeos.infrastructure.database.models import AppSetting, Base, TaskRecord
from lifeos.infrastructure.database.repository import SettingsRepository
from lifeos.infrastructure.database.task_repository import TaskRepository, TaskTitleError
from lifeos.infrastructure.database.url import (
    DEFAULT_DATABASE_FILENAME,
    DatabaseTarget,
    MigrationTargetError,
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
    "MigrationTargetError",
    "SettingsRepository",
    "TaskRecord",
    "TaskRepository",
    "TaskTitleError",
    "UnresolvedDatabaseError",
    "create_database",
    "resolve_target",
    "upgrade_to_head",
]
