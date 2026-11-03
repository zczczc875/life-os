"""Composition root; component imports are deferred until startup."""

import sys


def main() -> int:
    """Initialize infrastructure and run the desktop event loop."""
    from PySide6.QtWidgets import QApplication

    from lifeos.config.settings import get_settings
    from lifeos.infrastructure.database.engine import create_database
    from lifeos.infrastructure.logging.setup import setup_logging
    from lifeos.ui.main_window import MainWindow

    settings = get_settings()
    setup_logging(settings)
    database = create_database(settings)
    try:
        database_status = database.check_connection()
        application = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow(settings.app_version, database_status)
        window.show()
        return application.exec()
    finally:
        database.dispose()
