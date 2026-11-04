"""Real UI, service and database flow with a disposable SQLite database."""

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt

from lifeos.config.settings import Settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.tasks import TaskService
from lifeos.ui.main_window import MainWindow
from lifeos.ui.task_panel import EMPTY_TITLE_MESSAGE


def test_ui_creates_completes_and_shows_task_after_process_restart(qtbot, tmp_path):
    data_dir = tmp_path / "data"
    database = create_database(Settings(data_dir=data_dir))
    database.ensure_schema()
    window = MainWindow("test", True, task_service=TaskService(database))
    qtbot.addWidget(window)
    window.show()
    panel = window.task_panel

    panel.task_input.setText("   ")
    qtbot.mouseClick(panel.add_button, Qt.MouseButton.LeftButton)
    assert panel.error_message() == EMPTY_TITLE_MESSAGE
    assert panel.task_titles() == []
    assert TaskService(database).list_tasks() == []

    panel.task_input.setText("  准备项目汇报  ")
    qtbot.mouseClick(panel.add_button, Qt.MouseButton.LeftButton)
    assert panel.task_titles() == ["准备项目汇报"]
    assert panel.task_input.text() == ""
    assert panel.error_message() == ""

    panel.task_list.item(0).setCheckState(Qt.CheckState.Checked)
    completed = panel.task_list.item(0)
    assert completed.checkState() == Qt.CheckState.Checked
    assert completed.font().strikeOut()
    tasks = TaskService(database).list_tasks()
    assert len(tasks) == 1 and tasks[0].status == "completed"
    assert tasks[0].completed_at is not None
    window.close()
    database.dispose()

    env = {k: v for k, v in os.environ.items() if not k.startswith("LIFEOS_")}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["QT_QPA_PLATFORM"] = "offscreen"
    restart = """\
from pathlib import Path
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from lifeos.config.settings import Settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.tasks import TaskService
from lifeos.ui.main_window import MainWindow
app = QApplication([])
db = create_database(Settings(data_dir=Path(sys.argv[1])))
window = MainWindow('test', True, task_service=TaskService(db))
window.show()
app.processEvents()
assert window.task_panel.task_titles() == ['准备项目汇报']
assert window.task_panel.task_list.item(0).checkState() == Qt.CheckState.Checked
window.close()
db.dispose()
"""
    subprocess.run(
        [sys.executable, "-c", restart, str(data_dir)],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
