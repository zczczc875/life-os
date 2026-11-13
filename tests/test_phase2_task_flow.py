"""Real UI, service and database flow with a disposable SQLite database."""

import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from lifeos.ai.local_provider import LocalDraftProvider
from lifeos.config.settings import Settings
from lifeos.infrastructure.database import task_repository
from lifeos.infrastructure.database.engine import create_database
from lifeos.tasks import TaskService
from lifeos.ui.main_window import MainWindow
from lifeos.ui.task_panel import EMPTY_TITLE_MESSAGE


@pytest.mark.parametrize(
    ("entry", "due_text"),
    [
        ("准备项目汇报", ""),
        ("准备项目汇报 DDL: 2000-02-29", "2000-02-29"),
        ("明天下午三点半前准备项目汇报", "2000-02-29 15:30"),
    ],
    ids=["undated", "overdue-date", "overdue-local-time"],
)
def test_ui_archives_completed_task_and_shows_it_after_process_restart(
    qtbot, tmp_path, monkeypatch, entry, due_text
):
    from lifeos.ui.completed_tasks import CompletedTasksDialog

    data_dir = tmp_path / "data"
    database = create_database(Settings(data_dir=data_dir))
    database.ensure_schema()
    local_completion = datetime(2026, 12, 1, 0, 15)
    stored_completion = local_completion.astimezone(UTC).replace(tzinfo=None)
    monkeypatch.setattr(task_repository, "utcnow", lambda: stored_completion)
    provider = LocalDraftProvider(today=date(2000, 2, 28))
    window = MainWindow(
        "test", True, task_service=TaskService(database), quick_parse=provider.parse_quick_task
    )
    qtbot.addWidget(window)
    window.show()
    panel = window.task_panel

    panel.task_input.setText("   ")
    qtbot.mouseClick(panel.add_button, Qt.MouseButton.LeftButton)
    assert panel.error_message() == EMPTY_TITLE_MESSAGE
    assert panel.task_titles() == []
    assert TaskService(database).list_tasks() == []

    panel.task_input.setText(f"  {entry}  ")
    qtbot.mouseClick(panel.add_button, Qt.MouseButton.LeftButton)
    expected_title = "准备项目汇报"
    if due_text:
        expected_title += f"  ·  截止 {due_text}"
    assert panel.task_titles() == [f"已逾期  ·  {expected_title}" if due_text else expected_title]
    assert panel.task_input.text() == ""
    assert panel.error_message() == ""

    panel.task_list.item(0).setCheckState(Qt.CheckState.Checked)
    assert panel.task_titles() == []
    tasks = TaskService(database).list_tasks()
    assert len(tasks) == 1 and tasks[0].status == "completed"
    assert tasks[0].completed_at == stored_completion.replace(tzinfo=UTC)
    assert tasks[0].due_on == (datetime.fromisoformat(due_text).date() if due_text else None)
    assert tasks[0].due_time == (
        datetime.fromisoformat(due_text).time() if " " in due_text else None
    )
    window.completed_tasks_button.click()
    archive = window.findChild(CompletedTasksDialog)
    assert archive is not None and archive.isVisible()
    assert archive.task_tree.topLevelItemCount() == 1
    month = archive.task_tree.topLevelItem(0)
    expected_month = "2000 年 2 月" if due_text else "2026 年 12 月"
    assert month.text(0) == expected_month
    assert month.childCount() == 1
    completed = month.child(0)
    assert completed.text(0) == "准备项目汇报"
    assert completed.text(1) == (due_text or "—")
    assert completed.text(2) == "2026-12-01 00:15"
    assert completed.text(3) == ("逾期完成" if due_text else "已完成")
    archive.reject()
    window.close()
    database.dispose()

    env = {k: v for k, v in os.environ.items() if not k.startswith("LIFEOS_")}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["QT_QPA_PLATFORM"] = "offscreen"
    restart = """\
from pathlib import Path
import sys
from PySide6.QtWidgets import QApplication
from lifeos.config.settings import Settings
from lifeos.infrastructure.database.engine import create_database
from lifeos.tasks import TaskService
from lifeos.ui.completed_tasks import CompletedTasksDialog
from lifeos.ui.main_window import MainWindow
app = QApplication([])
db = create_database(Settings(data_dir=Path(sys.argv[1])))
window = MainWindow('test', True, task_service=TaskService(db))
window.show()
app.processEvents()
assert window.task_panel.task_titles() == []
window.completed_tasks_button.click()
archive = window.findChild(CompletedTasksDialog)
assert archive is not None
assert archive.task_tree.topLevelItemCount() == 1
month = archive.task_tree.topLevelItem(0)
assert month.text(0) == sys.argv[2]
assert month.childCount() == 1
assert month.child(0).text(0) == "准备项目汇报"
archive.reject()
window.close()
db.dispose()
"""
    subprocess.run(
        [
            sys.executable,
            "-c",
            restart,
            str(data_dir),
            expected_month,
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
