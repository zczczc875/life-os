"""Composition root; component imports are deferred until startup."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lifeos.instance import SingleInstance


def main(*, start_in_tray: bool = False, instance: SingleInstance | None = None) -> int:
    """Initialize infrastructure and run the desktop event loop."""
    from PySide6.QtWidgets import QApplication, QMessageBox
    from sqlalchemy import inspect
    from sqlalchemy.exc import SQLAlchemyError

    from lifeos.ai.local_provider import LocalDraftProvider
    from lifeos.config.close_preferences import ClosePreferences
    from lifeos.config.settings import get_settings
    from lifeos.config.windows_startup import WindowsStartup
    from lifeos.infrastructure.database.engine import create_database
    from lifeos.infrastructure.logging.setup import setup_logging
    from lifeos.tasks import TaskService
    from lifeos.tasks.reminders import ReminderService
    from lifeos.ui.main_window import MainWindow

    settings = get_settings()
    setup_logging(settings)
    database = create_database(settings)
    try:
        database_status = database.check_connection()
        application = QApplication.instance() or QApplication(sys.argv)
        task_service = None
        if database_status:
            try:
                inspector = inspect(database.engine)
                has_task_schema = inspector.has_table("tasks") and {
                    "due_on",
                    "due_time",
                    "reminder_claimed_at",
                } <= {column["name"] for column in inspector.get_columns("tasks")}
            except SQLAlchemyError:
                database_status = False
                has_task_schema = False
            if has_task_schema:
                task_service = TaskService(database)
            elif database_status:
                QMessageBox.warning(
                    None,
                    "数据库需要迁移",
                    "任务数据库尚未升级到当前版本。"
                    "请在项目目录运行 python -m alembic upgrade head，"
                    "然后重新启动 LifeOS。",
                )
        provider = LocalDraftProvider() if task_service is not None else None
        windows_startup = (
            WindowsStartup.for_current_executable(settings.data_dir)
            if instance is not None and task_service is not None
            else None
        )
        window = MainWindow(
            settings.app_version,
            database_status,
            task_service=task_service,
            draft_preview=provider.extract_tasks if provider is not None else None,
            quick_parse=provider.parse_quick_task if provider is not None else None,
            reminder_service=ReminderService(database) if task_service is not None else None,
            close_preferences=ClosePreferences(database) if task_service is not None else None,
            windows_startup=windows_startup,
        )
        if instance is not None:
            instance.activate_requested.connect(window.restore_window)
        if not (start_in_tray and window.minimize_to_tray()):
            window.show()
        return application.exec()
    finally:
        database.dispose()
