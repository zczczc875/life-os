"""Composition root; component imports are deferred until startup."""

import sys


def main() -> int:
    """Initialize infrastructure and run the desktop event loop."""
    from PySide6.QtWidgets import QApplication, QMessageBox
    from sqlalchemy import inspect
    from sqlalchemy.exc import SQLAlchemyError

    from lifeos.config.settings import get_settings
    from lifeos.infrastructure.database.engine import create_database
    from lifeos.infrastructure.logging.setup import setup_logging
    from lifeos.tasks import TaskService
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
                has_task_table = inspect(database.engine).has_table("tasks")
            except SQLAlchemyError:
                database_status = False
                has_task_table = False
            if has_task_table:
                task_service = TaskService(database)
            elif database_status:
                QMessageBox.warning(
                    None,
                    "数据库需要迁移",
                    "任务表尚未创建。请在项目目录运行 python -m alembic upgrade head，"
                    "然后重新启动 LifeOS。",
                )
        window = MainWindow(settings.app_version, database_status, task_service=task_service)
        window.show()
        return application.exec()
    finally:
        database.dispose()
